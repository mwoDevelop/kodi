import io
import stat
from types import SimpleNamespace
from xml.etree import ElementTree

import pytest

from tools import kodi_flatpak_managed_addon_settings as managed
from tools import kodi_flatpak_stable_rollout as stable


class _WriteBuffer(io.BytesIO):
    def __init__(self, callback):
        super().__init__()
        self.callback = callback

    def close(self):
        if not self.closed:
            self.callback(self.getvalue())
        super().close()


class FakeSftp:
    def __init__(self, files):
        self.files = dict(files)
        self.directories = {
            path.rsplit("/", 1)[0] for path in self.files
        }

    def lstat(self, path):
        if path in self.directories:
            return SimpleNamespace(st_mode=stat.S_IFDIR | 0o700)
        if path not in self.files:
            raise FileNotFoundError("missing")
        return SimpleNamespace(st_mode=stat.S_IFREG | 0o600)

    def open(self, path, mode):
        if mode == "rb":
            return io.BytesIO(self.files[path])
        if mode == "wxb":
            if path in self.files:
                raise OSError("exists")
            return _WriteBuffer(lambda payload: self.files.__setitem__(path, payload))
        raise AssertionError(mode)

    def chmod(self, _path, _mode):
        pass

    def mkdir(self, path, mode=0o777):
        assert mode == 0o700
        self.directories.add(path)

    def posix_rename(self, source, destination):
        self.files[destination] = self.files.pop(source)

    def remove(self, path):
        if path not in self.files:
            raise FileNotFoundError("missing")
        del self.files[path]

    def close(self):
        pass


def _settings(**values):
    root = ElementTree.Element("settings")
    for setting_id, value in values.items():
        node = ElementTree.SubElement(root, "setting", {"id": setting_id})
        node.text = value
    return ElementTree.tostring(root, encoding="utf-8", xml_declaration=True)


def _environment(monkeypatch, running=False):
    root = "/profile"
    sftp = FakeSftp(
        {
            root + "/addons/plugin.video.umbrella/addon.xml": (
                b'<addon id="plugin.video.umbrella" version="6.7.86.1" />'
            ),
            root
            + "/userdata/addon_data/plugin.video.umbrella/settings.xml": _settings(
                **{
                    "indicators.alt": "1",
                    "markwatched.percent": "85",
                    "scrobble.source": "1",
                    "remove.av1": "true",
                }
            ),
        }
    )
    inventory = {
        "devices": {
            "nuc-mwo": {
                "platform": "linux-flatpak",
                "endpoints": {"ssh": {}},
            }
        },
        "references": {},
    }
    monkeypatch.setattr(managed, "load_sync_inventory", lambda *_args: inventory)
    monkeypatch.setattr(managed, "transport_for_device", lambda *_args: object())
    monkeypatch.setattr(
        managed,
        "lifecycle_for_device",
        lambda *_args: SimpleNamespace(
            probe_kodi=lambda: {
                "runtime_paths_qualified": True,
                "running": running,
                "data_root": root,
            }
        ),
    )
    monkeypatch.setattr(
        managed,
        "_connect_sftp",
        lambda *_args: (SimpleNamespace(close=lambda: None), sftp),
    )
    return sftp


def test_merge_settings_xml_preserves_unmanaged_values_and_storage_style():
    root = ElementTree.Element("settings")
    ElementTree.SubElement(root, "setting", {"id": "remove.av1"}).text = "true"
    ElementTree.SubElement(
        root, "setting", {"id": "remove.hdr", "value": "false"}
    )
    ElementTree.SubElement(root, "setting", {"id": "private"}).text = "keep"

    payload = managed.merge_settings_xml(
        ElementTree.tostring(root),
        {"remove.av1": "false", "remove.hdr": "true"},
    )
    parsed = ElementTree.fromstring(payload)
    nodes = {node.attrib["id"]: node for node in parsed.findall("setting")}

    assert nodes["remove.av1"].text == "false"
    assert nodes["remove.hdr"].attrib["value"] == "true"
    assert nodes["private"].text == "keep"


def test_flatpak_audit_and_apply_are_idempotent(monkeypatch):
    sftp = _environment(monkeypatch)

    audit = managed.reconcile(managed.ROOT, "nuc-mwo", apply=False)
    applied = managed.reconcile(managed.ROOT, "nuc-mwo", apply=True)
    repeated = managed.reconcile(managed.ROOT, "nuc-mwo", apply=True)

    assert audit["status"] == "DRIFT"
    assert audit["changed_setting_ids"] == {
        "plugin.video.umbrella": [
            "remove.3D.sources",
            "remove.av1",
            "remove.dolby.vision",
            "remove.hdr",
            "remove.hevc",
        ]
    }
    assert applied["status"] == "UPDATED"
    assert repeated["status"] == "NO_CHANGE"
    payload = sftp.files[
        "/profile/userdata/addon_data/plugin.video.umbrella/settings.xml"
    ]
    assert managed._settings_values(payload)["remove.av1"] == "false"


def test_flatpak_apply_refuses_to_write_while_kodi_runs(monkeypatch):
    _environment(monkeypatch, running=True)

    with pytest.raises(RuntimeError, match="must be stopped"):
        managed.reconcile(managed.ROOT, "nuc-mwo", apply=True)


def test_flatpak_stable_rollout_applies_managed_settings_after_kodi_rollout(
    monkeypatch,
):
    monkeypatch.setattr(
        stable, "prepare", lambda *_args: {
            "addons": {
                "service.mwodevelop.profilesync": {
                    "path": "profile.zip",
                    "sha256": "a" * 64,
                }
            },
            "repository": {"path": "repo.zip", "sha256": "b" * 64},
        }
    )
    monkeypatch.setattr(stable, "rollout", lambda _args: {"result": "pass"})
    monkeypatch.setattr(
        stable,
        "reconcile_settings",
        lambda _root, device, apply: {
            "device": device,
            "status": "NO_CHANGE",
            "apply": apply,
        },
    )

    result = stable.stable_rollout("nuc-mwo")

    assert result["managed_settings"] == {
        "device": "nuc-mwo",
        "status": "NO_CHANGE",
        "apply": True,
    }
