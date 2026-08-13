#!/usr/bin/env python3
"""Apply and verify OpenSubtitles.com credentials in Umbrella on Android."""

from __future__ import annotations

import argparse
import json
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


REMOTE_SCRIPT = "/sdcard/Download/.mwo-opensubtitles-com-configure.py"
REMOTE_CONFIG = "/sdcard/Download/.mwo-opensubtitles-com-credentials.json"
REMOTE_REPORT = "/sdcard/Download/.mwo-opensubtitles-com-configure.json"
ADAPTER = "opensubtitles-com-v1"
ENVIRONMENT_NAMES = (
    "OPENSUBTITLES_USER",
    "OPENSUBTITLES_PASS",
    "OPENSUBTITLES_TOKEN",
)


def validate_profile(profile):
    required = {"adapter", "username_ref", "password_ref", "token_ref"}
    if not isinstance(profile, dict) or set(profile) != required:
        raise ValueError("invalid private OpenSubtitles.com profile")
    if profile["adapter"] != ADAPTER:
        raise ValueError("unsupported OpenSubtitles.com adapter")
    expected = {
        "username_ref": "OPENSUBTITLES_USER",
        "password_ref": "OPENSUBTITLES_PASS",
        "token_ref": "OPENSUBTITLES_TOKEN",
    }
    if any(profile.get(field) != reference for field, reference in expected.items()):
        raise ValueError("unsupported OpenSubtitles.com reference")
    return dict(profile)


def resolve_credentials(profile, references):
    profile = validate_profile(profile)
    values = []
    for field in ("username_ref", "password_ref", "token_ref"):
        reference = profile[field]
        value = references.get(reference)
        if not isinstance(value, str) or not value or len(value) > 2048:
            raise ValueError(f"missing private reference: {reference}")
        values.append(value)
    return tuple(values)


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
    probe_download=False,
):
    username, password, token = resolve_credentials(profile, references)
    payload = {
        "schema": 1,
        "username": username,
        "password": password,
        "token": token.removeprefix("Bearer "),
        "probe_download": bool(probe_download),
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
            raise TimeoutError("OpenSubtitles.com Umbrella adapter timed out")
        if not report.get("ok"):
            error_type = report.get("error_type", "unknown")
            stage = report.get("stage", "unknown")
            raise RuntimeError(
                f"OpenSubtitles.com Umbrella adapter failed: {error_type} at {stage}"
            )
        return {"adapter": ADAPTER, "serial": serial, **report}
    finally:
        adb_command(
            adb,
            port,
            serial,
            "shell",
            (
                f"rm -f '{REMOTE_SCRIPT}' '{REMOTE_CONFIG}' "
                f"'{REMOTE_REPORT}' '{REMOTE_REPORT}.tmp'"
            ),
            check=False,
            timeout=10,
        )


def main():
    root = Path(__file__).resolve().parents[1]
    parser = argparse.ArgumentParser()
    parser.add_argument("--serial", required=True)
    parser.add_argument("--references", default=".env")
    parser.add_argument("--username-ref", default="OPENSUBTITLES_USER")
    parser.add_argument("--password-ref", default="OPENSUBTITLES_PASS")
    parser.add_argument("--token-ref", default="OPENSUBTITLES_TOKEN")
    parser.add_argument("--probe-download", action="store_true")
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
            "username_ref": args.username_ref,
            "password_ref": args.password_ref,
            "token_ref": args.token_ref,
        },
        load_private_references(references),
        root / "tests/e2e/kodi_opensubtitles_com_configure.py",
        timeout=args.timeout,
        probe_download=args.probe_download,
    )
    print(json.dumps(result, indent=2, sort_keys=True))


if __name__ == "__main__":
    main()
