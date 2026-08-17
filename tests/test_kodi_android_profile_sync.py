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
