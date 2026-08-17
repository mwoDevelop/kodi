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
ENVIRONMENT_NAMES = (
    "YOUTUBE_API_KEY",
    "YOUTUBE_CLIENT_ID",
    "YOUTUBE_CLIENT_SECRET",
    "YOUTUBE_USER",
)
API_KEY = re.compile(r"^AIza[A-Za-z0-9_-]{20,80}$")
CLIENT_ID = re.compile(r"^[0-9]+-[A-Za-z0-9_-]+(?:[.]apps[.]googleusercontent[.]com)?$")


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
    for field in (
        "api_key_ref",
        "client_id_ref",
        "client_secret_ref",
        "account_hint_ref",
    ):
        reference = profile[field]
        value = references.get(reference)
        if not isinstance(value, str) or not value or len(value) > 2048:
            raise ValueError(f"missing private reference: {reference}")
        values.append(value.strip())
    api_key, client_id, client_secret, account_hint = values
    if not API_KEY.fullmatch(api_key):
        raise ValueError("invalid YouTube API key reference")
    if not CLIENT_ID.fullmatch(client_id):
        raise ValueError("invalid YouTube OAuth client ID reference")
    if not client_secret or any(character.isspace() for character in client_secret):
        raise ValueError("invalid YouTube OAuth client secret reference")
    if "@" not in account_hint or any(
        character.isspace() for character in account_hint
    ):
        raise ValueError("invalid YouTube account hint reference")
    return api_key, client_id, client_secret, account_hint


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
    try:
        with AdbJsonRpcClient(adb, port, serial) as rpc:
            rpc.call("XBMC.ExecuteBuiltin", {"command": command, "wait": False})
    except (OSError, RuntimeError, TimeoutError):
        AdbEventClient(adb, port, serial).execute_builtin(command)
    return _wait_report(adb, port, serial, deadline)


def configure(
    adb,
    port,
    serial,
    profile,
    references,
    device_script,
    timeout=120,
):
    api_key, client_id, client_secret, account_hint = resolve_credentials(
        profile, references
    )
    payload = {
        "schema": 1,
        "addon_version": EXPECTED_ADDON_VERSION,
        "api_key": api_key,
        "client_id": client_id,
        "client_secret": client_secret,
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


def main():
    root = Path(__file__).resolve().parents[1]
    parser = argparse.ArgumentParser()
    parser.add_argument("--serial", required=True)
    parser.add_argument("--references", default=".env")
    parser.add_argument("--api-key-ref", default="YOUTUBE_API_KEY")
    parser.add_argument("--client-id-ref", default="YOUTUBE_CLIENT_ID")
    parser.add_argument("--client-secret-ref", default="YOUTUBE_CLIENT_SECRET")
    parser.add_argument("--account-hint-ref", default="YOUTUBE_USER")
    parser.add_argument("--adb", default="/home/mwo/android-sdk/platform-tools/adb")
    parser.add_argument("--adb-server-port", type=int, default=5038)
    parser.add_argument("--timeout", type=float, default=120)
    args = parser.parse_args()
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
        timeout=args.timeout,
    )
    print(json.dumps(result, indent=2, sort_keys=True))


if __name__ == "__main__":
    main()
