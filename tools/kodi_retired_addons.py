#!/usr/bin/env python3
"""Remove project-retired Kodi add-ons and their orphaned profile data."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from tools.kodi_addon_remove import remove_addon
from tools.kodi_default_addons import addon_details
from tools.kodi_profile import adb_command


# Leaf add-ons precede their former repositories. The removal adapter refuses
# to delete a repository that still owns any installed add-on.
RETIRED_ADDONS = (
    "plugin.video.fenlight",
    "plugin.youtube2kodilibrary",
    "script.module.cocoscrapers",
    "plugin.video.watchnixtoons2",
    "repository.cocoscrapers",
    "repository.atreides.tools",
    "repository.universalscrapers",
)


def reconcile_retired_addons(adb: str, port: int, serial: str) -> dict:
    removed = []
    for addon_id in RETIRED_ADDONS:
        paths = adb_command(
            adb,
            port,
            serial,
            "shell",
            "test -d '/sdcard/Android/data/org.xbmc.kodi/files/.kodi/addons/%s' "
            "-o -d '/sdcard/Android/data/org.xbmc.kodi/files/.kodi/userdata/addon_data/%s'"
            % (addon_id, addon_id),
            check=False,
        )
        if paths.returncode != 0 and addon_details(
            adb, port, serial, addon_id
        ) is None:
            continue
        result = remove_addon(adb, port, serial, addon_id, timeout=90)
        if result.get("directory_removed") or result.get("addon_data_removed"):
            removed.append(addon_id)
    return {
        "status": "UPDATED" if removed else "NO_CHANGE",
        "removed": removed,
        "checked": len(RETIRED_ADDONS),
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--serial", required=True)
    parser.add_argument(
        "--adb", default="/home/mwo/android-sdk/platform-tools/adb"
    )
    parser.add_argument("--adb-server-port", type=int, default=5038)
    args = parser.parse_args()
    print(
        json.dumps(
            reconcile_retired_addons(
                args.adb, args.adb_server_port, args.serial
            ),
            indent=2,
            sort_keys=True,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
