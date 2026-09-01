import json

import pytest

from tools.kodi_profile_sync_state import (
    configure,
    configure_identity,
    configure_secret_mode,
    probe,
)


class Addon:
    def __init__(self, settings=None):
        self.settings = {
            "enabled": "true",
            "server_url": "",
            "ca_certificate": "",
            "logical_device_id": "",
            "channel": "home-stable",
            "startup_delay_seconds": "15",
            "interval_hours": "6",
            "read_only": "true",
            **(settings or {}),
        }

    def getSetting(self, setting_id):
        return self.settings.get(setting_id, "")

    def setSetting(self, setting_id, value):
        self.settings[setting_id] = value

    def getAddonInfo(self, key):
        assert key == "version"
        return "0.1.6"


def test_probe_redacts_server_and_secrets(tmp_path):
    addon = Addon(
        {
            "server_url": "https://profile-sync.example.test",
            "logical_device_id": "sony-tv",
        }
    )
    (tmp_path / "state.json").write_text(
        json.dumps(
            {
                "schema": 1,
                "status": "IDLE",
                "enrollment": {
                    "logical_device_id": "sony-tv",
                    "channel": "home-stable",
                },
                "access_token": "never-print-token",
                "signing_seed": "never-print-seed",
            }
        ),
        encoding="utf-8",
    )

    result = probe(addon, tmp_path)

    serialized = json.dumps(result)
    assert result["identity_consistent"] is True
    assert result["has_access_token"] is True
    assert result["has_signing_seed"] is True
    assert result["server_url_configured"] is True
    assert result["ca_certificate_configured"] is False
    assert "profile-sync.example.test" not in serialized
    assert "never-print" not in serialized


def test_probe_accepts_schema_2_and_reports_only_redacted_secret_health(tmp_path):
    addon = Addon(
        {
            "server_url": "https://profile-sync.example.test",
            "logical_device_id": "x88pro20",
        }
    )
    (tmp_path / "state.json").write_text(
        json.dumps(
            {
                "schema": 2,
                "status": "NO_CHANGE",
                "enrollment": {
                    "logical_device_id": "x88pro20",
                    "channel": "home-stable",
                    "encryption_key_id": "encryption-public-id",
                },
                "access_token": "never-print-token",
                "signing_seed": "never-print-seed",
                "encryption_private_key": "never-print-private-key",
                "secret_state": "SHADOW_VERIFIED",
                "secret_type": "youtube-session-v1",
                "secret_set_generation": 1,
                "secret_last_verified_utc": "2026-08-21T18:00:00Z",
                "playback_status": "HEALTHY",
                "playback_last_success_utc": "2026-08-21T18:01:00Z",
                "playback_cursor": 4,
                "playback_pending_events": 0,
                "playback_pending_mapping": 1,
                "playback_pending_application": 2,
                "favourites_status": "HEALTHY",
                "favourites_last_success_utc": "2026-09-01T18:01:00Z",
                "favourites_cursor": 7,
                "favourites_pending_count": 0,
                "favourites_dynamic_fence": True,
            }
        ),
        encoding="utf-8",
    )

    result = probe(addon, tmp_path)

    serialized = json.dumps(result)
    assert result["has_encryption_private_key"] is True
    assert result["encryption_key_registered"] is True
    assert result["secret_state"] == "SHADOW_VERIFIED"
    assert result["secret_set_generation"] == 1
    assert result["playback_status"] == "HEALTHY"
    assert result["playback_cursor"] == 4
    assert result["playback_pending_mapping"] == 1
    assert result["playback_pending_application"] == 2
    assert result["favourites_status"] == "HEALTHY"
    assert result["favourites_cursor"] == 7
    assert result["favourites_pending_count"] == 0
    assert result["favourites_dynamic_fence"] is True
    assert "never-print" not in serialized


def test_configure_sets_per_device_identity_without_creating_credentials(
    tmp_path,
):
    addon = Addon()

    result = configure(
        addon,
        tmp_path,
        "http://127.0.0.1:18765",
        "x88pro20",
        "home-stable",
        "true",
    )

    assert result["logical_device_id"] == "x88pro20"
    assert result["paired"] is False
    assert result["has_access_token"] is False
    assert addon.settings["server_url"] == "http://127.0.0.1:18765"


def test_configure_sets_private_ca_for_verified_https(tmp_path):
    addon = Addon()

    result = configure(
        addon,
        tmp_path,
        "https://192.0.2.39:18765",
        "x88pro20",
        "home-stable",
        "true",
        "special://profile/addon_data/service.mwodevelop.profilesync/ca.pem",
    )

    assert result["ca_certificate_configured"] is True
    assert addon.settings["ca_certificate"].startswith("special://profile/")


def test_configure_rejects_private_ca_with_plain_http(tmp_path):
    with pytest.raises(ValueError, match="requires HTTPS"):
        configure(
            Addon(),
            tmp_path,
            "http://127.0.0.1:18765",
            "x88pro20",
            "home-stable",
            "true",
            "special://profile/addon_data/service.mwodevelop.profilesync/ca.pem",
        )


def test_configure_refuses_to_relabel_existing_enrollment(tmp_path):
    addon = Addon()
    (tmp_path / "state.json").write_text(
        json.dumps(
            {
                "schema": 1,
                "status": "IDLE",
                "enrollment": {
                    "logical_device_id": "sony-tv",
                    "channel": "home-stable",
                },
            }
        ),
        encoding="utf-8",
    )

    with pytest.raises(ValueError, match="explicit re-pair"):
        configure(
            addon,
            tmp_path,
            "http://127.0.0.1:18765",
            "x88pro20",
            "home-stable",
            "true",
        )


def test_identity_profile_does_not_invent_server_or_enrollment(tmp_path):
    addon = Addon()

    result = configure_identity(
        addon,
        tmp_path,
        "bedroom-tv",
        "home-stable",
        "15",
        "6",
        "true",
    )

    assert result["logical_device_id"] == "bedroom-tv"
    assert result["server_url_configured"] is False
    assert result["paired"] is False
    assert result["status"] == "UNPAIRED"


def test_secret_mode_requires_enrolled_encryption_key_and_persists(tmp_path):
    addon = Addon()
    (tmp_path / "state.json").write_text(
        json.dumps(
            {
                "schema": 2,
                "status": "NO_CHANGE",
                "enrollment": {
                    "logical_device_id": "x88pro20",
                    "channel": "home-stable",
                    "encryption_key_id": "encryption-public-id",
                },
                "encryption_private_key": "private-value",
            }
        ),
        encoding="utf-8",
    )

    result = configure_secret_mode(addon, tmp_path, "canary")

    assert result["secret_mode"] == "canary"
    assert addon.getSetting("secret_mode") == "canary"


def test_secret_mode_rejects_unpaired_or_unknown_mode(tmp_path):
    with pytest.raises(ValueError, match="not enrolled"):
        configure_secret_mode(Addon(), tmp_path, "canary")
    with pytest.raises(ValueError, match="invalid"):
        configure_secret_mode(Addon(), tmp_path, "unsupported")
