#!/usr/bin/env python3
"""Build, validate and atomically apply portable Kodi user-state bundles."""

from __future__ import annotations

import hashlib
import json
import os
import re
import shutil
import sys
import tempfile
import xml.etree.ElementTree as ET
import zipfile
from pathlib import Path, PurePosixPath


SCHEMA = 1
ADAPTER_ID = "kodi.favourites"
ARTWORK_URI = "special://profile/favourite-artwork/"
STATE_NAME = ".mwodevelop-portable-state.json"
JOURNAL_NAME = ".mwodevelop-portable-state-journal.json"
STAGE_NAME = ".mwodevelop-portable-state-stage"
BACKUP_NAME = ".mwodevelop-portable-state-backup"
MAX_FAVOURITES = 500
MAX_FILE_BYTES = 5 * 1024 * 1024
MAX_BUNDLE_BYTES = 64 * 1024 * 1024
SAFE_ARTWORK = re.compile(r"^[a-f0-9]{64}\.(?:gif|jpg|png|webp)$")
MANAGED_ROOTS = ("favourites.xml", "favourite-artwork")


def canonical_json(value):
    return json.dumps(
        value, sort_keys=True, separators=(",", ":"), ensure_ascii=False
    ).encode("utf-8")


def digest(payload):
    return hashlib.sha256(payload).hexdigest()


def _atomic_write(path, payload):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    descriptor, temporary = tempfile.mkstemp(
        prefix=".%s." % path.name, dir=str(path.parent)
    )
    try:
        with os.fdopen(descriptor, "wb") as handle:
            handle.write(payload)
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(temporary, path)
    finally:
        if os.path.exists(temporary):
            os.unlink(temporary)


def _safe_artwork_name(uri):
    if not isinstance(uri, str) or not uri.startswith(ARTWORK_URI):
        return None
    relative = uri[len(ARTWORK_URI) :]
    if not SAFE_ARTWORK.fullmatch(relative):
        raise ValueError("favourite references unsafe portable artwork")
    return relative


def validate_favourites(payload):
    if not payload or len(payload) > MAX_FILE_BYTES:
        raise ValueError("favourites.xml has an invalid size")
    try:
        root = ET.fromstring(payload)
    except ET.ParseError as error:
        raise ValueError("favourites.xml is not valid XML") from error
    if root.tag != "favourites" or any(
        node.tag != "favourite" for node in list(root)
    ):
        raise ValueError("favourites.xml has an invalid root")
    nodes = root.findall("favourite")
    if len(nodes) > MAX_FAVOURITES:
        raise ValueError("favourites.xml contains too many entries")
    artwork = set()
    for node in nodes:
        if set(node.attrib).difference({"name", "thumb"}):
            raise ValueError("favourite contains unsupported attributes")
        name = node.attrib.get("name", "")
        thumb = node.attrib.get("thumb", "")
        action = node.text or ""
        if (
            not name
            or len(name) > 1024
            or len(thumb) > 8192
            or not action
            or len(action) > 16384
        ):
            raise ValueError("favourite contains an invalid field")
        artwork_name = _safe_artwork_name(thumb)
        if artwork_name:
            artwork.add(artwork_name)
    return root, artwork


def _file_record(path, relative):
    payload = Path(path).read_bytes()
    if not payload or len(payload) > MAX_FILE_BYTES:
        raise ValueError("%s has an invalid size" % relative)
    return {
        "path": relative,
        "sha256": digest(payload),
        "size": len(payload),
    }, payload


def _safe_managed_relative(relative):
    path = PurePosixPath(str(relative))
    return relative == "favourites.xml" or (
        len(path.parts) == 2
        and path.parts[0] == "favourite-artwork"
        and (
            SAFE_ARTWORK.fullmatch(path.parts[1])
            or path.parts[1] == "manifest.json"
        )
    )


def _identity(files):
    return {
        "schema": SCHEMA,
        "adapters": {
            ADAPTER_ID: {
                "apply_mode": "next_start",
                "files": files,
            }
        },
    }


def build_bundle(profile_root, output):
    profile_root = Path(profile_root).resolve()
    output = Path(output).resolve()
    favourites = profile_root / "favourites.xml"
    if favourites.is_symlink() or not favourites.is_file():
        raise ValueError("Kodi profile has no regular favourites.xml")
    favourite_payload = favourites.read_bytes()
    _root, artwork_names = validate_favourites(favourite_payload)
    records = []
    payloads = {}
    record = {
        "path": "favourites.xml",
        "sha256": digest(favourite_payload),
        "size": len(favourite_payload),
    }
    records.append(record)
    payloads["favourites.xml"] = favourite_payload
    artwork_root = profile_root / "favourite-artwork"
    for name in sorted(artwork_names):
        path = artwork_root / name
        if path.is_symlink() or not path.is_file():
            raise ValueError("portable favourite artwork is missing: %s" % name)
        record, payload = _file_record(
            path, "favourite-artwork/%s" % name
        )
        if record["sha256"] != name.split(".", 1)[0]:
            raise ValueError("portable favourite artwork digest differs from name")
        records.append(record)
        payloads[record["path"]] = payload
    source_manifest = artwork_root / "manifest.json"
    if source_manifest.is_file() and not source_manifest.is_symlink():
        record, payload = _file_record(
            source_manifest, "favourite-artwork/manifest.json"
        )
        try:
            document = json.loads(payload.decode("utf-8"))
        except (UnicodeDecodeError, ValueError) as error:
            raise ValueError("favourite artwork manifest is invalid") from error
        if (
            not isinstance(document, dict)
            or document.get("schema") != 1
            or not isinstance(document.get("entries"), dict)
        ):
            raise ValueError("favourite artwork manifest is invalid")
        records.append(record)
        payloads[record["path"]] = payload
    identity = _identity(records)
    manifest = {
        **identity,
        "bundle_id": "sha256:" + digest(canonical_json(identity)),
    }
    output.parent.mkdir(parents=True, exist_ok=True)
    descriptor, temporary = tempfile.mkstemp(
        prefix=".%s." % output.name, dir=str(output.parent)
    )
    os.close(descriptor)
    try:
        with zipfile.ZipFile(
            temporary, "w", compression=zipfile.ZIP_DEFLATED
        ) as archive:
            for relative, payload in sorted(payloads.items()):
                info = zipfile.ZipInfo("payload/" + relative)
                info.date_time = (1980, 1, 1, 0, 0, 0)
                info.compress_type = zipfile.ZIP_DEFLATED
                info.external_attr = 0o600 << 16
                archive.writestr(info, payload)
            info = zipfile.ZipInfo("manifest.json")
            info.date_time = (1980, 1, 1, 0, 0, 0)
            info.compress_type = zipfile.ZIP_DEFLATED
            info.external_attr = 0o600 << 16
            archive.writestr(info, canonical_json(manifest) + b"\n")
        if os.path.getsize(temporary) > MAX_BUNDLE_BYTES:
            raise ValueError("portable-state bundle is too large")
        os.replace(temporary, output)
    finally:
        if os.path.exists(temporary):
            os.unlink(temporary)
    return manifest


def _validate_manifest(document):
    if not isinstance(document, dict) or set(document) != {
        "schema",
        "bundle_id",
        "adapters",
    }:
        raise ValueError("portable-state manifest has invalid fields")
    if document.get("schema") != SCHEMA:
        raise ValueError("unsupported portable-state schema")
    adapters = document.get("adapters")
    if not isinstance(adapters, dict) or set(adapters) != {ADAPTER_ID}:
        raise ValueError("portable-state manifest has unsupported adapters")
    adapter = adapters[ADAPTER_ID]
    if (
        not isinstance(adapter, dict)
        or set(adapter) != {"apply_mode", "files"}
        or adapter["apply_mode"] != "next_start"
        or not isinstance(adapter["files"], list)
    ):
        raise ValueError("portable-state adapter contract mismatch")
    files = adapter["files"]
    if not files or len(files) > MAX_FAVOURITES + 2:
        raise ValueError("portable-state file inventory is invalid")
    seen = set()
    for item in files:
        if not isinstance(item, dict) or set(item) != {
            "path",
            "sha256",
            "size",
        }:
            raise ValueError("portable-state file record is invalid")
        relative = item["path"]
        if (
            not _safe_managed_relative(relative)
            or relative in seen
            or not re.fullmatch(r"[a-f0-9]{64}", str(item["sha256"]))
            or not isinstance(item["size"], int)
            or not 0 < item["size"] <= MAX_FILE_BYTES
        ):
            raise ValueError("portable-state file record is unsafe")
        seen.add(relative)
    if "favourites.xml" not in seen:
        raise ValueError("portable-state bundle has no favourites.xml")
    identity = _identity(files)
    expected = "sha256:" + digest(canonical_json(identity))
    if document.get("bundle_id") != expected:
        raise ValueError("portable-state bundle id mismatch")
    return files


def validate_bundle(bundle):
    bundle = Path(bundle)
    if not bundle.is_file() or bundle.stat().st_size > MAX_BUNDLE_BYTES:
        raise ValueError("portable-state bundle is missing or too large")
    with zipfile.ZipFile(bundle, "r") as archive:
        archive_names = archive.namelist()
        if len(archive_names) != len(set(archive_names)):
            raise ValueError("portable-state archive contains duplicate files")
        if "manifest.json" not in archive_names:
            raise ValueError("portable-state bundle has no manifest")
        manifest_payload = archive.read("manifest.json")
        if len(manifest_payload) > MAX_FILE_BYTES:
            raise ValueError("portable-state manifest is too large")
        document = json.loads(manifest_payload.decode("utf-8"))
        files = _validate_manifest(document)
        expected_names = {"manifest.json"} | {
            "payload/" + item["path"] for item in files
        }
        if set(archive_names) != expected_names:
            raise ValueError("portable-state archive inventory mismatch")
        favourite_payload = None
        for item in files:
            info = archive.getinfo("payload/" + item["path"])
            if info.file_size != item["size"] or info.file_size > MAX_FILE_BYTES:
                raise ValueError("portable-state file size mismatch")
            payload = archive.read(info)
            if digest(payload) != item["sha256"]:
                raise ValueError("portable-state file digest mismatch")
            if item["path"] == "favourites.xml":
                favourite_payload = payload
        _root, referenced = validate_favourites(favourite_payload)
        available = {
            PurePosixPath(item["path"]).name
            for item in files
            if item["path"].startswith("favourite-artwork/")
            and item["path"] != "favourite-artwork/manifest.json"
        }
        if referenced != available:
            raise ValueError("portable-state artwork inventory is not exact")
    return document


def _remove_known(path):
    path = Path(path)
    if path.is_symlink() or path.is_file():
        path.unlink()
    elif path.is_dir():
        shutil.rmtree(path)


def _write_journal(path, document):
    _atomic_write(path, canonical_json(document) + b"\n")


def recover(profile_root):
    profile_root = Path(profile_root).resolve()
    journal_path = profile_root / JOURNAL_NAME
    if not journal_path.is_file():
        return False
    document = json.loads(journal_path.read_text(encoding="utf-8"))
    if (
        not isinstance(document, dict)
        or document.get("schema") != SCHEMA
        or set(document).difference(
            {"schema", "bundle_id", "phase", "had_favourites", "had_artwork"}
        )
    ):
        raise ValueError("portable-state apply journal is invalid")
    backup = profile_root / BACKUP_NAME
    for name, had_key in (
        ("favourites.xml", "had_favourites"),
        ("favourite-artwork", "had_artwork"),
    ):
        target = profile_root / name
        saved = backup / name
        _remove_known(target)
        if document.get(had_key) and saved.exists():
            os.replace(saved, target)
    _remove_known(profile_root / STAGE_NAME)
    _remove_known(backup)
    journal_path.unlink()
    return True


def _favourites_semantics(payload):
    root, _artwork = validate_favourites(payload)
    def action(value):
        value = (value or "").strip()
        if "plugin.video.watchnixtoons2.mwodevelop" in value:
            operations = sorted(set(re.findall(r"action[A-Za-z]+", value)))
            return "plugin.video.watchnixtoons2.mwodevelop|%s" % ",".join(
                operations
            )
        return value

    return [
        (
            node.attrib.get("name", ""),
            node.attrib.get("thumb", ""),
            action(node.text),
        )
        for node in root.findall("favourite")
    ]


def _semantic_digests(items):
    return [digest(canonical_json(list(item))) for item in items]


def _match_details(profile_root, manifest, bundle):
    profile_root = Path(profile_root)
    mismatched = []
    semantic_difference = None
    for item in manifest["adapters"][ADAPTER_ID]["files"]:
        # The refresh manifest contains per-device observation metadata and
        # may be rewritten after startup. Favourites and content-addressed
        # artwork bytes remain the deterministic convergence boundary.
        if item["path"] == "favourite-artwork/manifest.json":
            continue
        path = profile_root.joinpath(*PurePosixPath(item["path"]).parts)
        differs = (
            not path.is_file()
            or path.is_symlink()
            or path.stat().st_size != item["size"]
            or digest(path.read_bytes()) != item["sha256"]
        )
        if differs and item["path"] == "favourites.xml" and path.is_file():
            with zipfile.ZipFile(bundle, "r") as archive:
                expected = archive.read("payload/favourites.xml")
            observed_semantics = _favourites_semantics(path.read_bytes())
            expected_semantics = _favourites_semantics(expected)
            differs = observed_semantics != expected_semantics
            if differs:
                expected_root, _ = validate_favourites(expected)
                observed_root, _ = validate_favourites(path.read_bytes())
                def action_shapes(root):
                    return [
                        {
                            "current_addon": "plugin.video.watchnixtoons2.mwodevelop"
                            in (node.text or ""),
                            "operations": sorted(
                                set(re.findall(r"action[A-Za-z]+", node.text or ""))
                            ),
                            "length": len(node.text or ""),
                        }
                        for node in root.findall("favourite")
                    ]
                semantic_difference = {
                    "expected": _semantic_digests(expected_semantics),
                    "observed": _semantic_digests(observed_semantics),
                    "fields": {
                        field: {
                            "expected": [digest(value.encode("utf-8")) for value in values],
                            "observed": [digest(value.encode("utf-8")) for value in observed_values],
                        }
                        for field, values, observed_values in (
                            (
                                "name",
                                [item[0] for item in expected_semantics],
                                [item[0] for item in observed_semantics],
                            ),
                            (
                                "thumb",
                                [item[1] for item in expected_semantics],
                                [item[1] for item in observed_semantics],
                            ),
                            (
                                "action",
                                [item[2] for item in expected_semantics],
                                [item[2] for item in observed_semantics],
                            ),
                        )
                    },
                    "action_shapes": {
                        "expected": action_shapes(expected_root),
                        "observed": action_shapes(observed_root),
                    },
                }
        if differs:
            mismatched.append(item["path"])
    expected_artwork = {
        PurePosixPath(item["path"]).name
        for item in manifest["adapters"][ADAPTER_ID]["files"]
        if item["path"].startswith("favourite-artwork/")
        and item["path"] != "favourite-artwork/manifest.json"
    }
    artwork_root = profile_root / "favourite-artwork"
    observed = (
        {
            path.name
            for path in artwork_root.iterdir()
            if path.is_file()
            and not path.is_symlink()
            and path.name != "manifest.json"
        }
        if artwork_root.is_dir()
        else set()
    )
    return {
        "matches": not mismatched and observed == expected_artwork,
        "mismatched_paths": mismatched,
        "missing_artwork": sorted(expected_artwork.difference(observed)),
        "unexpected_artwork": sorted(observed.difference(expected_artwork)),
        **(
            {"favourites_semantic_digests": semantic_difference}
            if semantic_difference is not None
            else {}
        ),
    }


def _matches(profile_root, manifest, bundle):
    return _match_details(profile_root, manifest, bundle)["matches"]


def apply_bundle(profile_root, bundle):
    profile_root = Path(profile_root).resolve()
    profile_root.mkdir(parents=True, exist_ok=True)
    recovered = recover(profile_root)
    manifest = validate_bundle(bundle)
    if _matches(profile_root, manifest, bundle):
        _atomic_write(
            profile_root / STATE_NAME, canonical_json(manifest) + b"\n"
        )
        return {
            "status": "NO_CHANGE",
            "bundle_id": manifest["bundle_id"],
            "recovered": recovered,
        }
    stage = profile_root / STAGE_NAME
    backup = profile_root / BACKUP_NAME
    _remove_known(stage)
    _remove_known(backup)
    stage.mkdir(mode=0o700)
    backup.mkdir(mode=0o700)
    with zipfile.ZipFile(bundle, "r") as archive:
        for item in manifest["adapters"][ADAPTER_ID]["files"]:
            target = stage.joinpath(*PurePosixPath(item["path"]).parts)
            target.parent.mkdir(parents=True, exist_ok=True)
            _atomic_write(target, archive.read("payload/" + item["path"]))
    had_favourites = (profile_root / "favourites.xml").exists()
    had_artwork = (profile_root / "favourite-artwork").exists()
    journal = {
        "schema": SCHEMA,
        "bundle_id": manifest["bundle_id"],
        "phase": "prepared",
        "had_favourites": had_favourites,
        "had_artwork": had_artwork,
    }
    journal_path = profile_root / JOURNAL_NAME
    _write_journal(journal_path, journal)
    try:
        for name in MANAGED_ROOTS:
            current = profile_root / name
            if current.exists():
                os.replace(current, backup / name)
        journal["phase"] = "backed_up"
        _write_journal(journal_path, journal)
        os.replace(stage / "favourites.xml", profile_root / "favourites.xml")
        artwork_stage = stage / "favourite-artwork"
        if artwork_stage.exists():
            os.replace(artwork_stage, profile_root / "favourite-artwork")
        else:
            (profile_root / "favourite-artwork").mkdir(mode=0o700)
        journal["phase"] = "installed"
        _write_journal(journal_path, journal)
        if not _matches(profile_root, manifest, bundle):
            raise RuntimeError("portable-state post-apply health check failed")
    except Exception:
        recover(profile_root)
        raise
    _remove_known(stage)
    _remove_known(backup)
    journal_path.unlink()
    _atomic_write(profile_root / STATE_NAME, canonical_json(manifest) + b"\n")
    return {
        "status": "APPLIED",
        "bundle_id": manifest["bundle_id"],
        "recovered": recovered,
    }


def profile_summary(profile_root):
    profile_root = Path(profile_root)
    favourites = profile_root / "favourites.xml"
    if not favourites.is_file():
        return {"favourites": 0, "watchnixtoons2": 0, "portable": 0}
    payload = favourites.read_bytes()
    root, artwork_names = validate_favourites(payload)
    watch = [
        node
        for node in root.findall("favourite")
        if "watchnixtoons2" in (node.text or "").casefold()
    ]
    missing_files = [
        name
        for name in sorted(artwork_names)
        if not (profile_root / "favourite-artwork" / name).is_file()
    ]
    artwork_root = profile_root / "favourite-artwork"
    artwork_inventory = (
        sorted(
            path.name
            for path in artwork_root.iterdir()
            if path.is_file()
            and not path.is_symlink()
            and SAFE_ARTWORK.fullmatch(path.name)
        )
        if artwork_root.is_dir()
        else []
    )
    return {
        "favourites": len(root.findall("favourite")),
        "watchnixtoons2": len(watch),
        "portable": sum(
            bool(_safe_artwork_name(node.attrib.get("thumb", "")))
            for node in watch
        ),
        "current_watch_actions": sum(
            "plugin.video.watchnixtoons2.mwodevelop"
            in (node.text or "")
            for node in watch
        ),
        "favourites_sha256": digest(payload),
        "favourites_semantic_sha256": digest(
            canonical_json(_favourites_semantics(payload))
        ),
        "artwork_inventory_sha256": digest(canonical_json(artwork_inventory)),
        "missing_artwork_files": missing_files,
    }


def _write_marker(path, document):
    _atomic_write(path, canonical_json(document) + b"\n")


def main():
    if len(sys.argv) < 4:
        raise SystemExit(
            "usage: kodi_portable_state.py MODE PROFILE MARKER [BUNDLE]"
        )
    mode, profile_arg, marker = sys.argv[1:4]
    try:
        try:
            import xbmcvfs

            profile = xbmcvfs.translatePath(profile_arg)
        except ImportError:
            profile = profile_arg
        if mode == "probe":
            result = profile_summary(profile)
        elif mode == "export" and len(sys.argv) == 5:
            result = build_bundle(profile, sys.argv[4])
        elif mode == "apply" and len(sys.argv) == 5:
            result = apply_bundle(profile, sys.argv[4])
        elif mode == "verify" and len(sys.argv) == 5:
            result = _match_details(
                profile, validate_bundle(sys.argv[4]), sys.argv[4]
            )
        else:
            raise ValueError("invalid portable-state mode or arguments")
        _write_marker(marker, {"ok": True, **result})
    except Exception as error:
        _write_marker(
            marker,
            {
                "ok": False,
                "error_type": type(error).__name__,
                "error": str(error)[:500],
            },
        )


if __name__ == "__main__":
    main()
