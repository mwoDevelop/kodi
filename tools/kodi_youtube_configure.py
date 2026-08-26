#!/usr/bin/env python3
"""Apply a redacted YouTube API profile inside Android Kodi."""

from __future__ import annotations

import argparse
import json
import re
import subprocess
import tempfile
import time
from pathlib import Path

try:
    from kodi_inventory import load_private_references
    from kodi_profile import (
        AdbEventClient,
        AdbJsonRpcClient,
        _wait_for_kodi_ready,
        adb_command,
    )
except ModuleNotFoundError:
    from tools.kodi_inventory import load_private_references
    from tools.kodi_profile import (
        AdbEventClient,
        AdbJsonRpcClient,
        _wait_for_kodi_ready,
        adb_command,
    )


REMOTE_SCRIPT = "/sdcard/Download/.mwo-youtube-configure.py"
REMOTE_CONFIG = "/sdcard/Download/.mwo-youtube-config.json"
REMOTE_REPORT = "/sdcard/Download/.mwo-youtube-configure.json"
ADAPTER = "youtube-oauth-v1"
EXPECTED_ADDON_VERSION = "7.4.4"
DEFAULT_SESSION_FILE = ".kodi-private/youtube/session.json"
# The in-Kodi adapter can perform five sequential 30-second network requests:
# API-key probe, three token refreshes and the account/channel probe. Keep a
# margin for Kodi dispatch and atomic report publication, especially on VPNs.
PRIVATE_ADAPTER_TIMEOUT_SECONDS = 210
ENVIRONMENT_NAMES = (
    "YOUTUBE_API_KEY",
    "YOUTUBE_CLIENT_ID",
    "YOUTUBE_CLIENT_SECRET",
    "YOUTUBE_USER",
)
API_KEY = re.compile(r"^AIza[A-Za-z0-9_-]{20,80}$")
CLIENT_ID = re.compile(r"^[0-9]+-[A-Za-z0-9_-]+(?:[.]apps[.]googleusercontent[.]com)?$")
CHANNEL_ID = re.compile(r"^UC[A-Za-z0-9_-]{20,30}$")
REFRESH_TOKEN = re.compile(r"^[A-Za-z0-9._/-]{20,4096}$")


def validate_profile(profile):
    required = {
        "adapter",
        "api_key_ref",
        "client_id_ref",
        "client_secret_ref",
        "account_hint_ref",
    }
    if not isinstance(profile, dict) or set(profile) != required:
        raise ValueError("invalid private YouTube profile")
    if profile["adapter"] != ADAPTER:
        raise ValueError("unsupported YouTube adapter")
    expected = {
        "api_key_ref": "YOUTUBE_API_KEY",
        "client_id_ref": "YOUTUBE_CLIENT_ID",
        "client_secret_ref": "YOUTUBE_CLIENT_SECRET",
        "account_hint_ref": "YOUTUBE_USER",
    }
    if any(profile.get(field) != reference for field, reference in expected.items()):
        raise ValueError("unsupported YouTube reference")
    return dict(profile)


def resolve_credentials(profile, references):
    profile = validate_profile(profile)
    values = []
    for field in ("api_key_ref", "client_id_ref", "client_secret_ref"):
        reference = profile[field]
        value = references.get(reference)
        if value is None:
            values.append("")
            continue
        if not isinstance(value, str) or len(value) > 2048:
            raise ValueError(f"invalid private reference: {reference}")
        values.append(value.strip())
    if any(values) and not all(values):
        missing = next(
            profile[field]
            for field, value in zip(
                ("api_key_ref", "client_id_ref", "client_secret_ref"),
                values,
            )
            if not value
        )
        raise ValueError(f"missing private reference: {missing}")
    account_hint = references.get(profile["account_hint_ref"], "")
    if not isinstance(account_hint, str) or len(account_hint) > 2048:
        raise ValueError("invalid YouTube account hint reference")
    account_hint = account_hint.strip()
    api_key, client_id, client_secret = values
    if not any(values):
        if account_hint and (
            "@" not in account_hint
            or any(character.isspace() for character in account_hint)
        ):
            raise ValueError("invalid YouTube account hint reference")
        return None, None, None, account_hint
    if not API_KEY.fullmatch(api_key):
        raise ValueError("invalid YouTube API key reference")
    if not CLIENT_ID.fullmatch(client_id):
        raise ValueError("invalid YouTube OAuth client ID reference")
    if not client_secret or any(character.isspace() for character in client_secret):
        raise ValueError("invalid YouTube OAuth client secret reference")
    if account_hint and (
        "@" not in account_hint
        or any(character.isspace() for character in account_hint)
    ):
        raise ValueError("invalid YouTube account hint reference")
    return api_key, client_id, client_secret, account_hint


def _private_session_path(root, references):
    configured = references.get("YOUTUBE_SESSION_FILE", DEFAULT_SESSION_FILE)
    if not isinstance(configured, str) or not configured.strip():
        raise ValueError("invalid YouTube session file reference")
    path = Path(configured.strip())
    if not path.is_absolute():
        path = Path(root) / path
    path = path.resolve()
    private_root = (Path(root) / ".kodi-private").resolve()
    if path == private_root or private_root not in path.parents:
        raise ValueError("YouTube session file must remain below .kodi-private")
    return path


def load_session(root, references):
    path = _private_session_path(root, references)
    if not path.exists():
        return None
    if not path.is_file() or path.is_symlink() or path.stat().st_mode & 0o077:
        raise ValueError("YouTube session file is unsafe")
    document = json.loads(path.read_text(encoding="utf-8"))
    required = {
        "schema",
        "addon_id",
        "addon_version",
        "account_hint",
        "expected_channel_id",
        "api_key",
        "client_id",
        "client_secret",
        "tv_refresh_token",
        "personal_refresh_token",
        "vr_refresh_token",
    }
    if not isinstance(document, dict) or set(document) != required:
        raise ValueError("invalid private YouTube session")
    if (
        document["schema"] != 1
        or document["addon_id"] != "plugin.video.youtube"
        or document["addon_version"] != EXPECTED_ADDON_VERSION
        or not API_KEY.fullmatch(document["api_key"])
        or not CLIENT_ID.fullmatch(document["client_id"])
        or not document["client_secret"]
        or any(character.isspace() for character in document["client_secret"])
        or not CHANNEL_ID.fullmatch(document["expected_channel_id"])
        or not REFRESH_TOKEN.fullmatch(document["tv_refresh_token"])
        or not REFRESH_TOKEN.fullmatch(document["personal_refresh_token"])
        or not REFRESH_TOKEN.fullmatch(document["vr_refresh_token"])
    ):
        raise ValueError("invalid private YouTube session")
    hint = document["account_hint"]
    expected_hint = references.get("YOUTUBE_USER", "")
    if (
        not isinstance(hint, str)
        or "@" not in hint
        or any(character.isspace() for character in hint)
        or not isinstance(expected_hint, str)
        or hint.casefold() != expected_hint.strip().casefold()
    ):
        raise ValueError("YouTube session account differs from YOUTUBE_USER")
    return document


def configuration(root, profile, references):
    session = load_session(root, references)
    api_key, client_id, client_secret, account_hint = resolve_credentials(
        profile, references
    )
    if session is None:
        return api_key, client_id, client_secret, account_hint, None
    session_values = (
        session["api_key"],
        session["client_id"],
        session["client_secret"],
    )
    configured_values = (api_key, client_id, client_secret)
    if api_key is not None and configured_values != session_values:
        raise ValueError("YouTube API references differ from private session")
    return (*session_values, session["account_hint"], session)


def _read_report(adb, port, serial):
    result = adb_command(
        adb,
        port,
        serial,
        "shell",
        f"cat '{REMOTE_REPORT}'",
        check=False,
        text=True,
        timeout=10,
    )
    payload = (result.stdout or "").strip()
    if not payload.startswith("{"):
        return None
    try:
        return json.loads(payload)
    except json.JSONDecodeError:
        return None


def _wait_report(adb, port, serial, deadline):
    while time.monotonic() < deadline:
        try:
            report = _read_report(adb, port, serial)
        except (OSError, subprocess.TimeoutExpired):
            report = None
        if report is not None:
            return report
        time.sleep(1)
    return None


def _dispatch(adb, port, serial, command, deadline):
    events = AdbEventClient(adb, port, serial)
    try:
        # Always prefer the device-local EventServer path. Android 14 may
        # expose ADB over LAN while binding Kodi's UDP listener only to
        # 127.0.0.1; a host UDP send then succeeds but is silently discarded.
        events.execute_builtin(command)
    except (OSError, RuntimeError, TimeoutError):
        with AdbJsonRpcClient(adb, port, serial) as rpc:
            rpc.call("XBMC.ExecuteBuiltin", {"command": command, "wait": False})
    return _wait_report(adb, port, serial, deadline)


def configure(
    adb,
    port,
    serial,
    profile,
    references,
    device_script,
    root=None,
    timeout=PRIVATE_ADAPTER_TIMEOUT_SECONDS,
):
    root = Path(root or Path(__file__).resolve().parents[1])
    api_key, client_id, client_secret, account_hint, session = configuration(
        root, profile, references
    )
    if api_key is None:
        return {
            "adapter": ADAPTER,
            "serial": serial,
            "schema": 1,
            "ok": True,
            "status": "API_CONFIG_REQUIRED",
            "authorization": "API_CONFIG_REQUIRED",
            "changed": False,
            "personal_api_configured": False,
            "account_hint_configured": bool(account_hint),
        }
    payload = {
        "schema": 2 if session else 1,
        "addon_version": EXPECTED_ADDON_VERSION,
        "api_key": api_key,
        "client_id": client_id,
        "client_secret": client_secret,
    }
    if session:
        payload["session"] = {
            "account_hint": session["account_hint"],
            "expected_channel_id": session["expected_channel_id"],
            "tv_refresh_token": session["tv_refresh_token"],
            "personal_refresh_token": session["personal_refresh_token"],
            "vr_refresh_token": session["vr_refresh_token"],
        }
    try:
        with tempfile.NamedTemporaryFile(
            mode="w", encoding="utf-8", suffix=".json"
        ) as private_config:
            json.dump(payload, private_config)
            private_config.flush()
            adb_command(adb, port, serial, "push", str(device_script), REMOTE_SCRIPT)
            adb_command(adb, port, serial, "push", private_config.name, REMOTE_CONFIG)
        adb_command(
            adb,
            port,
            serial,
            "shell",
            f"rm -f '{REMOTE_REPORT}' '{REMOTE_REPORT}.tmp'",
            check=False,
            timeout=10,
        )
        _wait_for_kodi_ready(adb, port, serial)
        report = _dispatch(
            adb,
            port,
            serial,
            f"RunScript({REMOTE_SCRIPT},{REMOTE_CONFIG},{REMOTE_REPORT})",
            time.monotonic() + timeout,
        )
        if report is None:
            raise TimeoutError("YouTube private adapter timed out")
        if not report.get("ok"):
            raise RuntimeError(
                "YouTube private adapter failed: {} at {}".format(
                    report.get("error_type", "unknown"),
                    report.get("stage", "unknown"),
                )
            )
        return {
            "adapter": ADAPTER,
            "serial": serial,
            "account_hint_configured": bool(account_hint),
            "session_configured": bool(session),
            **report,
        }
    finally:
        adb_command(
            adb,
            port,
            serial,
            "shell",
            f"rm -f '{REMOTE_SCRIPT}' '{REMOTE_CONFIG}' '{REMOTE_REPORT}' '{REMOTE_REPORT}.tmp'",
            check=False,
            timeout=10,
        )


def _parser():
    parser = argparse.ArgumentParser()
    parser.add_argument("--serial", required=True)
    parser.add_argument("--references", default=".env")
    parser.add_argument("--api-key-ref", default="YOUTUBE_API_KEY")
    parser.add_argument("--client-id-ref", default="YOUTUBE_CLIENT_ID")
    parser.add_argument("--client-secret-ref", default="YOUTUBE_CLIENT_SECRET")
    parser.add_argument("--account-hint-ref", default="YOUTUBE_USER")
    parser.add_argument("--adb", default="/home/mwo/android-sdk/platform-tools/adb")
    parser.add_argument("--adb-server-port", type=int, default=5038)
    parser.add_argument(
        "--timeout", type=float, default=PRIVATE_ADAPTER_TIMEOUT_SECONDS
    )
    return parser


def main():
    root = Path(__file__).resolve().parents[1]
    args = _parser().parse_args()
    references = Path(args.references)
    if not references.is_absolute():
        references = root / references
    result = configure(
        args.adb,
        args.adb_server_port,
        args.serial,
        {
            "adapter": ADAPTER,
            "api_key_ref": args.api_key_ref,
            "client_id_ref": args.client_id_ref,
            "client_secret_ref": args.client_secret_ref,
            "account_hint_ref": args.account_hint_ref,
        },
        load_private_references(references),
        root / "tests/e2e/kodi_youtube_configure.py",
        root=root,
        timeout=args.timeout,
    )
    print(json.dumps(result, indent=2, sort_keys=True))


if __name__ == "__main__":
    main()
