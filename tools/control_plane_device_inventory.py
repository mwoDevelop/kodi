#!/usr/bin/env python3
"""Build the redacted Control Plane device inventory from private references."""

from __future__ import annotations

import argparse
import json
import re
from pathlib import Path

DEVICE_ID = re.compile(r"^[a-z0-9][a-z0-9-]{1,95}$")
CHANNEL = re.compile(r"^[a-z0-9][a-z0-9-]{1,95}$")
CAPABILITY = re.compile(r"^[a-z0-9][a-z0-9-]{1,95}$")
VERSION = re.compile(r"^[0-9]+\.[0-9]+\.[0-9]+$")
MODES = frozenset({"always_on", "on_demand", "maintenance", "retired"})
DEFAULT_REQUIRED_CAPABILITIES = ("skin-shortcuts-menu-v1",)
DEFAULT_MINIMUM_CLIENT_VERSION = "1.5.0"


class InventoryError(ValueError):
    pass


def _key(device_id, suffix):
    token = re.sub(r"[^A-Za-z0-9]", "_", device_id).upper()
    return f"KODI_DEVICE_{token}_{suffix}"


def _positive_int(references, name, default, minimum):
    value = references.get(name, str(default)).strip()
    try:
        parsed = int(value)
    except ValueError as error:
        raise InventoryError(f"{name} must be an integer") from error
    if parsed < minimum:
        raise InventoryError(f"{name} is below the safe minimum")
    return parsed


def build_inventory(
    references,
    required_capabilities=DEFAULT_REQUIRED_CAPABILITIES,
    minimum_client_version=DEFAULT_MINIMUM_CLIENT_VERSION,
):
    """Return a strictly redacted schema-2 inventory.

    Only allowlisted policy keys are copied. Transport addresses, credentials,
    enrollment identifiers and every other value in ``references`` are ignored.
    """

    required_capabilities = sorted(set(required_capabilities))
    if (
        len(required_capabilities) > 32
        or any(not CAPABILITY.fullmatch(str(item)) for item in required_capabilities)
    ):
        raise InventoryError("required capabilities are invalid")
    if not isinstance(minimum_client_version, str) or not VERSION.fullmatch(
        minimum_client_version
    ):
        raise InventoryError("minimum client version is invalid")

    raw_ids = references.get("KODI_SYNC_DEVICES", "")
    devices = [item.strip() for item in raw_ids.split(",") if item.strip()]
    if not devices:
        raise InventoryError("KODI_SYNC_DEVICES is empty")
    if len(devices) != len(set(devices)) or any(
        not DEVICE_ID.fullmatch(item) for item in devices
    ):
        raise InventoryError("KODI_SYNC_DEVICES contains invalid or duplicate IDs")

    default_mode = references.get(
        "KODI_DEVICE_DEFAULT_MONITORING_MODE", "on_demand"
    ).strip()
    default_channel = references.get("KODI_DEVICE_DEFAULT_CHANNEL", "home-stable").strip()
    default_warning = _positive_int(
        references, "KODI_DEVICE_DEFAULT_WARNING_AFTER_SECONDS", 28800, 900
    )
    default_failure = _positive_int(
        references, "KODI_DEVICE_DEFAULT_FAILURE_AFTER_SECONDS", 259200, 900
    )
    if default_mode not in MODES or not CHANNEL.fullmatch(default_channel):
        raise InventoryError("default device monitoring policy is invalid")
    if default_failure < default_warning:
        raise InventoryError("default failure threshold precedes warning")

    rows = []
    for device_id in devices:
        mode = references.get(
            _key(device_id, "MONITORING_MODE"), default_mode
        ).strip()
        channel = references.get(_key(device_id, "CHANNEL"), default_channel).strip()
        warning = _positive_int(
            references,
            _key(device_id, "WARNING_AFTER_SECONDS"),
            default_warning,
            900,
        )
        failure = _positive_int(
            references,
            _key(device_id, "FAILURE_AFTER_SECONDS"),
            default_failure,
            900,
        )
        maintenance = references.get(_key(device_id, "MAINTENANCE_UNTIL"), "").strip()
        if mode not in MODES or not CHANNEL.fullmatch(channel):
            raise InventoryError(f"device policy is invalid for {device_id}")
        if failure < warning:
            raise InventoryError(f"failure threshold precedes warning for {device_id}")
        if mode == "maintenance" and not maintenance:
            raise InventoryError(f"maintenance deadline is required for {device_id}")
        if mode != "maintenance" and maintenance:
            raise InventoryError(
                f"maintenance deadline is allowed only in maintenance mode for {device_id}"
            )
        rows.append(
            {
                "logical_device_id": device_id,
                "monitoring_mode": mode,
                "channel": channel,
                "warning_after_seconds": warning,
                "failure_after_seconds": failure,
                "maintenance_until": maintenance or None,
                "required_capabilities": required_capabilities,
                "minimum_client_version": minimum_client_version,
            }
        )
    return {"schema": 2, "devices": rows}


def _read_env(path):
    values = {}
    for line in Path(path).read_text(encoding="utf-8").splitlines():
        stripped = line.strip()
        if not stripped or stripped.startswith("#") or "=" not in stripped:
            continue
        key, value = stripped.split("=", 1)
        values[key.strip()] = value.strip().strip('"').strip("'")
    return values


def main(argv=None):
    parser = argparse.ArgumentParser()
    parser.add_argument("--env", default=".env")
    parser.add_argument("--output")
    args = parser.parse_args(argv)
    payload = json.dumps(build_inventory(_read_env(args.env)), indent=2, sort_keys=True)
    if args.output:
        Path(args.output).write_text(payload + "\n", encoding="utf-8")
    else:
        print(payload)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
