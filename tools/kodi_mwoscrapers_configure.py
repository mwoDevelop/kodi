#!/usr/bin/env python3
"""Apply canonical mwoScrapers provider settings inside Android Kodi."""

from __future__ import annotations

import argparse
import json
import subprocess
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from tools.kodi_profile import (  # noqa: E402
    AdbEventClient,
    AdbJsonRpcClient,
    _wait_for_kodi_ready,
    adb_command,
)

REMOTE_SCRIPT = "/sdcard/Download/mwo-mwoscrapers-configure.py"
REMOTE_REPORT = "/sdcard/Download/mwo-mwoscrapers-configure.json"
PUBLIC_TORRENTIO = "https://torrentio.strem.fun"
PUBLIC_COMET = "https://comet.feels.legal"


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


def configure(adb, port, serial, torrentio_endpoint, comet_endpoint, timeout):
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
        command = "RunScript(%s,%s,%s,%s)" % (
            REMOTE_SCRIPT,
            REMOTE_REPORT,
            torrentio_endpoint.rstrip("/"),
            comet_endpoint.rstrip("/"),
        )
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
            raise RuntimeError(
                "Kodi provider configuration failed: %s at %s"
                % (
                    result.get("error_type", "unknown"),
                    result.get("error_stage", "unknown"),
                )
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
    )
    print(json.dumps(result, indent=2, sort_keys=True))


if __name__ == "__main__":
    main()
