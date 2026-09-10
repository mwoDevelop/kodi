from tools import kodi_android_profile_sync as profile_sync

import pytest


def load_device_module(monkeypatch):
    import importlib.util
    import sys
    import types

    for name in ("xbmc", "xbmcaddon", "xbmcgui", "xbmcvfs"):
        monkeypatch.setitem(sys.modules, name, types.ModuleType(name))
    spec = importlib.util.spec_from_file_location(
        "profile_device_recovery", "tools/kodi_profile_sync_device.py"
    )
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


@pytest.mark.parametrize(
    "change",
    [
        {"status": "ERROR"},
        {"status": "QUARANTINED"},
        {"applied_revision": None},
        {"assigned_revision": "other"},
        {"quarantined_revisions": ["revision"]},
        {"pending_report": {"result": "failure"}},
        {"journal": True},
    ],
)
def test_terminal_recovery_refuses_unverified_state(monkeypatch, tmp_path, change):
    module = load_device_module(monkeypatch)
    document = {
        "status": "APPLIED",
        "applied_revision": "revision",
        "assigned_revision": "revision",
        "terminal_configuration_fingerprint": "old",
        **change,
    }
    if change.get("journal"):
        (tmp_path / "apply-journal.json").write_text("{}")

    class State:
        def read(self):
            return document

        def update_public(self, **_):
            raise AssertionError("unsafe state write")

    with pytest.raises(RuntimeError, match="verified applied revision"):
        module.clear_recovered_terminal_block(State(), str(tmp_path))
    assert not list(tmp_path.glob("terminal-recovery-*"))


def test_terminal_recovery_preserves_identity_and_private_backup_then_noop(
    monkeypatch, tmp_path
):
    import json
    import stat

    module = load_device_module(monkeypatch)
    document = {
        "status": "NO_CHANGE",
        "applied_revision": "revision",
        "assigned_revision": "revision",
        "terminal_configuration_fingerprint": "old",
        "access_token": "private-test-token",
        "enrollment": {"generation": 21},
    }

    class State:
        def read(self):
            return dict(document)

        def update_public(self, **values):
            document.update(values)

    state = State()
    assert module.clear_recovered_terminal_block(state, str(tmp_path))
    (backup,) = tmp_path.glob("terminal-recovery-*.json")
    assert stat.S_IMODE(backup.stat().st_mode) == 0o600
    assert json.loads(backup.read_text())["terminal_configuration_fingerprint"] == "old"
    assert document["access_token"] == "private-test-token"
    assert document["enrollment"] == {"generation": 21}
    assert not module.clear_recovered_terminal_block(state, str(tmp_path))
    assert len(list(tmp_path.glob("terminal-recovery-*"))) == 1


def test_recovered_service_is_reenabled_even_if_disable_fails(monkeypatch):
    calls = []

    class Rpc:
        def __enter__(self):
            return self

        def __exit__(self, *_):
            pass

        def call(self, _method, params):
            calls.append(params)
            if not params["enabled"]:
                raise RuntimeError("transport error")

    monkeypatch.setattr(profile_sync, "AdbJsonRpcClient", lambda *_: Rpc())
    with pytest.raises(RuntimeError, match="transport error"):
        profile_sync._resume_recovered_service("adb", 5038, "device")
    assert [c["enabled"] for c in calls] == [False, True]
    assert all(c["addonid"] == "service.mwodevelop.profilesync" for c in calls)


def test_device_error_location_does_not_expose_exception_text(monkeypatch, tmp_path):
    import importlib.util
    import json
    import sys
    import types
    from pathlib import Path

    for name in ("xbmc", "xbmcaddon", "xbmcgui", "xbmcvfs"):
        monkeypatch.setitem(sys.modules, name, types.ModuleType(name))
    spec = importlib.util.spec_from_file_location(
        "profile_device_probe", Path("tools/kodi_profile_sync_device.py")
    )
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    captured = []
    monkeypatch.setattr(
        module, "_write_atomic", lambda _p, payload: captured.append(payload)
    )
    private_path = str(tmp_path / "sensitive-config-filename")
    monkeypatch.setattr(sys, "argv", ["probe", private_path, "marker"])
    module.main()
    report = json.loads(captured[0])
    assert report["error_type"] == "FileNotFoundError"
    assert report["error_location"].startswith("kodi_profile_sync_device.py:")
    assert "sensitive-config-filename" not in captured[0].decode()
    assert str(tmp_path) not in captured[0].decode()


def test_android_target_tags_use_live_primary_abi(monkeypatch):
    class Result:
        stdout = "arm64-v8a,armeabi-v7a\n"

    monkeypatch.setattr(
        profile_sync,
        "adb_command",
        lambda *_args, **_kwargs: Result(),
    )

    tags = profile_sync._target_tags({"platform": "android"}, "adb", 5038, "serial")

    assert tags == ["android-tv:arm64-v8a", "home"]


def test_invalid_report_signature_requires_exact_reenrollment_signal():
    assert profile_sync._requires_reenrollment(
        {
            "ok": False,
            "error_type": "ApiError",
            "error_code": "invalid report signature",
            "http_status": 400,
        }
    )
    assert not profile_sync._requires_reenrollment(
        {
            "ok": False,
            "error_type": "ApiError",
            "error_code": "invalid access token",
            "http_status": 401,
        }
    )


def test_quarantined_first_assignment_is_eligible_for_explicit_replacement():
    active = "sha256:" + "a" * 64
    observed = {
        "paired": True,
        "identity_consistent": True,
        "status": "QUARANTINED",
        "applied_revision": None,
        "assigned_revision": active,
    }

    assert profile_sync._can_replace_quarantined_enrollment(observed, active)


def test_applied_or_stale_quarantine_is_not_eligible_for_replacement():
    active = "sha256:" + "a" * 64
    base = {
        "paired": True,
        "identity_consistent": True,
        "status": "QUARANTINED",
        "applied_revision": None,
        "assigned_revision": active,
    }

    assert not profile_sync._can_replace_quarantined_enrollment(
        {**base, "applied_revision": "sha256:" + "b" * 64}, active
    )
    assert not profile_sync._can_replace_quarantined_enrollment(
        {**base, "assigned_revision": "sha256:" + "c" * 64}, active
    )


def test_explicit_replacement_requires_same_enrolled_identity():
    assert profile_sync._can_replace_enrollment(
        {
            "paired": True,
            "identity_consistent": True,
            "enrollment_id": "enr:current",
        }
    )
    assert not profile_sync._can_replace_enrollment(
        {
            "paired": True,
            "identity_consistent": False,
            "enrollment_id": "enr:foreign",
        }
    )
    assert not profile_sync._can_replace_enrollment(
        {"paired": False, "identity_consistent": False, "enrollment_id": None}
    )
