#!/usr/bin/env python3
"""Run a reversible Profile Sync apply/rollback canary on Android Kodi."""

from __future__ import annotations

import argparse
import json
import time
from pathlib import Path

from tools.kodi_devices import load_registry, resolve_device
from tools.kodi_profile import (
    AdbEventClient,
    adb_command,
    adb_output,
)


REMOTE_PROBE = "/sdcard/Download/.mwo-profile-sync-apply-probe.py"
REMOTE_MARKER = "/sdcard/Download/.mwo-profile-sync-apply-result.json"


def main():
    repository = Path(__file__).resolve().parents[2]
    parser = argparse.ArgumentParser()
    parser.add_argument("--device", required=True)
    parser.add_argument(
        "--adb", default="/home/mwo/android-sdk/platform-tools/adb"
    )
    parser.add_argument("--adb-server-port", type=int, default=5038)
    parser.add_argument("--result", type=Path)
    args = parser.parse_args()

    registry = load_registry(repository / ".kodi-private/devices.json")
    device = resolve_device(registry, args.device)
    if device["platform"] not in {"android", "android-emulator"}:
        raise ValueError("apply canary requires an Android Kodi device")
    serial = device["endpoints"]["adb"]
    model = adb_output(
        args.adb,
        args.adb_server_port,
        serial,
        "shell",
        "getprop ro.product.model",
    ).strip()
    if model != device["expected"]["model"]:
        raise RuntimeError("device registry resolved to the wrong model")

    local_probe = repository / "tests/e2e/profile_sync_apply_probe.py"
    adb_command(
        args.adb,
        args.adb_server_port,
        serial,
        "push",
        str(local_probe),
        REMOTE_PROBE,
        text=True,
    )
    try:
        adb_command(
            args.adb,
            args.adb_server_port,
            serial,
            "shell",
            "rm -f '%s'" % REMOTE_MARKER,
            check=False,
        )
        AdbEventClient(
            args.adb, args.adb_server_port, serial
        ).execute_builtin("RunScript(%s,%s)" % (REMOTE_PROBE, REMOTE_MARKER))
        deadline = time.monotonic() + 90
        document = None
        while time.monotonic() < deadline:
            marker = adb_command(
                args.adb,
                args.adb_server_port,
                serial,
                "shell",
                "cat '%s'" % REMOTE_MARKER,
                check=False,
                text=True,
            )
            if marker.returncode == 0 and marker.stdout.strip().startswith("{"):
                document = json.loads(marker.stdout)
                break
            time.sleep(1)
        if document is None:
            raise TimeoutError("Profile Sync apply marker timed out")
        if not document.get("ok"):
            raise RuntimeError(
                "Profile Sync apply canary failed: %s"
                % document.get("error_type", "unknown")
            )
        report = {
            "schema": 1,
            "logical_device_id": args.device,
            "model": model,
            "successful_apply": document["successful_apply"],
            "rollback": document["rollback"],
            "settings_restored": document["settings_restored"],
            "journal_clean": document["journal_clean"],
            "result": "pass",
        }
        rendered = json.dumps(report, indent=2, sort_keys=True)
        if args.result is not None:
            destination = args.result.resolve()
            destination.parent.mkdir(parents=True, exist_ok=True)
            destination.write_text(rendered + "\n", encoding="utf-8")
        print(rendered)
    finally:
        adb_command(
            args.adb,
            args.adb_server_port,
            serial,
            "shell",
            "rm -f '%s' '%s'" % (REMOTE_PROBE, REMOTE_MARKER),
            check=False,
        )


if __name__ == "__main__":
    raise SystemExit(main())
