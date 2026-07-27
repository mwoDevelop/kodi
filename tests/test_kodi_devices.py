import json

import pytest

from tools.kodi_devices import (
    load_registry,
    migrate_reinstall_config,
    resolve_device,
    validate_registry,
)
from tools.kodi_reinstall import load_config


def registry():
    return {
        "schema": 1,
        "devices": {
            "android-tv": {
                "display_name": "Android TV",
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


def write_json(path, document):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(document, indent=2) + "\n",
        encoding="utf-8",
    )


def test_registry_validation_and_resolution(tmp_path):
    path = tmp_path / "devices.json"
    write_json(path, registry())

    loaded = load_registry(path)
    device = resolve_device(loaded, "android-tv")

    assert device["logical_device_id"] == "android-tv"
    assert device["expected"]["model"] == "TV MODEL"
    assert device["endpoints"]["adb"] == "private-tv:5555"


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


def test_migration_preserves_target_data_and_creates_backup(tmp_path):
    repository = tmp_path / "repo"
    private = repository / ".kodi-private"
    private.mkdir(parents=True)
    config = private / "kodi-reinstall.json"
    devices = private / "devices.json"
    write_json(
        config,
        {
            "schema": 1,
            "targets": [
                {
                    "name": "emulator-master",
                    "serial": "private-emulator:5555",
                    "expected_model": "EMULATOR",
                    "expected_kodi_version": "21.3",
                    "snapshot": ".kodi-private/snapshot",
                    "apk": ".kodi-private/kodi.apk",
                    "apk_sha256": "b" * 64,
                }
            ],
        },
    )

    migrated_devices, migrated_config = migrate_reinstall_config(
        config,
        devices,
        repository,
        publishers=["emulator-master"],
    )

    assert migrated_config["schema"] == 2
    assert migrated_config["targets"][0]["logical_device_id"] == "emulator-master"
    assert "serial" not in migrated_config["targets"][0]
    assert migrated_devices["devices"]["emulator-master"]["roles"] == [
        "consumer",
        "publisher",
    ]
    assert config.with_suffix(".json.schema1.bak").is_file()
    assert config.stat().st_mode & 0o777 == 0o600
    assert devices.stat().st_mode & 0o777 == 0o600
