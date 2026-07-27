#!/usr/bin/env python3
"""Read-only Kodi inventory through the registered transport and lifecycle."""

from __future__ import annotations

import argparse
import json
import re
import stat
from pathlib import Path

try:
    from kodi_devices import load_registry, resolve_device
    from kodi_lifecycle import lifecycle_for_device
    from kodi_transports import transport_for_device
except ModuleNotFoundError:
    from tools.kodi_devices import load_registry, resolve_device
    from tools.kodi_lifecycle import lifecycle_for_device
    from tools.kodi_transports import transport_for_device


ENV_NAME = re.compile(r"^[A-Za-z_][A-Za-z0-9_]*$")


def load_private_references(path):
    path = Path(path)
    if not path.exists():
        return {}
    if stat.S_IMODE(path.stat().st_mode) & 0o077:
        raise ValueError("private reference file permissions are too broad")
    references = {}
    for number, raw_line in enumerate(
        path.read_text(encoding="utf-8").splitlines(),
        1,
    ):
        line = raw_line.strip()
        if not line or line.startswith("#"):
            continue
        key, separator, value = line.partition("=")
        key = key.strip()
        if not separator or not ENV_NAME.fullmatch(key):
            raise ValueError("invalid private reference at line %s" % number)
        if key in references:
            raise ValueError("duplicate private reference: %s" % key)
        value = value.strip()
        if (
            len(value) >= 2
            and value[0] == value[-1]
            and value[0] in {'"', "'"}
        ):
            value = value[1:-1]
        if not value:
            raise ValueError("empty private reference: %s" % key)
        references[key] = value
    return references


def inventory_device(
    repository,
    logical_device_id,
    devices_file=".kodi-private/devices.json",
    references_file=".env",
    adb="adb",
    adb_server_port=5038,
):
    repository = Path(repository).resolve()
    devices_path = repository / devices_file
    references_path = repository / references_file
    device = resolve_device(load_registry(devices_path), logical_device_id)
    references = load_private_references(references_path)
    transport = transport_for_device(
        device,
        references=references,
        adb=adb,
        adb_server_port=adb_server_port,
    )
    probe = lifecycle_for_device(device, transport).probe_kodi()
    return {
        "logical_device_id": logical_device_id,
        "platform": probe["platform"],
        "transport": probe["transport"],
        "model": probe["model"],
        "abi": probe["abi"],
        "kodi_version": probe["kodi_version"],
        "running": probe["running"],
        "runtime_paths_qualified": probe["runtime_paths_qualified"],
        **(
            {"runtime_path_status": probe["runtime_path_status"]}
            if "runtime_path_status" in probe
            else {}
        ),
    }


def main():
    repository = Path(__file__).resolve().parents[1]
    parser = argparse.ArgumentParser()
    parser.add_argument("logical_device_id")
    parser.add_argument(
        "--devices",
        default=".kodi-private/devices.json",
    )
    parser.add_argument("--references", default=".env")
    parser.add_argument("--adb", default="adb")
    parser.add_argument("--adb-server-port", type=int, default=5038)
    args = parser.parse_args()
    result = inventory_device(
        repository,
        args.logical_device_id,
        devices_file=args.devices,
        references_file=args.references,
        adb=args.adb,
        adb_server_port=args.adb_server_port,
    )
    print(json.dumps(result, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
