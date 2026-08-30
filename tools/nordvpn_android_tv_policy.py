#!/usr/bin/env python3
"""Audit a non-secret NordVPN Android TV split-tunnel policy over ADB."""

from __future__ import annotations

import argparse
import json
import os
import re
import subprocess
from pathlib import Path

SCHEMA = 1
DEVICE_ID = re.compile(r"^[a-z0-9][a-z0-9._-]{0,63}$")
PACKAGE = re.compile(r"^[A-Za-z0-9_]+(?:\.[A-Za-z0-9_]+)+$")
ANDROID_USER_UID_MIN = 0
ANDROID_USER_UID_MAX = 99999
FIRST_APPLICATION_UID = 10000
LAST_APPLICATION_UID = 19999
SDK_SANDBOX_UID_OFFSET = 10000
SDK_SANDBOX_MIN_API = 33


def _require_string(value, label):
    if not isinstance(value, str) or not value:
        raise ValueError(f"{label} must be a non-empty string")
    return value


def _validate_packages(value, label):
    if (
        not isinstance(value, list)
        or not value
        or len(value) != len(set(value))
        or any(
            not isinstance(item, str) or not PACKAGE.fullmatch(item) for item in value
        )
    ):
        raise ValueError(f"{label} must contain unique Android package names")
    return value


def validate_profile(document):
    if not isinstance(document, dict) or set(document) != {
        "schema",
        "device_id",
        "platform",
        "expected",
        "vpn",
    }:
        raise ValueError("NordVPN policy has unsupported or missing fields")
    if document["schema"] != SCHEMA:
        raise ValueError("unsupported NordVPN policy schema")
    if not DEVICE_ID.fullmatch(_require_string(document["device_id"], "device_id")):
        raise ValueError("invalid device_id")
    if document["platform"] != "android-tv":
        raise ValueError("NordVPN policy supports only Android TV")
    expected = document["expected"]
    if not isinstance(expected, dict) or set(expected) != {"model", "android_user_id"}:
        raise ValueError("expected has unsupported or missing fields")
    _require_string(expected["model"], "expected model")
    if expected["android_user_id"] != 0:
        raise ValueError("only the primary Android user is supported")
    vpn = document["vpn"]
    required_vpn = {
        "package",
        "split_tunneling",
        "excluded_packages",
        "required_tunneled_packages",
        "require_active_validated_tunnel",
    }
    if not isinstance(vpn, dict) or set(vpn) != required_vpn:
        raise ValueError("vpn has unsupported or missing fields")
    if vpn["package"] != "com.nordvpn.android":
        raise ValueError("vpn package must be the native NordVPN client")
    if vpn["split_tunneling"] is not True:
        raise ValueError("split_tunneling must be enabled")
    excluded = _validate_packages(vpn["excluded_packages"], "excluded_packages")
    tunneled = _validate_packages(
        vpn["required_tunneled_packages"], "required_tunneled_packages"
    )
    if set(excluded) & set(tunneled):
        raise ValueError("a package cannot be both excluded and tunneled")
    if not isinstance(vpn["require_active_validated_tunnel"], bool):
        raise TypeError("require_active_validated_tunnel must be boolean")
    return document


def load_profile(path):
    return validate_profile(json.loads(Path(path).read_text(encoding="utf-8")))


class AdbClient:
    def __init__(self, executable, serial, server_port=None, timeout=20):
        self.serial = serial
        self.command = [executable]
        self.timeout = timeout
        if server_port is not None:
            self.command.extend(["-P", str(server_port)])

    def shell(self, *arguments):
        result = subprocess.run(
            [*self.command, "-s", self.serial, "shell", *arguments],
            check=True,
            capture_output=True,
            text=True,
            timeout=self.timeout,
        )
        return result.stdout.strip().replace("\r", "")


def _package_uid(client, package):
    output = client.shell("pm", "list", "packages", "-U", package)
    match = re.fullmatch(
        rf"package:{re.escape(package)} uid:(\d+)(?:,\d+)*", output
    )
    return int(match.group(1)) if match else None


def _connected_vpn_network(connectivity):
    for line in connectivity.splitlines():
        legacy_connected = (
            "type: VPN[]" in line and "state: CONNECTED/CONNECTED" in line
        )
        modern_connected = re.search(r"\bni\{VPN CONNECTED\b", line)
        if legacy_connected or modern_connected:
            return line
    return ""


def _uid_ranges(vpn_network):
    match = re.search(r"Uids: <\{([^}]*)\}>", vpn_network)
    if not match:
        return []
    ranges = []
    for raw_item in match.group(1).split(","):
        item = raw_item.strip()
        if not item:
            continue
        start, end = item.split("-", 1) if "-" in item else (item, item)
        ranges.append((int(start), int(end)))
    return ranges


def _uid_is_tunneled(uid, ranges):
    return any(start <= uid <= end for start, end in ranges)


def _excluded_uids(ranges):
    excluded = set(range(ANDROID_USER_UID_MIN, ANDROID_USER_UID_MAX + 1))
    for start, end in ranges:
        if start < ANDROID_USER_UID_MIN or end > ANDROID_USER_UID_MAX or end < start:
            return None
        excluded.difference_update(range(start, end + 1))
    return excluded


def _expected_excluded_uids(package_uids, android_sdk):
    expected = {uid for uid in package_uids if uid is not None}
    if android_sdk >= SDK_SANDBOX_MIN_API:
        expected.update(
            uid + SDK_SANDBOX_UID_OFFSET
            for uid in tuple(expected)
            if FIRST_APPLICATION_UID <= uid <= LAST_APPLICATION_UID
        )
    return expected


def audit_profile(profile, client):
    vpn = profile["vpn"]
    model = client.shell("getprop", "ro.product.model")
    android_sdk = int(client.shell("getprop", "ro.build.version.sdk"))
    current_user = client.shell("am", "get-current-user")
    vpn_uid = _package_uid(client, vpn["package"])
    excluded_package_uids = {
        package: _package_uid(client, package) for package in vpn["excluded_packages"]
    }
    tunneled_package_uids = {
        package: _package_uid(client, package)
        for package in vpn["required_tunneled_packages"]
    }
    connectivity = client.shell("dumpsys", "connectivity")
    vpn_network = _connected_vpn_network(connectivity)
    ranges = _uid_ranges(vpn_network)
    excluded_uids = _excluded_uids(ranges) if ranges else None
    expected_excluded_uids = _expected_excluded_uids(
        excluded_package_uids.values(), android_sdk
    )
    owner_match = re.search(
        r"(?:EstablishingAppUid|OwnerUid): (\d+)", vpn_network
    )
    owner_uid = int(owner_match.group(1)) if owner_match else None
    packages_available = all(
        uid is not None
        for uid in [
            vpn_uid,
            *excluded_package_uids.values(),
            *tunneled_package_uids.values(),
        ]
    )
    active_validated = bool(vpn_network) and "VALIDATED" in vpn_network
    checks = {
        "model": model == profile["expected"]["model"],
        "android_user": current_user == str(profile["expected"]["android_user_id"]),
        "required_packages": packages_available,
        "nordvpn_owns_tunnel": vpn_uid is not None and owner_uid == vpn_uid,
        "active_validated_tunnel": active_validated
        or not vpn["require_active_validated_tunnel"],
        "split_tunneling_enabled": bool(ranges) and bool(excluded_uids),
        "only_declared_packages_excluded": (
            packages_available
            and excluded_uids is not None
            and excluded_uids == expected_excluded_uids
        ),
        "required_packages_tunneled": (
            packages_available
            and all(
                _uid_is_tunneled(uid, ranges) for uid in tunneled_package_uids.values()
            )
        ),
    }
    return {
        "schema": SCHEMA,
        "device_id": profile["device_id"],
        "serial": client.serial,
        "policy": {
            "split_tunneling": True,
            "excluded_packages": list(vpn["excluded_packages"]),
            "required_tunneled_packages": list(vpn["required_tunneled_packages"]),
        },
        "checks": checks,
        "compliant": all(checks.values()),
    }


def parse_args(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--profile", required=True)
    parser.add_argument("--serial", required=True)
    parser.add_argument("--adb", default=os.environ.get("ADB", "adb"))
    parser.add_argument("--adb-server-port", type=int)
    parser.add_argument("--timeout", type=int, default=20)
    return parser.parse_args(argv)


def main(argv=None):
    args = parse_args(argv)
    profile = load_profile(args.profile)
    client = AdbClient(args.adb, args.serial, args.adb_server_port, args.timeout)
    try:
        report = audit_profile(profile, client)
    except (subprocess.CalledProcessError, subprocess.TimeoutExpired) as error:
        report = {
            "schema": SCHEMA,
            "device_id": profile["device_id"],
            "serial": args.serial,
            "compliant": False,
            "error": "ADB_UNAVAILABLE",
            "detail": type(error).__name__,
        }
    print(json.dumps(report, indent=2, sort_keys=True))
    return 0 if report["compliant"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
