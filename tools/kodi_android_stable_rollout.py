#!/usr/bin/env python3
"""Idempotently reconcile exact public channel artifacts on Android Kodi."""

from __future__ import annotations

import argparse
import json
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from tools.kodi_addon_candidate_rollout import rollout
from tools.kodi_default_addons import addon_details
from tools.kodi_devices import load_registry, resolve_device, resolve_private_endpoint
from tools.kodi_inventory import load_private_references
from tools.kodi_profile import (
    KODI_PACKAGE,
    _wait_for_kodi_ready,
    adb_command,
)
from tools.kodi_reinstall import assign_addon_origins_in_kodi
from tools.kodi_stable_artifacts import prepare


ADDON_ORDER = (
    "script.module.mwoscrapers",
    "script.mwoscrapers",
    "plugin.video.umbrella",
    "plugin.video.watchnixtoons2.mwodevelop",
    "service.mwodevelop.profilesync",
)


def wake_android_tv(adb, port, serial):
    for command in (
        "input keyevent KEYCODE_WAKEUP",
        "wm dismiss-keyguard",
        "input keyevent KEYCODE_HOME",
    ):
        adb_command(
            adb,
            port,
            serial,
            "shell",
            command,
            check=False,
        )
    time.sleep(1)


def ensure_kodi_ready(adb, port, serial):
    running = adb_command(
        adb,
        port,
        serial,
        "shell",
        "pidof %s" % KODI_PACKAGE,
        check=False,
        text=True,
    )
    if running.returncode != 0 or not (running.stdout or "").strip():
        wake_android_tv(adb, port, serial)
        adb_command(
            adb,
            port,
            serial,
            "shell",
            "monkey -p %s -c android.intent.category.LAUNCHER 1 >/dev/null"
            % KODI_PACKAGE,
        )
        _wait_for_kodi_ready(adb, port, serial)
        return "started"
    try:
        _wait_for_kodi_ready(adb, port, serial, timeout=15)
        return "ready"
    except TimeoutError:
        adb_command(
            adb,
            port,
            serial,
            "shell",
            "am force-stop %s" % KODI_PACKAGE,
        )
        time.sleep(2)
        wake_android_tv(adb, port, serial)
        adb_command(
            adb,
            port,
            serial,
            "shell",
            "monkey -p %s -c android.intent.category.LAUNCHER 1 >/dev/null"
            % KODI_PACKAGE,
        )
        _wait_for_kodi_ready(adb, port, serial)
        return "restarted"


def reconcile(device_id, adb, port, channel="stable"):
    references = load_private_references(ROOT / ".env")
    device = resolve_private_endpoint(
        resolve_device(load_registry(ROOT / ".kodi-private/devices.json"), device_id),
        references,
        required=True,
    )
    if device["platform"] not in {"android", "android-emulator"}:
        raise ValueError("Android stable rollout requires an Android device")
    serial = device["endpoints"]["adb"]
    kodi_preflight = ensure_kodi_ready(adb, port, serial)
    prepared = prepare(ROOT, channel=channel)
    repository_id = prepared["repository_id"]
    available = {
        repository_id: prepared["repository"],
        **prepared["addons"],
    }
    actions = []
    for addon_id in (repository_id, *ADDON_ORDER):
        artifact = available[addon_id]
        current = addon_details(adb, port, serial, addon_id)
        if current and current.get("enabled") and str(current.get("version")) == artifact["version"]:
            actions.append({"addon": addon_id, "action": "unchanged", "version": artifact["version"]})
            continue
        try:
            applied = rollout(
                adb,
                port,
                serial,
                artifact["path"],
                addon_id,
                artifact["version"],
                240,
                repair_orphan=False,
            )
        except RuntimeError as error:
            if (
                current is not None
                or "PermissionError at backup-installed-addon" not in str(error)
            ):
                raise
            applied = rollout(
                adb,
                port,
                serial,
                artifact["path"],
                addon_id,
                artifact["version"],
                240,
                repair_orphan=True,
            )
        actions.append({"addon": addon_id, "action": "installed", "version": artifact["version"], "repaired_orphan": bool(applied.get("repaired_orphan"))})
    origins = {
        addon_id: repository_id
        for addon_id in prepared["addons"]
    }
    assign_addon_origins_in_kodi(
        adb,
        port,
        {"serial": serial, "addon_origins": origins},
        ROOT / "tools/kodi_profile_origin_device.py",
        timeout=180,
    )
    return {
        "schema": 1,
        "device": device_id,
        "channel": channel,
        "result": "pass",
        "lock_sha256": prepared["lock_sha256"],
        "kodi_preflight": kodi_preflight,
        "actions": actions,
    }


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--device", required=True)
    parser.add_argument("--adb", default="/home/mwo/android-sdk/platform-tools/adb")
    parser.add_argument("--adb-server-port", type=int, default=5038)
    parser.add_argument(
        "--channel", choices=("stable", "testing"), default="stable"
    )
    args = parser.parse_args()
    print(
        json.dumps(
            reconcile(
                args.device,
                args.adb,
                args.adb_server_port,
                args.channel,
            ),
            indent=2,
            sort_keys=True,
        )
    )


if __name__ == "__main__":
    main()
