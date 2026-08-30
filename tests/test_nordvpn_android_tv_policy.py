import json
from pathlib import Path

import pytest

from tools.nordvpn_android_tv_policy import (
    audit_profile,
    load_profile,
    validate_profile,
)

ROOT = Path(__file__).resolve().parents[1]


def repository_profile(name="sony-tv-nordvpn.json"):
    return load_profile(ROOT / "manifests" / "device-profiles" / name)


class FakeAdb:
    serial = "device:5555"

    def __init__(self, *, ranges="0-10142, 10144-99999", modern=False):
        self.modern = modern
        self.model = "Google TV Streamer" if modern else "BRAVIA 4K GB ATV3"
        self.sdk = "35" if modern else "28"
        self.ranges = ranges

    def shell(self, *arguments):
        if arguments == ("getprop", "ro.product.model"):
            return self.model
        if arguments == ("getprop", "ro.build.version.sdk"):
            return self.sdk
        if arguments == ("am", "get-current-user"):
            return "0"
        uids = (
            {
                "com.nordvpn.android": "10115",
                "com.netflix.ninja": "10116",
                "org.xbmc.kodi": "10052,1010052",
            }
            if self.modern
            else {
                "com.nordvpn.android": "10032",
                "com.netflix.ninja": "10143",
                "org.xbmc.kodi": "10197",
            }
        )
        if arguments[:4] == ("pm", "list", "packages", "-U"):
            package = arguments[4]
            return f"package:{package} uid:{uids[package]}"
        if arguments == ("dumpsys", "connectivity"):
            if self.modern:
                return (
                    "NetworkAgentInfo{network{102} ni{VPN CONNECTED extra: } "
                    "Score(Policies : IS_VPN&IS_VALIDATED) "
                    f"nc{{[ Transports: WIFI|VPN Uids: <{{{self.ranges}}}> "
                    "OwnerUid: 10115]}"
                )
            return (
                "NetworkAgentInfo{ ni{[type: VPN[], state: CONNECTED/CONNECTED]} "
                "lp{{InterfaceName: tun0}} nc{[ Transports: WIFI|VPN "
                f"Capabilities: INTERNET&VALIDATED Uids: <{{{self.ranges}}}> "
                "EstablishingAppUid: 10032]}"
            )
        raise AssertionError(f"unexpected adb command: {arguments!r}")


def test_versioned_profiles_are_valid_and_contain_no_credentials():
    for name in ("sony-tv-nordvpn.json", "bedroom-tv-nordvpn.json"):
        profile = repository_profile(name)
        assert profile["vpn"]["split_tunneling"] is True
        assert profile["vpn"]["excluded_packages"] == ["com.netflix.ninja"]
        assert profile["vpn"]["required_tunneled_packages"] == ["org.xbmc.kodi"]
        serialized = json.dumps(profile).lower()
        assert "password" not in serialized
        assert "token" not in serialized


def test_audit_accepts_only_netflix_excluded_and_kodi_tunneled():
    report = audit_profile(repository_profile(), FakeAdb())

    assert report["compliant"] is True
    assert all(report["checks"].values())


def test_audit_accepts_android_14_vpn_and_sdk_sandbox_uid():
    report = audit_profile(
        repository_profile("bedroom-tv-nordvpn.json"),
        FakeAdb(
            modern=True,
            ranges="0-10115, 10117-20115, 20117-99999",
        ),
    )

    assert report["compliant"] is True
    assert all(report["checks"].values())


def test_audit_rejects_an_additional_excluded_uid():
    report = audit_profile(repository_profile(), FakeAdb(ranges="0-10141, 10144-99999"))

    assert report["compliant"] is False
    assert report["checks"]["only_declared_packages_excluded"] is False


def test_audit_rejects_netflix_in_tunnel():
    report = audit_profile(repository_profile(), FakeAdb(ranges="0-99999"))

    assert report["compliant"] is False
    assert report["checks"]["only_declared_packages_excluded"] is False


def test_validation_rejects_package_in_both_policy_sets():
    profile = repository_profile()
    profile["vpn"]["required_tunneled_packages"] = ["com.netflix.ninja"]

    with pytest.raises(ValueError, match="both excluded and tunneled"):
        validate_profile(profile)
