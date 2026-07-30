"""Atomically apply a validated add-on candidate ZIP inside Kodi."""

import json
import os
import re
import shutil
import stat
import sys
from pathlib import Path, PurePosixPath
from xml.etree import ElementTree
from zipfile import ZipFile

import xbmcvfs

SAFE_ID = re.compile(r"^[a-z0-9_.-]+$")
MAX_FILES = 2000
MAX_BYTES = 32 * 1024 * 1024


def _safe_members(archive, addon_id):
    members = []
    total = 0
    for member in archive.infolist():
        path = PurePosixPath(member.filename)
        if (
            path.is_absolute()
            or not path.parts
            or path.parts[0] != addon_id
            or ".." in path.parts
        ):
            raise ValueError("unsafe candidate archive path")
        mode = member.external_attr >> 16
        if stat.S_ISLNK(mode):
            raise ValueError("candidate archive contains a symlink")
        if member.file_size < 0:
            raise ValueError("invalid candidate member size")
        total += member.file_size
        members.append(member)
    if not members or len(members) > MAX_FILES or total > MAX_BYTES:
        raise ValueError("candidate archive exceeds policy")
    return members


def _identity(addon_xml):
    root = ElementTree.parse(addon_xml).getroot()
    return root.attrib.get("id"), root.attrib.get("version")


def _apply(zip_path, addon_id, expected_version):
    if not SAFE_ID.fullmatch(addon_id):
        raise ValueError("unsafe add-on id")
    addon_root = Path(
        xbmcvfs.translatePath("special://home/addons")
    ).resolve()
    work_root = Path(
        xbmcvfs.translatePath("special://temp/mwodevelop-candidate")
    ).resolve()
    target = addon_root / addon_id
    staging = work_root / ("staging-" + addon_id)
    backup = work_root / ("backup-" + addon_id)
    if target.parent != addon_root or staging.parent != work_root:
        raise ValueError("unsafe candidate target")
    shutil.rmtree(staging, ignore_errors=True)
    shutil.rmtree(backup, ignore_errors=True)
    work_root.mkdir(parents=True, exist_ok=True)
    with ZipFile(zip_path) as archive:
        members = _safe_members(archive, addon_id)
        archive.extractall(staging, members=members)
    candidate = staging / addon_id
    found_id, found_version = _identity(candidate / "addon.xml")
    if found_id != addon_id or found_version != expected_version:
        raise ValueError("candidate identity mismatch")
    replaced = target.exists()
    if replaced:
        os.replace(target, backup)
    try:
        os.replace(candidate, target)
        installed_id, installed_version = _identity(target / "addon.xml")
        if installed_id != addon_id or installed_version != expected_version:
            raise ValueError("installed candidate identity mismatch")
    except Exception:
        shutil.rmtree(target, ignore_errors=True)
        if replaced and backup.exists():
            os.replace(backup, target)
        raise
    shutil.rmtree(backup, ignore_errors=True)
    shutil.rmtree(staging, ignore_errors=True)
    return {"files": len(members), "version": expected_version}


def main():
    marker = sys.argv[4] if len(sys.argv) > 4 else ""
    result = {"ok": False, "schema": 1}
    try:
        if len(sys.argv) != 5:
            raise ValueError("expected zip, add-on id, version and marker")
        result.update(_apply(sys.argv[1], sys.argv[2], sys.argv[3]))
        result["ok"] = True
    except Exception as error:  # noqa: BLE001 - report Kodi apply boundary
        result["error_type"] = type(error).__name__
    if not marker:
        return
    Path(marker).parent.mkdir(parents=True, exist_ok=True)
    Path(marker).write_text(
        json.dumps(result, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )


if __name__ == "__main__":
    main()
