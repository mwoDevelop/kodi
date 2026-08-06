"""Transactional Profile Sync bootstrap executed inside Kodi Flatpak."""

from __future__ import annotations

import json
import os
import re
import shutil
import stat
import sys
import time
import zipfile
from pathlib import Path, PurePosixPath
from xml.etree import ElementTree

import xbmc
import xbmcaddon
import xbmcvfs


ADDON_ID = "service.mwodevelop.profilesync"
REPOSITORY_ID = "repository.mwodevelop"
MARKER_NAME = "flatpak-rollout-result.json"
SAFE_STAGE = re.compile(r"^\.mwodevelop-flatpak-[0-9a-f]{16}$")
MAX_FILES = 4000
MAX_BYTES = 64 * 1024 * 1024


def _write_atomic(path, document):
    payload = (json.dumps(document, sort_keys=True) + "\n").encode("utf-8")
    temporary = str(path) + ".tmp"
    with open(temporary, "wb") as handle:
        handle.write(payload)
        handle.flush()
        os.fsync(handle.fileno())
    os.chmod(temporary, 0o600)
    os.replace(temporary, path)


def _safe_members(archive, addon_id):
    members = []
    total = 0
    for member in archive.infolist():
        path = PurePosixPath(member.filename)
        mode = member.external_attr >> 16
        if (
            path.is_absolute()
            or not path.parts
            or path.parts[0] != addon_id
            or ".." in path.parts
            or stat.S_ISLNK(mode)
            or member.file_size < 0
        ):
            raise ValueError("unsafe candidate archive")
        members.append(member)
        total += member.file_size
    if not members or len(members) > MAX_FILES or total > MAX_BYTES:
        raise ValueError("candidate archive exceeds policy")
    return members


def _extract_candidate(archive_path, addon_id, output):
    with zipfile.ZipFile(archive_path) as archive:
        members = _safe_members(archive, addon_id)
        archive.extractall(output, members=members)
    root = output / addon_id
    addon = ElementTree.parse(root / "addon.xml").getroot()
    if addon.get("id") != addon_id or not addon.get("version"):
        raise ValueError("candidate identity mismatch")
    return root, addon.get("version")


def _rpc(method, params):
    response = json.loads(
        xbmc.executeJSONRPC(
            json.dumps(
                {
                    "jsonrpc": "2.0",
                    "id": method,
                    "method": method,
                    "params": params,
                },
                separators=(",", ":"),
            )
        )
    )
    if "error" in response:
        raise RuntimeError("Kodi JSON-RPC rejected %s" % method)
    return response.get("result")


def _enable(addon_id, timeout=30):
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        try:
            if _rpc(
                "Addons.SetAddonEnabled",
                {"addonid": addon_id, "enabled": True},
            ) == "OK":
                return
        except RuntimeError:
            pass
        xbmc.sleep(1000)
    raise RuntimeError("Kodi refused to enable %s" % addon_id)


def _remove(path):
    if path.is_symlink() or path.is_file():
        path.unlink(missing_ok=True)
    elif path.is_dir():
        shutil.rmtree(path)


def _recover(journal, targets, backup):
    if not journal.is_file():
        return
    document = json.loads(journal.read_text(encoding="utf-8"))
    existing = document.get("existing")
    if document.get("schema") != 1 or not isinstance(existing, list):
        raise ValueError("invalid Flatpak rollout journal")
    for name, target in reversed(list(targets.items())):
        saved = backup / name
        if saved.exists():
            _remove(target)
            os.replace(saved, target)
        elif name not in existing:
            _remove(target)
    journal.unlink(missing_ok=True)
    _remove(backup)


def _identity(addon_xml, expected_id):
    addon = ElementTree.parse(addon_xml).getroot()
    if addon.get("id") != expected_id or not addon.get("version"):
        raise ValueError("installed add-on identity mismatch")
    return addon.get("version")


def _sync(profile_root, addon_root, profile_version, repository_version):
    profile_data = profile_root / "addon_data" / ADDON_ID
    _enable(REPOSITORY_ID)
    addon_root_text = str(addon_root / ADDON_ID)
    if addon_root_text not in sys.path:
        sys.path.insert(0, addon_root_text)
    from resources.lib.mwoprofilesync.apply import (
        KodiAddonSettings,
        TransactionalApplier,
    )
    from resources.lib.mwoprofilesync.portable import (
        KodiFavourites,
        PortableFavouritesAdapter,
    )
    from resources.lib.mwoprofilesync.state import StateStore
    from resources.lib.mwoprofilesync.sync import ReadOnlySync

    addon = xbmcaddon.Addon(ADDON_ID)
    state = StateStore(profile_data)
    applier = TransactionalApplier(
        profile_data,
        state,
        KodiAddonSettings(xbmcaddon.Addon),
        portable=PortableFavouritesAdapter(
            str(profile_root), KodiFavourites(xbmc.executeJSONRPC)
        ),
    )
    applier.recover()
    sync = ReadOnlySync(addon, state, applier=applier)()
    addon.setSetting("enabled", "true")
    _enable(ADDON_ID)
    local = state.read()
    enrollment = local.get("enrollment") or {}
    return {
        "ok": True,
        "profile_sync_version": profile_version,
        "repository_version": repository_version,
        "logical_device_id": enrollment.get("logical_device_id"),
        "status": local.get("status"),
        "sync_status": sync.get("status"),
        "assigned_revision": local.get("assigned_revision"),
        "applied_revision": local.get("applied_revision"),
        "pending_report": bool(local.get("pending_report")),
    }


def _paths(stage):
    addon_root = Path(xbmcvfs.translatePath("special://home/addons")).resolve()
    profile_root = Path(xbmcvfs.translatePath("special://profile")).resolve()
    temp_root = Path(xbmcvfs.translatePath("special://temp")).resolve()
    stage = stage.resolve()
    if stage.parent != temp_root or not SAFE_STAGE.fullmatch(stage.name):
        raise ValueError("unsafe Flatpak rollout stage")
    return stage, addon_root, profile_root


def _sync_existing(stage):
    stage, addon_root, profile_root = _paths(stage)
    expected = json.loads((stage / "expected.json").read_text(encoding="utf-8"))
    if set(expected) != {
        "logical_device_id",
        "profile_sync_version",
        "repository_version",
    }:
        raise ValueError("invalid Flatpak sync receipt")
    profile_version = _identity(
        addon_root / ADDON_ID / "addon.xml", ADDON_ID
    )
    repository_version = _identity(
        addon_root / REPOSITORY_ID / "addon.xml", REPOSITORY_ID
    )
    if (
        profile_version != expected["profile_sync_version"]
        or repository_version != expected["repository_version"]
    ):
        raise ValueError("installed Flatpak add-on version differs")
    result = _sync(
        profile_root,
        addon_root,
        profile_version,
        repository_version,
    )
    if result["logical_device_id"] != expected["logical_device_id"]:
        raise ValueError("installed Flatpak enrollment identity differs")
    return result


def _transaction(stage):
    stage, addon_root, profile_root = _paths(stage)
    supplied = stage / "profile-data"
    required = {
        "settings.xml",
        "state.json",
        "profile-sync-ca.pem",
    }
    if (
        not supplied.is_dir()
        or {item.name for item in supplied.iterdir()} != required
        or any(not item.is_file() or item.is_symlink() for item in supplied.iterdir())
    ):
        raise ValueError("invalid Profile Sync configuration payload")
    work = stage / "work"
    backup = stage / "backup"
    journal = stage / "journal.json"
    targets = {
        "profile-addon": addon_root / ADDON_ID,
        "repository-addon": addon_root / REPOSITORY_ID,
        "profile-data": profile_root / "addon_data" / ADDON_ID,
    }
    for target in targets.values():
        if target.parent not in {addon_root, profile_root / "addon_data"}:
            raise ValueError("unsafe Flatpak rollout target")
    _recover(journal, targets, backup)
    _remove(work)
    work.mkdir(mode=0o700)
    profile_candidate, profile_version = _extract_candidate(
        stage / "profile-sync.zip", ADDON_ID, work / "profile"
    )
    repository_candidate, repository_version = _extract_candidate(
        stage / "repository.zip", REPOSITORY_ID, work / "repository"
    )
    existing = [name for name, target in targets.items() if target.exists()]
    backup.mkdir(mode=0o700)
    _write_atomic(journal, {"schema": 1, "existing": existing})
    try:
        for name, target in targets.items():
            if name in existing:
                os.replace(target, backup / name)
            target.parent.mkdir(parents=True, exist_ok=True)
        os.replace(profile_candidate, targets["profile-addon"])
        os.replace(repository_candidate, targets["repository-addon"])
        os.replace(supplied, targets["profile-data"])
        xbmc.executebuiltin("UpdateLocalAddons")
        xbmc.sleep(3000)
        result = _sync(
            profile_root,
            addon_root,
            profile_version,
            repository_version,
        )
    except BaseException:
        _recover(journal, targets, backup)
        xbmc.executebuiltin("UpdateLocalAddons")
        raise
    journal.unlink(missing_ok=True)
    _remove(backup)
    _remove(work)
    return result


def main():
    stage = Path(sys.argv[1]) if len(sys.argv) == 3 else Path("/")
    mode = sys.argv[2] if len(sys.argv) == 3 else "invalid"
    marker = stage / MARKER_NAME
    autoexec = Path(xbmcvfs.translatePath("special://profile/autoexec.py"))
    try:
        if mode == "install":
            result = _transaction(stage)
        elif mode == "sync":
            result = _sync_existing(stage)
        else:
            raise ValueError("invalid Flatpak rollout mode")
    except BaseException as error:
        result = {
            "ok": False,
            "error_type": type(error).__name__,
            "error_code": getattr(error, "code", None),
        }
    try:
        autoexec.unlink()
        _write_atomic(marker, result)
    except BaseException as error:
        _write_atomic(
            marker,
            {
                "ok": False,
                "error_type": type(error).__name__,
                "error_code": getattr(error, "code", None),
            },
        )
    finally:
        xbmc.sleep(1000)
        xbmc.executebuiltin("Quit")


if __name__ == "__main__":
    main()
