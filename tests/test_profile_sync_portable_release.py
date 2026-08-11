import json
import sqlite3

import pytest

from tools.kodi_portable_state import build_bundle
from tools.profile_sync_portable_release import (
    _database_state,
    _latest_enrollments,
    _portable_export,
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
          channel TEXT, target_tags TEXT, revoked INTEGER, last_seen_at INTEGER
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
        "INSERT INTO enrollments VALUES (?, 'device-a', 1, 'home-stable', ?, 0, 1)",
        ("enr:old00000", '["home"]'),
    )
    database.execute(
        "INSERT INTO enrollments VALUES (?, 'device-a', 2, 'home-stable', ?, 0, 2)",
        ("enr:new00000", '["android:arm64","home"]'),
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
