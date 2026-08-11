import json
import xml.etree.ElementTree as ET
from pathlib import Path

import pytest

from tools.kodi_profile import (
    _build_restore_archive,
    canonical_json,
    digest,
    snapshot_restore_status,
    verify_snapshot,
)
from tools.legacy_inventory import scan_roots
from tools.migrations.legacy_config import migrate_config_pair
from tools.migrations.legacy_policy import migrate_policy_document
from tools.migrations.watchnixtoons2_snapshot import migrate_snapshot
from tools.schema_lifecycle import load_lifecycle


ROOT = Path(__file__).resolve().parents[1]


def _write_json(path, document):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(document, indent=2) + "\n", encoding="utf-8")


def _legacy_reinstall():
    return {
        "schema": 1,
        "targets": [
            {
                "name": "android-tv",
                "serial": "192.0.2.10:5555",
                "expected_model": "TV",
                "expected_kodi_version": "21.3",
                "snapshot": ".kodi-private/snapshot",
            }
        ],
    }


def _current_registry():
    return {
        "schema": 2,
        "devices": {
            "android-tv": {
                "display_name": "Television",
                "physical_host_id": "tv-host",
                "principal_id": "principal-tv",
                "platform": "android",
                "roles": ["consumer"],
                "expected": {"model": "TV", "kodi_major": 21},
                "endpoints": {"adb": "192.0.2.10:5555"},
                "profile_channel": "home-stable",
            }
        },
    }


def test_schema_lifecycle_manifest_is_complete():
    document = load_lifecycle(ROOT / "manifests/schema-lifecycle.json")

    assert document["formats"]["testing_lock"]["current"] == [1]
    assert document["formats"]["device_registry"]["legacy"] == [1]
    assert document["formats"]["disaster_recovery_snapshot"]["legacy"] == []


def test_config_pair_migration_recovers_after_first_commit_and_is_noop(tmp_path):
    repository = tmp_path / "repo"
    private = repository / ".kodi-private"
    config = private / "kodi-reinstall.json"
    devices = private / "devices.json"
    _write_json(config, _legacy_reinstall())
    _write_json(devices, _current_registry())

    with pytest.raises(RuntimeError, match="injected failure"):
        migrate_config_pair(
            config,
            devices,
            repository,
            publishers=["android-tv"],
            apply=True,
            fail_after="devices",
        )

    assert json.loads(devices.read_text())["devices"]["android-tv"]["roles"] == [
        "consumer",
        "publisher",
    ]
    assert json.loads(config.read_text())["schema"] == 1

    migrated_devices, migrated_config, changed = migrate_config_pair(
        config, devices, repository, apply=True
    )

    assert changed is True
    assert migrated_config["schema"] == 2
    assert migrated_devices["schema"] == 2
    assert not list(private.glob("*.legacy-migration-journal.json"))

    second_devices, second_config, changed = migrate_config_pair(
        config, devices, repository, apply=True
    )
    assert changed is False
    assert second_devices == migrated_devices
    assert second_config == migrated_config


def test_config_pair_conflict_is_fail_closed(tmp_path):
    repository = tmp_path / "repo"
    private = repository / ".kodi-private"
    config = private / "kodi-reinstall.json"
    devices = private / "devices.json"
    legacy = _legacy_reinstall()
    current = _current_registry()
    current["devices"]["android-tv"]["endpoints"]["adb"] = "192.0.2.99:5555"
    _write_json(config, legacy)
    _write_json(devices, current)

    with pytest.raises(ValueError, match="conflicts"):
        migrate_config_pair(config, devices, repository, apply=True)

    assert json.loads(config.read_text()) == legacy
    assert json.loads(devices.read_text()) == current
    assert not list(private.glob("*.legacy-migration-journal.json"))


def test_policy_migration_is_default_deny_and_semantically_equal():
    legacy = {
        "schema": 1,
        "name": "legacy",
        "include": ["userdata/**"],
        "exclude": ["userdata/Thumbnails/**"],
    }

    migrated, changed = migrate_policy_document(
        legacy,
        corpus=[
            "userdata/favourites.xml",
            "userdata/Thumbnails/a.jpg",
            "addons/plugin.video.example/addon.xml",
        ],
    )

    assert changed is True
    assert migrated["scopes"]["routine"] == {
        "default": "excluded",
        "default_profile_only": True,
        "device_local_paths": [],
        "adapters": [],
    }


def _legacy_snapshot(path):
    payload = path / "payload"
    old_addon = payload / "addons/plugin.video.watchnixtoons2"
    old_data = payload / "userdata/addon_data/plugin.video.watchnixtoons2"
    old_repo = payload / "addons/repository.oldsalt"
    old_addon.mkdir(parents=True)
    old_data.mkdir(parents=True)
    old_repo.mkdir(parents=True)
    (old_addon / "addon.xml").write_text(
        '<addon id="plugin.video.watchnixtoons2" version="0.1"/>',
        encoding="utf-8",
    )
    (old_repo / "addon.xml").write_text(
        '<addon id="repository.oldsalt" version="1.0"/>', encoding="utf-8"
    )
    (old_data / "settings.xml").write_text(
        '<settings><setting id="addon">plugin.video.watchnixtoons2</setting></settings>',
        encoding="utf-8",
    )
    favourites = payload / "userdata/favourites.xml"
    favourites.parent.mkdir(parents=True, exist_ok=True)
    root = ET.Element("favourites")
    item = ET.SubElement(root, "favourite", {"name": "Cartoon", "thumb": ""})
    item.text = 'ActivateWindow(10025,"plugin://plugin.video.watchnixtoons2/?x=1",return)'
    ET.ElementTree(root).write(favourites, encoding="utf-8")
    installer = path / "installer"
    installer.mkdir()
    files = {}
    for file_path in sorted(payload.rglob("*")):
        if file_path.is_file():
            data = file_path.read_bytes()
            files[file_path.relative_to(payload).as_posix()] = {
                "sha256": digest(data),
                "size": len(data),
            }
    identity = {
        "schema": 1,
        "policy_sha256": "a" * 64,
        "device": {"model": "TEST", "kodi_version": "21.3"},
        "selected_skin": "skin.estuary",
        "addons": [
            {
                "id": "plugin.video.watchnixtoons2",
                "version": "0.1",
                "enabled": True,
                "origin": "repository.oldsalt",
            },
            {
                "id": "repository.oldsalt",
                "version": "1.0",
                "enabled": True,
                "origin": "",
            },
        ],
        "files": files,
        "installer": {"apks": []},
    }
    manifest = {
        **identity,
        "created_utc": "2026-01-01T00:00:00+00:00",
        "snapshot_id": digest(canonical_json(identity)),
    }
    _write_json(path / "manifest.json", manifest)
    return manifest


def test_watch_snapshot_is_quarantined_and_migrated_to_new_artifact(tmp_path):
    source = tmp_path / "legacy"
    source.mkdir()
    original = _legacy_snapshot(source)
    current_addon = tmp_path / "current-addon"
    current_addon.mkdir()
    (current_addon / "addon.xml").write_text(
        '<addon id="plugin.video.watchnixtoons2.mwodevelop" version="1.2.3"/>',
        encoding="utf-8",
    )
    (current_addon / "default.py").write_text("# current\n", encoding="utf-8")

    assert verify_snapshot(source)["snapshot_id"] == original["snapshot_id"]
    assert snapshot_restore_status(source) == "LEGACY_QUARANTINED"
    with pytest.raises(ValueError, match="LEGACY_QUARANTINED"):
        _build_restore_archive(source, tmp_path / "restore.tar")

    output = tmp_path / "current"
    manifest, evidence = migrate_snapshot(source, output, current_addon)

    assert manifest["snapshot_id"] != original["snapshot_id"]
    assert evidence["migrated_from"] == original["snapshot_id"]
    assert snapshot_restore_status(output) == "CURRENT"
    assert (output / "payload/addons/plugin.video.watchnixtoons2.mwodevelop/addon.xml").is_file()
    assert not (output / "payload/addons/plugin.video.watchnixtoons2").exists()
    assert not (output / "payload/addons/repository.oldsalt").exists()
    assert (output / "payload/userdata/addon_data/plugin.video.watchnixtoons2.mwodevelop/settings.xml").is_file()


def test_inventory_classifies_by_document_type_without_values(tmp_path):
    root = tmp_path / "private"
    _write_json(root / "devices.json.schema1.bak", {"schema": 1, "devices": {"secret-device": {}}})
    lifecycle = load_lifecycle(ROOT / "manifests/schema-lifecycle.json")

    findings, errors = scan_roots([("private", root)], lifecycle)

    assert errors == []
    assert findings == [
        {
            "format": "device_registry",
            "schema": 1,
            "status": "LEGACY_QUARANTINED",
            "sha256": findings[0]["sha256"],
            "location": "private/devices.json.schema1.bak",
        }
    ]
    assert "secret-device" not in json.dumps(findings)
