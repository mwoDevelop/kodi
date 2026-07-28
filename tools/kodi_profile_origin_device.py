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


def _apply(
    database,
    origins,
    previous_origins=None,
    repository_checksums=None,
):
    previous_origins = previous_origins or {}
    repository_checksums = repository_checksums or {}
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
                expected_checksum = repository_checksums.get(origin)
                if (
                    expected_checksum is not None
                    and repository[0] != expected_checksum
                ):
                    raise RepositoryIndexNotReady(
                        "repository index checksum differs"
                    )
                candidate = connection.execute(
                    """
                    SELECT addons.version
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
                    previous = previous_origins.get(addon_id)
                    if installed[0] != previous:
                        raise RuntimeError("add-on has a different origin")
                    previous_repository = connection.execute(
                        "SELECT checksum FROM repo WHERE addonID=?",
                        (previous,),
                    ).fetchone()
                    if not previous_repository or not previous_repository[0]:
                        raise RepositoryIndexNotReady(
                            "previous repository index is not ready"
                        )
                    expected_previous_checksum = repository_checksums.get(
                        previous
                    )
                    if (
                        expected_previous_checksum is not None
                        and previous_repository[0]
                        != expected_previous_checksum
                    ):
                        raise RepositoryIndexNotReady(
                            "previous repository checksum differs"
                        )
                    previous_candidate = connection.execute(
                        """
                        SELECT addons.version
                        FROM addons
                        JOIN addonlinkrepo
                          ON addonlinkrepo.idAddon=addons.id
                        JOIN repo ON repo.id=addonlinkrepo.idRepo
                        WHERE addons.addonID=? AND repo.addonID=?
                        """,
                        (addon_id, previous),
                    ).fetchone()
                    if not previous_candidate:
                        raise RepositoryIndexNotReady(
                            "add-on is absent from previous index"
                        )
                    if previous_candidate[0] != candidate[0]:
                        raise RuntimeError(
                            "repository candidates differ"
                        )
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
            document = json.load(handle)
        previous_origins = {}
        repository_checksums = {}
        if isinstance(document, dict) and document.get("schema") == 2:
            origins = document.get("origins")
            previous_origins = document.get("previous_origins", {})
            repository_checksums = document.get(
                "repository_checksums", {}
            )
        else:
            origins = document
        if not isinstance(origins, dict) or not origins:
            raise ValueError("origin mapping is empty")
        if not isinstance(previous_origins, dict):
            raise ValueError("previous origin mapping is invalid")
        if not isinstance(repository_checksums, dict):
            raise ValueError("repository checksum mapping is invalid")
        for addon_id, previous in previous_origins.items():
            if addon_id not in origins:
                raise ValueError("previous origin has no target")
            if not SAFE_ADDON_ID.fullmatch(previous):
                raise ValueError("unsafe previous repository identifier")
        for repository, checksum in repository_checksums.items():
            if not SAFE_ADDON_ID.fullmatch(repository):
                raise ValueError("unsafe checksum repository identifier")
            if not re.fullmatch(r"[0-9a-f]{64}", checksum):
                raise ValueError("invalid repository checksum")
        _apply(
            _database(),
            origins,
            previous_origins,
            repository_checksums,
        )
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
