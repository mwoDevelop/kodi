#!/usr/bin/env python3
"""Run the sanitized MwoScrapers provider matrix inside Android Kodi."""

import argparse
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

REMOTE_SCRIPT = "/sdcard/Download/mwo-mwoscrapers-probe.py"
REMOTE_REPORT = "/sdcard/Download/mwo-mwoscrapers-probe.json"
EXPECTED_PROVIDERS = {
    "comet",
    "eztv",
    "mediafusion",
    "piratebay",
    "torrentio",
    "torz",
}
EXPECTED_CASES = {
    "movie-sintel": "movie",
    "movie-big-buck-bunny": "movie",
    "movie-older": "movie",
    "movie-non-english": "movie",
    "episode-breaking-bad-s01e01": "episode",
    "episode-game-of-thrones-s01e01": "episode",
    "negative-breaking-bad-s99e99": "negative",
}


def _validate(report):
    rows = report.get("probe")
    capabilities = report.get("capabilities")
    if not isinstance(rows, list) or not isinstance(capabilities, dict):
        raise TypeError("Kodi provider probe report is incomplete")
    if set(capabilities) != EXPECTED_PROVIDERS:
        raise RuntimeError("Kodi provider registry differs from the release set")
    observed_cases = [
        (row.get("provider"), row.get("case"), row.get("kind"))
        for row in rows
        if isinstance(row, dict)
    ]
    expected_cases = {
        (provider, case, kind)
        for provider in EXPECTED_PROVIDERS
        for case, kind in EXPECTED_CASES.items()
    }
    if len(observed_cases) != len(expected_cases) or set(observed_cases) != expected_cases:
        raise RuntimeError("Kodi provider probe matrix is incomplete or duplicated")
    errors = [
        row
        for row in rows
        if row.get("error_type") is not None
        or not isinstance(row.get("result_count"), int)
    ]
    if errors:
        raise RuntimeError("Kodi provider probe contains network or contract errors")
    for row in rows:
        if row.get("kind") == "negative" and row.get("result_count") != 0:
            raise RuntimeError("Kodi provider returned a false-positive episode")
    for provider, supported in capabilities.items():
        provider_rows = [row for row in rows if row.get("provider") == provider]
        for case, kind in EXPECTED_CASES.items():
            if kind == "negative" or not supported.get(f"{kind}s"):
                continue
            matching = [
                row
                for row in provider_rows
                if row.get("case") == case and row.get("kind") == kind
            ]
            if len(matching) != 1 or matching[0].get("result_count", 0) <= 0:
                raise RuntimeError(
                    f"Kodi provider has no {kind} coverage for {case}: {provider}"
                )


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
    if not payload.startswith("{"):
        return None
    try:
        return json.loads(payload)
    except json.JSONDecodeError:
        return None


def _wait_report(adb, port, serial, deadline):
    while time.monotonic() < deadline:
        report = _report(adb, port, serial)
        if report is not None:
            return report
        time.sleep(1)
    return None


def _dispatch_and_wait(adb, port, serial, command, deadline):
    report = None
    try:
        with AdbJsonRpcClient(adb, port, serial) as rpc:
            rpc.call("XBMC.ExecuteBuiltin", {"command": command, "wait": False})
    except (OSError, RuntimeError, TimeoutError):
        pass
    else:
        report = _wait_report(
            adb, port, serial, min(deadline, time.monotonic() + 20)
        )
    if report is not None:
        return report

    events = AdbEventClient(adb, port, serial)
    try:
        events.execute_builtin(command)
        report = _wait_report(
            adb, port, serial, min(deadline, time.monotonic() + 20)
        )
    except (OSError, RuntimeError, TimeoutError, subprocess.TimeoutExpired):
        report = None
    if report is not None:
        return report

    try:
        events.execute_builtin_from_host(command)
    except (OSError, RuntimeError, TimeoutError):
        return None
    return _wait_report(adb, port, serial, deadline)


def probe(adb, port, serial, timeout):
    script = ROOT / "tests/e2e/kodi_mwoscrapers_probe.py"
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
        command = f"RunScript({REMOTE_SCRIPT},{REMOTE_REPORT})"
        deadline = time.monotonic() + timeout
        report = _dispatch_and_wait(adb, port, serial, command, deadline)
        if report is None:
            raise TimeoutError("Kodi MwoScrapers probe timed out")
        if report.get("registry_error"):
            raise RuntimeError(
                f"Kodi provider registry failed: {report['registry_error']}"
            )
        _validate(report)
        return {"schema": 1, "serial": serial, "report": report}
    finally:
        try:
            adb_command(
                adb,
                port,
                serial,
                "shell",
                f"rm -f '{REMOTE_SCRIPT}' '{REMOTE_REPORT}' '{REMOTE_REPORT}.tmp'",
                check=False,
                timeout=10,
            )
        except (OSError, subprocess.TimeoutExpired):
            pass


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--serial", required=True)
    parser.add_argument(
        "--adb", default="/home/mwo/android-sdk/platform-tools/adb"
    )
    parser.add_argument("--adb-server-port", type=int, default=5038)
    parser.add_argument("--timeout", type=float, default=120)
    parser.add_argument("--result", type=Path)
    args = parser.parse_args()
    result = probe(
        args.adb,
        args.adb_server_port,
        args.serial,
        args.timeout,
    )
    rendered = json.dumps(result, indent=2, sort_keys=True) + "\n"
    if args.result:
        args.result.parent.mkdir(parents=True, exist_ok=True)
        args.result.write_text(rendered, encoding="utf-8")
    print(rendered, end="")


if __name__ == "__main__":
    main()
