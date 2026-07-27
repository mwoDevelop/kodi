#!/usr/bin/env python3
"""Validate and resolve private Kodi device inventory."""

from __future__ import annotations

import argparse
import json
import os
import re
import shutil
import tempfile
from pathlib import Path


SCHEMA = 1
LOGICAL_DEVICE_ID = re.compile(r"^[a-z0-9][a-z0-9._-]{0,63}$")
CHANNEL = LOGICAL_DEVICE_ID
ROLES = {"consumer", "publisher"}


def _require_string(value, label):
    if not isinstance(value, str) or not value:
        raise ValueError("%s must be a non-empty string" % label)
    return value


def validate_registry(document):
    if not isinstance(document, dict) or set(document) != {"schema", "devices"}:
        raise ValueError("device inventory has unsupported top-level fields")
    if document.get("schema") != SCHEMA:
        raise ValueError("unsupported device inventory schema")
    devices = document.get("devices")
    if not isinstance(devices, dict) or not devices:
        raise ValueError("device inventory has no devices")
    for logical_id, device in devices.items():
        if not isinstance(logical_id, str) or not LOGICAL_DEVICE_ID.fullmatch(
            logical_id
        ):
            raise ValueError("invalid logical device id: %r" % logical_id)
        if not isinstance(device, dict):
            raise ValueError("%s device must be an object" % logical_id)
        allowed = {
            "display_name",
            "roles",
            "expected",
            "endpoints",
            "profile_channel",
        }
        if set(device) != allowed:
            raise ValueError("%s device has unsupported or missing fields" % logical_id)
        _require_string(device["display_name"], "%s display_name" % logical_id)
        roles = device["roles"]
        if (
            not isinstance(roles, list)
            or not roles
            or len(roles) != len(set(roles))
            or any(role not in ROLES for role in roles)
        ):
            raise ValueError("%s has invalid roles" % logical_id)
        expected = device["expected"]
        if not isinstance(expected, dict) or not set(expected).issubset(
            {"model", "kodi_major", "abi"}
        ):
            raise ValueError("%s has invalid expected fields" % logical_id)
        _require_string(expected.get("model"), "%s expected model" % logical_id)
        kodi_major = expected.get("kodi_major")
        if not isinstance(kodi_major, int) or kodi_major < 19:
            raise ValueError("%s has invalid Kodi major" % logical_id)
        abi = expected.get("abi")
        if abi is not None and (
            not isinstance(abi, list)
            or not abi
            or len(abi) != len(set(abi))
            or any(not isinstance(item, str) or not item for item in abi)
        ):
            raise ValueError("%s has invalid ABI list" % logical_id)
        endpoints = device["endpoints"]
        if (
            not isinstance(endpoints, dict)
            or "adb" not in endpoints
            or not set(endpoints).issubset({"adb", "jsonrpc"})
        ):
            raise ValueError("%s has invalid endpoints" % logical_id)
        _require_string(endpoints["adb"], "%s ADB endpoint" % logical_id)
        if "jsonrpc" in endpoints:
            endpoint = _require_string(
                endpoints["jsonrpc"], "%s JSON-RPC endpoint" % logical_id
            )
            if not endpoint.startswith(("http://", "https://")):
                raise ValueError("%s has invalid JSON-RPC endpoint" % logical_id)
        channel = _require_string(
            device["profile_channel"], "%s profile channel" % logical_id
        )
        if not CHANNEL.fullmatch(channel):
            raise ValueError("%s has invalid profile channel" % logical_id)
    return document


def load_registry(path):
    document = json.loads(Path(path).read_text(encoding="utf-8"))
    return validate_registry(document)


def resolve_device(registry, logical_device_id):
    validate_registry(registry)
    try:
        device = registry["devices"][logical_device_id]
    except KeyError as error:
        raise ValueError(
            "unknown logical device: %s" % logical_device_id
        ) from error
    return {
        "logical_device_id": logical_device_id,
        **device,
    }


def _kodi_major(version):
    match = re.match(r"^(\d+)", str(version))
    if not match:
        raise ValueError("invalid Kodi version: %r" % version)
    return int(match.group(1))


def _atomic_private_json(path, document):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
    path.parent.chmod(0o700)
    payload = json.dumps(document, indent=2, sort_keys=True) + "\n"
    descriptor, temporary = tempfile.mkstemp(
        prefix=".%s." % path.name,
        dir=str(path.parent),
        text=True,
    )
    try:
        with os.fdopen(descriptor, "w", encoding="utf-8") as handle:
            handle.write(payload)
            handle.flush()
            os.fsync(handle.fileno())
        os.chmod(temporary, 0o600)
        os.replace(temporary, path)
    finally:
        if os.path.exists(temporary):
            os.unlink(temporary)
    path.chmod(0o600)


def migrate_reinstall_config(
    config_path,
    devices_path,
    repository,
    publishers=(),
):
    config_path = Path(config_path).resolve()
    devices_path = Path(devices_path).resolve()
    repository = Path(repository).resolve()
    document = json.loads(config_path.read_text(encoding="utf-8"))
    if document.get("schema") != 1 or not isinstance(
        document.get("targets"), list
    ):
        raise ValueError("migration requires a schema 1 reinstall config")
    publisher_set = set(publishers)
    devices = {}
    targets = []
    for target in document["targets"]:
        logical_id = target.get("name")
        if not isinstance(logical_id, str) or not LOGICAL_DEVICE_ID.fullmatch(
            logical_id
        ):
            raise ValueError("target name is not a valid logical device id")
        if logical_id in devices:
            raise ValueError("duplicate logical device: %s" % logical_id)
        roles = ["consumer"]
        if logical_id in publisher_set:
            roles.append("publisher")
        devices[logical_id] = {
            "display_name": logical_id,
            "roles": roles,
            "expected": {
                "model": target["expected_model"],
                "kodi_major": _kodi_major(target["expected_kodi_version"]),
            },
            "endpoints": {"adb": target["serial"]},
            "profile_channel": "home-stable",
        }
        migrated = {
            key: value
            for key, value in target.items()
            if key not in {"name", "serial", "expected_model"}
        }
        migrated["logical_device_id"] = logical_id
        targets.append(migrated)
    unknown_publishers = sorted(publisher_set.difference(devices))
    if unknown_publishers:
        raise ValueError(
            "unknown publisher devices: %s" % ", ".join(unknown_publishers)
        )
    registry = validate_registry({"schema": SCHEMA, "devices": devices})
    try:
        devices_relative = devices_path.relative_to(repository).as_posix()
    except ValueError as error:
        raise ValueError("devices inventory must be below repository") from error
    migrated_config = {
        "schema": 2,
        "devices_file": devices_relative,
        "targets": targets,
    }
    backup = config_path.with_suffix(config_path.suffix + ".schema1.bak")
    if backup.exists() or devices_path.exists():
        raise FileExistsError("migration output or backup already exists")
    shutil.copy2(config_path, backup)
    backup.chmod(0o600)
    _atomic_private_json(devices_path, registry)
    _atomic_private_json(config_path, migrated_config)
    return registry, migrated_config


def main():
    repository = Path(__file__).resolve().parents[1]
    parser = argparse.ArgumentParser()
    subparsers = parser.add_subparsers(dest="command", required=True)
    validate = subparsers.add_parser("validate")
    validate.add_argument(
        "--devices", default=".kodi-private/devices.json"
    )
    resolve = subparsers.add_parser("resolve")
    resolve.add_argument("logical_device_id")
    resolve.add_argument("--devices", default=".kodi-private/devices.json")
    migrate = subparsers.add_parser("migrate-reinstall")
    migrate.add_argument(
        "--config", default=".kodi-private/kodi-reinstall.json"
    )
    migrate.add_argument(
        "--devices", default=".kodi-private/devices.json"
    )
    migrate.add_argument("--publisher", action="append", default=[])
    migrate.add_argument("--yes", action="store_true")
    args = parser.parse_args()
    devices_path = repository / args.devices
    if args.command == "validate":
        registry = load_registry(devices_path)
        print(
            json.dumps(
                {
                    "schema": registry["schema"],
                    "devices": sorted(registry["devices"]),
                },
                indent=2,
            )
        )
        return 0
    if args.command == "resolve":
        device = resolve_device(load_registry(devices_path), args.logical_device_id)
        print(
            json.dumps(
                {
                    "logical_device_id": device["logical_device_id"],
                    "display_name": device["display_name"],
                    "roles": device["roles"],
                    "expected": device["expected"],
                    "profile_channel": device["profile_channel"],
                    "endpoint_kinds": sorted(device["endpoints"]),
                },
                indent=2,
                sort_keys=True,
            )
        )
        return 0
    if not args.yes:
        print("Re-run with --yes to migrate the private reinstall config.")
        return 0
    registry, config = migrate_reinstall_config(
        repository / args.config,
        devices_path,
        repository,
        publishers=args.publisher,
    )
    print(
        json.dumps(
            {
                "schema": config["schema"],
                "devices": sorted(registry["devices"]),
                "targets": [
                    item["logical_device_id"] for item in config["targets"]
                ],
            },
            indent=2,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
