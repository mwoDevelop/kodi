import pytest

from tools.control_plane_device_inventory import InventoryError, build_inventory


def test_inventory_is_redacted_and_supports_per_device_policy():
    payload = build_inventory(
        {
            "KODI_SYNC_DEVICES": "bluestacks1,sony-tv",
            "KODI_DEVICE_SONY_TV_MONITORING_MODE": "always_on",
            "KODI_DEVICE_SONY_TV_WARNING_AFTER_SECONDS": "3600",
            "KODI_DEVICE_SONY_TV_FAILURE_AFTER_SECONDS": "7200",
            "SONY_TV_ADB": "192.0.2.10:5555",
            "PROFILE_SYNC_TOKEN": "must-not-leak",
        }
    )

    assert payload == {
        "schema": 2,
        "devices": [
            {
                "logical_device_id": "bluestacks1",
                "monitoring_mode": "on_demand",
                "channel": "home-stable",
                "warning_after_seconds": 28800,
                "failure_after_seconds": 259200,
                "maintenance_until": None,
                "required_capabilities": ["skin-shortcuts-menu-v1"],
                "minimum_client_version": "1.5.0",
            },
            {
                "logical_device_id": "sony-tv",
                "monitoring_mode": "always_on",
                "channel": "home-stable",
                "warning_after_seconds": 3600,
                "failure_after_seconds": 7200,
                "maintenance_until": None,
                "required_capabilities": ["skin-shortcuts-menu-v1"],
                "minimum_client_version": "1.5.0",
            },
        ],
    }
    serialized = str(payload)
    assert "192.0.2.10" not in serialized
    assert "must-not-leak" not in serialized


def test_inventory_rejects_duplicates_and_invalid_thresholds():
    with pytest.raises(InventoryError, match="invalid or duplicate"):
        build_inventory({"KODI_SYNC_DEVICES": "sony-tv,sony-tv"})

    with pytest.raises(InventoryError, match="precedes warning"):
        build_inventory(
            {
                "KODI_SYNC_DEVICES": "sony-tv",
                "KODI_DEVICE_SONY_TV_WARNING_AFTER_SECONDS": "7200",
                "KODI_DEVICE_SONY_TV_FAILURE_AFTER_SECONDS": "3600",
            }
        )

    with pytest.raises(InventoryError, match="required capabilities"):
        build_inventory(
            {"KODI_SYNC_DEVICES": "sony-tv"},
            required_capabilities=["invalid_capability"],
        )

    with pytest.raises(InventoryError, match="minimum client version"):
        build_inventory(
            {"KODI_SYNC_DEVICES": "sony-tv"},
            minimum_client_version="1.5",
        )
