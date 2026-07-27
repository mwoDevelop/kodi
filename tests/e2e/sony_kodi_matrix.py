#!/usr/bin/env python3
"""Run a redacted, reproducible Kodi resolver matrix on a Sony Android TV.

The test controls Kodi through its TCP JSON-RPC endpoint and uses ADB only for
device identity and log collection.  It does not read or write debrid tokens.
"""

from __future__ import annotations

import argparse
import base64
import json
import re
import socket
import struct
import subprocess
import time
from pathlib import Path
from urllib.parse import quote_plus, urlencode


KODI_ROOT = "/sdcard/Android/data/org.xbmc.kodi/files/.kodi"
ADDONS = {
    "plugin.video.umbrella",
    "plugin.video.watchnixtoons2.mwodevelop",
    "repository.mwodevelop",
    "script.module.mwoscrapers",
    "script.mwoscrapers",
}
CASES = {
    "sintel": {
        "media_type": "movie",
        "title": "Sintel",
        "year": 2010,
        "imdb": "tt1727587",
        "tmdb": "45745",
        "navigation": ["Sintel (2010)"],
    },
    "big_buck_bunny": {
        "media_type": "movie",
        "title": "Big Buck Bunny",
        "year": 2008,
        "imdb": "tt1254207",
        "tmdb": "10378",
        "navigation": ["Big Buck Bunny (2008)"],
    },
    "tears_of_steel": {
        "media_type": "movie",
        "title": "Tears of Steel",
        "year": 2012,
        "imdb": "tt2285752",
        "tmdb": "133792",
        "navigation": ["Tears of Steel (2012)"],
    },
    "the_matrix": {
        "media_type": "movie",
        "title": "The Matrix",
        "year": 1999,
        "imdb": "tt0133093",
        "tmdb": "603",
        "navigation": ["The Matrix (1999)"],
    },
    "interstellar": {
        "media_type": "movie",
        "title": "Interstellar",
        "year": 2014,
        "imdb": "tt0816692",
        "tmdb": "157336",
        "navigation": ["Interstellar (2014)"],
    },
    "breaking_bad_s01e01": {
        "media_type": "episode",
        "title": "Pilot",
        "tvshowtitle": "Breaking Bad",
        "year": 2008,
        "imdb": "tt0903747",
        "tmdb": "1396",
        "tvdb": "81189",
        "season": 1,
        "episode": 1,
        "premiered": "2008-01-20",
        "navigation": [
            "Breaking Bad",
            "Season 1",
            "Pilot",
        ],
    },
    "house_of_the_dragon_s01e01": {
        "media_type": "episode",
        "title": "The Heirs of the Dragon",
        "tvshowtitle": "House of the Dragon",
        "year": 2022,
        "imdb": "tt11198330",
        "tmdb": "94997",
        "tvdb": "371572",
        "season": 1,
        "episode": 1,
        "premiered": "2022-08-21",
        "navigation": [
            "House of the Dragon",
            "Season 1",
            "The Heirs of the Dragon",
        ],
    },
    "house_of_the_dragon_s03e01": {
        "media_type": "episode",
        "title": "Salt and Sea, Fire and Blood",
        "tvshowtitle": "House of the Dragon",
        "year": 2022,
        "imdb": "tt11198330",
        "tmdb": "94997",
        "tvdb": "371572",
        "season": 3,
        "episode": 1,
        "premiered": "2026-06-21",
        "navigation": [
            "House of the Dragon",
            "Season 3",
            "Salt and Sea, Fire and Blood",
        ],
    },
}
ERROR_TERMS = (
    " error ",
    "exception",
    "failed",
    "failure",
    "unplayable",
    "not supported",
    "timed out",
    "timeout",
)
DIAGNOSTIC_TERMS = (
    "umbrella",
    "mwoscraper",
    "torrentio",
    "real-debrid",
    "sourcesresolve",
    "videoplayer",
    "demux",
    "mediacodec",
)
TERMINAL_FAILURE_MARKERS = (
    "Playlist Player: skipping unplayable item",
    "Attempt to set unplayable index",
)


def run(adb: str, serial: str, *args: str, check: bool = True) -> str:
    completed = subprocess.run(
        [adb, "-s", serial, *args],
        check=check,
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
    )
    return completed.stdout or ""


def shell(adb: str, serial: str, command: str, check: bool = True) -> str:
    return run(adb, serial, "shell", command, check=check)


class JsonRpc:
    def __init__(self, host: str, port: int = 9090, timeout: float = 15.0):
        self.host = host
        self.port = port
        self.timeout = timeout
        self.request_id = 0

    def call(self, method: str, params: dict | None = None):
        self.request_id += 1
        request = {
            "jsonrpc": "2.0",
            "id": self.request_id,
            "method": method,
        }
        if params is not None:
            request["params"] = params
        with socket.create_connection((self.host, self.port), self.timeout) as sock:
            sock.settimeout(self.timeout)
            sock.sendall((json.dumps(request, separators=(",", ":")) + "\n").encode())
            payload = b""
            while True:
                chunk = sock.recv(65536)
                if not chunk:
                    raise RuntimeError("Kodi closed JSON-RPC before returning a result")
                payload += chunk
                try:
                    response = json.loads(payload)
                    break
                except json.JSONDecodeError:
                    continue
        if "error" in response:
            raise RuntimeError("%s: %r" % (method, response["error"]))
        return response.get("result")


class EventClient:
    """Minimal Kodi EventServer client for executing a PlayMedia builtin.

    Packet layout follows Kodi's GPL event client reference implementation:
    https://github.com/xbmc/xbmc/blob/master/tools/EventClients/lib/python/xbmcclient.py
    """

    HEADER_SIZE = 32
    MAX_PACKET_SIZE = 1024
    MAX_PAYLOAD_SIZE = MAX_PACKET_SIZE - HEADER_SIZE
    PT_HELO = 0x01
    PT_BYE = 0x02
    PT_BLOB = 0x08
    PT_ACTION = 0x0A
    ACTION_EXECBUILTIN = 0x01

    def __init__(self, host: str, port: int = 9777):
        self.address = (host, port)
        self.uid = int(time.time()) & 0xFFFFFFFF

    def _header(
        self,
        packet_type: int,
        sequence: int,
        packet_count: int,
        payload_size: int,
    ) -> bytes:
        return (
            b"XBMC"
            + bytes((2, 0))
            + struct.pack("!H", packet_type)
            + struct.pack("!I", sequence)
            + struct.pack("!I", packet_count)
            + struct.pack("!H", payload_size)
            + struct.pack("!I", self.uid)
            + (b"\0" * 10)
        )

    def _send(self, sock: socket.socket, packet_type: int, payload: bytes = b""):
        chunks = [
            payload[offset : offset + self.MAX_PAYLOAD_SIZE]
            for offset in range(0, len(payload), self.MAX_PAYLOAD_SIZE)
        ] or [b""]
        for index, chunk in enumerate(chunks, start=1):
            chunk_type = packet_type if index == 1 else self.PT_BLOB
            packet = self._header(chunk_type, index, len(chunks), len(chunk)) + chunk
            sock.sendto(packet, self.address)

    def execute_builtin(self, command: str):
        hello = (
            b"mwoDevelop Sony Kodi E2E\0"
            + bytes((0,))
            + struct.pack("!H", 0)
            + struct.pack("!I", 0)
            + struct.pack("!I", 0)
        )
        action = bytes((self.ACTION_EXECBUILTIN,)) + command.encode("utf-8") + b"\0"
        with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as sock:
            self._send(sock, self.PT_HELO, hello)
            self._send(sock, self.PT_ACTION, action)
            self._send(sock, self.PT_BYE)

    def play_media(self, media_url: str):
        self.execute_builtin("PlayMedia(%s)" % media_url)


class AdbEventClient(EventClient):
    """Send EventServer datagrams from inside an ADB-connected Android guest."""

    def __init__(
        self,
        adb: str,
        serial: str,
        host: str = "127.0.0.1",
        port: int = 9777,
        source_port: int = 40140,
    ):
        super().__init__(host, port)
        self.adb = adb
        self.serial = serial
        self.source_port = source_port

    def _packets(self, packet_type: int, payload: bytes = b"") -> list[bytes]:
        chunks = [
            payload[offset : offset + self.MAX_PAYLOAD_SIZE]
            for offset in range(0, len(payload), self.MAX_PAYLOAD_SIZE)
        ] or [b""]
        packets = []
        for index, chunk in enumerate(chunks, start=1):
            chunk_type = packet_type if index == 1 else self.PT_BLOB
            packets.append(
                self._header(chunk_type, index, len(chunks), len(chunk)) + chunk
            )
        return packets

    def execute_builtin(self, command: str):
        hello = (
            b"mwoDevelop Sony Kodi E2E\0"
            + bytes((0,))
            + struct.pack("!H", 0)
            + struct.pack("!I", 0)
            + struct.pack("!I", 0)
        )
        action = bytes((self.ACTION_EXECBUILTIN,)) + command.encode("utf-8") + b"\0"
        for packet_type, payload in (
            (self.PT_HELO, hello),
            (self.PT_ACTION, action),
            (self.PT_BYE, b""),
        ):
            for packet in self._packets(packet_type, payload):
                encoded = base64.b64encode(packet).decode("ascii")
                command_line = (
                    "echo %s | base64 -d | "
                    "nc -u -p %d -q 1 %s %d"
                    % (
                        encoded,
                        self.source_port,
                        self.address[0],
                        self.address[1],
                    )
                )
                run(
                    self.adb,
                    self.serial,
                    "shell",
                    command_line,
                )


def addon_version(adb: str, serial: str, addon_id: str) -> str | None:
    path = "%s/addons/%s/addon.xml" % (KODI_ROOT, addon_id)
    manifest = shell(adb, serial, "sed -n '1,5p' '%s'" % path, check=False)
    match = re.search(r'<addon[^>]+version="([^"]+)"', manifest.replace("\n", " "))
    return match.group(1) if match else None


def kodi_version(adb: str, serial: str) -> str | None:
    output = shell(adb, serial, "dumpsys package org.xbmc.kodi", check=False)
    match = re.search(r"versionName=([^\s]+)", output)
    return match.group(1) if match else None


def log_line_count(adb: str, serial: str, filename: str = "kodi.log") -> int:
    output = shell(
        adb,
        serial,
        "wc -l < '%s/temp/%s'" % (KODI_ROOT, filename),
        check=False,
    ).strip()
    return int(output) if output.isdigit() else 0


def log_since(
    adb: str,
    serial: str,
    first_line: int,
    filename: str = "kodi.log",
) -> str:
    return shell(
        adb,
        serial,
        "tail -n +%d '%s/temp/%s'"
        % (max(1, first_line), KODI_ROOT, filename),
        check=False,
    )


def redact(line: str) -> str:
    line = re.sub(
        r"(?i)(refreshing expired [^:]*token:).*",
        r"\1 <redacted>",
        line,
    )
    line = re.sub(r"magnet:\?[^\s<]+", "<redacted-magnet>", line)
    line = re.sub(r"plugin://[^\s\]]+", "<redacted-plugin-url>", line)
    line = re.sub(r"https?://[^\s<]+", "<redacted-url>", line)
    line = re.sub(
        r"(?i)(token|apikey|api_key|auth|password|secret)=([^&\s]+)",
        r"\1=<redacted>",
        line,
    )
    return line[:1200]


def diagnostic_lines(log_text: str) -> tuple[list[str], list[str]]:
    diagnostics = []
    errors = []
    for raw_line in log_text.splitlines():
        lower = " %s " % raw_line.lower()
        if any(term in lower for term in DIAGNOSTIC_TERMS):
            diagnostics.append(redact(raw_line))
        if any(term in lower for term in ERROR_TERMS):
            errors.append(redact(raw_line))
    return diagnostics[-120:], errors[-80:]


def terminal_failure_state(log_text: str) -> str | None:
    if any(marker in log_text for marker in TERMINAL_FAILURE_MARKERS):
        return "unplayable"
    return None


def plugin_url(case: dict, e2e_nonce: int | None = None) -> str:
    meta = {
        key: value
        for key, value in case.items()
        if key
        in {
            "media_type",
            "title",
            "tvshowtitle",
            "year",
            "imdb",
            "tmdb",
            "tvdb",
            "season",
            "episode",
            "premiered",
            "navigation",
        }
    }
    meta.pop("navigation", None)
    meta["mediatype"] = meta.pop("media_type")
    params = dict(case)
    params.pop("media_type")
    params.pop("navigation", None)
    params.update(
        {
            "action": "play_Item",
            "all_providers": "true",
            "meta": json.dumps(meta, separators=(",", ":")),
            "rescrape": "true",
            # Umbrella uses 1 for autoplay and 0 for its source selection window.
            "select": "1",
        }
    )
    if e2e_nonce is not None:
        params["e2e_nonce"] = str(e2e_nonce)
    return "plugin://plugin.video.umbrella/?%s" % urlencode(params)


def open_media(rpc: JsonRpc, media_url: str):
    """Open a plug-in URL over the same acknowledged transport used for polling."""
    rpc.call("Player.Open", {"item": {"file": media_url}})


def active_video_player(rpc: JsonRpc) -> int | None:
    players = rpc.call("Player.GetActivePlayers") or []
    for player in players:
        if player.get("type") == "video":
            return int(player["playerid"])
    return None


def stop_playback(rpc: JsonRpc):
    player_id = active_video_player(rpc)
    if player_id is not None:
        rpc.call("Player.Stop", {"playerid": player_id})
        time.sleep(2)
    try:
        rpc.call("Input.Back")
    except (OSError, RuntimeError):
        pass


def playback_properties(rpc: JsonRpc, player_id: int) -> dict:
    result = rpc.call(
        "Player.GetProperties",
        {
            "playerid": player_id,
            "properties": ["percentage", "speed", "time", "totaltime"],
        },
    )
    return result if isinstance(result, dict) else {}


def current_control_label(rpc: JsonRpc) -> str:
    result = rpc.call("GUI.GetProperties", {"properties": ["currentcontrol"]})
    if not isinstance(result, dict):
        return ""
    control = result.get("currentcontrol")
    return str(control.get("label", "")) if isinstance(control, dict) else ""


def focus_matching_control(
    rpc: JsonRpc,
    expected_label: str,
    timeout: int = 60,
) -> str:
    started = time.monotonic()
    last_label = ""
    while time.monotonic() - started < timeout:
        try:
            last_label = current_control_label(rpc)
            normalized_expected = re.sub(
                r"\s*\(\d{4}\)\s*$",
                "",
                expected_label,
            ).strip("[] ")
            normalized_actual = re.sub(
                r"\s*\(\d{4}\)\s*$",
                "",
                last_label,
            ).strip("[] ")
            normalized_actual = re.sub(
                r"^\d+x\d+\.\s*",
                "",
                normalized_actual,
                flags=re.IGNORECASE,
            )
            if normalized_expected.casefold() == normalized_actual.casefold():
                return last_label
            rpc.call("Input.Down")
        except (OSError, RuntimeError, socket.timeout):
            pass
        time.sleep(1)
    raise RuntimeError(
        "could not focus %r; last control was %r" % (expected_label, last_label)
    )


def open_case_through_gui(
    rpc: JsonRpc,
    events: EventClient,
    case: dict,
) -> list[str]:
    search_action = (
        "movieSearchterm" if case["media_type"] == "movie" else "tvSearchterm"
    )
    search_name = case["title"]
    if case["media_type"] == "episode":
        search_name = case["tvshowtitle"]
    directory = (
        "plugin://plugin.video.umbrella/?action=%s&name=%s"
        % (search_action, quote_plus(str(search_name)))
    )
    # Reset nested add-on navigation so every case starts from the same GUI state.
    events.execute_builtin("ActivateWindow(Home)")
    time.sleep(2)
    events.execute_builtin("ActivateWindow(Videos,%s,return)" % directory)
    # Network search plus metadata enrichment takes several seconds on this TV.
    time.sleep(8)

    visited = []
    navigation = list(case.get("navigation") or [])
    for index, expected_label in enumerate(navigation):
        selected = focus_matching_control(rpc, expected_label)
        visited.append(selected)
        rpc.call("Input.Select")
        if index != len(navigation) - 1:
            time.sleep(6)
    return visited


def run_case(
    rpc: JsonRpc,
    events: EventClient,
    adb: str,
    serial: str,
    case_name: str,
    case: dict,
    timeout: int,
    observe_seconds: int,
    direct_play: bool = False,
) -> dict:
    stop_playback(rpc)
    kodi_start_line = log_line_count(adb, serial) + 1
    umbrella_start_line = log_line_count(adb, serial, "umbrella.log") + 1
    started_at = time.monotonic()
    if direct_play:
        navigation = []
        rpc.call("GUI.ActivateWindow", {"window": "home"})
        time.sleep(2)
        open_media(rpc, plugin_url(case, e2e_nonce=time.time_ns()))
    else:
        navigation = open_case_through_gui(rpc, events, case)
    playback_started_at = None
    last_properties = {}
    state = "resolve_timeout"
    next_failure_probe = time.monotonic() + 4

    while time.monotonic() - started_at < timeout:
        try:
            player_id = active_video_player(rpc)
        except (OSError, RuntimeError, socket.timeout):
            time.sleep(2)
            continue
        if player_id is None:
            if playback_started_at is not None:
                state = "playback_stopped_early"
                break
            if time.monotonic() >= next_failure_probe:
                state = terminal_failure_state(
                    log_since(adb, serial, kodi_start_line)
                ) or state
                if state == "unplayable":
                    break
                next_failure_probe = time.monotonic() + 4
            time.sleep(2)
            continue
        if playback_started_at is None:
            playback_started_at = time.monotonic()
        try:
            last_properties = playback_properties(rpc, player_id)
        except (OSError, RuntimeError, socket.timeout):
            pass
        if time.monotonic() - playback_started_at >= observe_seconds:
            state = "played"
            break
        time.sleep(2)

    resolve_seconds = (
        round(playback_started_at - started_at, 3)
        if playback_started_at is not None
        else None
    )
    observed = (
        round(time.monotonic() - playback_started_at, 3)
        if playback_started_at is not None
        else 0
    )
    stop_playback(rpc)
    time.sleep(2)
    kodi_log = log_since(adb, serial, kodi_start_line)
    umbrella_log = log_since(
        adb,
        serial,
        umbrella_start_line,
        "umbrella.log",
    )
    diagnostics, errors = diagnostic_lines(kodi_log)
    resolver_diagnostics, resolver_errors = diagnostic_lines(umbrella_log)
    return {
        "case": case_name,
        "media_type": case["media_type"],
        "title": case["title"],
        "state": state,
        "resolve_seconds": resolve_seconds,
        "observed_seconds": observed,
        "player": last_properties,
        "navigation": navigation,
        "diagnostics": diagnostics,
        "errors": errors,
        "resolver_diagnostics": resolver_diagnostics,
        "resolver_errors": resolver_errors,
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--adb", required=True)
    parser.add_argument("--serial", default="192.168.1.12:5555")
    parser.add_argument("--host", default="192.168.1.12")
    parser.add_argument("--jsonrpc-port", type=int, default=9090)
    parser.add_argument(
        "--event-via-adb",
        action="store_true",
        help="send Kodi EventServer packets from inside the ADB target",
    )
    parser.add_argument("--case", action="append", choices=sorted(CASES))
    parser.add_argument("--timeout", type=int, default=300)
    parser.add_argument("--observe-seconds", type=int, default=20)
    parser.add_argument(
        "--direct-play",
        action="store_true",
        help="invoke Umbrella's autoplay URL without skin-dependent search navigation",
    )
    parser.add_argument(
        "--result",
        default="docs/e2e-results/sony-android-tv-resolver-matrix.json",
    )
    args = parser.parse_args()

    selected = args.case or list(CASES)
    rpc = JsonRpc(args.host, args.jsonrpc_port)
    events = (
        AdbEventClient(args.adb, args.serial)
        if args.event_via_adb
        else EventClient(args.host)
    )
    if rpc.call("JSONRPC.Ping") != "pong":
        raise RuntimeError("Kodi JSON-RPC did not return pong")

    report = {
        "schema": 1,
        "device": {
            "serial": args.serial,
            "manufacturer": shell(
                args.adb, args.serial, "getprop ro.product.manufacturer"
            ).strip(),
            "model": shell(args.adb, args.serial, "getprop ro.product.model").strip(),
            "android": shell(
                args.adb, args.serial, "getprop ro.build.version.release"
            ).strip(),
            "kodi": kodi_version(args.adb, args.serial),
        },
        "addons": {
            addon_id: addon_version(args.adb, args.serial, addon_id)
            for addon_id in sorted(ADDONS)
        },
        "settings": {
            "selection": "autoplay",
            "all_providers": True,
            "rescrape": True,
            "direct_play_transport": "jsonrpc",
            "tokens_collected": False,
        },
        "results": [],
    }
    for case_name in selected:
        print("Running %s..." % case_name, flush=True)
        result = run_case(
            rpc,
            events,
            args.adb,
            args.serial,
            case_name,
            CASES[case_name],
            args.timeout,
            args.observe_seconds,
            args.direct_play,
        )
        report["results"].append(result)
        print(
            "%s: %s (resolve=%s, observed=%s)"
            % (
                case_name,
                result["state"],
                result["resolve_seconds"],
                result["observed_seconds"],
            ),
            flush=True,
        )

    result_path = Path(args.result)
    result_path.parent.mkdir(parents=True, exist_ok=True)
    result_path.write_text(
        json.dumps(report, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    print("Wrote %s" % result_path)
    return 0 if all(item["state"] == "played" for item in report["results"]) else 1


if __name__ == "__main__":
    raise SystemExit(main())
