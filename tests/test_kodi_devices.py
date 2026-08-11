import json
from pathlib import Path

import pytest

from tools.kodi_devices import (
    load_registry,
    resolve_device,
    resolve_private_endpoint,
    validate_registry,
)
from tools.kodi_reinstall import load_config


def registry():
    return {
        "schema": 2,
        "devices": {
            "android-tv": {
                "display_name": "Android TV",
                "physical_host_id": "android-tv-host",
                "principal_id": "principal-android-tv",
                "platform": "android",
                "roles": ["consumer"],
                "expected": {
                    "model": "TV MODEL",
                    "kodi_major": 21,
                    "abi": ["armeabi-v7a"],
                },
                "endpoints": {
                    "adb": "private-tv:5555",
                    "jsonrpc": "http://private-tv:9090",
                },
                "profile_channel": "home-stable",
            }
        },
    }


def registry_v2(platform="android"):
    document = json.loads(json.dumps(registry()))
    document["devices"]["android-tv"]["platform"] = platform
    return document


def linux_registry():
    return {
        "schema": 2,
        "devices": {
            "linux-consumer": {
                "display_name": "Linux consumer",
                "physical_host_id": "linux-host",
                "principal_id": "principal-linux-01",
                "platform": "linux-flatpak",
                "roles": ["consumer"],
                "expected": {
                    "model": "LINUX MODEL",
                    "kodi_major": 21,
                    "abi": ["x86_64"],
                    "flatpak_app_id": "tv.kodi.Kodi",
                    "kodi_data_root": ".var/app/tv.kodi.Kodi/data",
                },
                "endpoints": {
                    "ssh": {
                        "host": "private-linux",
                        "user_ref": "LINUX_USER",
                        "credential_ref": "LINUX_KEY",
                        "known_hosts_ref": "LINUX_KNOWN_HOSTS",
                    }
                },
                "profile_channel": "home-stable",
            }
        },
    }


def write_json(path, document):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(document, indent=2) + "\n",
        encoding="utf-8",
    )


def test_versioned_schema_two_example_matches_runtime_validator():
    repository = Path(__file__).resolve().parents[1]
    document = json.loads(
        (repository / "manifests/devices.example.json").read_text(
            encoding="utf-8"
        )
    )

    assert validate_registry(document) == document


def test_registry_validation_and_resolution(tmp_path):
    path = tmp_path / "devices.json"
    write_json(path, registry())

    loaded = load_registry(path)
    device = resolve_device(loaded, "android-tv")

    assert loaded["schema"] == 2
    assert device["logical_device_id"] == "android-tv"
    assert device["platform"] == "android"
    assert device["expected"]["model"] == "TV MODEL"
    assert device["endpoints"]["adb"] == "private-tv:5555"


def test_registry_rejects_retired_schema_one():
    document = registry()
    document["schema"] = 1
    for field in ("physical_host_id", "principal_id", "platform"):
        document["devices"]["android-tv"].pop(field)

    with pytest.raises(ValueError, match="unsupported device inventory schema"):
        validate_registry(document)


def test_private_android_endpoint_overrides_stale_registry_address():
    device = resolve_device(registry_v2(), "android-tv")

    resolved = resolve_private_endpoint(
        device,
        {"KODI_DEVICE_ANDROID_TV_ADB": "192.0.2.50:5555"},
    )

    assert resolved["endpoints"] == {
        "adb": "192.0.2.50:5555",
        "jsonrpc": "http://private-tv:9090",
    }
    assert device["endpoints"]["adb"] == "private-tv:5555"


def test_private_linux_endpoint_requires_and_overrides_current_host():
    device = resolve_device(linux_registry(), "linux-consumer")

    with pytest.raises(ValueError, match="KODI_DEVICE_LINUX_CONSUMER_SSH_HOST"):
        resolve_private_endpoint(device, {}, required=True)

    resolved = resolve_private_endpoint(
        device,
        {"KODI_DEVICE_LINUX_CONSUMER_SSH_HOST": "192.0.2.51"},
        required=True,
    )

    assert resolved["endpoints"]["ssh"]["host"] == "192.0.2.51"
    assert device["endpoints"]["ssh"]["host"] == "private-linux"


def test_registry_is_default_deny():
    document = registry()
    document["devices"]["android-tv"]["unexpected"] = True

    with pytest.raises(ValueError, match="unsupported or missing"):
        validate_registry(document)


def test_registry_rejects_duplicate_roles():
    document = registry()
    document["devices"]["android-tv"]["roles"] = ["consumer", "consumer"]

    with pytest.raises(ValueError, match="invalid roles"):
        validate_registry(document)


def test_registry_v2_accepts_linux_and_rejects_duplicate_identity():
    document = linux_registry()
    assert validate_registry(document) == document
    duplicate = json.loads(json.dumps(document["devices"]["linux-consumer"]))
    document["devices"]["linux-other"] = duplicate

    with pytest.raises(
        ValueError,
        match="duplicate physical_host_id/principal_id",
    ):
        validate_registry(document)


def test_registry_v2_rejects_ssh_for_android():
    document = linux_registry()
    device = document["devices"]["linux-consumer"]
    device["platform"] = "android"
    device["expected"].pop("flatpak_app_id")
    device["expected"].pop("kodi_data_root")

    with pytest.raises(ValueError, match="Android platform requires ADB"):
        validate_registry(document)


def test_schema_two_reinstall_resolves_inventory(tmp_path, monkeypatch):
    repository = tmp_path / "repo"
    private = repository / ".kodi-private"
    private.mkdir(parents=True)
    devices = private / "devices.json"
    config = private / "kodi-reinstall.json"
    write_json(devices, registry())
    write_json(
        config,
        {
            "schema": 2,
            "devices_file": ".kodi-private/devices.json",
            "targets": [
                {
                    "logical_device_id": "android-tv",
                    "expected_kodi_version": "21.3",
                    "snapshot": ".kodi-private/snapshot",
                    "apk": ".kodi-private/kodi.apk",
                    "apk_sha256": "a" * 64,
                }
            ],
        },
    )

    class Result:
        returncode = 0

    monkeypatch.setattr(
        "tools.kodi_profile.subprocess.run", lambda *args, **kwargs: Result()
    )
    _path, targets = load_config(config, repository)

    assert targets[0]["name"] == "android-tv"
    assert targets[0]["serial"] == "private-tv:5555"
    assert targets[0]["expected_model"] == "TV MODEL"


def test_schema_two_reinstall_rejects_endpoint_duplication(
    tmp_path, monkeypatch
):
    repository = tmp_path / "repo"
    private = repository / ".kodi-private"
    private.mkdir(parents=True)
    write_json(private / "devices.json", registry())
    config = private / "kodi-reinstall.json"
    write_json(
        config,
        {
            "schema": 2,
            "targets": [
                {
                    "logical_device_id": "android-tv",
                    "serial": "duplicated",
                }
            ],
        },
    )

    class Result:
        returncode = 0

    monkeypatch.setattr(
        "tools.kodi_profile.subprocess.run", lambda *args, **kwargs: Result()
    )
    with pytest.raises(ValueError, match="duplicates device inventory"):
        load_config(config, repository)


def test_schema_two_reinstall_rejects_linux_before_transport(
    tmp_path,
    monkeypatch,
):
    repository = tmp_path / "repo"
    private = repository / ".kodi-private"
    private.mkdir(parents=True)
    write_json(private / "devices.json", linux_registry())
    config = private / "kodi-reinstall.json"
    write_json(
        config,
        {
            "schema": 2,
            "targets": [
                {
                    "logical_device_id": "linux-consumer",
                    "expected_kodi_version": "21.3",
                }
            ],
        },
    )

    class Result:
        returncode = 0

    monkeypatch.setattr(
        "tools.kodi_profile.subprocess.run", lambda *args, **kwargs: Result()
    )
    with pytest.raises(
        ValueError,
        match="unsupported reinstall platform linux-flatpak",
    ):
        load_config(config, repository)
