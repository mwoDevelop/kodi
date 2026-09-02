#!/usr/bin/env python3
"""Validate the allow-listed declarative Aeon Nox Silvo main menu."""

from __future__ import annotations

import copy
import json
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
