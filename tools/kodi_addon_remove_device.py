"""Remove one unowned Kodi add-on from inside Kodi's scoped profile."""

import glob
import json
import os
import re
import shutil
import sqlite3
import sys

import xbmcvfs


SAFE_ADDON_ID = re.compile(r"^[A-Za-z0-9._-]+$")


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


def _remove_database(database, addon_id):
    connection = sqlite3.connect(database)
    try:
        dependents = [
            row[0]
            for row in connection.execute(
                """
                SELECT addonID
                FROM installed
                WHERE origin=? AND addonID<>?
                ORDER BY addonID
                """,
                (addon_id, addon_id),
            )
        ]
        if dependents:
            raise RuntimeError("repository still owns installed add-ons")
        with connection:
            repository_ids = [
                row[0]
                for row in connection.execute(
                    "SELECT id FROM repo WHERE addonID=?",
                    (addon_id,),
                )
            ]
            for repository_id in repository_ids:
                connection.execute(
                    "DELETE FROM addonlinkrepo WHERE idRepo=?",
                    (repository_id,),
                )
            connection.execute(
                "DELETE FROM repo WHERE addonID=?", (addon_id,)
            )
            connection.execute(
                "DELETE FROM installed WHERE addonID=?", (addon_id,)
            )
            connection.execute(
                "DELETE FROM update_rules WHERE addonID=?", (addon_id,)
            )
            connection.execute(
                "DELETE FROM package WHERE addonID=?", (addon_id,)
            )
        return {"repository_rows": len(repository_ids)}
    finally:
        connection.close()


def _remove(addon_id):
    if not SAFE_ADDON_ID.fullmatch(addon_id):
        raise ValueError("unsafe add-on identifier")
    addons = xbmcvfs.translatePath("special://home/addons")
    target = os.path.join(addons, addon_id)
    backup = target + ".mwo-remove"
    if os.path.exists(backup):
        raise RuntimeError("unfinished add-on removal exists")
    moved = False
    if os.path.isdir(target):
        os.replace(target, backup)
        moved = True
    try:
        result = _remove_database(_database(), addon_id)
    except Exception:
        if moved:
            os.replace(backup, target)
        raise
    if moved:
        shutil.rmtree(backup)
    addon_data = xbmcvfs.translatePath(
        "special://profile/addon_data/%s" % addon_id
    )
    addon_data_removed = False
    if os.path.isdir(addon_data):
        shutil.rmtree(addon_data)
        addon_data_removed = True
    packages = os.path.join(addons, "packages")
    removed_packages = 0
    for package in glob.glob(os.path.join(packages, addon_id + "-*.zip")):
        if os.path.isfile(package):
            os.remove(package)
            removed_packages += 1
    return {
        **result,
        "addon_data_removed": addon_data_removed,
        "directory_removed": moved,
        "packages_removed": removed_packages,
    }


def main():
    addon_id, marker_path = sys.argv[1:3]
    try:
        result = _remove(addon_id)
        _write_marker(marker_path, {"ok": True, **result})
    except Exception as exc:
        _write_marker(
            marker_path,
            {"ok": False, "error_type": type(exc).__name__},
        )


if __name__ == "__main__":
    main()
