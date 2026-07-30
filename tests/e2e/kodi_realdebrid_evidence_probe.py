"""Emit boolean Real-Debrid resolver evidence without copying Kodi logs."""

import json
import sys
from pathlib import Path

import xbmcvfs


LOG = xbmcvfs.translatePath("special://temp/umbrella.log")


def main():
    marker = sys.argv[1] if len(sys.argv) > 1 else ""
    result = {"ok": False, "schema": 1}
    try:
        lines = Path(LOG).read_text(
            encoding="utf-8", errors="replace"
        ).splitlines()[-600:]
        lowered = [line.lower() for line in lines]
        result.update(
            {
                "add_magnet_observed": any(
                    "realdebrid.add_magnet" in line for line in lowered
                ),
                "played_as_resolve_observed": any(
                    "played file as resolve" in line for line in lowered
                ),
                "resolver_rejection_count": sum(
                    "real-debrid resolver rejected source" in line
                    for line in lowered
                ),
                "ok": True,
            }
        )
    except Exception as error:  # noqa: BLE001 - report Kodi probe boundary
        result["error_type"] = type(error).__name__
    if marker:
        Path(marker).parent.mkdir(parents=True, exist_ok=True)
        Path(marker).write_text(
            json.dumps(result, indent=2, sort_keys=True) + "\n",
            encoding="utf-8",
        )


if __name__ == "__main__":
    main()
