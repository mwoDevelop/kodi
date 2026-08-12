#!/usr/bin/env python3
"""Apply canonical mwoScrapers provider settings inside Android Kodi."""

from __future__ import annotations

import argparse
import base64
import json
import subprocess
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from tools.kodi_profile import (
    AdbEventClient,
    AdbJsonRpcClient,
    _wait_for_kodi_ready,
    adb_command,
)

REMOTE_SCRIPT = "/sdcard/Download/mwo-mwoscrapers-configure.py"
REMOTE_REPORT = "/sdcard/Download/mwo-mwoscrapers-configure.json"
PUBLIC_TORRENTIO = "https://torrentio.strem.fun"
PUBLIC_COMET = "https://comet.feels.legal"
PUBLIC_ENDPOINTS = {
    "torrentio": PUBLIC_TORRENTIO,
    "comet": PUBLIC_COMET,
    "torz": "https://stremthru.elfhosted.com/stremio/torz",
    "mediafusion": "https://mediafusionfortheweebs.midnightignite.me",
    "eztv": "https://eztvx.to",
    "piratebay": "https://apibay.org",
}
CANONICAL_PROVIDERS = tuple(PUBLIC_ENDPOINTS)


def _report(adb, port, serial):
    result = adb_command(
        adb,
        port,
        serial,
        "shell",
        f"cat '{REMOTE_REPORT}'",
        check=False,
        text=True,
        timeout=10,
    )
    payload = (result.stdout or "").strip()
    return json.loads(payload) if payload.startswith("{") else None


def _wait_report(adb, port, serial, deadline):
    while time.monotonic() < deadline:
        try:
            result = _report(adb, port, serial)
        except (OSError, subprocess.TimeoutExpired):
            result = None
        if result is not None:
            return result
        time.sleep(1)
    return None


def configure(
    adb,
    port,
    serial,
    torrentio_endpoint,
    comet_endpoint,
    timeout,
    enabled_providers=None,
    provider_endpoints=None,
):
    script = ROOT / "tests/e2e/kodi_mwoscrapers_configure.py"
    adb_command(adb, port, serial, "push", str(script), REMOTE_SCRIPT, timeout=30)
    try:
        adb_command(
            adb,
            port,
            serial,
            "shell",
            f"rm -f '{REMOTE_REPORT}'",
            check=False,
            timeout=10,
        )
        _wait_for_kodi_ready(adb, port, serial)
        endpoints = dict(PUBLIC_ENDPOINTS)
        endpoints.update(provider_endpoints or {})
        endpoints["torrentio"] = torrentio_endpoint.rstrip("/")
        endpoints["comet"] = comet_endpoint.rstrip("/")
        enabled = list(enabled_providers or CANONICAL_PROVIDERS)
        payload = json.dumps(
            {"enabled": enabled, "endpoints": endpoints},
            separators=(",", ":"),
            sort_keys=True,
        ).encode("utf-8")
        encoded = base64.urlsafe_b64encode(payload).rstrip(b"=").decode("ascii")
        command = f"RunScript({REMOTE_SCRIPT},{REMOTE_REPORT},{encoded})"
        deadline = time.monotonic() + timeout
        result = None
        try:
            with AdbJsonRpcClient(adb, port, serial) as rpc:
                rpc.call("XBMC.ExecuteBuiltin", {"command": command, "wait": False})
            result = _wait_report(
                adb, port, serial, min(deadline, time.monotonic() + 12)
            )
        except (OSError, RuntimeError, TimeoutError):
            result = None
        events = AdbEventClient(adb, port, serial)
        while result is None and time.monotonic() < deadline:
            try:
                events.execute_builtin(command)
            except (
                OSError,
                RuntimeError,
                TimeoutError,
                subprocess.TimeoutExpired,
            ):
                time.sleep(1)
                continue
            result = _wait_report(
                adb,
                port,
                serial,
                min(deadline, time.monotonic() + 10),
            )
        if result is None:
            raise TimeoutError("Kodi provider configuration timed out")
        if not result.get("ok"):
            error_type = result.get("error_type", "unknown")
            error_stage = result.get("error_stage", "unknown")
            raise RuntimeError(
                f"Kodi provider configuration failed: {error_type} at {error_stage}"
            )
        return {"serial": serial, **result}
    finally:
        try:
            adb_command(
                adb,
                port,
                serial,
                "shell",
                f"rm -f '{REMOTE_SCRIPT}' '{REMOTE_REPORT}'",
                check=False,
                timeout=10,
            )
        except (
            OSError,
            RuntimeError,
            TimeoutError,
            subprocess.TimeoutExpired,
        ):
            pass


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--serial", required=True)
    parser.add_argument(
        "--torrentio-endpoint", default=PUBLIC_TORRENTIO
    )
    parser.add_argument("--comet-endpoint", default=PUBLIC_COMET)
    parser.add_argument(
        "--enable-provider",
        action="append",
        choices=sorted(PUBLIC_ENDPOINTS),
        help=(
            "provider to enable; repeat as needed; defaults to the qualified set"
        ),
    )
    parser.add_argument(
        "--adb", default="/home/mwo/android-sdk/platform-tools/adb"
    )
    parser.add_argument("--adb-server-port", type=int, default=5038)
    parser.add_argument("--timeout", type=float, default=60)
    args = parser.parse_args()
    result = configure(
        args.adb,
        args.adb_server_port,
        args.serial,
        args.torrentio_endpoint,
        args.comet_endpoint,
        args.timeout,
        enabled_providers=args.enable_provider,
    )
    print(json.dumps(result, indent=2, sort_keys=True))


if __name__ == "__main__":
    main()
