"""Assign restored add-ons to a verified Kodi repository index."""

import glob
import json
import os
import re
import sqlite3
import sys

import xbmcvfs


SAFE_ADDON_ID = re.compile(r"^[A-Za-z0-9._-]+$")


class RepositoryIndexNotReady(RuntimeError):
    pass


def _write_marker(path, value):
    temporary = path + ".tmp"
    with open(temporary, "w", encoding="utf-8") as handle:
        json.dump(value, handle, sort_keys=True)
        handle.flush()
        os.fsync(handle.fileno())
    os.replace(temporary, path)


def _database():
    root = xbmcvfs.translatePath("special://database")
    candidates = glob.glob(os.path.join(root, "Addons*.db"))
    numbered = []
    for path in candidates:
        match = re.search(r"Addons([0-9]+)[.]db$", path)
        if match:
            numbered.append((int(match.group(1)), path))
    if not numbered:
        raise RuntimeError("Kodi add-on database was not found")
    return max(numbered)[1]


def _apply(database, origins):
    connection = sqlite3.connect(database)
    try:
        with connection:
            for addon_id, origin in origins.items():
                if not SAFE_ADDON_ID.fullmatch(addon_id):
                    raise ValueError("unsafe add-on identifier")
                if not SAFE_ADDON_ID.fullmatch(origin):
                    raise ValueError("unsafe repository identifier")
                repository = connection.execute(
                    "SELECT checksum FROM repo WHERE addonID=?",
                    (origin,),
                ).fetchone()
                if not repository or not repository[0]:
                    raise RepositoryIndexNotReady(
                        "repository index is not ready"
                    )
                candidate = connection.execute(
                    """
                    SELECT 1
                    FROM addons
                    JOIN addonlinkrepo ON addonlinkrepo.idAddon=addons.id
                    JOIN repo ON repo.id=addonlinkrepo.idRepo
                    WHERE addons.addonID=? AND repo.addonID=?
                    """,
                    (addon_id, origin),
                ).fetchone()
                if not candidate:
                    raise RepositoryIndexNotReady(
                        "add-on is absent from repository index"
                    )
                installed = connection.execute(
                    "SELECT origin FROM installed WHERE addonID=?",
                    (addon_id,),
                ).fetchone()
                if not installed:
                    raise RuntimeError("add-on is not installed")
                if installed[0] not in ("", origin):
                    raise RuntimeError("add-on has a different origin")
                connection.execute(
                    "UPDATE installed SET origin=? WHERE addonID=?",
                    (origin, addon_id),
                )
    finally:
        connection.close()


def main():
    mapping_path, marker_path = sys.argv[1:3]
    try:
        with open(mapping_path, encoding="utf-8") as handle:
            origins = json.load(handle)
        if not isinstance(origins, dict) or not origins:
            raise ValueError("origin mapping is empty")
        _apply(_database(), origins)
        _write_marker(
            marker_path,
            {"ok": True, "updated": len(origins)},
        )
    except Exception as exc:
        _write_marker(
            marker_path,
            {"ok": False, "error_type": type(exc).__name__},
        )


if __name__ == "__main__":
    main()
