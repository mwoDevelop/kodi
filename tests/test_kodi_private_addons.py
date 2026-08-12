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


def test_registry_validates_allow_listed_profile_and_references():
    profiles = private_addons.validate_profiles(
        [PROFILE, OPENSUBTITLES_PROFILE]
    )
    private_addons.validate_references(
        profiles,
        {
            "RAPIDEO_USER": "user",
            "RAPIDEO_PASS": "pass",
            "OPENSUBTITLES_USER": "subtitle-user",
            "OPENSUBTITLES_PASS": "subtitle-pass",
        },
    )
    assert profiles == [PROFILE, OPENSUBTITLES_PROFILE]


def test_registry_rejects_unknown_adapter():
    with pytest.raises(ValueError, match="unsupported private add-on adapter"):
        private_addons.validate_profiles(
            [{**PROFILE, "adapter": "arbitrary"}]
        )
