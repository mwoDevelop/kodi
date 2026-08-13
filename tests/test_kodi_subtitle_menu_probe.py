from tests.e2e.kodi_subtitle_menu_probe import (
    LEGACY_ID,
    MODERN_ID,
    run_probe,
)


class FakeRpc:
    def __init__(self, *, default=MODERN_ID, include_legacy=True):
        self.default = default
        self.include_legacy = include_legacy
        self.stopped = False

    def call(self, method, params=None):
        if method == "Addons.GetAddons":
            addons = [
                {
                    "addonid": MODERN_ID,
                    "enabled": True,
                    "name": "OpenSubtitles.com (mwoDevelop)",
                    "version": "1.0.13.1",
                }
            ]
            if self.include_legacy:
                addons.append(
                    {
                        "addonid": LEGACY_ID,
                        "enabled": True,
                        "name": "OpenSubtitles.org",
                        "version": "5.1.5",
                    }
                )
            return {"addons": addons}
        if method == "Settings.GetSettingValue":
            return {"value": self.default}
        if method == "Player.Open":
            return "OK"
        if method == "Player.GetActivePlayers":
            return [{"playerid": 1, "type": "video"}]
        if method == "GUI.GetProperties":
            return {
                "currentwindow": {"id": 10153, "label": "Subtitle search"}
            }
        if method == "Player.Stop":
            self.stopped = True
            return "OK"
        raise AssertionError(method)


class FakeEvents:
    def __init__(self):
        self.commands = []

    def execute_builtin(self, command):
        self.commands.append(command)


def test_probe_verifies_both_services_default_and_search_window():
    rpc = FakeRpc()
    events = FakeEvents()

    report = run_probe(rpc, events, timeout=0.1)

    assert report["ok"] is True
    assert set(report["services"]) == {LEGACY_ID, MODERN_ID}
    assert report["defaults"] == {"movie": MODERN_ID, "tv": MODERN_ID}
    assert report["subtitle_window"]["id"] == 10153
    assert events.commands == ["ActivateWindow(subtitlesearch)"]
    assert rpc.stopped is True


def test_probe_rejects_missing_legacy_alternative():
    rpc = FakeRpc(include_legacy=False)

    try:
        run_probe(rpc, FakeEvents(), timeout=0.1)
    except RuntimeError as error:
        assert "missing" in str(error)
    else:
        raise AssertionError("missing legacy service was accepted")


def test_probe_rejects_wrong_global_default_before_playback():
    rpc = FakeRpc(default=LEGACY_ID)

    try:
        run_probe(rpc, FakeEvents(), timeout=0.1)
    except RuntimeError as error:
        assert "global default" in str(error)
    else:
        raise AssertionError("legacy global default was accepted")

    assert rpc.stopped is False
