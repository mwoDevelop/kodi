#!/usr/bin/env python3
"""Validate the allow-listed declarative Aeon Nox Silvo main menu."""

from __future__ import annotations

import copy
import json
import xml.etree.ElementTree as ET
from pathlib import Path

ADAPTER_ID = "kodi.skin_menu"
CAPABILITY = "skin-shortcuts-menu-v1"
MINIMUM_CLIENT_VERSION = "1.5.0"
EXPECTED_ITEMS = [
    {
        "id": "programs",
        "label": "$SKIN[31957|skin.aeon.nox.silvo|None]",
        "label2": "",
        "icon": "special://skin/extras/icons/DefaultAddon.png",
        "action": "ActivateWindow(1133)",
    },
    {
        "id": "settings",
        "label": "13000",
        "label2": "",
        "icon": "special://skin/extras/icons/DefaultAddonService.png",
        "action": "ActivateWindow(Settings)",
    },
    {
        "id": "favourites",
        "label": "Cartoons",
        "label2": "Custom item",
        "icon": "special://skin/extras/icons/Favorites.png",
        "action": "ActivateWindow(FavouritesBrowser)",
    },
    {
        "id": "playdisc",
        "label": "$SKIN[31958|skin.aeon.nox.silvo|None]",
        "label2": "",
        "icon": "special://skin/extras/icons/Disc.png",
        "action": "PlayDisc",
        "visible": "System.HasMediaDVD",
    },
]


def expected_document():
    return {
        "adapter": "skin_shortcuts_v1",
        "apply_mode": "hot_apply",
        "ownership": "whole_document",
        "skin_id": "skin.aeon.nox.silvo",
        "menu_id": "mainmenu",
        "items": copy.deepcopy(EXPECTED_ITEMS),
    }


def load_skin_menu(path):
    document = json.loads(Path(path).read_text(encoding="utf-8"))
    if document != expected_document():
        raise ValueError("skin menu differs from the allow-listed V1 contract")
    return document


def _source_items(payload):
    root = ET.fromstring(payload)
    if root.tag != "shortcuts":
        raise ValueError("skin menu source root differs")
    result = []
    mapping = {
        "defaultID": "id",
        "label": "label",
        "label2": "label2",
        "icon": "icon",
        "action": "action",
        "visible": "visible",
    }
    for shortcut in root.findall("shortcut"):
        values = {}
        for node in shortcut:
            if node.tag == "thumb":
                continue
            key = mapping.get(node.tag)
            if key is None or key in values:
                raise ValueError("skin menu source field differs")
            values[key] = node.text or ""
        result.append(values)
    return result


def _generated_items(payload):
    root = ET.fromstring(payload)
    include = root.find("./include[@name='skinshortcuts-mainmenu']")
    if include is None:
        raise ValueError("generated skin menu include is missing")
    result = []
    for item in include.findall("item"):
        unconditional = [
            node.text or ""
            for node in item.findall("onclick")
            if "condition" not in node.attrib
        ]
        conditioned = [
            (node.attrib.get("condition"), node.text or "")
            for node in item.findall("onclick")
            if "condition" in node.attrib
        ]
        if len(unconditional) != 1 or conditioned != [
            (
                "String.IsEqual(ListItem.Property(path),ActivateWindow(1129))",
                "SetProperty(CustomSelect,search,Home)",
            )
        ]:
            raise ValueError("generated skin menu actions differ")
        action = unconditional[0]
        paths = [
            node.text or ""
            for node in item.findall("property")
            if node.attrib.get("name") == "path"
        ]
        if paths != [action]:
            raise ValueError("generated skin menu path differs")
        visible = next(
            (
                node.text or ""
                for node in item.findall("visible")
                if (node.text or "") == "System.HasMediaDVD"
            ),
            "",
        )
        result.append(
            {
                "label": item.findtext("label", default=""),
                "label2": item.findtext("label2", default=""),
                "icon": item.findtext("icon", default=""),
                "action": action,
                "path": action,
                "visible": visible,
            }
        )
    return result


def _expected_generated(items):
    result = []
    for item in items:
        label = item["label"]
        if label.isdigit():
            label = "$LOCALIZE[%s]" % label
        elif label.startswith("$SKIN["):
            label = "$LOCALIZE[%s]" % label.split("[", 1)[1].split("|", 1)[0]
        result.append(
            {
                "label": label,
                "label2": item["label2"],
                "icon": item["icon"],
                "action": item["action"],
                "path": item["action"],
                "visible": item.get("visible", ""),
            }
        )
    return result


def probe_device(adb, port, serial):
    # Import lazily to keep the manifest/parser module independent from the
    # Android orchestration module.  The probe is deliberately executed inside
    # Kodi: app-private files written atomically can be unreadable to adb shell.
    from tools.kodi_portable_state_rollout import _profile_sync_probe

    observed = _profile_sync_probe(adb, port, serial)
    status = observed.get("skin_menu_probe_status")
    if status not in {"MATCH", "MISMATCH"}:
        raise RuntimeError("in-Kodi skin menu probe is unavailable: %s" % status)
    return {
        "source_match": observed.get("skin_menu_source_match") is True,
        "generated_match": observed.get("skin_menu_generated_match") is True,
        "source_items": observed.get("skin_menu_source_items"),
        "generated_items": observed.get("skin_menu_generated_items"),
    }
