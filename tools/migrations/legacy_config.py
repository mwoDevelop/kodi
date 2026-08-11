#!/usr/bin/env python3
"""Recoverable offline migration of schema 1 registry/reinstall documents."""

from __future__ import annotations

import argparse
import copy
import hashlib
import json
import os
import re
import sys
import tempfile
from pathlib import Path


LOGICAL_ID = re.compile(r"^[a-z0-9][a-z0-9._-]{0,63}$")
PLATFORMS = {"android", "android-emulator"}
JOURNAL_SCHEMA = 1
REPOSITORY_ROOT = Path(__file__).resolve().parents[2]
if str(REPOSITORY_ROOT) not in sys.path:
    sys.path.insert(0, str(REPOSITORY_ROOT))


def _canonical_json(document):
    return json.dumps(
        document, sort_keys=True, separators=(",", ":"), ensure_ascii=False
    ).encode("utf-8")


def _digest(payload):
    return hashlib.sha256(payload).hexdigest()


def _document_digest(document):
    return _digest(_canonical_json(document))


def _read_json(path):
    return json.loads(Path(path).read_text(encoding="utf-8"))


def _fsync_directory(path):
    descriptor = os.open(str(path), os.O_RDONLY)
    try:
        os.fsync(descriptor)
    finally:
        os.close(descriptor)


def _atomic_json(path, document):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
    path.parent.chmod(0o700)
    descriptor, temporary = tempfile.mkstemp(
        prefix=".%s." % path.name, dir=str(path.parent), text=True
    )
    try:
        with os.fdopen(descriptor, "w", encoding="utf-8") as handle:
            handle.write(json.dumps(document, indent=2, sort_keys=True) + "\n")
            handle.flush()
            os.fsync(handle.fileno())
        os.chmod(temporary, 0o600)
        os.replace(temporary, path)
        _fsync_directory(path.parent)
    finally:
        if os.path.exists(temporary):
            os.unlink(temporary)
    path.chmod(0o600)


def _default_principal(logical_id):
    value = hashlib.sha256(logical_id.encode("utf-8")).hexdigest()[:16]
    return "principal-%s" % value


def _kodi_major(value):
    match = re.match(r"^(\d+)", str(value))
    if not match:
        raise ValueError("invalid Kodi version: %r" % value)
    return int(match.group(1))


def _legacy_target_device(target, publishers, platforms):
    logical_id = target.get("name")
    if not isinstance(logical_id, str) or not LOGICAL_ID.fullmatch(logical_id):
        raise ValueError("target name is not a valid logical device id")
    serial = target.get("serial")
    model = target.get("expected_model")
    if not isinstance(serial, str) or not serial:
        raise ValueError("%s has no ADB endpoint" % logical_id)
    if not isinstance(model, str) or not model:
        raise ValueError("%s has no expected model" % logical_id)
    platform = platforms.get(logical_id, "android")
    if platform not in PLATFORMS:
        raise ValueError("legacy ADB target cannot migrate to %s" % platform)
    roles = ["consumer"]
    if logical_id in publishers:
        roles.append("publisher")
    return logical_id, {
        "display_name": logical_id,
        "physical_host_id": logical_id,
        "principal_id": _default_principal(logical_id),
        "platform": platform,
        "roles": roles,
        "expected": {
            "model": model,
            "kodi_major": _kodi_major(target.get("expected_kodi_version")),
        },
        "endpoints": {"adb": serial},
        "profile_channel": "home-stable",
    }


def _validate_current_registry(document):
    if document.get("schema") != 2 or not isinstance(document.get("devices"), dict):
        raise ValueError("device registry must use schema 2")
    try:
        from tools.kodi_devices import validate_registry
    except ModuleNotFoundError:
        from kodi_devices import validate_registry
    validate_registry(document)


def _same_canonical_target(existing, proposed):
    return (
        existing.get("platform") == proposed["platform"]
        and existing.get("endpoints", {}).get("adb")
        == proposed["endpoints"]["adb"]
        and existing.get("expected", {}).get("model")
        == proposed["expected"]["model"]
        and existing.get("expected", {}).get("kodi_major")
        == proposed["expected"]["kodi_major"]
    )


def build_migration(config_document, devices_document, repository, devices_path, publishers=(), platforms=None):
    if config_document.get("schema") == 2:
        if devices_document is None:
            raise ValueError("schema 2 reinstall config requires a device registry")
        _validate_current_registry(devices_document)
        return copy.deepcopy(devices_document), copy.deepcopy(config_document), False
    if config_document.get("schema") != 1 or not isinstance(config_document.get("targets"), list):
        raise ValueError("migration requires reinstall schema 1 or an already current pair")

    publisher_set = set(publishers)
    platform_map = dict(platforms or {})
    existing = {} if devices_document is None else copy.deepcopy(devices_document.get("devices", {}))
    if devices_document is not None:
        _validate_current_registry(devices_document)
    migrated_targets = []
    seen = set()
    for target in config_document["targets"]:
        if not isinstance(target, dict):
            raise ValueError("legacy reinstall target must be an object")
        logical_id, proposed = _legacy_target_device(target, publisher_set, platform_map)
        if logical_id in seen:
            raise ValueError("duplicate logical device: %s" % logical_id)
        seen.add(logical_id)
        if logical_id in existing:
            if not _same_canonical_target(existing[logical_id], proposed):
                raise ValueError("device registry conflicts with reinstall target: %s" % logical_id)
            roles = set(existing[logical_id]["roles"])
            roles.update(proposed["roles"])
            existing[logical_id]["roles"] = sorted(roles, key=lambda item: (item != "consumer", item))
        else:
            existing[logical_id] = proposed
        migrated = {
            key: copy.deepcopy(value)
            for key, value in target.items()
            if key not in {"name", "serial", "expected_model"}
        }
        migrated["logical_device_id"] = logical_id
        migrated_targets.append(migrated)
    unknown_publishers = sorted(publisher_set.difference(seen))
    unknown_platforms = sorted(set(platform_map).difference(seen))
    if unknown_publishers:
        raise ValueError("unknown publisher devices: %s" % ", ".join(unknown_publishers))
    if unknown_platforms:
        raise ValueError("platform override references unknown devices: %s" % ", ".join(unknown_platforms))
    registry = {"schema": 2, "devices": existing}
    _validate_current_registry(registry)
    repository = Path(repository).resolve()
    try:
        relative_devices = Path(devices_path).resolve().relative_to(repository).as_posix()
    except ValueError as error:
        raise ValueError("devices inventory must be below repository") from error
    migrated_config = {
        key: copy.deepcopy(value)
        for key, value in config_document.items()
        if key not in {"schema", "targets", "devices_file"}
    }
    migrated_config.update(
        {"schema": 2, "devices_file": relative_devices, "targets": migrated_targets}
    )
    return registry, migrated_config, True


def _journal_path(config_path):
    return Path(config_path).with_name(".%s.legacy-migration-journal.json" % Path(config_path).name)


def _backup(path, document, suffix):
    backup = Path(path).with_suffix(Path(path).suffix + suffix)
    if backup.exists():
        if _read_json(backup) != document:
            raise FileExistsError("migration backup differs from input: %s" % backup.name)
    else:
        _atomic_json(backup, document)
    return backup


def _current_digest(path):
    path = Path(path)
    if not path.exists():
        return None
    return _document_digest(_read_json(path))


def _commit_target(path, before_digest, after_document):
    current = _current_digest(path)
    after_digest = _document_digest(after_document)
    if current == after_digest:
        return
    if current != before_digest:
        raise RuntimeError("migration target changed concurrently: %s" % Path(path).name)
    _atomic_json(path, after_document)


def _resume_transaction(journal_path, fail_after=None):
    journal = _read_json(journal_path)
    if journal.get("schema") != JOURNAL_SCHEMA:
        raise ValueError("unsupported legacy migration journal")
    config_path = Path(journal["config_path"])
    devices_path = Path(journal["devices_path"])
    phase = journal["phase"]
    if phase == "prepared":
        _commit_target(devices_path, journal["devices_before_sha256"], journal["devices_after"])
        journal["phase"] = "devices_committed"
        _atomic_json(journal_path, journal)
        if fail_after == "devices":
            raise RuntimeError("injected failure after devices commit")
        phase = journal["phase"]
    if phase == "devices_committed":
        _commit_target(config_path, journal["config_before_sha256"], journal["config_after"])
        journal["phase"] = "config_committed"
        _atomic_json(journal_path, journal)
        if fail_after == "config":
            raise RuntimeError("injected failure after config commit")
        phase = journal["phase"]
    if phase != "config_committed":
        raise ValueError("invalid legacy migration journal phase")
    if _current_digest(devices_path) != _document_digest(journal["devices_after"]):
        raise RuntimeError("migrated registry verification failed")
    if _current_digest(config_path) != _document_digest(journal["config_after"]):
        raise RuntimeError("migrated reinstall verification failed")
    journal_path.unlink()
    _fsync_directory(journal_path.parent)
    return journal["devices_after"], journal["config_after"]


def migrate_config_pair(config_path, devices_path, repository, publishers=(), platforms=None, apply=False, fail_after=None):
    config_path = Path(config_path).resolve()
    devices_path = Path(devices_path).resolve()
    journal_path = _journal_path(config_path)
    if journal_path.exists():
        if not apply:
            raise RuntimeError("an interrupted migration requires --apply recovery")
        devices, config = _resume_transaction(journal_path, fail_after=fail_after)
        return devices, config, True
    config_document = _read_json(config_path)
    devices_document = _read_json(devices_path) if devices_path.exists() else None
    registry, config, changed = build_migration(
        config_document,
        devices_document,
        repository,
        devices_path,
        publishers=publishers,
        platforms=platforms,
    )
    if not changed or not apply:
        return registry, config, changed
    _backup(config_path, config_document, ".schema1.bak")
    if devices_document is not None:
        _backup(devices_path, devices_document, ".pre-legacy-migration.bak")
    journal = {
        "schema": JOURNAL_SCHEMA,
        "phase": "prepared",
        "config_path": str(config_path),
        "devices_path": str(devices_path),
        "config_before_sha256": _document_digest(config_document),
        "devices_before_sha256": (
            _document_digest(devices_document) if devices_document is not None else None
        ),
        "config_after": config,
        "devices_after": registry,
    }
    _atomic_json(journal_path, journal)
    if fail_after == "prepared":
        raise RuntimeError("injected failure after transaction prepare")
    devices, config = _resume_transaction(journal_path, fail_after=fail_after)
    return devices, config, True


def _platforms(values):
    result = {}
    for value in values:
        logical_id, separator, platform = value.partition("=")
        if not separator or not LOGICAL_ID.fullmatch(logical_id) or platform not in PLATFORMS:
            raise ValueError("platform must use LOGICAL_ID=android|android-emulator")
        if logical_id in result:
            raise ValueError("duplicate platform override: %s" % logical_id)
        result[logical_id] = platform
    return result


def main():
    repository = Path(__file__).resolve().parents[2]
    parser = argparse.ArgumentParser()
    parser.add_argument("--config", default=str(repository / ".kodi-private/kodi-reinstall.json"))
    parser.add_argument("--devices", default=str(repository / ".kodi-private/devices.json"))
    parser.add_argument("--publisher", action="append", default=[])
    parser.add_argument("--platform", action="append", default=[])
    parser.add_argument("--apply", action="store_true")
    args = parser.parse_args()
    registry, config, changed = migrate_config_pair(
        args.config,
        args.devices,
        repository,
        publishers=args.publisher,
        platforms=_platforms(args.platform),
        apply=args.apply,
    )
    print(json.dumps({"changed": changed, "applied": bool(changed and args.apply), "devices": sorted(registry["devices"]), "schema": config["schema"]}, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
