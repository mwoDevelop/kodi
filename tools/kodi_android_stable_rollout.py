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
from tools.kodi_advancedsettings_policy import reconcile_android_advancedsettings
from tools.kodi_default_addons import addon_details
from tools.kodi_devices import load_registry, resolve_device, resolve_private_endpoint
from tools.kodi_inventory import load_private_references
from tools.kodi_retired_addons import reconcile_retired_addons
from tools.kodi_profile import (
    KODI_PACKAGE,
    _wait_for_kodi_ready,
    adb_command,
)
from tools.kodi_reinstall import (
    assign_addon_origins_in_kodi,
    installed_addon_origins_in_kodi,
)
from tools.kodi_stable_artifacts import prepare


ADDON_ORDER = (
    "script.module.mwoscrapers",
    "script.mwoscrapers",
    "plugin.video.umbrella",
    "plugin.video.watchnixtoons2.mwodevelop",
    "service.subtitles.opensubtitles-com",
    "service.mwodevelop.profilesync",
)


def reconcile_origins(adb, port, serial, prepared, channel):
    origins = desired_origins(prepared, channel)
    if not origins:
        return {"status": "NO_CHANGE", "origins": 0}
    current_origins = installed_addon_origins_in_kodi(
        adb,
        port,
        serial,
        origins,
        ROOT / "tools/kodi_profile_origin_device.py",
    )
    previous_origins, version_transitions = origin_transition(
        prepared, channel, origins, current_origins
    )
    assign_addon_origins_in_kodi(
        adb,
        port,
        {
            "serial": serial,
            "addon_origins": origins,
            "addon_previous_origins": previous_origins,
            "addon_version_transitions": version_transitions,
        },
        ROOT / "tools/kodi_profile_origin_device.py",
        timeout=180,
    )
    return {"status": "UPDATED", "origins": len(origins)}


def desired_origins(prepared, channel, stable_components=None):
    """Return only origins that the selected channel must own.

    Testing reuses stable artifacts for unchanged components. Keeping their
    stable origin avoids needless repository ownership churn and lets Kodi
    update them from the stable channel. Only artifacts that differ from the
    stable lock are owned by the testing repository.
    """
    if channel == "stable":
        return {addon_id: prepared["repository_id"] for addon_id in prepared["addons"]}
    if stable_components is None:
        stable_lock = json.loads(
            (ROOT / "manifests/locks/stable.json").read_text(encoding="utf-8")
        )
        stable_components = stable_lock["components"]
    return {
        addon_id: prepared["repository_id"]
        for addon_id, artifact in prepared["addons"].items()
        if stable_components.get(addon_id, {}).get("zip_sha256")
        != artifact.get("sha256")
    }


def origin_transition(
    prepared,
    channel,
    origins,
    current_origins,
    opposite_components=None,
):
    """Describe the only repository-origin transition allowed by a rollout."""
    if not origins:
        return {}, {}
    opposite_channel = "testing" if channel == "stable" else "stable"
    opposite_repository = (
        "repository.mwodevelop.testing"
        if opposite_channel == "testing"
        else "repository.mwodevelop"
    )
    if opposite_components is None:
        opposite_lock = json.loads(
            (ROOT / "manifests/locks" / (opposite_channel + ".json")).read_text(
                encoding="utf-8"
            )
        )
        opposite_components = opposite_lock["components"]
    previous = {}
    transitions = {}
    for addon_id in origins:
        current_origin = current_origins.get(addon_id)
        if current_origin in (None, "", prepared["repository_id"]):
            continue
        if current_origin != opposite_repository:
            raise RuntimeError("%s has an unexpected repository origin" % addon_id)
        previous[addon_id] = current_origin
        previous_version = opposite_components.get(addon_id, {}).get("version")
        target_version = prepared["addons"][addon_id]["version"]
        if previous_version and previous_version != target_version:
            transitions[addon_id] = {
                "from": previous_version,
                "to": target_version,
            }
    return previous, transitions


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


def reconcile(
    device_id,
    adb,
    port,
    channel="stable",
    devices_file=None,
    references_file=None,
):
    devices_file = (
        Path(devices_file) if devices_file else ROOT / ".kodi-private/devices.json"
    )
    references_file = Path(references_file) if references_file else ROOT / ".env"
    references = load_private_references(references_file)
    device = resolve_private_endpoint(
        resolve_device(load_registry(devices_file), device_id),
        references,
        required=True,
    )
    if device["platform"] not in {"android", "android-emulator"}:
        raise ValueError("Android stable rollout requires an Android device")
    serial = device["endpoints"]["adb"]
    advancedsettings = reconcile_android_advancedsettings(adb, port, serial)
    if advancedsettings["status"] == "UPDATED":
        adb_command(
            adb,
            port,
            serial,
            "shell",
            "am force-stop %s" % KODI_PACKAGE,
        )
        time.sleep(2)
    kodi_preflight = ensure_kodi_ready(adb, port, serial)
    retired_addons = reconcile_retired_addons(adb, port, serial)
    prepared = prepare(ROOT, channel=channel)
    repository_id = prepared["repository_id"]
    available = {
        repository_id: prepared["repository"],
        **prepared["addons"],
    }
    actions = []
    managed = tuple(addon_id for addon_id in ADDON_ORDER if addon_id in available)
    for addon_id in (repository_id, *managed):
        artifact = available[addon_id]
        current = addon_details(adb, port, serial, addon_id)
        if (
            current
            and current.get("enabled")
            and str(current.get("version")) == artifact["version"]
        ):
            actions.append(
                {
                    "addon": addon_id,
                    "action": "unchanged",
                    "version": artifact["version"],
                }
            )
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
        actions.append(
            {
                "addon": addon_id,
                "action": "installed",
                "version": artifact["version"],
                "repaired_orphan": bool(applied.get("repaired_orphan")),
            }
        )
    origin_result = reconcile_origins(adb, port, serial, prepared, channel)
    return {
        "schema": 1,
        "device": device_id,
        "channel": channel,
        "result": "pass",
        "lock_sha256": prepared["lock_sha256"],
        "kodi_preflight": kodi_preflight,
        "advancedsettings": advancedsettings,
        "retired_addons": retired_addons,
        "actions": actions,
        "origins": origin_result,
    }


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--device", required=True)
    parser.add_argument("--adb", default="/home/mwo/android-sdk/platform-tools/adb")
    parser.add_argument("--adb-server-port", type=int, default=5038)
    parser.add_argument("--channel", choices=("stable", "testing"), default="stable")
    parser.add_argument("--devices", help="private device registry path")
    parser.add_argument("--references", help="private endpoint references path")
    args = parser.parse_args()
    print(
        json.dumps(
            reconcile(
                args.device,
                args.adb,
                args.adb_server_port,
                args.channel,
                devices_file=args.devices,
                references_file=args.references,
            ),
            indent=2,
            sort_keys=True,
        )
    )


if __name__ == "__main__":
    main()
