import json
import sqlite3
from pathlib import Path

import pytest

from tools.kodi_portable_state import build_bundle
from tools.profile_sync_portable_release import (
    _database_state,
    _latest_enrollments,
    _portable_export,
    _routine_export,
    _skin_menu_for_fleet,
    _trigger_sync,
    bootstrap_active,
)


def test_portable_bundle_becomes_profile_sync_adapter(tmp_path):
    profile = tmp_path / "profile"
    profile.mkdir()
    (profile / "favourites.xml").write_text(
        '<favourites><favourite name="Cartoons">'
        'ActivateWindow(10025,"plugin://plugin.video.watchnixtoons2.mwodevelop/",return)'
        "</favourite></favourites>",
        encoding="utf-8",
    )
    bundle = tmp_path / "portable.zip"
    build_bundle(profile, bundle)

    exported = _portable_export(bundle)

    assert exported["adapter"]["adapter"] == "kodi_favourites_v1"
    assert exported["adapter"]["items"] == [
        {
            "title": "Cartoons",
            "type": "window",
            "window": "videos",
            "windowparameter": (
                "plugin://plugin.video.watchnixtoons2.mwodevelop/"
            ),
        }
    ]


def test_private_umbrella_authority_becomes_default_deny_routine_update(
    tmp_path,
):
    repository = tmp_path / "repository"
    private = repository / ".kodi-private"
    private.mkdir(parents=True)
    settings = private / "umbrella.xml"
    settings.write_text(
        '<settings version="2">'
        '<setting id="provider.external.enabled">true</setting>'
        '<setting id="external_provider.name">mwoscrapers</setting>'
        '<setting id="external_provider.module">script.module.mwoscrapers</setting>'
        '<setting id="realdebrid.filter.filename">false</setting>'
        '<setting id="realdebridtoken">must-not-export</setting>'
        "</settings>",
        encoding="utf-8",
    )
    manifests = repository / "manifests"
    manifests.mkdir()
    source_policy = Path("manifests/kodi-profile-policy.json")
    (manifests / "kodi-profile-policy.json").write_bytes(
        source_policy.read_bytes()
    )

    revision = _routine_export(repository, settings, 2)
    values = revision["adapters"]["umbrella.preferences"]["values"]

    assert values["provider.external.enabled"] is True
    assert values["external_provider.name"] == "mwoscrapers"
    assert values["external_provider.module"] == "script.module.mwoscrapers"
    assert values["realdebrid.filter.filename"] is False
    assert "realdebridtoken" not in json.dumps(revision)


def test_database_state_and_latest_enrollment_are_exact(tmp_path):
    epoch = tmp_path / "epoch"
    epoch.mkdir()
    database = sqlite3.connect(epoch / "state.sqlite")
    database.executescript(
        """
        CREATE TABLE channels (
          channel TEXT, active_revision TEXT, candidate_revision TEXT,
          generation INTEGER
        );
        CREATE TABLE revisions (revision_id TEXT, manifest TEXT);
        CREATE TABLE enrollments (
          enrollment_id TEXT, logical_device_id TEXT, generation INTEGER,
          channel TEXT, target_tags TEXT, revoked INTEGER, last_seen_at INTEGER,
          client_version TEXT, client_capabilities TEXT
        );
        CREATE TABLE assignment_reports (
          enrollment_id TEXT, revision_id TEXT, assignment_kind TEXT,
          result TEXT
        );
        CREATE TABLE assignments (
          enrollment_id TEXT, channel TEXT, revision_id TEXT,
          assignment_kind TEXT, document TEXT
        );
        """
    )
    revision = "sha256:" + "a" * 64
    manifest = {"schema": 2, "revision_id": revision, "adapters": {}}
    database.execute(
        "INSERT INTO channels VALUES ('home-stable', ?, NULL, 4)", (revision,)
    )
    database.execute(
        "INSERT INTO revisions VALUES (?, ?)",
        (revision, json.dumps(manifest)),
    )
    database.execute(
        "INSERT INTO enrollments VALUES (?, 'device-a', 1, 'home-stable', ?, 0, 1, ?, ?)",
        ("enr:old00000", '["home"]', "1.4.2", "[]"),
    )
    database.execute(
        "INSERT INTO enrollments VALUES (?, 'device-a', 2, 'home-stable', ?, 0, 2, ?, ?)",
        ("enr:new00000", '["android:arm64","home"]', "1.5.0", '["skin-shortcuts-menu-v1"]'),
    )
    database.commit()
    database.close()

    state = _database_state(epoch)
    selected = _latest_enrollments(state, {"device-a"})

    assert state["active_revision"] == revision
    assert state["generation"] == 4
    assert selected["device-a"]["enrollment_id"] == "enr:new00000"
    assert selected["device-a"]["target_tags"] == ["android:arm64", "home"]


def test_latest_enrollment_fails_closed_for_unenrolled_device():
    with pytest.raises(RuntimeError, match="device-b"):
        _latest_enrollments({"enrollments": []}, {"device-b"})


def test_skin_menu_waits_for_every_enrollment_capability():
    menu, pending = _skin_menu_for_fleet(
        Path("."),
        {
            "ready": {
                "client_version": "1.5.0",
                "client_capabilities": '["skin-shortcuts-menu-v1"]',
            },
            "old": {
                "client_version": "1.4.2",
                "client_capabilities": "[]",
            },
        },
    )

    assert menu is None
    assert pending == ["old"]


def test_skin_menu_loads_only_after_the_whole_fleet_is_ready():
    menu, pending = _skin_menu_for_fleet(
        Path("."),
        {
            "android": {
                "client_version": "1.5.0",
                "client_capabilities": '["skin-shortcuts-menu-v1"]',
            },
            "flatpak": {
                "client_version": "1.6.0",
                "client_capabilities": '["skin-shortcuts-menu-v1"]',
            },
        },
    )

    assert menu["adapter"] == "skin_shortcuts_v1"
    assert pending == []


def test_trigger_sync_prefers_acknowledged_jsonrpc_dispatch(monkeypatch):
    revision = "sha256:" + "b" * 64
    calls = []

    class Rpc:
        def __init__(self, *_args):
            pass

        def __enter__(self):
            return self

        def __exit__(self, *_args):
            pass

        def call(self, method, params):
            calls.append((method, params))
            return "OK"

    monkeypatch.setattr(
        "tools.profile_sync_portable_release.AdbJsonRpcClient", Rpc
    )
    monkeypatch.setattr(
        "tools.profile_sync_portable_release._wait_for_kodi_ready",
        lambda *_args: None,
    )
    monkeypatch.setattr(
        "tools.profile_sync_portable_release._profile_sync_probe",
        lambda *_args: {
            "enrollment_id": "enr:device000",
            "assigned_revision": revision,
            "applied_revision": revision,
            "status": "NO_CHANGE",
        },
    )
    monkeypatch.setattr(
        "tools.profile_sync_portable_release._cleanup", lambda *_args: None
    )
    monkeypatch.setattr(
        "tools.profile_sync_portable_release.time.sleep", lambda *_args: None
    )

    result = _trigger_sync(
        {
            "devices": {
                "device-a": {
                    "platform": "android",
                    "endpoints": {"adb": "192.0.2.10:5555"},
                }
            }
        },
        "device-a",
        "adb",
        5038,
        revision,
    )

    assert result["status"] == "NO_CHANGE"
    assert calls == [
        (
            "XBMC.ExecuteBuiltin",
            {
                "command": (
                    "RunScript(special://home/addons/"
                    "service.mwodevelop.profilesync/default.py,--sync-once)"
                ),
                "wait": False,
            },
        )
    ]


def test_bootstrap_active_signs_only_a_missing_current_assignment(
    monkeypatch, tmp_path
):
    revision = "sha256:" + "a" * 64
    state = {
        "active_revision": revision,
        "generation": 4,
        "enrollments": [
            {
                "enrollment_id": "enr:new00000",
                "logical_device_id": "device-a",
                "generation": 2,
                "channel": "home-stable",
                "target_tags": '["android:arm64","home"]',
                "revoked": 0,
            }
        ],
        "assignments": [],
    }

    class Session:
        closed = False

        def close(self):
            self.closed = True

    session = Session()
    calls = []
    monkeypatch.setattr(
        "tools.profile_sync_portable_release.connect",
        lambda *_args: session,
    )
    monkeypatch.setattr(
        "tools.profile_sync_portable_release._backup",
        lambda *_args: (tmp_path, {"backup_id": "backup-1"}),
    )
    monkeypatch.setattr(
        "tools.profile_sync_portable_release._database_state",
        lambda *_args: state,
    )
    monkeypatch.setattr(
        "tools.profile_sync_portable_release._assignment",
        lambda *_args: {"assignment_id": "sha256:" + "b" * 64},
    )
    monkeypatch.setattr(
        "tools.profile_sync_portable_release._admin",
        lambda *args: calls.append(args),
    )

    result = bootstrap_active(tmp_path, "device-a")

    assert result["status"] == "BOOTSTRAPPED"
    assert calls[0][1:4] == (
        "bootstrap_active",
        "publish",
        "/v1/channels/home-stable/bootstrap-assignments",
    )
    assert session.closed is True
