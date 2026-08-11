"""Apply only allowlisted private Umbrella settings inside Kodi."""

from __future__ import annotations

import json
import os
import sys

import xbmcaddon


ADDON_ID = "plugin.video.umbrella"
ALLOWED = {
    "realdebrid.enable",
    "realdebridtoken",
    "realdebridusername",
    "realdebrid.clientid",
    "realdebridrefresh",
    "realdebridsecret",
}


def _write(path, document):
    temporary = path + ".tmp"
    with open(temporary, "w", encoding="utf-8") as destination:
        json.dump(document, destination, sort_keys=True)
        destination.write("\n")
        destination.flush()
        os.fsync(destination.fileno())
    os.replace(temporary, path)


def main():
    config_path, marker = sys.argv[1:3]
    report = {"ok": False, "schema": 1}
    try:
        with open(config_path, encoding="utf-8") as source:
            document = json.load(source)
        settings = document.get("settings")
        if (
            document.get("schema") != 1
            or not isinstance(settings, dict)
            or set(settings) != ALLOWED
            or any(
                not isinstance(value, str) or not value or len(value) > 2048
                for value in settings.values()
            )
        ):
            raise ValueError("invalid Umbrella private settings payload")
        addon = xbmcaddon.Addon(ADDON_ID)
        changed = False
        for setting_id, value in settings.items():
            if addon.getSetting(setting_id) != value:
                addon.setSetting(setting_id, value)
                changed = True
        report = {
            "ok": True,
            "schema": 1,
            "addon_version": addon.getAddonInfo("version"),
            "changed": changed,
            "configured": len(settings),
        }
    except Exception as error:  # noqa: BLE001 - Kodi runtime boundary
        report["error_type"] = type(error).__name__
    _write(marker, report)


if __name__ == "__main__":
    main()
