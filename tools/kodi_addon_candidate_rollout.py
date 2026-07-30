#!/usr/bin/env python3
"""Apply an exact local candidate ZIP to one Android Kodi runtime."""

from __future__ import annotations

import argparse
import json
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from tools.kodi_profile import (
    KODI_PACKAGE,
    AdbEventClient,
    AdbJsonRpcClient,
    _wait_for_kodi_ready,
    adb_command,
)

REMOTE_SCRIPT = "/sdcard/Download/mwo-addon-candidate-apply.py"
REMOTE_ZIP = "/sdcard/Download/mwo-addon-candidate.zip"
REMOTE_MARKER = "/sdcard/Download/mwo-addon-candidate-result.json"


def _marker(adb, port, serial):
    result = adb_command(
        adb,
        port,
        serial,
        "shell",
        f"cat '{REMOTE_MARKER}'",
        check=False,
        text=True,
        timeout=10,
    )
    payload = (result.stdout or "").strip()
    return json.loads(payload) if payload.startswith("{") else None


def _wait_marker(adb, port, serial, deadline):
    while time.monotonic() < deadline:
        result = _marker(adb, port, serial)
        if result is not None:
            return result
        time.sleep(1)
    return None


def _execute(adb, port, serial, command, deadline):
    try:
        with AdbJsonRpcClient(adb, port, serial) as rpc:
            rpc.call(
                "XBMC.ExecuteBuiltin",
                {"command": command, "wait": False},
            )
        result = _wait_marker(
            adb,
            port,
            serial,
            min(deadline, time.monotonic() + 12),
        )
    except (OSError, RuntimeError, TimeoutError):
        result = None
    if result is None:
        AdbEventClient(adb, port, serial).execute_builtin(command)
        result = _wait_marker(adb, port, serial, deadline)
    return result


def rollout(adb, port, serial, candidate, addon_id, version, timeout):
    script = ROOT / "tests/e2e/kodi_addon_candidate_apply.py"
    for source, destination in (
        (script, REMOTE_SCRIPT),
        (candidate, REMOTE_ZIP),
    ):
        adb_command(
            adb,
            port,
            serial,
            "push",
            str(source),
            destination,
            timeout=60,
        )
    try:
        adb_command(
            adb,
            port,
            serial,
            "shell",
            f"rm -f '{REMOTE_MARKER}'",
            check=False,
        )
        _wait_for_kodi_ready(adb, port, serial)
        command = (
            f"RunScript({REMOTE_SCRIPT},{REMOTE_ZIP},"
            f"{addon_id},{version},{REMOTE_MARKER})"
        )
        result = _execute(
            adb,
            port,
            serial,
            command,
            time.monotonic() + timeout,
        )
        if result is None:
            raise TimeoutError("Kodi candidate rollout timed out")
        if not result.get("ok"):
            raise RuntimeError(
                "Kodi candidate apply failed: "
                f"{result.get('error_type', 'unknown')}"
            )
        adb_command(
            adb,
            port,
            serial,
            "shell",
            f"am force-stop {KODI_PACKAGE}",
        )
        adb_command(
            adb,
            port,
            serial,
            "shell",
            "monkey -p "
            f"{KODI_PACKAGE} -c android.intent.category.LAUNCHER "
            "1 >/dev/null",
        )
        _wait_for_kodi_ready(adb, port, serial)
        AdbEventClient(adb, port, serial).execute_builtin(
            "UpdateLocalAddons"
        )
        addon = {}
        version_deadline = time.monotonic() + 20
        while time.monotonic() < version_deadline:
            with AdbJsonRpcClient(adb, port, serial) as rpc:
                details = rpc.call(
                    "Addons.GetAddonDetails",
                    {
                        "addonid": addon_id,
                        "properties": ["version", "enabled"],
                    },
                )
            addon = details.get("addon", {})
            if (
                str(addon.get("version")) == version
                and addon.get("enabled")
            ):
                break
            time.sleep(1)
        if str(addon.get("version")) != version or not addon.get("enabled"):
            raise RuntimeError("Kodi did not activate the candidate version")
        return {"addon": addon_id, "serial": serial, **result}
    finally:
        adb_command(
            adb,
            port,
            serial,
            "shell",
            "rm -f "
            f"'{REMOTE_SCRIPT}' '{REMOTE_ZIP}' '{REMOTE_MARKER}'",
            check=False,
        )


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("candidate", type=Path)
    parser.add_argument("--addon-id", required=True)
    parser.add_argument("--version", required=True)
    parser.add_argument("--serial", required=True)
    parser.add_argument(
        "--adb", default="/home/mwo/android-sdk/platform-tools/adb"
    )
    parser.add_argument("--adb-server-port", type=int, default=5038)
    parser.add_argument("--timeout", type=float, default=120)
    args = parser.parse_args()
    candidate = args.candidate.resolve()
    if not candidate.is_file():
        parser.error("candidate ZIP does not exist")
    result = rollout(
        args.adb,
        args.adb_server_port,
        args.serial,
        candidate,
        args.addon_id,
        args.version,
        args.timeout,
    )
    print(json.dumps(result, indent=2, sort_keys=True))


if __name__ == "__main__":
    main()
