#!/usr/bin/env python3
"""Refresh portable favourite artwork inside running Android Kodi profiles."""

from __future__ import annotations

import argparse
import json
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from tools.kodi_profile import (
    AdbEventClient,
    KODI_PACKAGE,
    _wait_for_kodi_ready,
    adb_command,
)


REMOTE_SCRIPT = "/sdcard/Download/mwo-favourite-artwork.py"
REMOTE_MARKER = "/sdcard/Download/mwo-favourite-artwork-result.json"
FAVOURITES = "special://profile/favourites.xml"
ARTWORK = "special://profile/favourite-artwork"


def rollout(adb, port, serial, script, timeout=120):
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
        AdbEventClient(adb, port, serial).execute_builtin(
            "RunScript(%s,%s,%s,%s)"
            % (REMOTE_SCRIPT, FAVOURITES, ARTWORK, REMOTE_MARKER)
        )
        deadline = time.monotonic() + timeout
        result = None
        while time.monotonic() < deadline:
            marker = adb_command(
                adb,
                port,
                serial,
                "shell",
                "cat '%s'" % REMOTE_MARKER,
                check=False,
                text=True,
            )
            if marker.returncode == 0 and marker.stdout.strip():
                result = json.loads(marker.stdout)
                break
            time.sleep(1)
        if result is None:
            raise TimeoutError("favourite artwork rollout timed out")
        if not result.get("ok"):
            raise RuntimeError(
                "favourite artwork rollout failed: %s"
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
        return {"serial": serial, **result}
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
    parser.add_argument(
        "--adb", default="/home/mwo/android-sdk/platform-tools/adb"
    )
    parser.add_argument("--adb-server-port", type=int, default=5038)
    parser.add_argument("--serial", action="append", required=True)
    args = parser.parse_args()
    script = Path(__file__).with_name("favourite_artwork.py").resolve()
    results = [
        rollout(args.adb, args.adb_server_port, serial, script)
        for serial in args.serial
    ]
    print(json.dumps({"schema": 1, "results": results}, indent=2, sort_keys=True))


if __name__ == "__main__":
    main()
