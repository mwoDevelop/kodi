import json
import tarfile
from pathlib import Path

import pytest

from tools import kodi_addon_settings_rollout as rollout_module
from tools.kodi_addon_settings_rollout import (
    build_restore_archive,
    load_setting_sources,
)
from tools.kodi_profile import RestoreCommandMayBeQueued


def write_settings(path, values):
    body = "".join(
        '<setting id="%s">%s</setting>' % item
        for item in values.items()
    )
    path.write_text("<settings>%s</settings>" % body, encoding="utf-8")


def test_private_settings_archive_has_semantic_inventory_without_values(
    tmp_path,
):
    umbrella = tmp_path / "umbrella.xml"
    scrapers = tmp_path / "scrapers.xml"
    write_settings(umbrella, {"token": "private", "enabled": "true"})
    write_settings(scrapers, {"provider.comet": "true"})
    sources = load_setting_sources(
        [
            "plugin.video.umbrella=%s" % umbrella,
            "script.module.mwoscrapers=%s" % scrapers,
        ]
    )
    archive = tmp_path / "restore.tar"

    manifest = build_restore_archive(sources, archive, "a" * 32)

    assert manifest["operation_id"] == "a" * 32
    assert set(manifest["files"]) == {
        "userdata/addon_data/plugin.video.umbrella/settings.xml",
        "userdata/addon_data/script.module.mwoscrapers/settings.xml",
    }
    serialized = json.dumps(manifest)
    assert "private" not in serialized
    with tarfile.open(archive) as handle:
        stored = json.load(handle.extractfile("restore-manifest.json"))
        assert stored == manifest
        assert handle.extractfile(
            "payload/userdata/addon_data/plugin.video.umbrella/settings.xml"
        ).read() == umbrella.read_bytes()


def test_settings_sources_reject_duplicate_addon(tmp_path):
    source = tmp_path / "settings.xml"
    write_settings(source, {"enabled": "true"})

    with pytest.raises(ValueError, match="duplicate"):
        load_setting_sources(
            [
                "plugin.video.umbrella=%s" % source,
                "plugin.video.umbrella=%s" % source,
            ]
        )


def test_settings_sources_reject_unsafe_addon_id(tmp_path):
    source = tmp_path / "settings.xml"
    write_settings(source, {"enabled": "true"})

    with pytest.raises(ValueError, match="invalid"):
        load_setting_sources(["../umbrella=%s" % source])


def test_queued_restore_is_quiesced_before_unlock(monkeypatch, tmp_path):
    source = tmp_path / "settings.xml"
    device_script = tmp_path / "device.py"
    write_settings(source, {"enabled": "true"})
    device_script.write_text("# device helper\n", encoding="utf-8")
    sources = load_setting_sources(["plugin.video.example=%s" % source])
    calls = []

    monkeypatch.setattr(
        rollout_module,
        "_acquire_restore_lock",
        lambda *args: calls.append("lock"),
    )
    monkeypatch.setattr(rollout_module, "_push", lambda *args: None)
    monkeypatch.setattr(
        rollout_module,
        "adb_command",
        lambda *args, **kwargs: None,
    )
    monkeypatch.setattr(rollout_module, "_start_kodi", lambda *args: None)
    monkeypatch.setattr(
        rollout_module,
        "_addon_versions",
        lambda *args: {"plugin.video.example": "1.0.0"},
    )
    monkeypatch.setattr(
        rollout_module,
        "_run_restore_script",
        lambda *args, **kwargs: (_ for _ in ()).throw(
            RestoreCommandMayBeQueued("not acknowledged")
        ),
    )
    monkeypatch.setattr(
        rollout_module,
        "_quiesce_incomplete_restore",
        lambda *args, **kwargs: calls.append(
            ("quiesce", kwargs["command_may_be_queued"])
        ),
    )
    monkeypatch.setattr(
        rollout_module,
        "_cleanup_restore_staging",
        lambda *args: calls.append("cleanup"),
    )
    monkeypatch.setattr(
        rollout_module,
        "_release_restore_lock",
        lambda *args: calls.append("unlock"),
    )

    with pytest.raises(RestoreCommandMayBeQueued):
        rollout_module.rollout(
            "adb", 5038, "serial", sources, device_script
        )

    assert calls == [
        "lock",
        ("quiesce", True),
        "cleanup",
        "unlock",
    ]
