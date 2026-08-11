#!/usr/bin/env python3
"""Validate and resolve private Kodi device inventory."""

from __future__ import annotations

import argparse
import copy
import json
import re
from pathlib import Path


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
    if schema != SCHEMA:
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
        _validate_v2_device(logical_id, device)
    identities = [
        (item["physical_host_id"], item["principal_id"])
        for item in devices.values()
    ]
    if len(identities) != len(set(identities)):
        raise ValueError("duplicate physical_host_id/principal_id identity")
    return document


def normalize_registry(document):
    validate_registry(document)
    return copy.deepcopy(document)


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
    raise AssertionError("unhandled command")


if __name__ == "__main__":
    raise SystemExit(main())
