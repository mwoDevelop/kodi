#!/usr/bin/env python3
"""Render the read-only Control Plane dashboard in an existing Chrome CDP."""

from __future__ import annotations

import argparse
import base64
import hashlib
import json
import os
import socket
import struct
import threading
import time
import urllib.parse
import urllib.request
from http.server import ThreadingHTTPServer
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
CONTROL_PLANE = ROOT.parent / "kodi-control-plane"


def free_port():
    with socket.socket() as listener:
        listener.bind(("127.0.0.1", 0))
        return listener.getsockname()[1]


class DashboardService:
    def __init__(self):
        self.refreshes = 0

    def refresh_once(self, include_schedules=True):
        if include_schedules is not True:
            raise RuntimeError("manual refresh omitted schedules")
        self.refreshes += 1

    def dashboard(self):
        return {
            "schema": 1,
            "generated_at": int(time.time()),
            "overall_state": "DEGRADED",
            "fleet": {"total": 4, "online": 3, "stale_or_offline": 1, "revoked": 0},
            "services": {
                "services": [
                    {
                        "id": "profile-sync-fleet",
                        "state": "OK",
                        "last_success_at": int(time.time()),
                        "trust_level": "authenticated_observation",
                    }
                ]
            },
            "schedules": {
                "jobs": [
                    {
                        "id": "github-kodi-publish-pages",
                        "scheduler_status": "SEEN",
                        "run_result": "SUCCESS",
                        "freshness": "FRESH",
                        "next_expected": "2026-08-22T03:10:00Z",
                    }
                ]
            },
            "alerts": {"alerts": [{"fingerprint": "fixture:degraded"}]},
        }

    def schedules(self):
        return self.dashboard()["schedules"]

    def services(self):
        return self.dashboard()["services"]

    def alerts(self):
        return self.dashboard()["alerts"]


class AuditStore:
    def append_audit(self, _actor, _action, _details):
        return {"sequence": 1}


class WebSocket:
    def __init__(self, url):
        parsed = urllib.parse.urlparse(url)
        self.socket = socket.create_connection(
            (parsed.hostname, parsed.port), timeout=5
        )
        key = base64.b64encode(os.urandom(16)).decode("ascii")
        target = parsed.path + (("?" + parsed.query) if parsed.query else "")
        request = (
            f"GET {target} HTTP/1.1\r\n"
            f"Host: {parsed.hostname}:{parsed.port}\r\n"
            "Upgrade: websocket\r\nConnection: Upgrade\r\n"
            f"Sec-WebSocket-Key: {key}\r\nSec-WebSocket-Version: 13\r\n"
            "\r\n"
        )
        self.socket.sendall(request.encode("ascii"))
        response = b""
        while b"\r\n\r\n" not in response:
            response += self.socket.recv(4096)
        if not response.startswith(b"HTTP/1.1 101"):
            raise RuntimeError(
                "Chrome rejected the CDP WebSocket handshake: "
                + response.decode("utf-8", errors="replace")[:500]
            )
        expected = base64.b64encode(
            hashlib.sha1(
                (key + "258EAFA5-E914-47DA-95CA-C5AB0DC85B11").encode()
            ).digest()
        )
        if expected not in response:
            raise RuntimeError("invalid CDP WebSocket accept key")
        self.sequence = 0

    def _send(self, payload):
        data = payload.encode("utf-8")
        mask = os.urandom(4)
        length = len(data)
        header = bytearray([0x81])
        if length < 126:
            header.append(0x80 | length)
        elif length <= 65535:
            header.append(0x80 | 126)
            header.extend(struct.pack("!H", length))
        else:
            header.append(0x80 | 127)
            header.extend(struct.pack("!Q", length))
        header.extend(mask)
        header.extend(byte ^ mask[index % 4] for index, byte in enumerate(data))
        self.socket.sendall(header)

    def _exact(self, count):
        result = b""
        while len(result) < count:
            block = self.socket.recv(count - len(result))
            if not block:
                raise RuntimeError("CDP WebSocket closed")
            result += block
        return result

    def _receive(self):
        first, second = self._exact(2)
        opcode = first & 0x0F
        length = second & 0x7F
        if length == 126:
            length = struct.unpack("!H", self._exact(2))[0]
        elif length == 127:
            length = struct.unpack("!Q", self._exact(8))[0]
        masked = second & 0x80
        mask = self._exact(4) if masked else None
        payload = self._exact(length)
        if mask:
            payload = bytes(
                byte ^ mask[index % 4] for index, byte in enumerate(payload)
            )
        if opcode == 0x8:
            raise RuntimeError("CDP WebSocket closed")
        if opcode == 0x9:
            self._send(payload.decode("utf-8"))
            return self._receive()
        return json.loads(payload)

    def call(self, method, params=None):
        self.sequence += 1
        identity = self.sequence
        self._send(
            json.dumps({"id": identity, "method": method, "params": params or {}})
        )
        while True:
            message = self._receive()
            if message.get("id") == identity:
                if "error" in message:
                    raise RuntimeError(str(message["error"]))
                return message.get("result", {})

    def close(self):
        self.socket.close()


def main(argv=None):
    parser = argparse.ArgumentParser()
    parser.add_argument("--cdp", default="http://127.0.0.1:9222")
    args = parser.parse_args(argv)
    import sys

    sys.path.insert(0, str(CONTROL_PLANE / "src"))
    from kodi_control_plane.http import Handler

    class BrowserHandler(Handler):
        def _actor(self):
            return "e2e:chrome-cdp"

    BrowserHandler.surface = "api"
    dashboard_service = DashboardService()
    BrowserHandler.service = dashboard_service
    BrowserHandler.store = AuditStore()
    server = ThreadingHTTPServer(("127.0.0.1", free_port()), BrowserHandler)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    target = None
    websocket = None
    try:
        page = f"http://127.0.0.1:{server.server_port}/"
        request = urllib.request.Request(
            args.cdp + "/json/new?" + urllib.parse.quote(page, safe=""), method="PUT"
        )
        with urllib.request.urlopen(request, timeout=5) as response:
            target = json.load(response)
        websocket = WebSocket(target["webSocketDebuggerUrl"])
        websocket.call("Runtime.enable")
        deadline = time.monotonic() + 10
        value = None
        expression = "JSON.stringify({ready:document.readyState,overall:document.querySelector('#overall').textContent,total:document.querySelector('#fleet-total').textContent,services:document.querySelector('#services').textContent,schedules:document.querySelector('#schedules').textContent,error:document.querySelector('#error').textContent})"
        while time.monotonic() < deadline:
            result = websocket.call(
                "Runtime.evaluate", {"expression": expression, "returnByValue": True}
            )
            raw = result.get("result", {}).get("value")
            value = json.loads(raw) if raw else None
            if value and value["overall"] == "DEGRADED":
                break
            time.sleep(0.2)
        if not value or value["total"] != "4" or value["error"]:
            raise RuntimeError(f"dashboard did not render: {value}")
        if "profile-sync-fleet" not in value["services"]:
            raise RuntimeError("status sources were not rendered")
        if "github-kodi-publish-pages" not in value["schedules"]:
            raise RuntimeError("scheduled jobs were not rendered")
        websocket.call(
            "Runtime.evaluate",
            {"expression": "document.querySelector('#refresh').click()"},
        )
        deadline = time.monotonic() + 10
        while time.monotonic() < deadline and dashboard_service.refreshes != 1:
            time.sleep(0.1)
        if dashboard_service.refreshes != 1:
            raise RuntimeError("manual refresh did not force source collection")
        result = websocket.call(
            "Runtime.evaluate",
            {
                "expression": (
                    "JSON.stringify({"
                    "busy:document.querySelector('#refresh').getAttribute('aria-busy'),"
                    "error:document.querySelector('#error').textContent})"
                ),
                "returnByValue": True,
            },
        )
        refresh_state = json.loads(result["result"]["value"])
        if refresh_state != {"busy": "false", "error": ""}:
            raise RuntimeError(f"manual refresh did not complete: {refresh_state}")
        print(
            json.dumps(
                {
                    "schema": 1,
                    "status": "PASS",
                    "browser": "Chrome CDP",
                    "manual_refresh": "PASS",
                    **value,
                },
                sort_keys=True,
            )
        )
    finally:
        if websocket:
            websocket.close()
        if target:
            try:
                urllib.request.urlopen(
                    args.cdp + "/json/close/" + target["id"], timeout=2
                )
            except OSError:
                pass
        server.shutdown()
        server.server_close()
        thread.join(timeout=2)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
