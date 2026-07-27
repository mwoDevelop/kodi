import json
from pathlib import Path

import pytest

from tools.kodi_profile import (
    _addon_inventory,
    _activate_skin,
    canonical_json,
    digest,
    ensure_private_output,
    glob_regex,
    included_by_policy,
    kodi_versions_compatible,
    requires_direct_copy,
    restore_snapshot,
    secure_private_tree,
    verify_snapshot,
)


def test_profile_policy_includes_settings_and_excludes_cache():
    policy = json.loads(
        Path("manifests/kodi-profile-policy.json").read_text(encoding="utf-8")
    )
    assert included_by_policy(
        "userdata/addon_data/plugin.video.umbrella/settings.xml", policy
    )
    assert included_by_policy(
        "userdata/addon_data/skin.aeon.nox.silvo/settings.xml", policy
    )
    assert included_by_policy(
        "addons/plugin.video.umbrella/addon.xml", policy
    )
    assert not included_by_policy(
        "userdata/addon_data/plugin.video.umbrella/cache.db", policy
    )
    assert not included_by_policy(
        "userdata/addon_data/plugin.video.umbrella/providers.db", policy
    )
    assert not included_by_policy(
        "userdata/Thumbnails/a/asset.jpg", policy
    )
    assert not included_by_policy(
        "addons/packages/plugin.zip", policy
    )


def test_single_star_does_not_cross_directory_boundaries():
    assert glob_regex("userdata/*.xml").fullmatch("userdata/guisettings.xml")
    assert not glob_regex("userdata/*.xml").fullmatch(
        "userdata/addon_data/example/settings.xml"
    )


def test_toybox_edge_case_is_copied_without_tar():
    assert requires_direct_copy(
        "addons/skin.aeon.nox.silvo/extras/moviegenres/default/...jpg"
    )
    assert not requires_direct_copy(
        "addons/skin.aeon.nox.silvo/media/Textures.xbt"
    )


def test_kodi_upgrade_compatibility_is_same_major_and_forward_only():
    assert kodi_versions_compatible("21.3", "21.3")
    assert kodi_versions_compatible("21.2", "21.3", allow_upgrade=True)
    assert not kodi_versions_compatible("21.3", "21.2", allow_upgrade=True)
    assert not kodi_versions_compatible("21.3", "22.0", allow_upgrade=True)
    assert not kodi_versions_compatible("21.2", "21.3")


def test_addon_inventory_skips_corrupt_manifest_but_leaves_payload(tmp_path):
    addons = tmp_path / "addons"
    good = addons / "plugin.video.good" / "addon.xml"
    corrupt = addons / "plugin.video.corrupt" / "addon.xml"
    good.parent.mkdir(parents=True)
    corrupt.parent.mkdir(parents=True)
    good.write_text(
        '<addon id="plugin.video.good" version="1.0.0"/>',
        encoding="utf-8",
    )
    corrupt.write_bytes(b"\0" * 32)

    inventory = _addon_inventory(
        tmp_path,
        {
            "plugin.video.good": {
                "enabled": True,
                "origin": "repository.example",
            }
        },
    )

    assert inventory == [
        {
            "id": "plugin.video.good",
            "version": "1.0.0",
            "enabled": True,
            "origin": "repository.example",
        }
    ]
    assert corrupt.read_bytes() == b"\0" * 32


def test_private_output_must_be_below_ignored_directory(
    tmp_path, monkeypatch
):
    repository = tmp_path / "repo"
    repository.mkdir()
    (repository / ".git").mkdir()
    private = repository / ".kodi-private"
    private.mkdir()

    class Result:
        returncode = 0

    monkeypatch.setattr(
        "tools.kodi_profile.subprocess.run", lambda *args, **kwargs: Result()
    )
    assert ensure_private_output(
        private / "snapshot", repository
    ) == (private / "snapshot").resolve()
    with pytest.raises(ValueError):
        ensure_private_output(repository / "tracked-snapshot", repository)


def test_private_tree_permissions_are_restricted(tmp_path):
    root = tmp_path / "snapshot"
    nested = root / "payload" / "userdata"
    nested.mkdir(parents=True)
    settings = nested / "settings.xml"
    settings.write_text("<settings/>", encoding="utf-8")
    root.chmod(0o755)
    nested.chmod(0o755)
    settings.chmod(0o644)

    secure_private_tree(root)

    assert root.stat().st_mode & 0o777 == 0o700
    assert nested.stat().st_mode & 0o777 == 0o700
    assert settings.stat().st_mode & 0o777 == 0o600


def test_verify_snapshot_rejects_payload_tampering(tmp_path):
    snapshot = tmp_path / "snapshot"
    payload = snapshot / "payload" / "userdata"
    installer = snapshot / "installer"
    payload.mkdir(parents=True)
    installer.mkdir()
    settings = payload / "guisettings.xml"
    settings.write_bytes(b"<settings/>")
    apk = installer / "base.apk"
    apk.write_bytes(b"apk")
    identity = {
        "schema": 1,
        "policy_sha256": "a" * 64,
        "device": {"kodi_version": "21.3"},
        "selected_skin": "skin.estuary",
        "addons": [],
        "files": {
            "userdata/guisettings.xml": {
                "sha256": digest(settings.read_bytes()),
                "size": settings.stat().st_size,
            }
        },
        "installer": {
            "apks": [
                {
                    "name": "base.apk",
                    "sha256": digest(apk.read_bytes()),
                    "size": apk.stat().st_size,
                }
            ]
        },
    }
    manifest = {
        **identity,
        "created_utc": "2026-07-27T00:00:00+00:00",
        "snapshot_id": digest(canonical_json(identity)),
    }
    (snapshot / "manifest.json").write_bytes(canonical_json(manifest))
    assert (
        verify_snapshot(snapshot)["snapshot_id"] == manifest["snapshot_id"]
    )
    settings.write_bytes(b"tampered")
    with pytest.raises(ValueError, match="payload inventory"):
        verify_snapshot(snapshot)


def test_activate_skin_accepts_only_the_expected_confirmation(monkeypatch):
    monkeypatch.setattr("tools.kodi_profile.time.sleep", lambda _seconds: None)

    class JsonRpc:
        def __init__(self):
            self.calls = []
            self.skin = "skin.estuary"

        def call(self, method, params=None):
            self.calls.append((method, params))
            if method == "Settings.SetSettingValue":
                self.skin = params["value"]
                return True
            if method == "GUI.GetProperties":
                return {
                    "currentwindow": {"id": 10100},
                    "currentcontrol": {"label": "No"},
                }
            if method == "Settings.GetSettingValue":
                return {"value": self.skin}
            return "OK"

    rpc = JsonRpc()
    _activate_skin(rpc, "skin.aeon.nox.silvo")
    methods = [method for method, _params in rpc.calls]
    assert methods.count("Settings.SetSettingValue") == 2
    assert ("Input.Left", None) in rpc.calls
    assert ("Input.Select", None) in rpc.calls


def test_restore_removes_device_staging_after_failure(monkeypatch):
    calls = []

    def fail(*_args, **_kwargs):
        raise RuntimeError("restore failed")

    def record(*args, **kwargs):
        calls.append((args, kwargs))

    monkeypatch.setattr("tools.kodi_profile._restore_snapshot_inner", fail)
    monkeypatch.setattr("tools.kodi_profile.adb_command", record)

    with pytest.raises(RuntimeError, match="restore failed"):
        restore_snapshot("adb", 5038, "serial", "snapshot", "script")

    assert len(calls) == 1
    assert calls[0][0][3] == "shell"
    assert "mwo-kodi-profile-restore.tar" in calls[0][0][4]
