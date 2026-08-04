#!/usr/bin/env python3
"""Apply Rapideo credentials from an ignored reference file on Android Kodi."""

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


REMOTE_SCRIPT = "/sdcard/Download/.mwo-rapideo-configure.py"
REMOTE_CONFIG = "/sdcard/Download/.mwo-rapideo-credentials.json"
REMOTE_REPORT = "/sdcard/Download/.mwo-rapideo-configure.json"
ADAPTER = "rapideo-v1"
ENVIRONMENT_NAMES = ("RAPIDEO_USER", "RAPIDEO_PASS")


def validate_profile(profile):
    required = {"adapter", "username_ref", "password_ref"}
    if not isinstance(profile, dict) or set(profile) != required:
        raise ValueError("invalid private add-on profile")
    if profile["adapter"] != ADAPTER:
        raise ValueError("unsupported private add-on adapter")
    for name in ("username_ref", "password_ref"):
        if profile[name] not in ENVIRONMENT_NAMES:
            raise ValueError("unsupported Rapideo reference")
    if profile["username_ref"] == profile["password_ref"]:
        raise ValueError("Rapideo references must differ")
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
    return json.loads(payload) if payload.startswith("{") else None


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


def configure(
    adb,
    port,
    serial,
    profile,
    references,
    device_script,
    timeout=90,
):
    username, password = resolve_credentials(profile, references)
    payload = {
        "schema": 1,
        "username": username,
        "password": password,
    }
    try:
        with tempfile.NamedTemporaryFile(
            mode="w", encoding="utf-8", suffix=".json"
        ) as private_config:
            json.dump(payload, private_config)
            private_config.flush()
            adb_command(
                adb, port, serial, "push", str(device_script), REMOTE_SCRIPT
            )
            adb_command(
                adb,
                port,
                serial,
                "push",
                private_config.name,
                REMOTE_CONFIG,
            )
        adb_command(
            adb,
            port,
            serial,
            "shell",
            "rm -f '%s'" % REMOTE_REPORT,
            check=False,
            timeout=10,
        )
        _wait_for_kodi_ready(adb, port, serial)
        command = "RunScript(%s,%s,%s)" % (
            REMOTE_SCRIPT,
            REMOTE_CONFIG,
            REMOTE_REPORT,
        )
        deadline = time.monotonic() + timeout
        report = None
        try:
            with AdbJsonRpcClient(adb, port, serial) as rpc:
                rpc.call(
                    "XBMC.ExecuteBuiltin",
                    {"command": command, "wait": False},
                )
            report = _wait_report(
                adb, port, serial, min(deadline, time.monotonic() + 15)
            )
        except (OSError, RuntimeError, TimeoutError):
            report = None
        events = AdbEventClient(adb, port, serial)
        while report is None and time.monotonic() < deadline:
            events.execute_builtin(command)
            report = _wait_report(
                adb, port, serial, min(deadline, time.monotonic() + 12)
            )
        if report is None:
            raise TimeoutError("Rapideo private adapter timed out")
        if not report.get("ok"):
            transport_key = {
                "authenticate": "authentication_transport",
                "account": "account_transport",
            }.get(report.get("stage"), "")
            transport = report.get(transport_key, {})
            transport_summary = ""
            if isinstance(transport, dict):
                transport_summary = " (HTTP %s, %s)" % (
                    transport.get("http_status", "unknown"),
                    transport.get("content_type", "unknown"),
                )
            api_error = report.get("authentication_api_error")
            if api_error is not None:
                transport_summary += " (API error %s)" % api_error
            raise RuntimeError(
                "Rapideo private adapter failed: %s at %s%s"
                % (
                    report.get("error_type", "unknown"),
                    report.get("stage", "unknown"),
                    transport_summary,
                )
            )
        return {"adapter": ADAPTER, "serial": serial, **report}
    finally:
        adb_command(
            adb,
            port,
            serial,
            "shell",
            "rm -f '%s' '%s' '%s'"
            % (REMOTE_SCRIPT, REMOTE_CONFIG, REMOTE_REPORT),
            check=False,
            timeout=10,
        )


def main():
    root = Path(__file__).resolve().parents[1]
    parser = argparse.ArgumentParser()
    parser.add_argument("--serial", required=True)
    parser.add_argument("--references", default=".env")
    parser.add_argument("--username-ref", default="RAPIDEO_USER")
    parser.add_argument("--password-ref", default="RAPIDEO_PASS")
    parser.add_argument(
        "--adb", default="/home/mwo/android-sdk/platform-tools/adb"
    )
    parser.add_argument("--adb-server-port", type=int, default=5038)
    parser.add_argument("--timeout", type=float, default=90)
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
        root / "tests/e2e/kodi_rapideo_configure.py",
        timeout=args.timeout,
    )
    print(json.dumps(result, indent=2, sort_keys=True))


if __name__ == "__main__":
    main()
