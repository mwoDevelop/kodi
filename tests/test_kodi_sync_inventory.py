import json

import pytest

from tools.kodi_sync_inventory import (
    device_env_prefix,
    load_sync_inventory,
)


def registry():
    return {
        "schema": 2,
        "devices": {
            "source-tv": {
                "display_name": "Source",
                "physical_host_id": "source-tv",
                "principal_id": "principal-source",
                "platform": "android",
                "roles": ["consumer", "publisher"],
                "expected": {"model": "Source", "kodi_major": 21},
                "endpoints": {"adb": "stale:5555"},
                "profile_channel": "home-stable",
            },
            "nuc-mwo": {
                "display_name": "NUC",
                "physical_host_id": "nuc",
                "principal_id": "principal-nuc",
                "platform": "linux-flatpak",
                "roles": ["consumer"],
                "expected": {
                    "model": "NUC",
                    "kodi_major": 21,
                    "flatpak_app_id": "tv.kodi.Kodi",
                    "kodi_data_root": ".var/app/tv.kodi.Kodi/data",
                },
                "endpoints": {
                    "ssh": {
                        "host": "stale",
                        "user_ref": "NUC_USER",
                        "credential_ref": "NUC_KEY",
                        "known_hosts_ref": "NUC_HOSTS",
                    }
                },
                "profile_channel": "home-stable",
            },
        },
    }


def write_private(tmp_path, env):
    private = tmp_path / ".kodi-private"
    private.mkdir()
    (private / "devices.json").write_text(
        json.dumps(registry()), encoding="utf-8"
    )
    path = tmp_path / ".env"
    path.write_text(env, encoding="utf-8")
    path.chmod(0o600)


def test_env_is_authoritative_for_membership_and_network_addresses(tmp_path):
    write_private(
        tmp_path,
        "\n".join(
            (
                "KODI_SYNC_PUBLISHER=source-tv",
                "KODI_SYNC_DEVICES=source-tv,nuc-mwo",
                "KODI_DEVICE_SOURCE_TV_ADB=192.0.2.20:5555",
                "KODI_DEVICE_NUC_MWO_SSH_HOST=192.0.2.21",
                "KODI_PROFILE_SYNC_CHANNEL=home-stable",
                "KODI_PROFILE_SYNC_STARTUP_DELAY_SECONDS=15",
                "KODI_PROFILE_SYNC_INTERVAL_HOURS=6",
                "KODI_PROFILE_SYNC_READ_ONLY=true",
                "NUC_USER=kodi",
                "NUC_KEY=/private/key",
                "NUC_HOSTS=/private/known_hosts",
            )
        )
        + "\n",
    )

    result = load_sync_inventory(tmp_path)

    assert result["publisher"] == "source-tv"
    assert result["order"] == ["source-tv", "nuc-mwo"]
    assert result["devices"]["source-tv"]["endpoints"]["adb"] == (
        "192.0.2.20:5555"
    )
    assert result["devices"]["nuc-mwo"]["endpoints"]["ssh"]["host"] == (
        "192.0.2.21"
    )


def test_inventory_rejects_unregistered_or_nonpublisher_source(tmp_path):
    write_private(
        tmp_path,
        "\n".join(
            (
                "KODI_SYNC_PUBLISHER=nuc-mwo",
                "KODI_SYNC_DEVICES=nuc-mwo,missing",
                "KODI_DEVICE_NUC_MWO_SSH_HOST=192.0.2.21",
                "KODI_PROFILE_SYNC_CHANNEL=home-stable",
                "KODI_PROFILE_SYNC_STARTUP_DELAY_SECONDS=15",
                "KODI_PROFILE_SYNC_INTERVAL_HOURS=6",
                "KODI_PROFILE_SYNC_READ_ONLY=true",
            )
        )
        + "\n",
    )

    with pytest.raises(ValueError, match="unknown devices"):
        load_sync_inventory(tmp_path)


def test_environment_key_mapping_is_stable():
    assert device_env_prefix("bedroom-tv") == "KODI_DEVICE_BEDROOM_TV"
