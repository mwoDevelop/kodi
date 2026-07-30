#!/usr/bin/env python3
"""Resolve the authoritative private Kodi sync device list from .env."""

from __future__ import annotations

import copy
import re
from pathlib import Path

try:
    from kodi_devices import load_registry
    from kodi_inventory import load_private_references
except ModuleNotFoundError:
    from tools.kodi_devices import load_registry
    from tools.kodi_inventory import load_private_references


SAFE_ENV_PART = re.compile(r"^[A-Z0-9_]+$")
SAFE_PROFILE_VALUE = re.compile(r"^[a-z0-9][a-z0-9._-]{0,63}$")


def device_env_prefix(logical_device_id):
    part = logical_device_id.upper().replace("-", "_").replace(".", "_")
    if not SAFE_ENV_PART.fullmatch(part):
        raise ValueError("logical device id cannot map to an environment key")
    return "KODI_DEVICE_%s" % part


def _device_list(value):
    devices = [item.strip() for item in value.split(",") if item.strip()]
    if not devices or len(devices) != len(set(devices)):
        raise ValueError("KODI_SYNC_DEVICES must be a unique non-empty list")
    return devices


def _profile_sync_policy(references):
    required = (
        "KODI_PROFILE_SYNC_CHANNEL",
        "KODI_PROFILE_SYNC_STARTUP_DELAY_SECONDS",
        "KODI_PROFILE_SYNC_INTERVAL_HOURS",
        "KODI_PROFILE_SYNC_READ_ONLY",
    )
    missing = [key for key in required if not references.get(key)]
    if missing:
        raise ValueError(
            "private references lack Profile Sync policy: %s"
            % ", ".join(missing)
        )
    channel = references["KODI_PROFILE_SYNC_CHANNEL"]
    if not SAFE_PROFILE_VALUE.fullmatch(channel):
        raise ValueError("KODI_PROFILE_SYNC_CHANNEL is invalid")
    try:
        startup = int(references["KODI_PROFILE_SYNC_STARTUP_DELAY_SECONDS"])
        interval = float(references["KODI_PROFILE_SYNC_INTERVAL_HOURS"])
    except ValueError as error:
        raise ValueError("Profile Sync schedule is invalid") from error
    read_only = references["KODI_PROFILE_SYNC_READ_ONLY"].casefold()
    if (
        not 0 <= startup <= 300
        or not 0.25 <= interval <= 168
        or read_only not in {"true", "false"}
    ):
        raise ValueError("Profile Sync policy is outside supported bounds")
    return {
        "channel": channel,
        "startup_delay_seconds": str(startup),
        "interval_hours": references["KODI_PROFILE_SYNC_INTERVAL_HOURS"],
        "read_only": read_only,
    }


def load_sync_inventory(
    repository,
    devices_file=".kodi-private/devices.json",
    references_file=".env",
):
    repository = Path(repository).resolve()
    registry = load_registry(repository / devices_file)
    references = load_private_references(repository / references_file)
    if "KODI_SYNC_DEVICES" not in references:
        raise ValueError("private references have no KODI_SYNC_DEVICES")
    if "KODI_SYNC_PUBLISHER" not in references:
        raise ValueError("private references have no KODI_SYNC_PUBLISHER")
    selected = _device_list(references["KODI_SYNC_DEVICES"])
    unknown = sorted(set(selected).difference(registry["devices"]))
    if unknown:
        raise ValueError(
            "KODI_SYNC_DEVICES contains unknown devices: %s"
            % ", ".join(unknown)
        )
    publisher = references["KODI_SYNC_PUBLISHER"]
    if publisher not in selected:
        raise ValueError("KODI_SYNC_PUBLISHER is not in KODI_SYNC_DEVICES")
    if "publisher" not in registry["devices"][publisher]["roles"]:
        raise ValueError("KODI_SYNC_PUBLISHER lacks the publisher role")
    resolved = {}
    for logical_id in selected:
        device = copy.deepcopy(registry["devices"][logical_id])
        prefix = device_env_prefix(logical_id)
        if device["platform"] in {"android", "android-emulator"}:
            key = prefix + "_ADB"
            endpoint = references.get(key)
            if not endpoint:
                raise ValueError("private references have no %s" % key)
            device["endpoints"] = {
                **{
                    key: value
                    for key, value in device["endpoints"].items()
                    if key == "jsonrpc"
                },
                "adb": endpoint,
            }
        elif device["platform"] == "linux-flatpak":
            key = prefix + "_SSH_HOST"
            host = references.get(key)
            if not host:
                raise ValueError("private references have no %s" % key)
            ssh = dict(device["endpoints"]["ssh"])
            ssh["host"] = host
            device["endpoints"] = {
                **{
                    key: value
                    for key, value in device["endpoints"].items()
                    if key == "jsonrpc"
                },
                "ssh": ssh,
            }
        else:
            raise ValueError("unsupported Kodi sync platform")
        resolved[logical_id] = {
            "logical_device_id": logical_id,
            **device,
        }
    return {
        "publisher": publisher,
        "order": selected,
        "devices": resolved,
        "references": references,
        "profile_sync": _profile_sync_policy(references),
    }
