#!/usr/bin/env python3
"""Export and idempotently restore authoritative private Umbrella settings."""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import stat
import subprocess
import sys
import tempfile
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from tools.kodi_addon_settings_rollout import load_setting_sources
from tools.kodi_profile import (
    AdbEventClient,
    AdbJsonRpcClient,
    _wait_for_kodi_ready,
    adb_command,
)
from tools.kodi_sync_inventory import load_sync_inventory


ADDON_ID = "plugin.video.umbrella"
REMOTE_SETTINGS = (
    "/sdcard/Android/data/org.xbmc.kodi/files/.kodi/userdata/addon_data/"
    + ADDON_ID
    + "/settings.xml"
)
REMOTE_SCRIPT = "/sdcard/Download/.mwo-umbrella-private.py"
REMOTE_CONFIG = "/sdcard/Download/.mwo-umbrella-private.json"
REMOTE_REPORT = "/sdcard/Download/.mwo-umbrella-private-result.json"
REQUIRED_PRIVATE = {
    "realdebridtoken",
    "realdebridusername",
    "realdebrid.clientid",
    "realdebridrefresh",
    "realdebridsecret",
}


def _device(
    repository,
    device_id,
    devices_file=".kodi-private/devices.json",
    references_file=".env",
):
    inventory = load_sync_inventory(
        repository,
        devices_file=devices_file,
        references_file=references_file,
    )
    if device_id not in inventory["devices"]:
        raise ValueError("unknown Umbrella settings device")
    device = inventory["devices"][device_id]
    if device["platform"] not in {"android", "android-emulator"}:
        raise ValueError("Umbrella settings authority requires Android")
    return device


def _pull(adb, port, serial, destination):
    result = adb_command(
        adb,
        port,
        serial,
        "pull",
        REMOTE_SETTINGS,
        str(destination),
        check=False,
        timeout=60,
    )
    return result.returncode == 0 and destination.is_file()


def _validated_source(path):
    source = load_setting_sources([ADDON_ID + "=" + str(path)])[ADDON_ID]
    missing = sorted(
        key for key in REQUIRED_PRIVATE if not source["values"].get(key)
    )
    if missing:
        raise ValueError("Umbrella authority lacks Real-Debrid credentials")
    return source


def _read_report(adb, port, serial):
    result = adb_command(
        adb,
        port,
        serial,
        "shell",
        "cat '%s'" % REMOTE_REPORT,
        check=False,
        text=True,
        timeout=10,
    )
    payload = (result.stdout or "").strip()
    return json.loads(payload) if payload.startswith("{") else None


def _wait_report(adb, port, serial, deadline):
    while time.monotonic() < deadline:
        try:
            result = _read_report(adb, port, serial)
        except (OSError, subprocess.TimeoutExpired):
            result = None
        if result is not None:
            return result
        time.sleep(1)
    return None


def _apply_private_values(adb, port, serial, values):
    payload = {
        "schema": 1,
        "settings": {
            **{key: values[key] for key in sorted(REQUIRED_PRIVATE)},
            "realdebrid.enable": "true",
        },
    }
    try:
        with tempfile.NamedTemporaryFile(
            mode="w", encoding="utf-8", suffix=".json"
        ) as private_config:
            json.dump(payload, private_config, sort_keys=True)
            private_config.flush()
            adb_command(
                adb,
                port,
                serial,
                "push",
                str(ROOT / "tools/kodi_umbrella_settings_device.py"),
                REMOTE_SCRIPT,
            )
            adb_command(
                adb, port, serial, "push", private_config.name, REMOTE_CONFIG
            )
        adb_command(
            adb,
            port,
            serial,
            "shell",
            "rm -f '%s'" % REMOTE_REPORT,
            check=False,
        )
        _wait_for_kodi_ready(adb, port, serial)
        command = "RunScript(%s,%s,%s)" % (
            REMOTE_SCRIPT,
            REMOTE_CONFIG,
            REMOTE_REPORT,
        )
        deadline = time.monotonic() + 90
        report = None
        try:
            with AdbJsonRpcClient(adb, port, serial) as rpc:
                rpc.call(
                    "XBMC.ExecuteBuiltin", {"command": command, "wait": False}
                )
            report = _wait_report(
                adb, port, serial, min(deadline, time.monotonic() + 15)
            )
        except (OSError, RuntimeError, TimeoutError):
            report = None
        events = AdbEventClient(adb, port, serial)
        while report is None and time.monotonic() < deadline:
            events.execute_builtin(command)
            report = _wait_report(
                adb, port, serial, min(deadline, time.monotonic() + 12)
            )
        if not report or not report.get("ok"):
            raise RuntimeError("Umbrella private settings adapter failed")
        return report
    finally:
        adb_command(
            adb,
            port,
            serial,
            "shell",
            "rm -f '%s' '%s' '%s'"
            % (REMOTE_SCRIPT, REMOTE_CONFIG, REMOTE_REPORT),
            check=False,
        )


def _atomic_private_write(output, payload):
    output = Path(output).resolve()
    private = (ROOT / ".kodi-private").resolve()
    if private not in output.parents:
        raise ValueError("Umbrella settings output must be private")
    output.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
    output.parent.chmod(0o700)
    descriptor, name = tempfile.mkstemp(prefix=".umbrella-", dir=output.parent)
    temporary = Path(name)
    try:
        with os.fdopen(descriptor, "wb") as handle:
            handle.write(payload)
            handle.flush()
            os.fsync(handle.fileno())
        os.chmod(temporary, 0o600)
        os.replace(temporary, output)
    finally:
        temporary.unlink(missing_ok=True)
    metadata = output.lstat()
    if not stat.S_ISREG(metadata.st_mode) or stat.S_IMODE(metadata.st_mode) != 0o600:
        raise RuntimeError("Umbrella settings permissions differ")


def export_settings(
    repository,
    device_id,
    output,
    adb,
    port,
    devices_file=".kodi-private/devices.json",
    references_file=".env",
):
    device = _device(repository, device_id, devices_file, references_file)
    serial = device["endpoints"]["adb"]
    with tempfile.TemporaryDirectory(prefix="umbrella-export-") as temporary:
        downloaded = Path(temporary) / "settings.xml"
        if not _pull(adb, port, serial, downloaded):
            raise RuntimeError("Umbrella publisher settings are unavailable")
        source = _validated_source(downloaded)
        _atomic_private_write(output, source["payload"])
    return {
        "schema": 1,
        "device": device_id,
        "status": "EXPORTED",
        "settings_sha256": hashlib.sha256(source["payload"]).hexdigest(),
    }


def _private_settings_match(observed_values, authoritative_values):
    return observed_values.get("realdebrid.enable") == "true" and all(
        observed_values.get(key) == authoritative_values.get(key)
        for key in REQUIRED_PRIVATE
    )


def apply_settings(
    repository,
    device_id,
    source_path,
    adb,
    port,
    devices_file=".kodi-private/devices.json",
    references_file=".env",
):
    device = _device(repository, device_id, devices_file, references_file)
    serial = device["endpoints"]["adb"]
    source = _validated_source(source_path)
    observed_values = {}
    with tempfile.TemporaryDirectory(prefix="umbrella-audit-") as temporary:
        observed = Path(temporary) / "settings.xml"
        if _pull(adb, port, serial, observed):
            observed_values = load_setting_sources(
                [ADDON_ID + "=" + str(observed)]
            )[ADDON_ID]["values"]
        if _private_settings_match(observed_values, source["values"]):
            return {
                "schema": 1,
                "device": device_id,
                "status": "NO_CHANGE",
                "settings_sha256": hashlib.sha256(source["payload"]).hexdigest(),
            }
    _apply_private_values(adb, port, serial, source["values"])
    return {
        "schema": 1,
        "device": device_id,
        "status": "APPLIED",
        "settings_sha256": hashlib.sha256(source["payload"]).hexdigest(),
    }


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("command", choices=("export", "apply"))
    parser.add_argument("--device", required=True)
    parser.add_argument(
        "--settings", default=".kodi-private/umbrella/settings.xml"
    )
    parser.add_argument(
        "--devices", default=".kodi-private/devices.json"
    )
    parser.add_argument("--references", default=".env")
    parser.add_argument("--adb", default="/home/mwo/android-sdk/platform-tools/adb")
    parser.add_argument("--adb-server-port", type=int, default=5038)
    args = parser.parse_args()
    settings = Path(args.settings)
    if not settings.is_absolute():
        settings = ROOT / settings
    if args.command == "export":
        result = export_settings(
            ROOT,
            args.device,
            settings,
            args.adb,
            args.adb_server_port,
            args.devices,
            args.references,
        )
    else:
        result = apply_settings(
            ROOT,
            args.device,
            settings,
            args.adb,
            args.adb_server_port,
            args.devices,
            args.references,
        )
    print(json.dumps(result, indent=2, sort_keys=True))


if __name__ == "__main__":
    main()
