#!/usr/bin/env python3
"""Run a sanitized Profile Sync production configure/sync step on Android."""

from __future__ import annotations

import argparse
import hashlib
import json
import stat
import time
from pathlib import Path

from tools.kodi_devices import load_registry, resolve_device
from tools.kodi_profile import (
    AdbEventClient,
    AdbJsonRpcClient,
    adb_command,
    adb_output,
)


REMOTE_PROBE = "/sdcard/Download/.mwo-profile-sync-production-probe.py"
REMOTE_CONFIG = "/sdcard/Download/.mwo-profile-sync-production-config.json"
REMOTE_CA = "/sdcard/Download/.mwo-profile-sync-production-ca.pem"
REMOTE_MARKER = "/sdcard/Download/.mwo-profile-sync-production-result.json"


def execute_builtin(adb, port, serial, command):
    try:
        with AdbJsonRpcClient(adb, port, serial) as rpc:
            rpc.call(
                "XBMC.ExecuteBuiltin",
                {"command": command, "wait": False},
            )
        return "jsonrpc"
    except (OSError, RuntimeError, TimeoutError):
        AdbEventClient(adb, port, serial).execute_builtin(command)
        return "eventserver"


def execute_until_marker(
    adb,
    port,
    serial,
    command,
    read_marker,
    timeout=120,
    retry_seconds=12,
):
    deadline = time.monotonic() + timeout
    transports = []
    while time.monotonic() < deadline:
        transports.append(execute_builtin(adb, port, serial, command))
        attempt = min(deadline, time.monotonic() + retry_seconds)
        while time.monotonic() < attempt:
            result = read_marker()
            if result is not None:
                return result, "+".join(dict.fromkeys(transports))
            time.sleep(1)
    raise TimeoutError("Profile Sync production probe timed out")


def main():
    repository = Path(__file__).resolve().parents[2]
    parser = argparse.ArgumentParser()
    parser.add_argument("--device", required=True)
    parser.add_argument("--devices", type=Path, required=True)
    parser.add_argument("--server-url", required=True)
    parser.add_argument("--ca-certificate", type=Path, required=True)
    parser.add_argument("--pairing-file", type=Path)
    parser.add_argument("--channel", default="home-stable")
    parser.add_argument("--action", choices=("configure", "sync"), required=True)
    parser.add_argument("--read-only", action="store_true")
    parser.add_argument("--result", type=Path)
    parser.add_argument(
        "--adb", default="/home/mwo/android-sdk/platform-tools/adb"
    )
    parser.add_argument("--adb-server-port", type=int, default=5038)
    args = parser.parse_args()
    registry = load_registry(args.devices.resolve())
    device = resolve_device(registry, args.device)
    serial = device["endpoints"]["adb"]
    model = adb_output(
        args.adb,
        args.adb_server_port,
        serial,
        "shell",
        "getprop ro.product.model",
    ).strip()
    if model != device["expected"]["model"]:
        raise RuntimeError("device registry resolved to the wrong model")
    ca_payload = args.ca_certificate.resolve().read_bytes()
    config = {
        "action": args.action,
        "ca_source": REMOTE_CA,
        "ca_sha256": hashlib.sha256(ca_payload).hexdigest(),
        "server_url": args.server_url,
        "logical_device_id": args.device,
        "channel": args.channel,
        "read_only": args.read_only,
    }
    if args.pairing_file:
        pairing_path = args.pairing_file.resolve()
        if stat.S_IMODE(pairing_path.stat().st_mode) & 0o077:
            raise ValueError("pairing file permissions are too broad")
        pairing = json.loads(pairing_path.read_text(encoding="utf-8"))
        if (
            pairing.get("logical_device_id") != args.device
            or pairing.get("channel") != args.channel
        ):
            raise ValueError("pairing file identity differs")
        config["pairing_code"] = pairing["code"]
    local_config = repository / ".kodi-private/e2e/.production-config.json"
    local_config.parent.mkdir(parents=True, exist_ok=True)
    local_config.write_text(json.dumps(config), encoding="utf-8")
    local_config.chmod(0o600)
    try:
        for source, destination in (
            (repository / "tests/e2e/profile_sync_production_probe.py", REMOTE_PROBE),
            (local_config, REMOTE_CONFIG),
            (args.ca_certificate.resolve(), REMOTE_CA),
        ):
            adb_command(
                args.adb,
                args.adb_server_port,
                serial,
                "push",
                str(source),
                destination,
                text=True,
            )
        adb_command(
            args.adb,
            args.adb_server_port,
            serial,
            "shell",
            "rm -f '%s'" % REMOTE_MARKER,
            check=False,
        )
        def read_marker():
            marker = adb_command(
                args.adb,
                args.adb_server_port,
                serial,
                "shell",
                "cat '%s'" % REMOTE_MARKER,
                check=False,
                text=True,
            )
            if marker.returncode == 0 and marker.stdout.strip().startswith("{"):
                return json.loads(marker.stdout)
            return None

        result, launch_transport = execute_until_marker(
            args.adb,
            args.adb_server_port,
            serial,
            "RunScript(%s,%s,%s)"
            % (REMOTE_PROBE, REMOTE_CONFIG, REMOTE_MARKER),
            read_marker,
        )
        if not result.get("ok"):
            raise RuntimeError(
                "Profile Sync production probe failed: %s/%s"
                % (
                    result.get("error_type", "unknown"),
                    result.get("error_code", "unknown"),
                )
            )
        result.update(
            {
                "device": args.device,
                "launch_transport": launch_transport,
                "model": model,
                "result": "pass",
            }
        )
        rendered = json.dumps(result, indent=2, sort_keys=True)
        if args.result:
            destination = args.result.resolve()
            destination.parent.mkdir(parents=True, exist_ok=True)
            destination.write_text(rendered + "\n", encoding="utf-8")
            destination.chmod(0o600)
        print(rendered)
    finally:
        local_config.unlink(missing_ok=True)
        adb_command(
            args.adb,
            args.adb_server_port,
            serial,
            "shell",
            "rm -f '%s' '%s' '%s' '%s'"
            % (REMOTE_PROBE, REMOTE_CONFIG, REMOTE_CA, REMOTE_MARKER),
            check=False,
        )


if __name__ == "__main__":
    raise SystemExit(main())
