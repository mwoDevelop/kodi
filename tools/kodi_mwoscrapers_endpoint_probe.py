#!/usr/bin/env python3
"""Run the sanitized mwoScrapers endpoint probe on Android Kodi devices."""

from __future__ import annotations

import argparse
import concurrent.futures
import json
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

REMOTE_SCRIPT = "/sdcard/Download/mwo-mwoscrapers-endpoint-probe.py"
REMOTE_REPORT = "/sdcard/Download/mwoscrapers-endpoint-probe.json"


def _read_report(adb, port, serial):
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
    if result.returncode == 0 and payload.startswith("{"):
        return json.loads(payload)
    return None


def _wait_report(adb, port, serial, deadline):
    while time.monotonic() < deadline:
        report = _read_report(adb, port, serial)
        if report is not None:
            return report
        time.sleep(1)
    return None


def _execute_probe(adb, port, serial, command, deadline):
    try:
        with AdbJsonRpcClient(adb, port, serial) as rpc:
            rpc.call(
                "XBMC.ExecuteBuiltin",
                {"command": command, "wait": False},
            )
        report = _wait_report(
            adb,
            port,
            serial,
            min(deadline, time.monotonic() + 12),
        )
    except (OSError, RuntimeError, TimeoutError):
        report = None
    events = AdbEventClient(adb, port, serial)
    while report is None and time.monotonic() < deadline:
        events.execute_builtin(command)
        report = _wait_report(
            adb,
            port,
            serial,
            min(deadline, time.monotonic() + 10),
        )
    return report


def probe(adb, port, serial, timeout):
    script = ROOT / "tests/e2e/kodi_mwoscrapers_endpoint_probe.py"
    try:
        adb_command(
            adb,
            port,
            serial,
            "push",
            str(script),
            REMOTE_SCRIPT,
            timeout=30,
        )
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
        deadline = time.monotonic() + timeout
        command = f"RunScript({REMOTE_SCRIPT},{REMOTE_REPORT})"
        report = _execute_probe(
            adb,
            port,
            serial,
            command,
            deadline,
        )
        if report is None:
            raise TimeoutError("Kodi endpoint probe timed out")
        if not report.get("ok"):
            raise RuntimeError(
                "Kodi probe failed: "
                f"{report.get('error_type', 'unknown')}"
            )
        return {"report": report, "serial": serial}
    except Exception as error:  # noqa: BLE001 - isolate each device result
        return {
            "error": str(error)[:200],
            "error_type": type(error).__name__,
            "serial": serial,
        }
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
        except Exception as cleanup_error:  # noqa: BLE001 - best effort
            del cleanup_error


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--adb", default="/home/mwo/android-sdk/platform-tools/adb"
    )
    parser.add_argument("--adb-server-port", type=int, default=5038)
    parser.add_argument("--serial", action="append", required=True)
    parser.add_argument("--timeout", type=float, default=60)
    args = parser.parse_args()
    with concurrent.futures.ThreadPoolExecutor(
        max_workers=min(4, len(args.serial))
    ) as pool:
        futures = [
            pool.submit(
                probe,
                args.adb,
                args.adb_server_port,
                serial,
                args.timeout,
            )
            for serial in args.serial
        ]
        results = [future.result() for future in futures]
    print(
        json.dumps(
            {"results": results, "schema": 1},
            indent=2,
            sort_keys=True,
        )
    )
    return 0 if all("report" in result for result in results) else 1


if __name__ == "__main__":
    raise SystemExit(main())
