import json
from pathlib import Path
from types import SimpleNamespace

import pytest

from tools import kodi_managed_addon_settings as managed


def _policy(tmp_path):
    path = tmp_path / "policy.json"
    path.write_text(
        json.dumps(
            {
                "schema": 1,
                "addons": {
                    "plugin.video.example": {
                        "version_range": {
                            "min_inclusive": "2.1.0",
                            "max_exclusive": "3.0.0",
                        },
                        "settings": {"playbackMethod": "1"},
                    }
                },
            }
        ),
        encoding="utf-8",
    )
    return path


def test_policy_selects_only_compatible_installed_versions(tmp_path):
    policy = managed.load_policy(_policy(tmp_path))

    assert managed.applicable_settings(
        policy, {"plugin.video.example": "2.1.0"}
    ) == {"plugin.video.example": {"playbackMethod": "1"}}
    assert managed.applicable_settings(
        policy, {"plugin.video.example": "3.0.0"}
    ) == {}


def test_repository_policy_manages_watchnixtoons2_auto_highest():
    policy = managed.load_policy(
        Path("manifests/kodi-managed-addon-settings.json")
    )

    assert managed.applicable_settings(
        policy,
        {"plugin.video.watchnixtoons2.mwodevelop": "0.29.2"},
    ) == {
        "plugin.video.watchnixtoons2.mwodevelop": {"playbackMethod": "1"}
    }


def test_policy_rejects_an_empty_version_range(tmp_path):
    path = _policy(tmp_path)
    document = json.loads(path.read_text(encoding="utf-8"))
    document["addons"]["plugin.video.example"]["version_range"] = {
        "min_inclusive": "3.0.0",
        "max_exclusive": "3.0.0",
    }
    path.write_text(json.dumps(document), encoding="utf-8")

    with pytest.raises(ValueError, match="empty range"):
        managed.load_policy(path)


def test_reconcile_is_idempotent_when_managed_values_match(monkeypatch, tmp_path):
    monkeypatch.setattr(
        managed,
        "read_android_settings",
        lambda *_args: {"playbackMethod": "1", "unmanaged": "keep"},
    )
    monkeypatch.setattr(
        managed,
        "rollout_settings",
        lambda *_args: (_ for _ in ()).throw(AssertionError("unexpected write")),
    )

    assert managed.reconcile_android_managed_settings(
        "adb",
        5038,
        "serial",
        {"plugin.video.example": "2.1.0"},
        _policy(tmp_path),
        tmp_path / "device.py",
    ) == {"status": "NO_CHANGE", "addons": 1, "settings": 1}


def test_reconcile_changes_only_the_managed_subset(monkeypatch, tmp_path):
    observed = [{"playbackMethod": "0", "unmanaged": "keep"}]
    applied = []

    monkeypatch.setattr(
        managed,
        "read_android_settings",
        lambda *_args: observed[-1],
    )

    def rollout(_adb, _port, _serial, sources, _script):
        applied.append(sources)
        assert sources["plugin.video.example"]["values"] == {
            "playbackMethod": "1"
        }
        observed.append({"playbackMethod": "1", "unmanaged": "keep"})

    monkeypatch.setattr(managed, "rollout_settings", rollout)

    result = managed.reconcile_android_managed_settings(
        "adb",
        5038,
        "serial",
        {"plugin.video.example": "2.2.0"},
        _policy(tmp_path),
        tmp_path / "device.py",
    )

    assert result == {
        "status": "UPDATED",
        "addons": 1,
        "settings": 1,
        "changed_addons": ["plugin.video.example"],
        "changed_settings": 1,
    }
    assert len(applied) == 1


def test_read_android_settings_accepts_text_and_value_attributes(monkeypatch):
    payload = (
        '<settings><setting id="first">one</setting>'
        '<setting id="second" value="two" /></settings>'
    )
    monkeypatch.setattr(
        managed,
        "adb_command",
        lambda *_args, **_kwargs: SimpleNamespace(returncode=0, stdout=payload),
    )

    assert managed.read_android_settings("adb", 5038, "serial", "addon") == {
        "first": "one",
        "second": "two",
    }
