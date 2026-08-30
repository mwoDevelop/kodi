#!/usr/bin/env python3
"""Reconcile a narrow, versioned set of managed Kodi add-on settings."""

from __future__ import annotations

import json
import re
import tempfile
import xml.etree.ElementTree as ET
from pathlib import Path

from tools.kodi_addon_settings_rollout import (
    load_setting_sources,
    rollout as rollout_settings,
)
from tools.kodi_profile import adb_command


SCHEMA = 1
SAFE_ID = re.compile(r"^[A-Za-z0-9._-]+$")
VERSION = re.compile(r"^[0-9]+(?:\.[0-9]+)*$")
KODI_ADDON_DATA = (
    "/sdcard/Android/data/org.xbmc.kodi/files/.kodi/userdata/addon_data"
)


def _version(value: str) -> tuple[int, ...]:
    if not isinstance(value, str) or not VERSION.fullmatch(value):
        raise ValueError("managed add-on setting has an invalid version")
    return tuple(int(part) for part in value.split("."))


def load_policy(path: Path) -> dict:
    document = json.loads(Path(path).read_text(encoding="utf-8"))
    if set(document) != {"schema", "addons"} or document["schema"] != SCHEMA:
        raise ValueError("managed add-on settings policy has an invalid schema")
    addons = document["addons"]
    if not isinstance(addons, dict) or not addons:
        raise ValueError("managed add-on settings policy has no add-ons")
    for addon_id, policy in addons.items():
        if not isinstance(addon_id, str) or not SAFE_ID.fullmatch(addon_id):
            raise ValueError("managed add-on settings policy has an invalid add-on ID")
        if not isinstance(policy, dict) or set(policy) != {
            "version_range",
            "settings",
        }:
            raise ValueError("managed add-on settings policy has an invalid entry")
        version_range = policy["version_range"]
        if not isinstance(version_range, dict) or set(version_range) != {
            "min_inclusive",
            "max_exclusive",
        }:
            raise ValueError("managed add-on settings policy has an invalid range")
        minimum = _version(version_range["min_inclusive"])
        maximum = _version(version_range["max_exclusive"])
        if minimum >= maximum:
            raise ValueError("managed add-on settings policy has an empty range")
        settings = policy["settings"]
        if (
            not isinstance(settings, dict)
            or not settings
            or any(
                not isinstance(setting_id, str)
                or not SAFE_ID.fullmatch(setting_id)
                or not isinstance(value, str)
                for setting_id, value in settings.items()
            )
        ):
            raise ValueError("managed add-on settings policy has invalid settings")
    return document


def applicable_settings(policy: dict, addon_versions: dict[str, str]) -> dict:
    selected = {}
    for addon_id, entry in sorted(policy["addons"].items()):
        installed = addon_versions.get(addon_id)
        if installed is None:
            continue
        current = _version(installed)
        version_range = entry["version_range"]
        if (
            _version(version_range["min_inclusive"])
            <= current
            < _version(version_range["max_exclusive"])
        ):
            selected[addon_id] = dict(sorted(entry["settings"].items()))
    return selected


def read_android_settings(adb, port, serial, addon_id) -> dict[str, str]:
    path = "%s/%s/settings.xml" % (KODI_ADDON_DATA, addon_id)
    result = adb_command(
        adb,
        port,
        serial,
        "shell",
        "cat '%s'" % path,
        check=False,
        text=True,
    )
    if result.returncode != 0 or not (result.stdout or "").strip():
        return {}
    root = ET.fromstring(result.stdout)
    values = {}
    for node in root.findall(".//setting"):
        setting_id = node.attrib.get("id")
        if setting_id:
            values[setting_id] = node.attrib.get("value", node.text or "")
    return values


def _write_sources(root: Path, desired: dict) -> list[str]:
    specifications = []
    for addon_id, settings in sorted(desired.items()):
        document = ET.Element("settings")
        for setting_id, value in sorted(settings.items()):
            node = ET.SubElement(document, "setting", {"id": setting_id})
            node.text = value
        path = root / (addon_id + ".xml")
        ET.ElementTree(document).write(path, encoding="utf-8", xml_declaration=True)
        specifications.append("%s=%s" % (addon_id, path))
    return specifications


def reconcile_android_managed_settings(
    adb,
    port,
    serial,
    addon_versions,
    policy_path,
    device_script,
):
    desired = applicable_settings(load_policy(policy_path), addon_versions)
    pending = {}
    managed_count = 0
    for addon_id, settings in desired.items():
        current = read_android_settings(adb, port, serial, addon_id)
        differences = {
            setting_id: value
            for setting_id, value in settings.items()
            if current.get(setting_id) != value
        }
        if differences:
            pending[addon_id] = differences
        managed_count += len(settings)
    if not pending:
        return {
            "status": "NO_CHANGE",
            "addons": len(desired),
            "settings": managed_count,
        }
    with tempfile.TemporaryDirectory(prefix="kodi-managed-settings-") as value:
        sources = load_setting_sources(_write_sources(Path(value), pending))
        rollout_settings(adb, port, serial, sources, Path(device_script))
    for addon_id, settings in desired.items():
        current = read_android_settings(adb, port, serial, addon_id)
        if any(current.get(setting_id) != value for setting_id, value in settings.items()):
            raise RuntimeError("managed add-on settings verification failed")
    return {
        "status": "UPDATED",
        "addons": len(desired),
        "settings": managed_count,
        "changed_addons": sorted(pending),
        "changed_settings": sum(len(item) for item in pending.values()),
    }
