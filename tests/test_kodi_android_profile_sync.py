from tools import kodi_android_profile_sync as profile_sync


def test_android_target_tags_use_live_primary_abi(monkeypatch):
    class Result:
        stdout = "arm64-v8a,armeabi-v7a\n"

    monkeypatch.setattr(
        profile_sync,
        "adb_command",
        lambda *_args, **_kwargs: Result(),
    )

    tags = profile_sync._target_tags(
        {"platform": "android"}, "adb", 5038, "serial"
    )

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
