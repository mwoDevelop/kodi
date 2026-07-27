#!/usr/bin/env python3
"""Validate WatchNixtoons2 catalogue and playback on a Sony Android TV."""

from __future__ import annotations

import argparse
import json
import re
import time
from pathlib import Path
from urllib.parse import quote

from sony_kodi_matrix import (
    JsonRpc,
    active_video_player,
    addon_version,
    ensure_kodi_foreground,
    kodi_version,
    log_line_count,
    log_since,
    playback_properties,
    redact,
    shell,
)

ADDON_ID = "plugin.video.watchnixtoons2.mwodevelop"

def playback_method(adb: str, serial: str) -> str | None:
    path = (
        "/sdcard/Android/data/org.xbmc.kodi/files/.kodi/userdata/addon_data/"
        + ADDON_ID
        + "/settings.xml"
    )
    payload = shell(
        adb,
        serial,
        "grep 'id=\"playbackMethod\"' '%s'" % path,
        check=False,
    )
    match = re.search(r">([^<]+)<", payload)
    return match.group(1) if match else None


def accept_quality_dialog(rpc: JsonRpc, timeout: int = 45) -> str | None:
    started = time.monotonic()
    while time.monotonic() - started < timeout:
        if active_video_player(rpc) is not None:
            return None
        gui = rpc.call(
            "GUI.GetProperties",
            {"properties": ["currentwindow", "currentcontrol"]},
        )
        window = gui.get("currentwindow", {}) if isinstance(gui, dict) else {}
        control = gui.get("currentcontrol", {}) if isinstance(gui, dict) else {}
        window_label = str(window.get("label", ""))
        control_label = str(control.get("label", ""))
        if "select quality" in window_label.casefold() or re.search(
            r"\b(?:480|720|1080)p?\b",
            control_label,
            re.IGNORECASE,
        ):
            rpc.call("Input.Select")
            return control_label
        time.sleep(0.5)
    return None


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--adb", required=True)
    parser.add_argument("--serial", default="192.168.1.12:5555")
    parser.add_argument("--host", default="192.168.1.12")
    parser.add_argument("--jsonrpc-port", type=int, default=9090)
    parser.add_argument("--content-path", default="mao-episode-17-english-subbed")
    parser.add_argument("--title", default="Mao Episode 17 English Subbed")
    parser.add_argument("--observe-seconds", type=int, default=15)
    parser.add_argument(
        "--result",
        default="docs/e2e-results/sony-watchnixtoons2.json",
    )
    args = parser.parse_args()

    rpc = JsonRpc(args.host, args.jsonrpc_port)
    ensure_kodi_foreground(args.adb, args.serial)
    if rpc.call("JSONRPC.Ping") != "pong":
        raise RuntimeError("Kodi JSON-RPC did not return pong")
    method = playback_method(args.adb, args.serial)
    if method not in (None, "0", "1", "2"):
        raise RuntimeError("unexpected WatchNixtoons2 playbackMethod: %r" % method)

    start_line = log_line_count(args.adb, args.serial) + 1
    root = rpc.call(
        "Files.GetDirectory",
        {
            "directory": "plugin://%s/" % ADDON_ID,
            "media": "files",
        },
    )
    root_items = root.get("files", []) if isinstance(root, dict) else []
    latest = next(
        (
            item
            for item in root_items
            if "latest releases" in str(item.get("label", "")).casefold()
        ),
        None,
    )
    if not latest:
        raise RuntimeError("Latest Releases menu was not available")
    menu_label = str(latest["label"])
    listing = rpc.call(
        "Files.GetDirectory",
        {
            "directory": latest["file"],
            "media": "files",
        },
    )
    catalogue = [
        str(item.get("label", "")).strip("[] ")
        for item in (
            listing.get("files", []) if isinstance(listing, dict) else []
        )[:16]
        if item.get("label")
    ]
    if not catalogue:
        raise RuntimeError("Latest Releases catalogue was empty")

    ensure_kodi_foreground(args.adb, args.serial)
    media_url = (
        "plugin://%s/?action=actionResolve&url=%s"
        % (ADDON_ID, quote("/" + args.content_path, safe=""))
    )
    rpc.call("Player.Open", {"item": {"file": media_url}})
    selected_quality = None
    if method in (None, "0"):
        selected_quality = accept_quality_dialog(rpc)

    started = time.monotonic()
    player_id = None
    while time.monotonic() - started < 75:
        player_id = active_video_player(rpc)
        if player_id is not None:
            break
        time.sleep(1)
    if player_id is None:
        raise RuntimeError("WatchNixtoons2 did not start playback")

    resolved_at = time.monotonic()
    initial = playback_properties(rpc, player_id)
    time.sleep(args.observe_seconds)
    final = playback_properties(rpc, player_id)
    rpc.call("Player.Stop", {"playerid": player_id})
    time.sleep(2)

    new_log = log_since(args.adb, args.serial, start_line)
    evidence = [
        redact(line)
        for line in new_log.splitlines()
        if any(
            marker in line
            for marker in (
                "VideoPlayer::OpenFile",
                "Creating InputStream",
                "Creating Demuxer",
                "Successful opened audio decoder",
            )
        )
    ][-20:]
    report = {
        "schema": 1,
        "device": {
            "serial": args.serial,
            "model": shell(
                args.adb,
                args.serial,
                "getprop ro.product.model",
            ).strip(),
            "kodi": kodi_version(args.adb, args.serial),
        },
        "addon": {
            "id": ADDON_ID,
            "version": addon_version(args.adb, args.serial, ADDON_ID),
            "playback_method": {
                None: "default_select_dialog",
                "0": "select_dialog",
                "1": "auto_highest",
                "2": "auto_lowest",
            }[method],
            "selected_quality": selected_quality,
        },
        "catalogue": {
            "menu": menu_label,
            "sample_count": len(catalogue),
            "sample": catalogue,
        },
        "playback": {
            "title": args.title,
            "content_path": args.content_path,
            "resolve_seconds": round(resolved_at - started, 3),
            "observed_seconds": args.observe_seconds,
            "initial": initial,
            "final": final,
            "log_evidence": evidence,
        },
        "result": "pass",
    }
    result = Path(args.result)
    result.parent.mkdir(parents=True, exist_ok=True)
    result.write_text(
        json.dumps(report, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    print(json.dumps(report, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
