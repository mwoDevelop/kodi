import hashlib
import importlib.util
import json
import stat
import subprocess
import sys
import types
import zipfile
from xml.etree import ElementTree

import pytest

from tools.kodi_flatpak_profile_sync_rollout import (
    _cleanup_command,
    build_settings,
    extract_addon,
)


def _write_addon_zip(path, member="service.test/addon.xml"):
    with zipfile.ZipFile(path, "w") as archive:
        archive.writestr(
            member,
            '<addon id="service.test" version="1.2.3" />',
        )
    return hashlib.sha256(path.read_bytes()).hexdigest()


def test_extract_addon_checks_digest_identity_and_inventory(tmp_path):
    archive = tmp_path / "addon.zip"
    digest = _write_addon_zip(archive)

    root, version = extract_addon(
        archive,
        "service.test",
        digest,
        tmp_path / "output",
    )

    assert version == "1.2.3"
    assert (root / "addon.xml").is_file()
    assert stat.S_IMODE((root / "addon.xml").stat().st_mode) == 0o644


def test_extract_addon_rejects_path_traversal(tmp_path):
    archive = tmp_path / "unsafe.zip"
    digest = _write_addon_zip(archive, "service.test/../outside")

    with pytest.raises(ValueError, match="unsafe entry"):
        extract_addon(
            archive,
            "service.test",
            digest,
            tmp_path / "output",
        )


def test_build_settings_contains_only_non_secret_device_configuration(tmp_path):
    destination = tmp_path / "settings.xml"

    values = build_settings(
        destination,
        "https://profile-sync.invalid:8766",
        "nuc-test",
        "home-stable",
        {
            "startup_delay_seconds": "15",
            "interval_hours": "6",
            "read_only": "true",
        },
    )

    parsed = {
        node.get("id"): node.text
        for node in ElementTree.parse(destination).getroot()
    }
    assert parsed == values
    assert parsed["enabled"] == "false"
    assert "token" not in destination.read_text(encoding="utf-8").lower()
    assert stat.S_IMODE(destination.stat().st_mode) == 0o600


def test_cleanup_command_is_valid_shell_and_scopes_all_paths_to_operation():
    operation = "0123456789abcdef"
    command = _cleanup_command(operation)

    subprocess.run(["sh", "-n", "-c", command], check=True)
    assert command.count(operation) == 6
    assert "/tmp/mwo-kodi-" in command
    assert "/tmp/mwo-xvfb-" in command


def test_in_kodi_recovery_restores_only_targets_already_moved(
    tmp_path, monkeypatch
):
    for name in ("xbmc", "xbmcaddon", "xbmcvfs"):
        monkeypatch.setitem(sys.modules, name, types.ModuleType(name))
    source = "tools/kodi_flatpak_profile_sync_device.py"
    spec = importlib.util.spec_from_file_location("flatpak_device_test", source)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)

    targets = {
        "untouched": tmp_path / "untouched",
        "moved": tmp_path / "moved",
        "new": tmp_path / "new",
    }
    backup = tmp_path / "backup"
    backup.mkdir()
    targets["untouched"].mkdir()
    (targets["untouched"] / "value").write_text("original")
    targets["moved"].mkdir()
    (targets["moved"] / "value").write_text("candidate")
    (backup / "moved").mkdir()
    (backup / "moved" / "value").write_text("original")
    targets["new"].mkdir()
    journal = tmp_path / "journal.json"
    journal.write_text(
        json.dumps(
            {"schema": 1, "existing": ["untouched", "moved"]}
        )
    )

    module._recover(journal, targets, backup)

    assert (targets["untouched"] / "value").read_text() == "original"
    assert (targets["moved"] / "value").read_text() == "original"
    assert not targets["new"].exists()
    assert not journal.exists()
    assert not backup.exists()
