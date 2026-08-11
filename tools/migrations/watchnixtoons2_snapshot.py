#!/usr/bin/env python3
"""Create a current, verified snapshot from legacy WatchNixtoons2 content."""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import shutil
import sys
import tempfile
import xml.etree.ElementTree as ET
from datetime import datetime, timezone
from pathlib import Path


OLD_ID = "plugin.video.watchnixtoons2"
CURRENT_ID = "plugin.video.watchnixtoons2.mwodevelop"
CURRENT_ORIGIN = "repository.mwodevelop"
REPOSITORY_ROOT = Path(__file__).resolve().parents[2]
if str(REPOSITORY_ROOT) not in sys.path:
    sys.path.insert(0, str(REPOSITORY_ROOT))


def _canonical_json(value):
    return json.dumps(
        value, sort_keys=True, separators=(",", ":"), ensure_ascii=False
    ).encode("utf-8")


def _digest(payload):
    return hashlib.sha256(payload).hexdigest()


def _inventory(payload_root):
    result = {}
    for path in sorted(payload_root.rglob("*")):
        if path.is_symlink():
            raise ValueError("snapshot payload cannot contain links")
        if path.is_file():
            payload = path.read_bytes()
            result[path.relative_to(payload_root).as_posix()] = {
                "sha256": _digest(payload),
                "size": len(payload),
            }
    return result


def _snapshot_identity(manifest):
    return {
        key: manifest[key]
        for key in (
            "schema",
            "policy_sha256",
            "device",
            "selected_skin",
            "addons",
            "files",
            "installer",
        )
    }


def _copy_current_addon(source, target):
    if not (source / "addon.xml").is_file():
        raise ValueError("current WatchNixtoons2 source has no addon.xml")
    root = ET.parse(source / "addon.xml").getroot()
    if root.attrib.get("id") != CURRENT_ID or not root.attrib.get("version"):
        raise ValueError("current WatchNixtoons2 source has invalid identity")
    shutil.copytree(
        source,
        target,
        ignore=shutil.ignore_patterns(".git", "__pycache__", "*.pyc"),
    )
    return root.attrib["version"]


def _migrate_addon_data(payload_root):
    old = payload_root / "userdata/addon_data" / OLD_ID
    current = payload_root / "userdata/addon_data" / CURRENT_ID
    migrated = 0
    if not old.exists():
        return migrated
    if old.is_symlink() or current.exists():
        raise ValueError("WatchNixtoons2 add-on data cannot be merged safely")
    old.rename(current)
    for path in current.rglob("*"):
        if path.is_symlink():
            raise ValueError("WatchNixtoons2 add-on data contains a link")
        if not path.is_file() or path.stat().st_size > 10 * 1024 * 1024:
            continue
        payload = path.read_bytes()
        try:
            text = payload.decode("utf-8")
        except UnicodeDecodeError:
            continue
        replaced = text.replace(OLD_ID, CURRENT_ID)
        if replaced != text:
            path.write_text(replaced, encoding="utf-8")
            migrated += 1
    return migrated


def migrate_snapshot(source, output, current_addon, opener=None):
    source = Path(source).resolve()
    output = Path(output).resolve()
    current_addon = Path(current_addon).resolve()
    if output.exists():
        raise ValueError("migrated snapshot output already exists")
    try:
        from tools.kodi_profile import secure_private_tree, verify_snapshot
        from tools.favourite_artwork import materialize
        from tools.legacy_inventory import snapshot_has_legacy_watch
    except ModuleNotFoundError:
        from kodi_profile import secure_private_tree, verify_snapshot
        from favourite_artwork import materialize
        from legacy_inventory import snapshot_has_legacy_watch

    original = verify_snapshot(source)
    if not snapshot_has_legacy_watch(original, source):
        raise ValueError("snapshot has no legacy WatchNixtoons2 content")
    output.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
    temporary = Path(tempfile.mkdtemp(prefix=".watch-migration-", dir=output.parent))
    try:
        shutil.copytree(source, temporary, dirs_exist_ok=True, symlinks=True)
        payload_root = temporary / "payload"
        old_origins = {
            item.get("origin")
            for item in original.get("addons", [])
            if isinstance(item, dict)
            and item.get("id") == OLD_ID
            and isinstance(item.get("origin"), str)
            and item.get("origin", "").startswith("repository.")
        }
        removed = []
        removal_targets = [
            ("addons", addon_id) for addon_id in sorted({OLD_ID} | old_origins)
        ] + [
            ("userdata/addon_data", addon_id) for addon_id in sorted(old_origins)
        ]
        for relative, addon_id in removal_targets:
            path = payload_root / relative / addon_id
            if path.is_symlink():
                raise ValueError("legacy add-on path cannot be a link")
            if path.exists():
                shutil.rmtree(path)
                removed.append("%s/%s" % (relative, addon_id))
        migrated_data = _migrate_addon_data(payload_root)
        current_target = payload_root / "addons" / CURRENT_ID
        if current_target.exists():
            shutil.rmtree(current_target)
        version = _copy_current_addon(current_addon, current_target)
        favourites = payload_root / "userdata/favourites.xml"
        artwork = payload_root / "userdata/favourite-artwork"
        artwork_result = materialize(favourites, artwork, opener=opener)
        addons = [
            item
            for item in original.get("addons", [])
            if item.get("id") not in ({OLD_ID} | old_origins)
        ]
        addons = [item for item in addons if item.get("id") != CURRENT_ID]
        addons.append(
            {
                "id": CURRENT_ID,
                "version": version,
                "enabled": True,
                "origin": CURRENT_ORIGIN,
            }
        )
        addons.sort(key=lambda item: item.get("id", ""))
        manifest = dict(original)
        manifest["addons"] = addons
        manifest["files"] = _inventory(payload_root)
        manifest["migrated_from"] = original["snapshot_id"]
        manifest["created_utc"] = datetime.now(timezone.utc).isoformat()
        manifest["snapshot_id"] = _digest(_canonical_json(_snapshot_identity(manifest)))
        (temporary / "manifest.json").write_bytes(_canonical_json(manifest) + b"\n")
        evidence = {
            "schema": 1,
            "migration": "watchnixtoons2",
            "migrated_from": original["snapshot_id"],
            "snapshot_id": manifest["snapshot_id"],
            "removed_paths": removed,
            "migrated_addon_data_files": migrated_data,
            "artwork": artwork_result,
        }
        (temporary / "migration-evidence.json").write_bytes(_canonical_json(evidence) + b"\n")
        secure_private_tree(temporary)
        verify_snapshot(temporary)
        if snapshot_has_legacy_watch(manifest, temporary):
            raise RuntimeError("migrated snapshot still contains legacy WatchNixtoons2")
        temporary.rename(output)
        return manifest, evidence
    except BaseException:
        shutil.rmtree(temporary, ignore_errors=True)
        raise


def main():
    repository = Path(__file__).resolve().parents[2]
    parser = argparse.ArgumentParser()
    parser.add_argument("source")
    parser.add_argument("output")
    parser.add_argument(
        "--current-addon",
        default=str(
            repository
            / "watchnixtoons2/mwodevelop/plugin.video.watchnixtoons2.mwodevelop"
        ),
    )
    args = parser.parse_args()
    manifest, evidence = migrate_snapshot(args.source, args.output, args.current_addon)
    print(json.dumps({"snapshot_id": manifest["snapshot_id"], "migrated_from": evidence["migrated_from"]}, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
