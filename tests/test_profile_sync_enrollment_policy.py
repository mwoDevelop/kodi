import copy
import json
from pathlib import Path

import pytest

from tools import profile_sync_enrollment_policy as policy


@pytest.fixture
def backend(monkeypatch, tmp_path):
    manifests = tmp_path / "manifests"
    manifests.mkdir()
    (manifests / "profile-sync-state-policy.json").write_bytes(
        Path("manifests/profile-sync-state-policy.json").read_bytes()
    )
    monkeypatch.setattr(
        policy,
        "load_sync_inventory",
        lambda _: {"devices": {"x88pro20": {"profile_channel": "home-stable"}}},
    )
    rows = [
        {
            "logical_device_id": "x88pro20",
            "enrollment_id": "enr:existing20",
            "generation": 20,
            "channel": "home-stable",
            "revoked": 0,
            "assignment_result": "success",
            "client_capabilities": json.dumps(list(policy.FEATURES.values())),
            "playback_state_enabled": 0,
            "playback_scope_id": "scope:home",
            "favourites_state_enabled": 1,
            "favourites_scope_id": "scope:home",
        }
    ]
    monkeypatch.setattr(policy, "read_enrollments", lambda *_: copy.deepcopy(rows))
    writes = []

    def set_feature(feature):
        def setter(_session, enrollment, enabled, scope):
            assert enrollment == rows[0]["enrollment_id"]
            writes.append(feature)
            rows[0][feature + "_state_enabled"] = int(enabled)
            rows[0][feature + "_scope_id"] = scope

        return setter

    monkeypatch.setattr(
        policy, "set_production_playback_state", set_feature("playback")
    )
    monkeypatch.setattr(
        policy, "set_production_favourites_state", set_feature("favourites")
    )
    return tmp_path, rows, writes


def run(backend, **kwargs):
    return policy.reconcile(
        backend[0], "x88pro20", session=object(), expected_generation=20, **kwargs
    )


def test_enable_exact_generation_then_noop(backend):
    result = run(backend)
    assert result["status"] == "APPLIED"
    assert result["generation"] == 20
    assert backend[2] == ["playback"]
    assert run(backend)["status"] == "NO_CHANGE"
    assert backend[2] == ["playback"]


def test_dry_run_does_not_change_backend(backend):
    assert run(backend, dry_run=True)["status"] == "WOULD_CHANGE"
    assert backend[2] == []
    assert backend[1][0]["playback_state_enabled"] == 0


@pytest.mark.parametrize(
    "change",
    [
        {"generation": 21},
        {"channel": "other"},
        {"revoked": 1},
        {"playback_scope_id": "scope:other"},
        {"client_capabilities": "[]"},
        {"assignment_result": "failure"},
        {"assignment_result": "drift_blocked"},
        {"playback_state_enabled": "false"},
        {"logical_device_id": "another-device"},
    ],
)
def test_foreign_stale_or_unsafe_identity_never_writes(backend, change):
    backend[1][0].update(change)
    with pytest.raises(RuntimeError):
        run(backend)
    assert backend[2] == []


def test_new_generation_gets_both_flags_without_touching_old_one(backend):
    old = copy.deepcopy(backend[1][0])
    old.update(generation=19, enrollment_id="enr:previous19")
    backend[1].append(old)
    backend[1][0].update(favourites_state_enabled=0, favourites_scope_id=None)
    assert run(backend)["changed_features"] == ["playback", "favourites"]
    assert old["playback_state_enabled"] == 0


def test_rotation_between_read_and_write_aborts(backend, monkeypatch):
    count = []

    def read(*_):
        count.append(True)
        rows = copy.deepcopy(backend[1])
        if len(count) > 1:
            rows[0]["generation"] = 21
        return rows

    monkeypatch.setattr(policy, "read_enrollments", read)
    with pytest.raises(RuntimeError, match="generation changed"):
        run(backend)
    assert backend[2] == []


def test_missing_readback_is_not_success(backend, monkeypatch):
    monkeypatch.setattr(policy, "set_production_playback_state", lambda *_: None)
    with pytest.raises(RuntimeError, match="did not converge"):
        run(backend)


def test_unregistered_channel_has_no_implicit_policy(backend):
    with pytest.raises(ValueError, match="no enrollment state policy"):
        policy.load_policy(backend[0], "other-channel")
