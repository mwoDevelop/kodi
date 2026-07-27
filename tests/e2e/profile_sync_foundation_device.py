#!/usr/bin/env python3
"""Read-only device E2E for schema 2 routine profile export."""

from __future__ import annotations

import argparse
import json
import re
import tempfile
from pathlib import Path, PurePosixPath

from tools.kodi_devices import load_registry, resolve_device
from tools.kodi_profile import KODI_PACKAGE, KODI_ROOT, adb_command, adb_output
from tools.kodi_routine_profile import (
    export_routine_profile,
    load_routine_policy,
    write_manifest,
)


FORBIDDEN_SETTING_IDS = {
    "realdebridtoken",
    "alldebridtoken",
    "premiumizetoken",
    "trakt.token",
    "trakt.refresh",
}


def kodi_major(adb, port, serial):
    package = adb_output(
        adb,
        port,
        serial,
        "shell",
        "dumpsys package %s" % KODI_PACKAGE,
    )
    version = re.search(r"versionName=([^\s]+)", package)
    if not version:
        raise RuntimeError("Kodi is not installed")
    match = re.match(r"^(\d+)", version.group(1))
    if not match:
        raise RuntimeError("Kodi version is invalid")
    return int(match.group(1)), version.group(1)


def pull_managed_inputs(adb, port, serial, root, routine):
    pulled = []
    for adapter in routine["adapters"]:
        relative = PurePosixPath(adapter["path"])
        result = adb_command(
            adb,
            port,
            serial,
            "exec-out",
            "cat",
            KODI_ROOT + "/" + relative.as_posix(),
            check=False,
            text=False,
        )
        if result.returncode:
            continue
        target = root.joinpath(*relative.parts)
        target.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
        target.write_bytes(result.stdout)
        target.chmod(0o600)
        pulled.append(relative.as_posix())
    return pulled


def verify_device(repository, logical_device_id, adb, port, output_root):
    registry = load_registry(repository / ".kodi-private/devices.json")
    device = resolve_device(registry, logical_device_id)
    serial = device["endpoints"]["adb"]
    if adb_output(adb, port, serial, "get-state").strip() != "device":
        raise RuntimeError("%s is not an authorized ADB device" % logical_device_id)
    model = adb_output(
        adb, port, serial, "shell", "getprop ro.product.model"
    ).strip()
    if model != device["expected"]["model"]:
        raise RuntimeError("%s resolved to an unexpected model" % logical_device_id)
    observed_abis = {
        item
        for item in adb_output(
            adb,
            port,
            serial,
            "shell",
            "getprop ro.product.cpu.abilist",
        ).strip().split(",")
        if item
    }
    expected_abis = set(device["expected"].get("abi", []))
    if expected_abis and not expected_abis.intersection(observed_abis):
        raise RuntimeError("%s ABI does not match inventory" % logical_device_id)
    major, version = kodi_major(adb, port, serial)
    if major != device["expected"]["kodi_major"]:
        raise RuntimeError("%s Kodi major does not match inventory" % logical_device_id)
    policy = repository / "manifests/kodi-profile-policy.json"
    _document, routine = load_routine_policy(policy)
    with tempfile.TemporaryDirectory(prefix="mwo-profile-e2e-") as temporary:
        temporary_root = Path(temporary)
        pulled = pull_managed_inputs(
            adb, port, serial, temporary_root, routine
        )
        manifest = export_routine_profile(temporary_root, policy, major)
    value_keys = {
        adapter_id: sorted(item["values"])
        for adapter_id, item in manifest["adapters"].items()
    }
    exported_ids = {
        setting_id
        for keys in value_keys.values()
        for setting_id in keys
    }
    forbidden = sorted(FORBIDDEN_SETTING_IDS.intersection(exported_ids))
    if forbidden:
        raise RuntimeError("%s exported forbidden setting ids" % logical_device_id)
    output = output_root / ("%s.json" % logical_device_id)
    write_manifest(output, manifest)
    output.chmod(0o600)
    return {
        "logical_device_id": logical_device_id,
        "model_matches": True,
        "kodi_version": version,
        "abi_matches": True,
        "pulled_inputs": sorted(pulled),
        "revision_id": manifest["revision_id"],
        "value_keys": value_keys,
        "forbidden_setting_ids": forbidden,
        "result": "pass",
    }


def main():
    repository = Path(__file__).resolve().parents[2]
    parser = argparse.ArgumentParser()
    parser.add_argument("--device", action="append")
    parser.add_argument(
        "--adb", default="/home/mwo/android-sdk/platform-tools/adb"
    )
    parser.add_argument("--adb-server-port", type=int, default=5038)
    parser.add_argument(
        "--output",
        default=".kodi-private/e2e/profile-sync-foundation",
    )
    args = parser.parse_args()
    registry = load_registry(repository / ".kodi-private/devices.json")
    selected = args.device or sorted(registry["devices"])
    output_root = (repository / args.output).resolve()
    private_root = (repository / ".kodi-private").resolve()
    if private_root not in output_root.parents:
        raise ValueError("E2E output must remain below .kodi-private")
    output_root.mkdir(parents=True, exist_ok=True, mode=0o700)
    output_root.chmod(0o700)
    results = [
        verify_device(
            repository,
            logical_device_id,
            args.adb,
            args.adb_server_port,
            output_root,
        )
        for logical_device_id in selected
    ]
    print(json.dumps({"schema": 1, "results": results}, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
