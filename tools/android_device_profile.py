#!/usr/bin/env python3
"""Audit and apply non-secret Android device policy from a versioned profile."""

from __future__ import annotations

import argparse
import ipaddress
import json
import os
import re
import subprocess
import time
import xml.etree.ElementTree as ElementTree
from pathlib import Path


SCHEMA = 1
DEVICE_ID = re.compile(r"^[a-z0-9][a-z0-9._-]{0,63}$")
ENV_NAME = re.compile(r"^[A-Z][A-Z0-9_]*$")


def _require_string(value, label):
    if not isinstance(value, str) or not value:
        raise ValueError("%s must be a non-empty string" % label)
    return value


def validate_profile(document):
    if not isinstance(document, dict) or set(document) != {
        "schema",
        "device_id",
        "platform",
        "expected",
        "vpn",
    }:
        raise ValueError("device profile has unsupported or missing fields")
    if document["schema"] != SCHEMA:
        raise ValueError("unsupported device profile schema")
    device_id = _require_string(document["device_id"], "device_id")
    if not DEVICE_ID.fullmatch(device_id):
        raise ValueError("invalid device_id")
    if document["platform"] != "android":
        raise ValueError("only Android device profiles are supported")
    expected = document["expected"]
    if not isinstance(expected, dict) or set(expected) != {"model"}:
        raise ValueError("expected must contain only model")
    _require_string(expected["model"], "expected model")
    vpn = document["vpn"]
    required_vpn = {
        "package",
        "always_on",
        "lockdown",
        "connection_profile_name",
        "reconnect_on_reboot",
        "credential_mode",
        "profile_path_env",
        "tunnel_interface",
        "require_validated_tunnel",
        "bypass_cidrs",
        "required_env",
    }
    if not isinstance(vpn, dict) or set(vpn) != required_vpn:
        raise ValueError("vpn has unsupported or missing fields")
    _require_string(vpn["package"], "vpn package")
    _require_string(vpn["connection_profile_name"], "connection profile name")
    if vpn["credential_mode"] != "inline_auth_user_pass":
        raise ValueError("vpn credential_mode is invalid")
    profile_path_env = _require_string(
        vpn["profile_path_env"], "vpn profile_path_env"
    )
    if not ENV_NAME.fullmatch(profile_path_env):
        raise ValueError("vpn profile_path_env is invalid")
    _require_string(vpn["tunnel_interface"], "vpn tunnel_interface")
    if not isinstance(vpn["require_validated_tunnel"], bool):
        raise ValueError("vpn require_validated_tunnel must be boolean")
    bypass_cidrs = vpn["bypass_cidrs"]
    if not isinstance(bypass_cidrs, list) or len(bypass_cidrs) != len(
        set(bypass_cidrs)
    ):
        raise ValueError("vpn bypass_cidrs must contain unique networks")
    try:
        networks = [ipaddress.ip_network(item, strict=True) for item in bypass_cidrs]
    except (TypeError, ValueError) as error:
        raise ValueError("vpn bypass_cidrs contains an invalid network") from error
    if any(network.version != 4 for network in networks):
        raise ValueError("vpn bypass_cidrs supports only IPv4 networks")
    if vpn["reconnect_on_reboot"] not in {
        "connect_latest",
        "restore_connection",
        "none",
    }:
        raise ValueError("vpn reconnect_on_reboot is invalid")
    if not isinstance(vpn["always_on"], bool):
        raise ValueError("vpn always_on must be boolean")
    if not isinstance(vpn["lockdown"], bool):
        raise ValueError("vpn lockdown must be boolean")
    if vpn["lockdown"] and not vpn["always_on"]:
        raise ValueError("vpn lockdown requires always_on")
    required_env = vpn["required_env"]
    if (
        not isinstance(required_env, list)
        or len(required_env) != len(set(required_env))
        or any(not isinstance(item, str) or not ENV_NAME.fullmatch(item) for item in required_env)
    ):
        raise ValueError("vpn required_env must contain unique environment names")
    if profile_path_env not in required_env:
        raise ValueError("vpn profile_path_env must be present in required_env")
    return document


def load_profile(path):
    return validate_profile(json.loads(Path(path).read_text(encoding="utf-8")))


def load_env(path):
    values = {}
    if path is None:
        return values
    for raw_line in Path(path).read_text(encoding="utf-8").splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        name, value = line.split("=", 1)
        name = name.strip()
        if ENV_NAME.fullmatch(name):
            values[name] = value.strip().strip("'\"")
    return values


def private_profile_is_ready(vpn, environment):
    """Verify the local autologin profile without returning secret material."""
    path_value = environment.get(vpn["profile_path_env"])
    username = environment.get("NORDVPN_SERVICE_USERNAME")
    password = environment.get("NORDVPN_SERVICE_PASSWORD")
    if not path_value or not username or not password:
        return False
    path = Path(path_value).expanduser()
    try:
        if not path.is_file() or path.stat().st_mode & 0o077:
            return False
        contents = path.read_text(encoding="utf-8")
    except (OSError, UnicodeError):
        return False
    opening = "<auth-user-pass>"
    closing = "</auth-user-pass>"
    if contents.count(opening) != 1 or contents.count(closing) != 1:
        return False
    credentials = contents.split(opening, 1)[1].split(closing, 1)[0].splitlines()
    credentials = [line.strip() for line in credentials if line.strip()]
    if credentials != [username, password]:
        return False
    for cidr in vpn["bypass_cidrs"]:
        network = ipaddress.ip_network(cidr, strict=True)
        route = "route %s %s net_gateway" % (
            network.network_address,
            network.netmask,
        )
        if route not in contents.splitlines():
            return False
    return True


def validated_tunnel_is_ready(connectivity, interface, tunnel):
    if "inet " not in tunnel:
        return False
    for network in connectivity.split("NetworkAgentInfo{")[1:]:
        if (
            "state: CONNECTED/CONNECTED" in network
            and "InterfaceName: %s" % interface in network
            and "Transports:" in network
            and "VPN" in network
            and "VALIDATED" in network
        ):
            return True
    return False


class AdbClient:
    def __init__(self, executable, serial, server_port=None):
        self.executable = executable
        self.serial = serial
        self.environment = os.environ.copy()
        if server_port is not None:
            self.environment["ADB_SERVER_PORT"] = str(server_port)

    def shell(self, *arguments):
        result = subprocess.run(
            [self.executable, "-s", self.serial, "shell", *arguments],
            check=True,
            capture_output=True,
            text=True,
            env=self.environment,
        )
        return result.stdout.strip().replace("\r", "")

    @staticmethod
    def _node_center(document, attribute, value):
        root = ElementTree.fromstring(document)
        for node in root.iter("node"):
            if node.attrib.get(attribute) != value:
                continue
            match = re.fullmatch(
                r"\[(\d+),(\d+)\]\[(\d+),(\d+)\]",
                node.attrib.get("bounds", ""),
            )
            if match:
                left, top, right, bottom = map(int, match.groups())
                return ((left + right) // 2, (top + bottom) // 2)
        return None

    def _dump_ui(self):
        path = "/sdcard/mwo-android-device-profile.xml"
        self.shell("uiautomator", "dump", path)
        return self.shell("cat", path)

    def _tap_node(self, document, attribute, value):
        center = self._node_center(document, attribute, value)
        if center is None:
            return False
        self.shell("input", "tap", str(center[0]), str(center[1]))
        time.sleep(0.5)
        return True

    def openvpn_reboot_action(self, package, desired=None):
        actions = {
            "connect_latest": "Connect latest",
            "restore_connection": "Restore connection",
            "none": "None",
        }
        self.shell(
            "am",
            "start",
            "-W",
            "-n",
            "%s/net.openvpn.unified.MainActivity" % package,
        )
        time.sleep(1.5)
        for _attempt in range(12):
            document = self._dump_ui()
            for action, label in actions.items():
                if self._node_center(
                    document, "resource-id", "Selected radio %s" % label
                ):
                    if desired is None or desired == action:
                        return action
                    target = "Select radio %s" % actions[desired]
                    if not self._tap_node(document, "resource-id", target):
                        raise RuntimeError("OpenVPN reboot option is not selectable")
                    verified = self._dump_ui()
                    selected = "Selected radio %s" % actions[desired]
                    if not self._node_center(verified, "resource-id", selected):
                        raise RuntimeError("OpenVPN reboot option did not persist")
                    return desired
            if self._tap_node(document, "content-desc", "Cancel"):
                continue
            if self._tap_node(document, "content-desc", "Settings"):
                continue
            if self._tap_node(document, "content-desc", "menu"):
                continue
            if (
                "Launch Options" in document
                or 'content-desc="Settings"' in document
                or 'text="Settings"' in document
            ):
                self.shell("input", "swipe", "1000", "950", "1000", "300", "600")
                time.sleep(0.5)
                continue
            self.shell("input", "keyevent", "KEYCODE_BACK")
            time.sleep(0.5)
        raise RuntimeError("could not reach OpenVPN Launch Options")


def audit_profile(profile, client, environment):
    vpn = profile["vpn"]
    expected_always_on = vpn["package"] if vpn["always_on"] else "null"
    expected_lockdown = "1" if vpn["lockdown"] else "0"
    model = client.shell("getprop", "ro.product.model")
    package_result = client.shell("pm", "list", "packages", "-e", vpn["package"])
    always_on = client.shell("settings", "get", "secure", "always_on_vpn_app")
    lockdown = client.shell("settings", "get", "secure", "always_on_vpn_lockdown")
    reconnect_on_reboot = client.openvpn_reboot_action(vpn["package"])
    try:
        tunnel = client.shell("ip", "addr", "show", vpn["tunnel_interface"])
    except subprocess.CalledProcessError:
        tunnel = ""
    connectivity = client.shell("dumpsys", "connectivity")
    missing_env = sorted(
        name for name in vpn["required_env"] if not environment.get(name)
    )
    checks = {
        "model": model == profile["expected"]["model"],
        "vpn_package_enabled": package_result == "package:%s" % vpn["package"],
        "always_on_vpn": always_on == expected_always_on,
        "lockdown": lockdown == expected_lockdown,
        "reconnect_on_reboot": reconnect_on_reboot
        == vpn["reconnect_on_reboot"],
        "required_env": not missing_env,
        "private_vpn_profile": private_profile_is_ready(vpn, environment),
        "validated_vpn_tunnel": (
            not vpn["require_validated_tunnel"]
            or validated_tunnel_is_ready(
                connectivity, vpn["tunnel_interface"], tunnel
            )
        ),
    }
    return {
        "schema": SCHEMA,
        "device_id": profile["device_id"],
        "serial": client.serial,
        "connection_profile_name": vpn["connection_profile_name"],
        "checks": checks,
        "missing_env": missing_env,
        "compliant": all(checks.values()),
    }


def apply_profile(profile, client, environment):
    preflight = audit_profile(profile, client, environment)
    if not preflight["checks"]["model"]:
        raise RuntimeError("device model does not match profile")
    if not preflight["checks"]["vpn_package_enabled"]:
        raise RuntimeError("configured VPN package is not enabled")
    if not preflight["checks"]["required_env"]:
        raise RuntimeError(
            "missing required environment variables: %s"
            % ", ".join(preflight["missing_env"])
        )
    vpn = profile["vpn"]
    client.openvpn_reboot_action(
        vpn["package"], desired=vpn["reconnect_on_reboot"]
    )
    if vpn["always_on"]:
        client.shell(
            "settings", "put", "secure", "always_on_vpn_app", vpn["package"]
        )
        client.shell(
            "settings",
            "put",
            "secure",
            "always_on_vpn_lockdown",
            "1" if vpn["lockdown"] else "0",
        )
    else:
        client.shell("settings", "delete", "secure", "always_on_vpn_app")
        client.shell("settings", "put", "secure", "always_on_vpn_lockdown", "0")
    result = audit_profile(profile, client, environment)
    if not result["compliant"]:
        raise RuntimeError("device profile verification failed")
    return result


def parse_args(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--profile", required=True)
    parser.add_argument("--serial", required=True)
    parser.add_argument("--adb", default=os.environ.get("ADB", "adb"))
    parser.add_argument("--adb-server-port", type=int)
    parser.add_argument("--env-file")
    parser.add_argument("action", choices=("audit", "apply"))
    parser.add_argument("--yes", action="store_true")
    return parser.parse_args(argv)


def main(argv=None):
    args = parse_args(argv)
    profile = load_profile(args.profile)
    environment = dict(os.environ)
    environment.update(load_env(args.env_file))
    client = AdbClient(args.adb, args.serial, args.adb_server_port)
    if args.action == "apply":
        if not args.yes:
            raise SystemExit("apply requires --yes")
        report = apply_profile(profile, client, environment)
    else:
        report = audit_profile(profile, client, environment)
    print(json.dumps(report, indent=2, sort_keys=True))
    return 0 if report["compliant"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
