#!/usr/bin/env python3
"""Safely remove one unowned add-on from an Android Kodi profile."""

from __future__ import annotations

import argparse
import json
import re
import sys
import time
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from tools.kodi_profile import (
    KODI_PACKAGE,
    AdbEventClient,
    AdbJsonRpcClient,
    _wait_for_kodi_ready,
    adb_command,
)


SAFE_ADDON_ID = re.compile(r"^[A-Za-z0-9._-]+$")
REMOTE_SCRIPT = "/sdcard/Download/mwo-addon-remove.py"
REMOTE_MARKER = "/sdcard/Download/mwo-addon-remove-result.json"


def _read_marker(adb, port, serial):
    marker = adb_command(
        adb,
        port,
        serial,
        "shell",
        "cat '%s'" % REMOTE_MARKER,
        check=False,
        text=True,
        timeout=10,
    )
    payload = (marker.stdout or "").strip()
    return json.loads(payload) if payload.startswith("{") else None


def remove_addon(adb, port, serial, addon_id, timeout=90):
    if not SAFE_ADDON_ID.fullmatch(addon_id):
        raise ValueError("unsafe add-on identifier")
    script = ROOT / "tools/kodi_addon_remove_device.py"
    adb_command(adb, port, serial, "push", str(script), REMOTE_SCRIPT)
    try:
        adb_command(
            adb,
            port,
            serial,
            "shell",
            "rm -f '%s'" % REMOTE_MARKER,
            check=False,
        )
        _wait_for_kodi_ready(adb, port, serial)
        with AdbJsonRpcClient(adb, port, serial) as rpc:
            try:
                rpc.call(
                    "Addons.SetAddonEnabled",
                    {"addonid": addon_id, "enabled": False},
                )
            except RuntimeError:
                pass
        events = AdbEventClient(adb, port, serial)
        deadline = time.monotonic() + timeout
        result = None
        while time.monotonic() < deadline:
            events.execute_builtin(
                "RunScript(%s,%s,%s)"
                % (REMOTE_SCRIPT, addon_id, REMOTE_MARKER)
            )
            attempt = min(deadline, time.monotonic() + 10)
            while time.monotonic() < attempt:
                result = _read_marker(adb, port, serial)
                if result is not None:
                    break
                time.sleep(1)
            if result is not None:
                break
        if result is None:
            raise TimeoutError("Kodi add-on removal did not finish")
        if not result.get("ok"):
            raise RuntimeError(
                "Kodi add-on removal failed: %s"
                % result.get("error_type", "unknown")
            )
        adb_command(
            adb,
            port,
            serial,
            "shell",
            "am force-stop %s" % KODI_PACKAGE,
        )
        adb_command(
            adb,
            port,
            serial,
            "shell",
            "monkey -p %s -c android.intent.category.LAUNCHER 1 >/dev/null"
            % KODI_PACKAGE,
        )
        _wait_for_kodi_ready(adb, port, serial)
        AdbEventClient(adb, port, serial).execute_builtin(
            "UpdateLocalAddons"
        )
        time.sleep(2)
        with AdbJsonRpcClient(adb, port, serial) as rpc:
            try:
                rpc.call(
                    "Addons.GetAddonDetails",
                    {"addonid": addon_id, "properties": ["enabled"]},
                )
            except RuntimeError:
                return {
                    "addon": addon_id,
                    "serial": serial,
                    **result,
                }
        raise RuntimeError("Kodi still reports the removed add-on")
    finally:
        adb_command(
            adb,
            port,
            serial,
            "shell",
            "rm -f '%s' '%s'" % (REMOTE_SCRIPT, REMOTE_MARKER),
            check=False,
        )


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--addon-id", required=True)
    parser.add_argument("--serial", required=True)
    parser.add_argument(
        "--adb", default="/home/mwo/android-sdk/platform-tools/adb"
    )
    parser.add_argument("--adb-server-port", type=int, default=5038)
    parser.add_argument("--timeout", type=float, default=90)
    args = parser.parse_args()
    result = remove_addon(
        args.adb,
        args.adb_server_port,
        args.serial,
        args.addon_id,
        args.timeout,
    )
    print(json.dumps(result, indent=2, sort_keys=True))


if __name__ == "__main__":
    main()
