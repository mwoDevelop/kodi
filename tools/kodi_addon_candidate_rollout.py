#!/usr/bin/env python3
"""Apply an exact local candidate ZIP to one Android Kodi runtime."""

from __future__ import annotations

import argparse
import base64
import json
import re
import subprocess
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
from tools.kodi_addon_runtime_compatibility import (
    assert_compatible,
    inspect_archive,
    load_policy,
)

REMOTE_SCRIPT = "/sdcard/Download/mwo-addon-transaction.py"
REMOTE_ZIP = "/sdcard/Download/mwo-addon-candidate.zip"
REMOTE_MARKER = "/sdcard/Download/mwo-addon-candidate-result.json"
POLICY_PATH = ROOT / "manifests/kodi-addon-runtime-compatibility.json"


def _restart_kodi(adb, port, serial):
    # Sleeping Android TV devices can accept ADB commands while refusing to
    # create Kodi's surface. Wake them before starting the package so the
    # post-install readiness check observes the real application lifecycle.
    adb_command(
        adb,
        port,
        serial,
        "shell",
        "input keyevent KEYCODE_WAKEUP",
        check=False,
    )
    adb_command(
        adb,
        port,
        serial,
        "shell",
        f"cmd package unsuspend {KODI_PACKAGE}",
        check=False,
    )
    adb_command(
        adb,
        port,
        serial,
        "shell",
        f"pm enable {KODI_PACKAGE}",
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
        try:
            result = _marker(adb, port, serial)
        except (OSError, subprocess.TimeoutExpired):
            result = None
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
        result = _wait_marker(
            adb,
            port,
            serial,
            min(deadline, time.monotonic() + 10),
        )
        if (
            result is None
            and time.monotonic() < deadline
            and hasattr(events, "execute_builtin_from_host")
        ):
            try:
                events.execute_builtin_from_host(command)
            except (OSError, RuntimeError, TimeoutError):
                pass
            else:
                result = _wait_marker(
                    adb,
                    port,
                    serial,
                    min(deadline, time.monotonic() + 10),
                )
    return result


def _application_version(value):
    if not isinstance(value, dict):
        raise RuntimeError("Kodi returned invalid application version facts")
    values = []
    for key in ("major", "minor"):
        item = value.get(key, 0)
        if not isinstance(item, int) or item < 0:
            raise RuntimeError("Kodi returned invalid application version facts")
        values.append(str(item))
    version = ".".join(values)
    revision = value.get("revision", 0)
    if isinstance(revision, int) and revision:
        version += ".%s" % revision
    elif isinstance(revision, str) and revision:
        if not re.fullmatch(r"[A-Za-z0-9.-]+", revision):
            raise RuntimeError(
                "Kodi returned invalid application version facts"
            )
        version += "+" + revision.replace("-", ".")
    elif revision not in {0, "", None}:
        raise RuntimeError("Kodi returned invalid application version facts")
    tag = value.get("tag", "")
    tag_version = value.get("tagversion", "")
    if tag and tag != "stable":
        version += "~%s%s" % (tag, tag_version)
    return version


def android_runtime_facts(adb, port, serial, platform="android"):
    with AdbJsonRpcClient(adb, port, serial) as rpc:
        application = rpc.call(
            "Application.GetProperties", {"properties": ["version"]}
        )
        addons = rpc.call(
            "Addons.GetAddons", {"properties": ["version", "enabled"]}
        ).get("addons", [])
    installed = {}
    for addon in addons:
        addon_id = addon.get("addonid")
        version = addon.get("version")
        enabled = addon.get("enabled")
        if (
            isinstance(addon_id, str)
            and isinstance(version, str)
            and isinstance(enabled, bool)
        ):
            installed[addon_id] = {"version": version, "enabled": enabled}
    package = adb_command(
        adb,
        port,
        serial,
        "shell",
        "dumpsys package %s" % KODI_PACKAGE,
        text=True,
        timeout=30,
    )
    primary = None
    for line in (package.stdout or "").splitlines():
        key, separator, value = line.strip().partition("=")
        if key == "primaryCpuAbi" and separator and value:
            primary = value
            break
    abilist = adb_command(
        adb,
        port,
        serial,
        "shell",
        "getprop ro.product.cpu.abilist",
        text=True,
        timeout=15,
    )
    abis = []
    for item in ([primary] if primary else []) + (
        (abilist.stdout or "").strip().split(",")
    ):
        if item and item not in abis:
            abis.append(item)
    return {
        "platform": platform,
        "kodi_version": _application_version(application.get("version")),
        "abis": abis,
        "installed_addons": installed,
    }


def _context(enabled, origin=None):
    payload = json.dumps(
        {"enabled": enabled, "origin": origin},
        sort_keys=True,
        separators=(",", ":"),
    ).encode("utf-8")
    return base64.urlsafe_b64encode(payload).decode("ascii").rstrip("=")


def _transaction_action(adb, port, serial, action, arguments, timeout):
    adb_command(
        adb,
        port,
        serial,
        "shell",
        "rm -f '%s'" % REMOTE_MARKER,
        check=False,
    )
    command = "RunScript(%s,%s,%s,%s)" % (
        REMOTE_SCRIPT,
        action,
        ",".join(str(item) for item in arguments),
        REMOTE_MARKER,
    )
    result = _execute(
        adb, port, serial, command, time.monotonic() + timeout
    )
    if result is None:
        raise TimeoutError("Kodi add-on transaction action timed out: %s" % action)
    if not result.get("ok"):
        raise RuntimeError(
            "Kodi add-on transaction failed: %s at %s: %s"
            % (
                result.get("error_type", "unknown"),
                result.get("error_stage", "unknown"),
                result.get("error", "unknown"),
            )
        )
    return result


def _verify_previous_addon(adb, port, serial, addon_id, previous, timeout=30):
    deadline = time.monotonic() + timeout
    observed = None
    while time.monotonic() < deadline:
        try:
            with AdbJsonRpcClient(adb, port, serial) as rpc:
                observed = rpc.call(
                    "Addons.GetAddonDetails",
                    {
                        "addonid": addon_id,
                        "properties": ["version", "enabled"],
                    },
                ).get("addon")
        except RuntimeError as error:
            if "code -32602" in str(error):
                observed = None
            else:
                time.sleep(1)
                continue
        if previous is None and observed is None:
            return
        if (
            previous is not None
            and observed is not None
            and str(observed.get("version")) == previous["version"]
            and bool(observed.get("enabled")) == previous["enabled"]
        ):
            return
        time.sleep(1)
    raise RuntimeError("rollback did not restore the previous Kodi add-on state")


def rollout(
    adb,
    port,
    serial,
    candidate,
    addon_id,
    version,
    timeout,
    repair_orphan=False,
    planned_versions=None,
    runtime_platform="android",
    policy_path=POLICY_PATH,
    inject_test_failure_after_activation=False,
):
    descriptor = inspect_archive(
        candidate,
        expected_id=addon_id,
        expected_version=version,
    )
    runtime = android_runtime_facts(
        adb, port, serial, platform=runtime_platform
    )
    compatibility = assert_compatible(
        [descriptor],
        runtime,
        load_policy(policy_path),
        planned_versions=planned_versions,
    )
    script = ROOT / "tools/device/kodi_addon_transaction.py"
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
    transaction_started = False
    previous = runtime["installed_addons"].get(addon_id)
    try:
        _wait_for_kodi_ready(adb, port, serial)
        status = _transaction_action(
            adb, port, serial, "status", [addon_id], min(timeout, 60)
        )
        if status.get("status") != "NO_CHANGE":
            _transaction_action(
                adb, port, serial, "rollback", [addon_id], min(timeout, 60)
            )
            adb_command(
                adb, port, serial, "shell", "am force-stop %s" % KODI_PACKAGE
            )
            _restart_kodi(adb, port, serial)
        arguments = [
            REMOTE_ZIP,
            addon_id,
            version,
            _context(
                previous.get("enabled") if previous else None,
                None,
            ),
        ]
        if repair_orphan:
            arguments.append("repair-orphan")
        result = _transaction_action(
            adb, port, serial, "prepare", arguments, timeout
        )
        transaction_started = True
        if inject_test_failure_after_activation:
            raise RuntimeError("injected failure after candidate activation")
        adb_command(
            adb,
            port,
            serial,
            "shell",
            f"am force-stop {KODI_PACKAGE}",
        )
        _restart_kodi(adb, port, serial)
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
            if str(addon.get("version")) == version and not addon.get(
                "enabled"
            ):
                with AdbJsonRpcClient(adb, port, serial) as rpc:
                    rpc.call(
                        "Addons.SetAddonEnabled",
                        {"addonid": addon_id, "enabled": True},
                    )
                time.sleep(1)
                continue
            if (
                str(addon.get("version")) == version
                and addon.get("enabled")
            ):
                break
            time.sleep(1)
        if str(addon.get("version")) != version or not addon.get("enabled"):
            raise RuntimeError("Kodi did not activate the candidate version")
        _transaction_action(
            adb,
            port,
            serial,
            "verify",
            [addon_id, version, _context(True, None)],
            min(timeout, 60),
        )
        committed = _transaction_action(
            adb, port, serial, "commit", [addon_id], min(timeout, 60)
        )
        transaction_started = False
        return {
            "addon": addon_id,
            "serial": serial,
            "compatibility": {
                "status": compatibility["status"],
                "policy_sha256": compatibility["policy_sha256"],
                "graph_sha256": compatibility["graph_sha256"],
            },
            **result,
            "transaction_status": committed["status"],
        }
    except Exception as error:
        try:
            recovery_status = _transaction_action(
                adb, port, serial, "status", [addon_id], min(timeout, 60)
            )
            if transaction_started or recovery_status.get("status") != "NO_CHANGE":
                _transaction_action(
                    adb, port, serial, "rollback", [addon_id], min(timeout, 60)
                )
                adb_command(
                    adb,
                    port,
                    serial,
                    "shell",
                    "am force-stop %s" % KODI_PACKAGE,
                    check=False,
                )
                _restart_kodi(adb, port, serial)
                AdbEventClient(adb, port, serial).execute_builtin(
                    "UpdateLocalAddons"
                )
                if previous is not None:
                    with AdbJsonRpcClient(adb, port, serial) as rpc:
                        rpc.call(
                            "Addons.SetAddonEnabled",
                            {
                                "addonid": addon_id,
                                "enabled": previous["enabled"],
                            },
                        )
                _verify_previous_addon(
                    adb, port, serial, addon_id, previous, timeout=30
                )
        except Exception as recovery_error:
            raise RuntimeError(
                "RECOVERY_REQUIRED after candidate failure: %s; rollback: %s"
                % (error, recovery_error)
            ) from error
        raise
    finally:
        try:
            adb_command(
                adb,
                port,
                serial,
                "shell",
                "rm -f "
                f"'{REMOTE_SCRIPT}' '{REMOTE_ZIP}' '{REMOTE_MARKER}'",
                check=False,
                timeout=10,
            )
        except (OSError, subprocess.TimeoutExpired):
            pass


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
    parser.add_argument(
        "--runtime-platform",
        choices=("android", "android-emulator"),
        default="android",
    )
    parser.add_argument(
        "--repair-orphan",
        action="store_true",
        help=(
            "remove an identity-verified orphan directory only when atomic "
            "backup is denied; caller must prove the add-on is not installed"
        ),
    )
    parser.add_argument(
        "--inject-test-failure-after-activation",
        action="store_true",
        help=argparse.SUPPRESS,
    )
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
        repair_orphan=args.repair_orphan,
        runtime_platform=args.runtime_platform,
        inject_test_failure_after_activation=(
            args.inject_test_failure_after_activation
        ),
    )
    print(json.dumps(result, indent=2, sort_keys=True))


if __name__ == "__main__":
    main()
