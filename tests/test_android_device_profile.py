import json
from pathlib import Path

import pytest

from tools.android_device_profile import (
    apply_profile,
    audit_profile,
    load_profile,
    validate_profile,
)


class FakeAdb:
    serial = "device:5555"

    def __init__(self):
        self.model = "X88Pro20"
        self.package = "net.openvpn.openvpn"
        self.always_on = "null"
        self.lockdown = "null"
        self.reconnect_on_reboot = "none"

    def shell(self, *arguments):
        if arguments == ("getprop", "ro.product.model"):
            return self.model
        if arguments[:4] == ("pm", "list", "packages", "-e"):
            return "package:%s" % self.package
        if arguments[:4] == ("settings", "get", "secure", "always_on_vpn_app"):
            return self.always_on
        if arguments[:4] == (
            "settings",
            "get",
            "secure",
            "always_on_vpn_lockdown",
        ):
            return self.lockdown
        if arguments[:4] == ("settings", "put", "secure", "always_on_vpn_app"):
            self.always_on = arguments[4]
            return ""
        if arguments[:4] == (
            "settings",
            "put",
            "secure",
            "always_on_vpn_lockdown",
        ):
            self.lockdown = arguments[4]
            return ""
        if arguments == (
            "settings",
            "delete",
            "secure",
            "always_on_vpn_app",
        ):
            self.always_on = "null"
            return ""
        if arguments == ("ip", "addr", "show", "tun0"):
            return "inet 10.100.0.2/20 scope global tun0"
        if arguments == ("dumpsys", "connectivity"):
            return (
                "NetworkAgentInfo{ state: CONNECTED/CONNECTED InterfaceName: tun0 "
                "Transports: ETHERNET|VPN VALIDATED"
            )
        raise AssertionError("unexpected adb command: %r" % (arguments,))

    def openvpn_reboot_action(self, _package, desired=None):
        if desired is not None:
            self.reconnect_on_reboot = desired
        return self.reconnect_on_reboot


def repository_profile():
    path = (
        Path(__file__).resolve().parents[1]
        / "manifests"
        / "device-profiles"
        / "x88pro20.json"
    )
    return load_profile(path)


def configured_environment(tmp_path):
    profile_path = tmp_path / "profile.ovpn"
    profile_path.write_text(
        "client\n<auth-user-pass>\nconfigured\nconfigured\n</auth-user-pass>\n"
        "route 192.168.1.0 255.255.255.0 net_gateway\n",
        encoding="utf-8",
    )
    profile_path.chmod(0o600)
    return {
        "KODI_DEVICE_X88PRO20_VPN_PROFILE": str(profile_path),
        "NORDVPN_SERVICE_USERNAME": "configured",
        "NORDVPN_SERVICE_PASSWORD": "configured",
    }


def test_versioned_x88_profile_is_valid_and_contains_no_secret_values():
    profile = repository_profile()

    assert profile["device_id"] == "x88pro20"
    assert profile["vpn"]["always_on"] is True
    assert profile["vpn"]["lockdown"] is False
    assert profile["vpn"]["reconnect_on_reboot"] == "connect_latest"
    assert profile["vpn"]["credential_mode"] == "inline_auth_user_pass"
    assert profile["vpn"]["require_validated_tunnel"] is True
    assert profile["vpn"]["bypass_cidrs"] == ["192.168.1.0/24"]
    serialized = json.dumps(profile)
    assert "configured" not in serialized


def test_apply_sets_always_on_without_lockdown_and_is_idempotent(tmp_path):
    profile = repository_profile()
    client = FakeAdb()

    environment = configured_environment(tmp_path)
    first = apply_profile(profile, client, environment)
    second = apply_profile(profile, client, environment)

    assert first["compliant"] is True
    assert second["compliant"] is True
    assert client.always_on == "net.openvpn.openvpn"
    assert client.lockdown == "0"
    assert client.reconnect_on_reboot == "connect_latest"
    assert second["checks"]["validated_vpn_tunnel"] is True


def test_audit_reports_missing_environment_without_exposing_values():
    report = audit_profile(repository_profile(), FakeAdb(), {})

    assert report["compliant"] is False
    assert report["checks"]["required_env"] is False
    assert report["checks"]["private_vpn_profile"] is False
    assert report["checks"]["validated_vpn_tunnel"] is True
    assert report["missing_env"] == [
        "KODI_DEVICE_X88PRO20_VPN_PROFILE",
        "NORDVPN_SERVICE_PASSWORD",
        "NORDVPN_SERVICE_USERNAME",
    ]


def test_validation_rejects_lockdown_without_always_on():
    profile = repository_profile()
    profile["vpn"]["always_on"] = False
    profile["vpn"]["lockdown"] = True

    with pytest.raises(ValueError, match="requires always_on"):
        validate_profile(profile)
