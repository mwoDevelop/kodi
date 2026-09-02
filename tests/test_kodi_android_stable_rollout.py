from pathlib import Path
from types import SimpleNamespace

from tools.kodi_android_stable_rollout import (
    desired_origins,
    ensure_kodi_ready,
    origin_transition,
    reconcile,
    reconcile_origins,
)

ADDON_IDS = (
    "script.module.mwoscrapers",
    "script.mwoscrapers",
    "plugin.video.umbrella",
    "plugin.video.watchnixtoons2.mwodevelop",
    "service.subtitles.opensubtitles-com",
    "service.mwodevelop.profilesync",
)


def test_empty_testing_origin_map_is_an_idempotent_no_op(monkeypatch):
    monkeypatch.setattr(
        "tools.kodi_android_stable_rollout.desired_origins",
        lambda _prepared, _channel: {},
    )
    monkeypatch.setattr(
        "tools.kodi_android_stable_rollout.installed_addon_origins_in_kodi",
        lambda *_args: (_ for _ in ()).throw(AssertionError("unexpected read")),
    )
    monkeypatch.setattr(
        "tools.kodi_android_stable_rollout.assign_addon_origins_in_kodi",
        lambda *_args, **_kwargs: (_ for _ in ()).throw(
            AssertionError("unexpected write")
        ),
    )

    assert reconcile_origins("adb", 5038, "device", {}, "testing") == {
        "status": "NO_CHANGE",
        "origins": 0,
    }


def test_android_stable_preflight_restarts_a_stale_kodi_process(monkeypatch):
    commands = []
    waits = []

    def adb_command(_adb, _port, _serial, *argv, **_kwargs):
        commands.append(argv)
        if argv == ("shell", "pidof org.xbmc.kodi"):
            return SimpleNamespace(returncode=0, stdout="1234\n")
        return SimpleNamespace(returncode=0, stdout="")

    def wait(_adb, _port, _serial, timeout=90):
        waits.append(timeout)
        if len(waits) == 1:
            raise TimeoutError("stale")

    monkeypatch.setattr("tools.kodi_android_stable_rollout.adb_command", adb_command)
    monkeypatch.setattr("tools.kodi_android_stable_rollout._wait_for_kodi_ready", wait)
    monkeypatch.setattr(
        "tools.kodi_android_stable_rollout.time.sleep", lambda _seconds: None
    )

    assert ensure_kodi_ready("adb", 5038, "device") == "restarted"
    assert waits == [15, 90]
    assert ("shell", "am force-stop org.xbmc.kodi") in commands
    assert ("shell", "input keyevent KEYCODE_WAKEUP") in commands
    assert ("shell", "input keyevent KEYCODE_HOME") in commands


def test_android_rollout_can_reconcile_testing_channel(monkeypatch, tmp_path):
    installed = []
    assigned = []
    loaded = {}
    repository_id = "repository.mwodevelop.testing"
    addons = {
        addon_id: {
            "path": tmp_path / (addon_id + ".zip"),
            "sha256": ("1" if addon_id == ADDON_IDS[0] else "2") * 64,
            "version": "2.0.0",
        }
        for addon_id in ADDON_IDS
    }
    prepared = {
        "channel": "testing",
        "repository_id": repository_id,
        "lock_sha256": "ab" * 32,
        "repository": {
            "path": tmp_path / "repository.zip",
            "version": "1.0.0",
        },
        "addons": addons,
    }
    dependency = {
        "id": "script.module.urllib3",
        "version": "2.2.3",
        "sha256": "3" * 64,
        "url": "https://mirrors.kodi.tv/addons/omega/urllib3.zip",
    }
    monkeypatch.setattr(
        "tools.kodi_android_stable_rollout.load_private_references",
        lambda path: loaded.setdefault("references", path) and {},
    )
    monkeypatch.setattr(
        "tools.kodi_android_stable_rollout.load_registry",
        lambda path: loaded.setdefault("devices", path) and {},
    )
    monkeypatch.setattr(
        "tools.kodi_android_stable_rollout.resolve_device",
        lambda _registry, _device: {},
    )
    monkeypatch.setattr(
        "tools.kodi_android_stable_rollout.resolve_private_endpoint",
        lambda *_args, **_kwargs: {
            "platform": "android",
            "endpoints": {"adb": "device"},
        },
    )
    monkeypatch.setattr(
        "tools.kodi_android_stable_rollout.ensure_kodi_ready",
        lambda *_args: "ready",
    )
    monkeypatch.setattr(
        "tools.kodi_android_stable_rollout.reconcile_android_advancedsettings",
        lambda *_args: {"status": "NO_CHANGE", "removed": []},
    )
    monkeypatch.setattr(
        "tools.kodi_android_stable_rollout.reconcile_retired_addons",
        lambda *_args: {"status": "NO_CHANGE", "removed": [], "checked": 6},
    )
    monkeypatch.setattr(
        "tools.kodi_android_stable_rollout.prepare",
        lambda _root, channel: prepared,
    )
    monkeypatch.setattr(
        "tools.kodi_android_stable_rollout.prepare_repository",
        lambda _root, channel: {
            "repository_id": "repository.mwodevelop",
            "repository": {
                "path": tmp_path / "stable-repository.zip",
                "version": "1.0.0",
            },
        },
    )
    monkeypatch.setattr(
        "tools.kodi_android_stable_rollout.load_official_dependencies",
        lambda _path: [dependency],
    )
    monkeypatch.setattr(
        "tools.kodi_android_stable_rollout.fetch_artifact",
        lambda _metadata, _cache: tmp_path / "urllib3.zip",
    )
    monkeypatch.setattr(
        "tools.kodi_android_stable_rollout.reconcile_official_dependencies",
        lambda *_args, **_kwargs: [
            {
                "addon": "script.module.urllib3",
                "action": "unchanged",
                "version": "2.2.3",
            }
        ],
    )
    monkeypatch.setattr(
        "tools.kodi_android_stable_rollout.addon_details",
        lambda *_args: None,
    )
    monkeypatch.setattr(
        "tools.kodi_android_stable_rollout.inspect_archive",
        lambda _path, expected_id, expected_version: {
            "id": expected_id,
            "version": expected_version,
        },
    )
    monkeypatch.setattr(
        "tools.kodi_android_stable_rollout.android_runtime_facts",
        lambda *_args, **_kwargs: {"kodi_version": "21.3"},
    )
    monkeypatch.setattr(
        "tools.kodi_android_stable_rollout.attest_android_runtime",
        lambda *_args, **_kwargs: {"status": "ATTESTATION_PASS"},
    )
    monkeypatch.setattr(
        "tools.kodi_android_stable_rollout.load_policy", lambda _path: {}
    )
    monkeypatch.setattr(
        "tools.kodi_android_stable_rollout.assert_compatible",
        lambda *_args, **_kwargs: {
            "status": "AUDIT_PASS",
            "policy_sha256": "c" * 64,
            "catalog_sha256": "e" * 64,
            "graph_sha256": "d" * 64,
            "order": [*ADDON_IDS, repository_id],
        },
    )

    def rollout(_adb, _port, _serial, path, addon_id, version, *_args, **_kwargs):
        installed.append((addon_id, Path(path), version))
        return {"repaired_orphan": False}

    monkeypatch.setattr("tools.kodi_android_stable_rollout.rollout", rollout)
    monkeypatch.setattr(
        "tools.kodi_android_stable_rollout.assign_addon_origins_in_kodi",
        lambda _adb, _port, target, *_args, **_kwargs: assigned.append(target),
    )
    monkeypatch.setattr(
        "tools.kodi_android_stable_rollout.desired_origins",
        lambda _prepared, _channel: {
            ADDON_IDS[0]: "repository.mwodevelop"
        },
    )
    monkeypatch.setattr(
        "tools.kodi_android_stable_rollout.installed_addon_origins_in_kodi",
        lambda *_args: {ADDON_IDS[0]: repository_id},
    )
    monkeypatch.setattr(
        "tools.kodi_android_stable_rollout.origin_transition",
        lambda _prepared, _channel, _origins, _current: (
            {ADDON_IDS[0]: repository_id},
            {},
        ),
    )
    def reconcile_settings(*_args):
        return {"status": "UPDATED", "addons": 1, "settings": 1}

    monkeypatch.setattr(
        "tools.kodi_android_stable_rollout.reconcile_installed_android_managed_settings",
        reconcile_settings,
    )

    result = reconcile(
        "x88pro20",
        "adb",
        5038,
        channel="testing",
        devices_file=tmp_path / "devices.json",
        references_file=tmp_path / "references.env",
    )

    assert result["channel"] == "testing"
    assert result["advancedsettings"]["status"] == "NO_CHANGE"
    assert result["retired_addons"]["status"] == "NO_CHANGE"
    assert result["official_dependencies"]["status"] == "NO_CHANGE"
    assert result["managed_settings"]["status"] == "UPDATED"
    assert loaded == {
        "devices": tmp_path / "devices.json",
        "references": tmp_path / "references.env",
    }
    assert [item[0] for item in installed] == [
        repository_id,
        "repository.mwodevelop",
        *ADDON_IDS,
    ]
    assert assigned == [
        {
            "serial": "device",
            "addon_origins": {ADDON_IDS[0]: "repository.mwodevelop"},
            "addon_previous_origins": {ADDON_IDS[0]: repository_id},
            "addon_version_transitions": {},
        }
    ]


def test_testing_channel_assigns_complete_mixed_origin_policy():
    prepared = {
        "repository_id": "repository.mwodevelop.testing",
        "addons": {
            "unchanged": {"sha256": "a" * 64},
            "candidate": {"sha256": "b" * 64},
        },
    }
    stable = {
        "unchanged": {"zip_sha256": "a" * 64},
        "candidate": {"zip_sha256": "c" * 64},
    }

    assert desired_origins(prepared, "testing", stable) == {
        "unchanged": "repository.mwodevelop",
        "candidate": "repository.mwodevelop.testing"
    }


def test_reconcile_origins_is_no_op_when_complete_policy_matches(monkeypatch):
    prepared = {
        "repository_id": "repository.mwodevelop.testing",
        "addons": {},
    }
    expected = {
        "unchanged": "repository.mwodevelop",
        "candidate": "repository.mwodevelop.testing",
    }
    monkeypatch.setattr(
        "tools.kodi_android_stable_rollout.desired_origins",
        lambda _prepared, _channel: expected,
    )
    monkeypatch.setattr(
        "tools.kodi_android_stable_rollout.installed_addon_origins_in_kodi",
        lambda *_args: dict(expected),
    )
    monkeypatch.setattr(
        "tools.kodi_android_stable_rollout.assign_addon_origins_in_kodi",
        lambda *_args, **_kwargs: (_ for _ in ()).throw(
            AssertionError("unexpected write")
        ),
    )

    assert reconcile_origins("adb", 5038, "device", prepared, "testing") == {
        "status": "NO_CHANGE",
        "origins": 2,
    }


def test_testing_origin_transition_allows_the_pinned_version_change():
    prepared = {
        "repository_id": "repository.mwodevelop.testing",
        "addons": {"candidate": {"version": "2.0.0"}},
    }

    previous, transitions = origin_transition(
        prepared,
        "testing",
        {"candidate": "repository.mwodevelop.testing"},
        {"candidate": "repository.mwodevelop"},
        {"candidate": {"version": "1.0.0"}},
    )

    assert previous == {"candidate": "repository.mwodevelop"}
    assert transitions == {"candidate": {"from": "1.0.0", "to": "2.0.0"}}


def test_testing_origin_transition_repairs_unchanged_component_to_stable():
    prepared = {
        "repository_id": "repository.mwodevelop.testing",
        "addons": {"unchanged": {"version": "2.0.0"}},
    }

    previous, transitions = origin_transition(
        prepared,
        "testing",
        {"unchanged": "repository.mwodevelop"},
        {"unchanged": "repository.mwodevelop.testing"},
        {"unchanged": {"version": "1.0.0"}},
    )

    assert previous == {"unchanged": "repository.mwodevelop.testing"}
    assert transitions == {}


def test_stable_transition_ignores_addons_already_owned_by_stable():
    prepared = {
        "repository_id": "repository.mwodevelop",
        "addons": {
            "already-stable": {"version": "2.0.0"},
            "candidate": {"version": "2.0.0"},
        },
    }

    previous, transitions = origin_transition(
        prepared,
        "stable",
        {
            "already-stable": "repository.mwodevelop",
            "candidate": "repository.mwodevelop",
        },
        {
            "already-stable": "repository.mwodevelop",
            "candidate": "repository.mwodevelop.testing",
        },
        {
            "already-stable": {"version": "2.0.0"},
            "candidate": {"version": "1.0.0"},
        },
    )

    assert previous == {"candidate": "repository.mwodevelop.testing"}
    assert transitions == {"candidate": {"from": "1.0.0", "to": "2.0.0"}}
