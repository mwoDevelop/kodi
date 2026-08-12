#!/usr/bin/env python3
"""Apply and verify OpenSubtitles.org credentials on Android Kodi."""

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


REMOTE_SCRIPT = "/sdcard/Download/.mwo-opensubtitles-configure.py"
REMOTE_CONFIG = "/sdcard/Download/.mwo-opensubtitles-credentials.json"
REMOTE_REPORT = "/sdcard/Download/.mwo-opensubtitles-configure.json"
ADAPTER = "opensubtitles-org-v1"
ENVIRONMENT_NAMES = ("OPENSUBTITLES_USER", "OPENSUBTITLES_PASS")


def validate_profile(profile):
    required = {"adapter", "username_ref", "password_ref"}
    if not isinstance(profile, dict) or set(profile) != required:
        raise ValueError("invalid private add-on profile")
    if profile["adapter"] != ADAPTER:
        raise ValueError("unsupported OpenSubtitles adapter")
    for field in ("username_ref", "password_ref"):
        if profile[field] not in ENVIRONMENT_NAMES:
            raise ValueError("unsupported OpenSubtitles reference")
    if profile["username_ref"] == profile["password_ref"]:
        raise ValueError("OpenSubtitles references must differ")
    return dict(profile)


def resolve_credentials(profile, references):
    profile = validate_profile(profile)
    values = []
    for field in ("username_ref", "password_ref"):
        reference = profile[field]
        value = references.get(reference)
        if not isinstance(value, str) or not value or len(value) > 512:
            raise ValueError("missing private reference: %s" % reference)
        values.append(value)
    return tuple(values)


def _read_report(adb, port, serial):
    result = adb_command(
        adb,
        port,
        serial,
        "shell",
        "cat '%s'" % REMOTE_REPORT,
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
    username, password = resolve_credentials(profile, references)
    payload = {"schema": 1, "username": username, "password": password}
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
            "rm -f '%s' '%s.tmp'" % (REMOTE_REPORT, REMOTE_REPORT),
            check=False,
            timeout=10,
        )
        _wait_for_kodi_ready(adb, port, serial)
        report = _dispatch(
            adb,
            port,
            serial,
            "RunScript(%s,%s,%s)" % (REMOTE_SCRIPT, REMOTE_CONFIG, REMOTE_REPORT),
            time.monotonic() + timeout,
        )
        if report is None:
            raise TimeoutError("OpenSubtitles private adapter timed out")
        if not report.get("ok"):
            if (
                report.get("error_type") == "VipRequiredError"
                and report.get("status") == "VIP_REQUIRED"
            ):
                return {"adapter": ADAPTER, "serial": serial, **report}
            raise RuntimeError(
                "OpenSubtitles private adapter failed: %s at %s (login %s)"
                % (
                    report.get("error_type", "unknown"),
                    report.get("stage", "unknown"),
                    report.get("login_status", "not-reached"),
                )
            )
        return {"adapter": ADAPTER, "serial": serial, **report}
    finally:
        adb_command(
            adb,
            port,
            serial,
            "shell",
            "rm -f '%s' '%s' '%s' '%s.tmp'"
            % (REMOTE_SCRIPT, REMOTE_CONFIG, REMOTE_REPORT, REMOTE_REPORT),
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
        },
        load_private_references(references),
        root / "tests/e2e/kodi_opensubtitles_configure.py",
        timeout=args.timeout,
    )
    print(json.dumps(result, indent=2, sort_keys=True))


if __name__ == "__main__":
    main()
