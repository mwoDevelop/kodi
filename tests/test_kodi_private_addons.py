import pytest

from tools import kodi_private_addons as private_addons


PROFILE = {
    "adapter": "rapideo-v1",
    "username_ref": "RAPIDEO_USER",
    "password_ref": "RAPIDEO_PASS",
}
OPENSUBTITLES_PROFILE = {
    "adapter": "opensubtitles-org-v1",
    "username_ref": "OPENSUBTITLES_USER",
    "password_ref": "OPENSUBTITLES_PASS",
}
OPENSUBTITLES_COM_PROFILE = {
    "adapter": "opensubtitles-com-v1",
    "username_ref": "OPENSUBTITLES_USER",
    "password_ref": "OPENSUBTITLES_PASS",
    "token_ref": "OPENSUBTITLES_TOKEN",
}
YOUTUBE_PROFILE = {
    "adapter": "youtube-oauth-v1",
    "api_key_ref": "YOUTUBE_API_KEY",
    "client_id_ref": "YOUTUBE_CLIENT_ID",
    "client_secret_ref": "YOUTUBE_CLIENT_SECRET",
    "account_hint_ref": "YOUTUBE_USER",
}


def test_registry_validates_allow_listed_profile_and_references():
    profiles = private_addons.validate_profiles(
        [
            PROFILE,
            OPENSUBTITLES_PROFILE,
            OPENSUBTITLES_COM_PROFILE,
            YOUTUBE_PROFILE,
        ]
    )
    private_addons.validate_references(
        profiles,
        {
            "RAPIDEO_USER": "user",
            "RAPIDEO_PASS": "pass",
            "OPENSUBTITLES_USER": "subtitle-user",
            "OPENSUBTITLES_PASS": "subtitle-pass",
            "OPENSUBTITLES_TOKEN": "subtitle-token",
            "YOUTUBE_API_KEY": "AIza" + "a" * 35,
            "YOUTUBE_CLIENT_ID": (
                "123456789-example.apps.googleusercontent.com"
            ),
            "YOUTUBE_CLIENT_SECRET": "GOCSPX-private",
            "YOUTUBE_USER": "youtube@example.invalid",
        },
    )
    assert profiles == [
        PROFILE,
        OPENSUBTITLES_PROFILE,
        OPENSUBTITLES_COM_PROFILE,
        YOUTUBE_PROFILE,
    ]


def test_registry_rejects_unknown_adapter():
    with pytest.raises(ValueError, match="unsupported private add-on adapter"):
        private_addons.validate_profiles(
            [{**PROFILE, "adapter": "arbitrary"}]
        )
