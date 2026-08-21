#!/usr/bin/env python3
"""Set and verify one Profile Sync secret delivery mode on Android Kodi."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from tools.kodi_portable_state_rollout import (
    REMOTE_MARKER,
    REMOTE_PROFILE_SYNC_SCRIPT,
    _cleanup,
    _push_tools,
    run_kodi_script,
)
from tools.kodi_sync_inventory import load_sync_inventory


def configure(repository, logical_device_id, mode, adb, port):
    inventory = load_sync_inventory(repository)
    device = inventory["devices"].get(logical_device_id)
    if not device or device["platform"] not in {"android", "android-emulator"}:
        raise ValueError("secret mode target must be a registered Android device")
    serial = device["endpoints"]["adb"]
    try:
        _push_tools(adb, port, serial, include_profile_sync=True)
        result = run_kodi_script(
            adb,
            port,
            serial,
            "RunScript("
            f"{REMOTE_PROFILE_SYNC_SCRIPT},configure-secret-mode,"
            f"{REMOTE_MARKER},{mode})",
            timeout=60,
        )
        if (
            result.get("secret_mode") != mode
            or not result.get("paired")
            or not result.get("encryption_key_registered")
            or not result.get("has_encryption_private_key")
        ):
            raise RuntimeError("Profile Sync secret mode verification failed")
        return {
            "schema": 1,
            "device": logical_device_id,
            "addon_version": result.get("addon_version"),
            "mode": mode,
            "result": "pass",
        }
    finally:
        _cleanup(adb, port, serial)


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--device", required=True)
    parser.add_argument("--mode", choices=("shadow", "canary", "active"), required=True)
    parser.add_argument("--adb", default="/home/mwo/android-sdk/platform-tools/adb")
    parser.add_argument("--adb-server-port", type=int, default=5038)
    args = parser.parse_args()
    print(
        json.dumps(
            configure(ROOT, args.device, args.mode, args.adb, args.adb_server_port),
            indent=2,
            sort_keys=True,
        )
    )


if __name__ == "__main__":
    main()
