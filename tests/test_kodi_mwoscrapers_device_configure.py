import json
import runpy
import sys
from types import SimpleNamespace


def test_device_configure_binds_umbrella_to_mwoscrapers(monkeypatch, tmp_path):
    settings = {
        "script.module.mwoscrapers": {},
        "plugin.video.umbrella": {},
    }

    class Addon:
        def __init__(self, addon_id):
            self.addon_id = addon_id

        def setSetting(self, key, value):
            settings[self.addon_id][key] = value

        def getSetting(self, key):
            return settings[self.addon_id].get(key, "")

        def getAddonInfo(self, key):
            assert key == "version"
            return "0.1.10"

    monkeypatch.setitem(sys.modules, "xbmcaddon", SimpleNamespace(Addon=Addon))
    monkeypatch.setitem(
        sys.modules,
        "xbmcvfs",
        SimpleNamespace(
            translatePath=lambda path: str(tmp_path / "providers.db")
        ),
    )
    output = tmp_path / "report.json"
    monkeypatch.setattr(
        sys,
        "argv",
        [
            "kodi_mwoscrapers_configure.py",
            str(output),
            "https://torrentio.strem.fun",
            "https://comet.feels.legal",
        ],
    )

    runpy.run_path(
        "tests/e2e/kodi_mwoscrapers_configure.py",
        run_name="__main__",
    )

    report = json.loads(output.read_text(encoding="utf-8"))
    assert report["ok"] is True
    assert report["external_provider_enabled"] is True
    assert settings["plugin.video.umbrella"] == {
        "provider.external.enabled": "true",
        "external_provider.name": "mwoscrapers",
        "external_provider.module": "script.module.mwoscrapers",
    }
