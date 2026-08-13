#!/usr/bin/env python3
"""Verify that Kodi exposes both subtitle services and defaults to .com."""

from __future__ import annotations

import argparse
import json
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))

from tools.kodi_profile import AdbEventClient, AdbJsonRpcClient

MODERN_ID = "service.subtitles.opensubtitles-com"
LEGACY_ID = "service.subtitles.opensubtitles"
TEST_MEDIA = "https://download.blender.org/durian/trailer/sintel_trailer-480p.mp4"
SUBTITLE_WINDOW_ID = 10153


def _enabled_subtitle_services(rpc):
    result = rpc.call(
        "Addons.GetAddons",
        {
            "type": "xbmc.subtitle.module",
            "properties": ["enabled", "name", "version"],
        },
    )
    return {
        addon["addonid"]: {
            "enabled": bool(addon.get("enabled")),
            "name": addon.get("name"),
            "version": addon.get("version"),
        }
        for addon in (result or {}).get("addons", [])
        if addon.get("addonid") in {MODERN_ID, LEGACY_ID}
    }


def _setting(rpc, setting_id):
    result = rpc.call("Settings.GetSettingValue", {"setting": setting_id})
    return result.get("value") if isinstance(result, dict) else None


def run_probe(rpc, events, timeout=30.0, media=TEST_MEDIA):
    services = _enabled_subtitle_services(rpc)
    missing = sorted({MODERN_ID, LEGACY_ID} - services.keys())
    disabled = sorted(
        addon_id
        for addon_id, details in services.items()
        if not details["enabled"]
    )
    if missing or disabled:
        raise RuntimeError(
            f"subtitle services unavailable: missing={missing} "
            f"disabled={disabled}"
        )

    defaults = {
        "movie": _setting(rpc, "subtitles.movie"),
        "tv": _setting(rpc, "subtitles.tv"),
    }
    if set(defaults.values()) != {MODERN_ID}:
        raise RuntimeError("OpenSubtitles.com is not the global default")

    player_id = None
    try:
        rpc.call("Player.Open", {"item": {"file": media}})
        deadline = time.monotonic() + timeout
        while time.monotonic() < deadline:
            players = rpc.call("Player.GetActivePlayers") or []
            video = next(
                (player for player in players if player.get("type") == "video"),
                None,
            )
            if video is not None:
                player_id = video["playerid"]
                break
            time.sleep(0.5)
        if player_id is None:
            raise RuntimeError("test video did not start")

        events.execute_builtin("ActivateWindow(subtitlesearch)")
        subtitle_window = None
        while time.monotonic() < deadline:
            result = rpc.call(
                "GUI.GetProperties", {"properties": ["currentwindow"]}
            )
            current = (result or {}).get("currentwindow") or {}
            if current.get("id") == SUBTITLE_WINDOW_ID:
                subtitle_window = current
                break
            time.sleep(0.5)
        if subtitle_window is None:
            raise RuntimeError("Kodi subtitle search window did not open")
    finally:
        if player_id is not None:
            rpc.call("Player.Stop", {"playerid": player_id})

    return {
        "ok": True,
        "schema": 1,
        "default_service": MODERN_ID,
        "defaults": defaults,
        "services": services,
        "subtitle_window": subtitle_window,
    }


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--adb", default="/home/mwo/android-sdk/platform-tools/adb"
    )
    parser.add_argument("--adb-server-port", type=int)
    parser.add_argument("--serial", required=True)
    parser.add_argument("--timeout", type=float, default=30.0)
    parser.add_argument("--media", default=TEST_MEDIA)
    args = parser.parse_args()

    with AdbJsonRpcClient(
        args.adb, args.adb_server_port, args.serial
    ) as rpc:
        report = run_probe(
            rpc,
            AdbEventClient(args.adb, args.adb_server_port, args.serial),
            timeout=args.timeout,
            media=args.media,
        )
    print(json.dumps(report, indent=2, sort_keys=True))


if __name__ == "__main__":
    main()
