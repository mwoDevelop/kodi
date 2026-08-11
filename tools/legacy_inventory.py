#!/usr/bin/env python3
"""Read-only, secret-safe inventory of project-owned Kodi legacy formats."""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import tarfile
import tempfile
import zipfile
from pathlib import Path, PurePosixPath


MAX_JSON_BYTES = 10 * 1024 * 1024
MAX_ARCHIVE_ENTRIES = 10_000
MAX_ARCHIVE_BYTES = 512 * 1024 * 1024
OLD_WATCH_ID = "plugin.video.watchnixtoons2"
CURRENT_WATCH_ID = "plugin.video.watchnixtoons2.mwodevelop"


def _digest(payload):
    return hashlib.sha256(payload).hexdigest()


def classify_document(document, hint=""):
    if not isinstance(document, dict) or not isinstance(document.get("schema"), int):
        return None
    schema = document["schema"]
    keys = set(document)
    hint = hint.casefold()
    if "manifest.json" in hint and {"files", "installer", "snapshot_id"}.issubset(keys):
        return "disaster_recovery_snapshot", schema
    if keys == {"schema", "devices"}:
        return "device_registry", schema
    if "targets" in keys and ("kodi-reinstall" in hint or schema in {1, 2}):
        return "reinstall_config", schema
    if {"include", "exclude"}.issubset(keys) or (
        "scopes" in keys and "policy" in hint
    ):
        return "profile_policy", schema
    if keys == {"schema", "entries"} and "favourite-artwork" in hint:
        return "favourite_artwork_manifest", schema
    if "channel" in keys and "components" in keys:
        return ("stable_lock" if document.get("channel") == "stable" else "testing_lock"), schema
    if "revision_id" in keys and ("adapters" in keys or "base" in keys):
        return "profile_sync_revision", schema
    if "bundle_id" in keys and "files" in keys:
        return "portable_state", schema
    if "enrollment" in keys and "status" in keys and "profilesync" in hint:
        return "profile_sync_local_state", schema
    return None


def snapshot_has_legacy_watch(document, snapshot_root=None):
    files = document.get("files", {})
    addons = document.get("addons", [])
    if any(
        path == "addons/%s" % OLD_WATCH_ID
        or path.startswith("addons/%s/" % OLD_WATCH_ID)
        or path == "userdata/addon_data/%s" % OLD_WATCH_ID
        or path.startswith("userdata/addon_data/%s/" % OLD_WATCH_ID)
        for path in files
    ):
        return True
    if any(isinstance(item, dict) and item.get("id") == OLD_WATCH_ID for item in addons):
        return True
    if snapshot_root is not None:
        favourites = Path(snapshot_root) / "payload/userdata/favourites.xml"
        if favourites.is_file() and favourites.stat().st_size <= MAX_JSON_BYTES:
            content = favourites.read_text(encoding="utf-8", errors="replace")
            if "plugin://%s/" % OLD_WATCH_ID in content:
                return True
    return False


def _status(format_name, schema, lifecycle, legacy_content=False):
    entry = lifecycle["formats"].get(format_name)
    if entry is None:
        return "UNKNOWN"
    if schema in entry["legacy"] or legacy_content:
        return "LEGACY_QUARANTINED"
    if schema in entry["current"]:
        return "CURRENT"
    return "UNKNOWN"


def _safe_member(name):
    path = PurePosixPath(name)
    return bool(name) and not path.is_absolute() and ".." not in path.parts


def _classify_json_payload(payload, hint, lifecycle, snapshot_root=None):
    if len(payload) > MAX_JSON_BYTES:
        return None
    try:
        document = json.loads(payload.decode("utf-8"))
    except (UnicodeDecodeError, ValueError):
        return None
    classified = classify_document(document, hint=hint)
    if classified is None:
        return None
    format_name, schema = classified
    legacy_content = format_name == "disaster_recovery_snapshot" and snapshot_has_legacy_watch(
        document, snapshot_root=snapshot_root
    )
    return {
        "format": format_name,
        "schema": schema,
        "status": _status(format_name, schema, lifecycle, legacy_content),
        "sha256": _digest(payload),
    }


def _scan_archive(path, location, lifecycle):
    findings = []
    total_size = 0
    if zipfile.is_zipfile(path):
        with zipfile.ZipFile(path) as archive:
            infos = archive.infolist()
            if len(infos) > MAX_ARCHIVE_ENTRIES:
                raise ValueError("archive has too many entries")
            for info in infos:
                if not _safe_member(info.filename) or info.is_dir():
                    continue
                total_size += info.file_size
                if total_size > MAX_ARCHIVE_BYTES:
                    raise ValueError("archive expands beyond inventory limit")
                if info.filename.endswith(".json") and info.file_size <= MAX_JSON_BYTES:
                    item = _classify_json_payload(
                        archive.read(info), "%s!%s" % (location, info.filename), lifecycle
                    )
                    if item:
                        findings.append({**item, "location": "%s!%s" % (location, info.filename)})
        return findings
    if tarfile.is_tarfile(path):
        with tarfile.open(path, mode="r:*") as archive:
            members = archive.getmembers()
            if len(members) > MAX_ARCHIVE_ENTRIES:
                raise ValueError("archive has too many entries")
            for member in members:
                if not _safe_member(member.name) or not member.isfile():
                    continue
                total_size += member.size
                if total_size > MAX_ARCHIVE_BYTES:
                    raise ValueError("archive expands beyond inventory limit")
                if member.name.endswith(".json") and member.size <= MAX_JSON_BYTES:
                    handle = archive.extractfile(member)
                    if handle is None:
                        continue
                    item = _classify_json_payload(
                        handle.read(MAX_JSON_BYTES + 1), "%s!%s" % (location, member.name), lifecycle
                    )
                    if item:
                        findings.append({**item, "location": "%s!%s" % (location, member.name)})
    return findings


def scan_roots(roots, lifecycle):
    findings = []
    errors = []
    for label, root in roots:
        root = Path(root).resolve()
        if not root.exists():
            continue
        paths = [root] if root.is_file() else sorted(root.rglob("*"))
        for path in paths:
            if path.is_symlink():
                errors.append({"location": "%s/<symlink>" % label, "error": "symlink_rejected"})
                continue
            if not path.is_file():
                continue
            relative = path.name if root.is_file() else path.relative_to(root).as_posix()
            location = "%s/%s" % (label, relative)
            try:
                if path.suffix.casefold() == ".json" or path.name.endswith(".json.schema1.bak"):
                    payload = path.read_bytes()
                    item = _classify_json_payload(
                        payload,
                        location,
                        lifecycle,
                        snapshot_root=path.parent if path.name == "manifest.json" else None,
                    )
                    if item:
                        findings.append({**item, "location": location})
                elif path.suffix.casefold() in {".zip", ".tar", ".tgz", ".gz"}:
                    findings.extend(_scan_archive(path, location, lifecycle))
            except (OSError, ValueError, tarfile.TarError, zipfile.BadZipFile) as error:
                errors.append({"location": location, "error": type(error).__name__})
    return findings, errors


def _atomic_private_json(path, document):
    path = Path(path).resolve()
    path.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
    path.parent.chmod(0o700)
    descriptor, temporary = tempfile.mkstemp(prefix=".%s." % path.name, dir=path.parent)
    try:
        with os.fdopen(descriptor, "w", encoding="utf-8") as handle:
            json.dump(document, handle, indent=2, sort_keys=True)
            handle.write("\n")
            handle.flush()
            os.fsync(handle.fileno())
        os.chmod(temporary, 0o600)
        os.replace(temporary, path)
    finally:
        if os.path.exists(temporary):
            os.unlink(temporary)


def main():
    repository = Path(__file__).resolve().parents[1]
    parser = argparse.ArgumentParser()
    parser.add_argument("--root", action="append", default=[], metavar="LABEL=PATH")
    parser.add_argument("--output", default=str(repository / ".kodi-private/legacy-inventory.json"))
    parser.add_argument("--lifecycle", default=str(repository / "manifests/schema-lifecycle.json"))
    args = parser.parse_args()
    try:
        from tools.schema_lifecycle import load_lifecycle
    except ModuleNotFoundError:
        from schema_lifecycle import load_lifecycle

    roots = []
    for value in args.root:
        label, separator, raw_path = value.partition("=")
        if not separator or not label or not raw_path or "/" in label or "\\" in label:
            raise ValueError("root must use LABEL=PATH")
        roots.append((label, Path(raw_path)))
    if not roots:
        roots = [
            ("private", repository / ".kodi-private"),
            ("device-backups", repository / ".device-backups"),
            ("portable-state", repository / "portable-state"),
            ("manifests", repository / "manifests"),
        ]
    findings, errors = scan_roots(roots, load_lifecycle(args.lifecycle))
    report = {
        "schema": 1,
        "findings": sorted(findings, key=lambda item: item["location"]),
        "errors": sorted(errors, key=lambda item: item["location"]),
        "summary": {
            "current": sum(item["status"] == "CURRENT" for item in findings),
            "legacy_quarantined": sum(item["status"] == "LEGACY_QUARANTINED" for item in findings),
            "unknown": sum(item["status"] == "UNKNOWN" for item in findings),
        },
    }
    _atomic_private_json(args.output, report)
    print(json.dumps(report["summary"], sort_keys=True))
    return 2 if report["summary"]["unknown"] or errors else 0


if __name__ == "__main__":
    raise SystemExit(main())
