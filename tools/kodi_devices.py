#!/usr/bin/env python3
"""Validate and resolve private Kodi device inventory."""

from __future__ import annotations

import argparse
import copy
import hashlib
import json
import os
import re
import shutil
import tempfile
from pathlib import Path


LEGACY_SCHEMA = 1
SCHEMA = 2
LOGICAL_DEVICE_ID = re.compile(r"^[a-z0-9][a-z0-9._-]{0,63}$")
CHANNEL = LOGICAL_DEVICE_ID
ROLES = {"consumer", "publisher"}
PLATFORMS = {"android", "android-emulator", "linux-flatpak"}
SAFE_ENV_PART = re.compile(r"^[A-Z0-9_]+$")


def _require_string(value, label):
    if not isinstance(value, str) or not value:
        raise ValueError("%s must be a non-empty string" % label)
    return value


def _validate_expected(expected, logical_id, platform=None):
    allowed = {"model", "kodi_major", "abi"}
    if platform == "linux-flatpak":
        allowed.update({"flatpak_app_id", "kodi_data_root"})
    if not isinstance(expected, dict) or not set(expected).issubset(allowed):
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
    if platform == "linux-flatpak":
        _require_string(
            expected.get("flatpak_app_id"),
            "%s expected Flatpak app id" % logical_id,
        )
        data_root = _require_string(
            expected.get("kodi_data_root"),
            "%s expected Kodi data root" % logical_id,
        )
        if data_root.startswith(("/", "~")) or ".." in Path(data_root).parts:
            raise ValueError("%s has unsafe Kodi data root" % logical_id)


def _validate_roles(roles, logical_id):
    if (
        not isinstance(roles, list)
        or not roles
        or len(roles) != len(set(roles))
        or any(role not in ROLES for role in roles)
    ):
        raise ValueError("%s has invalid roles" % logical_id)


def _validate_channel(channel, logical_id):
    value = _require_string(channel, "%s profile channel" % logical_id)
    if not CHANNEL.fullmatch(value):
        raise ValueError("%s has invalid profile channel" % logical_id)


def _validate_jsonrpc(endpoints, logical_id):
    if "jsonrpc" not in endpoints:
        return
    endpoint = _require_string(
        endpoints["jsonrpc"], "%s JSON-RPC endpoint" % logical_id
    )
    if not endpoint.startswith(("http://", "https://")):
        raise ValueError("%s has invalid JSON-RPC endpoint" % logical_id)


def _validate_v1_device(logical_id, device):
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
    _validate_roles(device["roles"], logical_id)
    _validate_expected(device["expected"], logical_id)
    endpoints = device["endpoints"]
    if (
        not isinstance(endpoints, dict)
        or "adb" not in endpoints
        or not set(endpoints).issubset({"adb", "jsonrpc"})
    ):
        raise ValueError("%s has invalid endpoints" % logical_id)
    _require_string(endpoints["adb"], "%s ADB endpoint" % logical_id)
    _validate_jsonrpc(endpoints, logical_id)
    _validate_channel(device["profile_channel"], logical_id)


def _validate_v2_device(logical_id, device):
    allowed = {
        "display_name",
        "physical_host_id",
        "principal_id",
        "platform",
        "roles",
        "expected",
        "endpoints",
        "profile_channel",
    }
    if set(device) != allowed:
        raise ValueError("%s device has unsupported or missing fields" % logical_id)
    _require_string(device["display_name"], "%s display_name" % logical_id)
    physical_host_id = _require_string(
        device["physical_host_id"], "%s physical_host_id" % logical_id
    )
    principal_id = _require_string(
        device["principal_id"], "%s principal_id" % logical_id
    )
    if not LOGICAL_DEVICE_ID.fullmatch(physical_host_id):
        raise ValueError("%s has invalid physical_host_id" % logical_id)
    if not LOGICAL_DEVICE_ID.fullmatch(principal_id):
        raise ValueError("%s has invalid principal_id" % logical_id)
    platform = device["platform"]
    if platform not in PLATFORMS:
        raise ValueError("%s has invalid platform" % logical_id)
    _validate_roles(device["roles"], logical_id)
    _validate_expected(device["expected"], logical_id, platform)
    endpoints = device["endpoints"]
    if not isinstance(endpoints, dict) or not set(endpoints).issubset(
        {"adb", "ssh", "jsonrpc"}
    ):
        raise ValueError("%s has invalid endpoints" % logical_id)
    has_adb = "adb" in endpoints
    has_ssh = "ssh" in endpoints
    if has_adb == has_ssh:
        raise ValueError("%s must configure exactly one host transport" % logical_id)
    if platform in {"android", "android-emulator"} and not has_adb:
        raise ValueError("%s Android platform requires ADB" % logical_id)
    if platform == "linux-flatpak" and not has_ssh:
        raise ValueError("%s Linux Flatpak platform requires SSH" % logical_id)
    if has_adb:
        _require_string(endpoints["adb"], "%s ADB endpoint" % logical_id)
    if has_ssh:
        ssh = endpoints["ssh"]
        required = {
            "host",
            "user_ref",
            "credential_ref",
            "known_hosts_ref",
        }
        if not isinstance(ssh, dict) or set(ssh) != required:
            raise ValueError("%s has invalid SSH endpoint" % logical_id)
        for field in sorted(required):
            _require_string(ssh[field], "%s SSH %s" % (logical_id, field))
    _validate_jsonrpc(endpoints, logical_id)
    _validate_channel(device["profile_channel"], logical_id)


def validate_registry(document):
    if not isinstance(document, dict) or set(document) != {"schema", "devices"}:
        raise ValueError("device inventory has unsupported top-level fields")
    schema = document.get("schema")
    if schema not in {LEGACY_SCHEMA, SCHEMA}:
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
        if schema == LEGACY_SCHEMA:
            _validate_v1_device(logical_id, device)
        else:
            _validate_v2_device(logical_id, device)
    if schema == SCHEMA:
        identities = [
            (item["physical_host_id"], item["principal_id"])
            for item in devices.values()
        ]
        if len(identities) != len(set(identities)):
            raise ValueError("duplicate physical_host_id/principal_id identity")
    return document


def _default_principal_id(logical_id):
    digest = hashlib.sha256(logical_id.encode("utf-8")).hexdigest()[:16]
    return "principal-%s" % digest


def normalize_registry(document, platforms=None):
    validate_registry(document)
    if document["schema"] == SCHEMA:
        return copy.deepcopy(document)
    platform_map = dict(platforms or {})
    unknown = sorted(set(platform_map).difference(document["devices"]))
    if unknown:
        raise ValueError(
            "platform override references unknown devices: %s"
            % ", ".join(unknown)
        )
    devices = {}
    for logical_id, device in document["devices"].items():
        platform = platform_map.get(logical_id, "android")
        if platform not in {"android", "android-emulator"}:
            raise ValueError(
                "legacy ADB device %s cannot migrate to %s"
                % (logical_id, platform)
            )
        devices[logical_id] = {
            "display_name": device["display_name"],
            "physical_host_id": logical_id,
            "principal_id": _default_principal_id(logical_id),
            "platform": platform,
            "roles": copy.deepcopy(device["roles"]),
            "expected": copy.deepcopy(device["expected"]),
            "endpoints": copy.deepcopy(device["endpoints"]),
            "profile_channel": device["profile_channel"],
        }
    return validate_registry({"schema": SCHEMA, "devices": devices})


def load_registry(path):
    document = json.loads(Path(path).read_text(encoding="utf-8"))
    return normalize_registry(document)


def resolve_device(registry, logical_device_id):
    registry = normalize_registry(registry)
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


def device_env_prefix(logical_device_id):
    part = logical_device_id.upper().replace("-", "_").replace(".", "_")
    if not SAFE_ENV_PART.fullmatch(part):
        raise ValueError("logical device id cannot map to an environment key")
    return "KODI_DEVICE_%s" % part


def resolve_private_endpoint(device, references, required=False):
    """Overlay the current host endpoint from private references.

    The versioned/private registry owns device identity and capabilities. The
    ignored reference file owns LAN and emulator addresses, which may change
    without changing that identity.
    """

    resolved = copy.deepcopy(device)
    prefix = device_env_prefix(resolved["logical_device_id"])
    endpoints = resolved["endpoints"]
    if resolved["platform"] in {"android", "android-emulator"}:
        key = prefix + "_ADB"
        endpoint = references.get(key)
        if required and not endpoint:
            raise ValueError("private references have no %s" % key)
        if endpoint:
            resolved["endpoints"] = {
                **(
                    {"jsonrpc": endpoints["jsonrpc"]}
                    if "jsonrpc" in endpoints
                    else {}
                ),
                "adb": endpoint,
            }
    elif resolved["platform"] == "linux-flatpak":
        key = prefix + "_SSH_HOST"
        host = references.get(key)
        if required and not host:
            raise ValueError("private references have no %s" % key)
        if host:
            ssh = dict(endpoints["ssh"])
            ssh["host"] = host
            resolved["endpoints"] = {
                **(
                    {"jsonrpc": endpoints["jsonrpc"]}
                    if "jsonrpc" in endpoints
                    else {}
                ),
                "ssh": ssh,
            }
    else:
        raise ValueError("unsupported Kodi sync platform")
    return resolved


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
        directory = os.open(path.parent, os.O_RDONLY)
        try:
            os.fsync(directory)
        finally:
            os.close(directory)
    finally:
        if os.path.exists(temporary):
            os.unlink(temporary)
    path.chmod(0o600)


def migrate_registry(path, platforms=None):
    path = Path(path).resolve()
    document = json.loads(path.read_text(encoding="utf-8"))
    validate_registry(document)
    if document["schema"] == SCHEMA:
        return normalize_registry(document), False
    migrated = normalize_registry(document, platforms=platforms)
    before = {
        logical_id: copy.deepcopy(device["endpoints"])
        for logical_id, device in document["devices"].items()
    }
    after = {
        logical_id: copy.deepcopy(device["endpoints"])
        for logical_id, device in migrated["devices"].items()
    }
    if before != after:
        raise RuntimeError("registry migration changed existing endpoints")
    backup = path.with_suffix(path.suffix + ".schema1.bak")
    if backup.exists():
        backup_document = json.loads(backup.read_text(encoding="utf-8"))
        if backup_document != document:
            raise FileExistsError("registry migration backup differs from input")
    else:
        shutil.copy2(path, backup)
        backup.chmod(0o600)
    _atomic_private_json(path, migrated)
    return migrated, True


def migrate_reinstall_config(
    config_path,
    devices_path,
    repository,
    publishers=(),
    platforms=None,
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
    registry = normalize_registry(
        {"schema": LEGACY_SCHEMA, "devices": devices},
        platforms=platforms,
    )
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
    migrate.add_argument(
        "--platform",
        action="append",
        default=[],
        metavar="LOGICAL_ID=PLATFORM",
    )
    migrate.add_argument("--yes", action="store_true")
    migrate_registry_parser = subparsers.add_parser("migrate-registry")
    migrate_registry_parser.add_argument(
        "--devices", default=".kodi-private/devices.json"
    )
    migrate_registry_parser.add_argument(
        "--platform",
        action="append",
        default=[],
        metavar="LOGICAL_ID=PLATFORM",
    )
    migrate_registry_parser.add_argument("--yes", action="store_true")
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
        target = (
            "private device registry"
            if args.command == "migrate-registry"
            else "private reinstall config"
        )
        print("Re-run with --yes to migrate the %s." % target)
        return 0
    platforms = {}
    for item in args.platform:
        logical_id, separator, platform = item.partition("=")
        if (
            not separator
            or not LOGICAL_DEVICE_ID.fullmatch(logical_id)
            or platform not in PLATFORMS
        ):
            raise ValueError(
                "platform must use LOGICAL_ID=android|android-emulator|linux-flatpak"
            )
        if logical_id in platforms:
            raise ValueError("duplicate platform override: %s" % logical_id)
        platforms[logical_id] = platform
    if args.command == "migrate-registry":
        registry, changed = migrate_registry(devices_path, platforms=platforms)
        print(
            json.dumps(
                {
                    "schema": registry["schema"],
                    "changed": changed,
                    "devices": sorted(registry["devices"]),
                },
                indent=2,
            )
        )
        return 0
    registry, config = migrate_reinstall_config(
        repository / args.config,
        devices_path,
        repository,
        publishers=args.publisher,
        platforms=platforms,
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
