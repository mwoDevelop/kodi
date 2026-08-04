"""Atomically apply a validated add-on candidate ZIP inside Kodi."""

import json
import os
import re
import shutil
import stat
import sys
import uuid
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


def _apply(zip_path, addon_id, expected_version, repair_orphan=False):
    stage = "validate"
    try:
        if not SAFE_ID.fullmatch(addon_id):
            raise ValueError("unsafe add-on id")
        addon_root = Path(
            xbmcvfs.translatePath("special://home/addons")
        ).resolve()
        work_root = Path(
            xbmcvfs.translatePath("special://temp/mwodevelop-candidate")
        ).resolve()
        target = addon_root / addon_id
        # Per-run names prevent an interrupted older rollout from blocking a
        # repair. This matters on Android scoped storage where the host cannot
        # safely clean Kodi's private work directory directly.
        operation = uuid.uuid4().hex
        staging = work_root / ("staging-%s-%s" % (addon_id, operation))
        backup = work_root / ("backup-%s-%s" % (addon_id, operation))
        if target.parent != addon_root or staging.parent != work_root:
            raise ValueError("unsafe candidate target")
        stage = "prepare-work-directory"
        work_root.mkdir(parents=True, exist_ok=True)
        stage = "extract-candidate"
        with ZipFile(zip_path) as archive:
            members = _safe_members(archive, addon_id)
            archive.extractall(staging, members=members)
        candidate = staging / addon_id
        stage = "verify-candidate"
        found_id, found_version = _identity(candidate / "addon.xml")
        if found_id != addon_id or found_version != expected_version:
            raise ValueError("candidate identity mismatch")
        replaced = target.exists()
        repaired_orphan = False
        stage = "backup-installed-addon"
        if replaced:
            try:
                os.replace(target, backup)
            except PermissionError:
                if not repair_orphan or target.is_symlink():
                    raise
                stage = "verify-orphan"
                try:
                    existing_id, _existing_version = _identity(
                        target / "addon.xml"
                    )
                except PermissionError:
                    # A legacy ADB-pushed directory can be completely
                    # unreadable to Kodi on scoped storage. The caller has
                    # already proved that this exact add-on id is absent from
                    # Kodi's database; the canonical target path is the final
                    # remaining identity boundary.
                    existing_id = addon_id
                if existing_id != addon_id:
                    raise ValueError("orphan add-on identity mismatch")
                stage = "remove-verified-orphan"
                shutil.rmtree(target)
                replaced = False
                repaired_orphan = True
        try:
            stage = "activate-candidate"
            os.replace(candidate, target)
            stage = "verify-installed-addon"
            installed_id, installed_version = _identity(target / "addon.xml")
            if installed_id != addon_id or installed_version != expected_version:
                raise ValueError("installed candidate identity mismatch")
        except Exception:
            stage = "rollback-candidate"
            shutil.rmtree(target, ignore_errors=True)
            if replaced and backup.exists():
                os.replace(backup, target)
            raise
        stage = "cleanup"
        shutil.rmtree(backup, ignore_errors=True)
        shutil.rmtree(staging, ignore_errors=True)
        return {
            "files": len(members),
            "version": expected_version,
            "repaired_orphan": repaired_orphan,
        }
    except Exception as error:
        error.apply_stage = stage
        raise


def main():
    marker = sys.argv[4] if len(sys.argv) > 4 else ""
    result = {"ok": False, "schema": 1}
    try:
        if len(sys.argv) not in {5, 6}:
            raise ValueError(
                "expected zip, add-on id, version, marker and optional repair"
            )
        repair_orphan = len(sys.argv) == 6 and sys.argv[5] == "repair-orphan"
        result.update(
            _apply(
                sys.argv[1],
                sys.argv[2],
                sys.argv[3],
                repair_orphan=repair_orphan,
            )
        )
        result["ok"] = True
    except Exception as error:  # noqa: BLE001 - report Kodi apply boundary
        result["error_type"] = type(error).__name__
        result["error_stage"] = getattr(error, "apply_stage", "unknown")
    if not marker:
        return
    Path(marker).parent.mkdir(parents=True, exist_ok=True)
    Path(marker).write_text(
        json.dumps(result, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )


if __name__ == "__main__":
    main()
