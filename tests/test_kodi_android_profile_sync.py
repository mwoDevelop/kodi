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
