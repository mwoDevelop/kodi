#!/usr/bin/env python3
"""Run a redacted long-enough YouTube playback probe through Android Kodi."""

from __future__ import annotations

import argparse
import hashlib
import json
import re
import sys
import time
from itertools import pairwise
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from tools.kodi_managed_addon_settings import (
    read_android_settings,
)
from tools.kodi_profile import (
    AdbJsonRpcClient,
    _wait_for_kodi_ready,
    adb_command,
)

KODI_LOG = (
    "/sdcard/Android/data/org.xbmc.kodi/files/.kodi/temp/kodi.log"
)
VIDEO_ID = re.compile(r"^[A-Za-z0-9_-]{11}$")
RPC_GRACE_SECONDS = 15


def _clock_seconds(value: dict) -> float:
    return (
        int(value.get("hours", 0)) * 3600
        + int(value.get("minutes", 0)) * 60
        + int(value.get("seconds", 0))
        + int(value.get("milliseconds", 0)) / 1000
    )


def diagnostic_counts(log_text: str) -> dict[str, int]:
    patterns = {
        "http_403": r"(?:HTTP error|Status:)[^\n]*403|403 (?:Client Error|Forbidden)",
        "segment_download_failed": r"Segment download failed|Download failed",
        "large_audio_sync_error": r"large audio sync error",
        "stillframe": r"Stillframe detected",
        "android_vr_client": r"Client:\s*28(?:\s|\(|\|)",
    }
    return {
        name: len(re.findall(pattern, log_text, flags=re.IGNORECASE))
        for name, pattern in patterns.items()
    }


def stalled_intervals(samples: list[dict]) -> int:
    return sum(
        1
        for before, after in pairwise(samples)
        if before["media_seconds"] >= 1
        and after["wall_seconds"] - before["wall_seconds"] >= 1
        and after["media_seconds"] - before["media_seconds"] < 0.5
    )


def successful_probe(report: dict, minimum_progress: float) -> bool:
    diagnostics = report["diagnostics"]
    return (
        report["state"] == "played"
        and report["media_progress_seconds"] >= minimum_progress
        and report["stalled_intervals"] == 0
        and all(value == 0 for value in diagnostics.values())
    )


def _log_lines(adb: str, port: int, serial: str) -> list[str]:
    result = adb_command(
        adb,
        port,
        serial,
        "shell",
        f"cat '{KODI_LOG}'",
        check=False,
        text=True,
    )
    return (result.stdout or "").splitlines()


def probe(
    adb: str,
    port: int,
    serial: str,
    video_id: str,
    observe_seconds: int,
    poll_seconds: float = 2.0,
) -> dict:
    if not VIDEO_ID.fullmatch(video_id):
        raise ValueError("invalid YouTube video id")
    if observe_seconds < 80:
        raise ValueError("YouTube probe must cross the known segment cutoff")
    adb_command(
        adb,
        port,
        serial,
        "shell",
        "input keyevent KEYCODE_WAKEUP; "
        "monkey -p org.xbmc.kodi -c android.intent.category.LAUNCHER 1 >/dev/null",
    )
    _wait_for_kodi_ready(adb, port, serial)
    start_line = len(_log_lines(adb, port, serial))
    started_at = time.monotonic()
    first_player_at = None
    rpc_unavailable_at = None
    samples = []
    state = "not_started"
    with AdbJsonRpcClient(adb, port, serial) as rpc:
        for player in rpc.call("Player.GetActivePlayers") or []:
            rpc.call("Player.Stop", {"playerid": player["playerid"]})
        rpc.call(
            "Player.Open",
            {
                "item": {
                    "file": "plugin://plugin.video.youtube/play/?video_id="
                    + video_id
                }
            },
        )
        deadline = started_at + observe_seconds + 30
        while time.monotonic() < deadline:
            now = time.monotonic()
            try:
                players = [
                    item
                    for item in (rpc.call("Player.GetActivePlayers") or [])
                    if item.get("type") == "video"
                ]
            except (OSError, RuntimeError, TimeoutError):
                if rpc_unavailable_at is None:
                    rpc_unavailable_at = now
                elif now - rpc_unavailable_at >= RPC_GRACE_SECONDS:
                    state = "jsonrpc_unavailable"
                    break
                time.sleep(poll_seconds)
                continue
            rpc_unavailable_at = None
            if not players:
                if first_player_at is not None:
                    state = "stopped_early"
                    break
                time.sleep(poll_seconds)
                continue
            if first_player_at is None:
                first_player_at = now
            try:
                properties = rpc.call(
                    "Player.GetProperties",
                    {
                        "playerid": players[0]["playerid"],
                        "properties": [
                            "time",
                            "speed",
                            "percentage",
                            "cachepercentage",
                        ],
                    },
                )
            except (OSError, RuntimeError, TimeoutError):
                time.sleep(poll_seconds)
                continue
            samples.append(
                {
                    "wall_seconds": round(now - started_at, 3),
                    "media_seconds": round(
                        _clock_seconds(properties.get("time", {})), 3
                    ),
                    "speed": properties.get("speed"),
                    "cache_percentage": properties.get("cachepercentage"),
                }
            )
            if now - first_player_at >= observe_seconds:
                state = "played"
                break
            time.sleep(poll_seconds)
        try:
            players = rpc.call("Player.GetActivePlayers") or []
        except (OSError, RuntimeError, TimeoutError):
            players = []
        for player in players:
            try:
                rpc.call("Player.Stop", {"playerid": player["playerid"]})
            except (OSError, RuntimeError, TimeoutError):
                pass
    log_text = "\n".join(_log_lines(adb, port, serial)[start_line:])
    progress = (
        samples[-1]["media_seconds"] - samples[0]["media_seconds"]
        if len(samples) >= 2
        else 0
    )
    settings = read_android_settings(
        adb, port, serial, "plugin.video.youtube"
    )
    report = {
        "schema": 1,
        "device": serial,
        "video_sha256": hashlib.sha256(video_id.encode()).hexdigest(),
        "observe_seconds": observe_seconds,
        "state": state,
        "start_delay_seconds": None
        if first_player_at is None
        else round(first_player_at - started_at, 3),
        "media_progress_seconds": round(progress, 3),
        "stalled_intervals": stalled_intervals(samples),
        "mpd_videos": settings.get("kodion.mpd.videos"),
        "diagnostics": diagnostic_counts(log_text),
        "samples": samples[::5] + (samples[-1:] if samples else []),
    }
    report["result"] = (
        "pass"
        if successful_probe(report, observe_seconds * 0.8)
        else "fail"
    )
    return report


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--adb", default="/home/mwo/android-sdk/platform-tools/adb"
    )
    parser.add_argument("--adb-server-port", type=int, default=5038)
    parser.add_argument("--serial", required=True)
    parser.add_argument("--video-id", default="aqz-KE-bpKQ")
    parser.add_argument("--observe-seconds", type=int, default=100)
    parser.add_argument("--result")
    args = parser.parse_args()
    report = probe(
        args.adb,
        args.adb_server_port,
        args.serial,
        args.video_id,
        args.observe_seconds,
    )
    payload = json.dumps(report, indent=2, sort_keys=True) + "\n"
    if args.result:
        Path(args.result).write_text(payload, encoding="utf-8")
    print(payload, end="")
    return 0 if report["result"] == "pass" else 1


if __name__ == "__main__":
    raise SystemExit(main())
