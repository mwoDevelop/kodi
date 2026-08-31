from types import SimpleNamespace

from tools.kodi_retired_addons import RETIRED_ADDONS, reconcile_retired_addons


def test_retired_addons_are_removed_leaf_first(monkeypatch):
    calls = []

    def remove(_adb, _port, _serial, addon_id, timeout):
        calls.append((addon_id, timeout))
        return {
            "directory_removed": addon_id == "plugin.video.fenlight",
            "addon_data_removed": False,
        }

    monkeypatch.setattr("tools.kodi_retired_addons.remove_addon", remove)
    monkeypatch.setattr(
        "tools.kodi_retired_addons.adb_command",
        lambda *_args, **_kwargs: SimpleNamespace(returncode=0),
    )
    monkeypatch.setattr(
        "tools.kodi_retired_addons.addon_details", lambda *_args: None
    )

    result = reconcile_retired_addons("adb", 5038, "device")

    assert [item[0] for item in calls] == list(RETIRED_ADDONS)
    assert [item[0] for item in calls[:2]] == [
        "plugin.video.fenlight",
        "plugin.youtube2kodilibrary",
    ]
    assert calls[-1][0] == "repository.universalscrapers"
    assert result == {
        "status": "UPDATED",
        "removed": ["plugin.video.fenlight"],
        "checked": len(RETIRED_ADDONS),
    }
