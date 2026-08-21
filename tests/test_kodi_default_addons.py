import hashlib
import io
from pathlib import Path
from zipfile import ZipFile

import pytest

from tools import kodi_default_addons as defaults

MANIFEST = Path("manifests/kodi-default-addons.json")


def archive(addon_id, version):
    output = io.BytesIO()
    with ZipFile(output, "w") as zipped:
        zipped.writestr(
            addon_id + "/addon.xml",
            '<addon id="%s" version="%s"/>' % (addon_id, version),
        )
    return output.getvalue()


def test_versioned_default_manifest_is_valid():
    document = defaults.load_manifest(MANIFEST)
    assert [item["id"] for item in document["addons"]] == [
        "repository.rapideo_pl",
        "script.module.xbmcswift2",
        "service.subtitles.opensubtitles",
        "plugin.video.rapideo_pl",
        "plugin.video.youtube",
    ]
    assert all(item["url"].startswith("https://") for item in document["addons"])
    youtube = document["addons"][-1]
    assert youtube["install_mode"] == "kodi-native-official"
    assert youtube["origin"] == "repository.xbmc.org"
    assert youtube["dependency_requirements"]["inputstream.adaptive"] == {
        "minimum_version": "19.0.0",
        "type": "platform",
        "supported_android_abis": ["arm64-v8a", "armeabi-v7a"],
    }


@pytest.mark.parametrize(
    ("actual", "minimum", "expected"),
    [
        ("19.0.0", "19.0.0", True),
        ("21.5.9", "19.0.0", True),
        ("2.27.1+matrix.1", "2.27.1", True),
        ("2.26.9", "2.27.1", False),
    ],
)
def test_version_at_least_uses_kodi_numeric_release_prefix(actual, minimum, expected):
    assert defaults.version_at_least(actual, minimum) is expected


def test_native_official_addon_is_installed_by_kodi_and_origin_is_audited(
    monkeypatch, tmp_path
):
    addon = {
        "id": "plugin.video.youtube",
        "version": "7.4.4",
        "kind": "plugin",
        "url": "https://example.invalid/youtube.zip",
        "sha256": "0" * 64,
        "source": "https://example.invalid/source",
        "license": "GPL-2.0-only",
        "origin": "repository.xbmc.org",
        "install_mode": "kodi-native-official",
        "dependencies": ["inputstream.adaptive"],
        "dependency_requirements": {
            "inputstream.adaptive": {
                "minimum_version": "19.0.0",
                "type": "platform",
            }
        },
    }
    installed = {}
    commands = []

    monkeypatch.setattr(
        defaults, "fetch_artifact", lambda *_args: tmp_path / "youtube.zip"
    )
    monkeypatch.setattr(
        defaults,
        "addon_details",
        lambda *_args: installed.get(_args[-1]),
    )

    class Events:
        def __init__(self, *_args):
            pass

        def execute_builtin(self, command):
            commands.append(command)
            if command == "InstallAddon(inputstream.adaptive)":
                installed["inputstream.adaptive"] = {
                    "enabled": True,
                    "version": "21.5.9",
                }
            if command == "InstallAddon(plugin.video.youtube)":
                installed["plugin.video.youtube"] = {
                    "enabled": True,
                    "version": "7.4.4",
                }

    monkeypatch.setattr(defaults, "AdbEventClient", Events)
    def install_official(*args, **_kwargs):
        addon_id = args[3]
        commands.append("InstallAddon(%s)" % addon_id)
        installed[addon_id] = {
            "enabled": True,
            "version": "21.5.9" if addon_id == "inputstream.adaptive" else "7.4.4",
        }

    monkeypatch.setattr(defaults, "install_official_addon", install_official)
    monkeypatch.setattr(defaults.time, "sleep", lambda *_args: None)
    monkeypatch.setattr(
        defaults,
        "installed_addon_origins_in_kodi",
        lambda *_args, **_kwargs: {"plugin.video.youtube": "repository.xbmc.org"},
    )

    result = defaults.reconcile_android(
        "adb",
        5038,
        "device",
        {"addons": [addon]},
        tmp_path,
        official_dependencies=[],
    )

    assert "InstallAddon(inputstream.adaptive)" in commands
    assert "InstallAddon(plugin.video.youtube)" in commands
    assert result["addons"] == {"plugin.video.youtube": "7.4.4"}
    assert result["actions"][-1]["install_mode"] == "kodi-native-official"


def test_official_install_accepts_only_new_kodi_confirmation(monkeypatch):
    calls = []
    states = iter(
        [
            {"currentwindow": {"id": 10000}},
            {
                "currentwindow": {"id": defaults.YES_NO_DIALOG_ID},
                "currentcontrol": {"label": "No"},
            },
        ]
    )

    class Rpc:
        def __init__(self, *_args):
            pass

        def __enter__(self):
            return self

        def __exit__(self, *_args):
            pass

        def call(self, method, _params=None):
            calls.append(method)
            if method == "GUI.GetProperties":
                return next(states)
            return "OK"

    class Events:
        def __init__(self, *_args):
            pass

        def execute_builtin(self, command):
            calls.append(command)

    monkeypatch.setattr(defaults, "AdbJsonRpcClient", Rpc)
    monkeypatch.setattr(defaults, "AdbEventClient", Events)
    monkeypatch.setattr(defaults, "addon_details", lambda *_args: None)

    result = defaults.install_official_addon(
        "adb", 5038, "device", "plugin.video.youtube", timeout=1
    )

    assert result == "accepted"
    assert calls == [
        "GUI.GetProperties",
        "UpdateAddonRepos",
        "InstallAddon(plugin.video.youtube)",
        "GUI.GetProperties",
        "Input.Left",
        "Input.Select",
    ]


def test_official_install_does_not_accept_stale_installed_version(monkeypatch):
    calls = []
    installed = iter(
        [
            {"enabled": True, "version": "7.3.0"},
            {"enabled": True, "version": "7.4.4"},
        ]
    )

    class Rpc:
        def __init__(self, *_args):
            pass

        def __enter__(self):
            return self

        def __exit__(self, *_args):
            pass

        def call(self, method, _params=None):
            calls.append(method)
            return {"currentwindow": {"id": 10000}}

    class Events:
        def __init__(self, *_args):
            pass

        def execute_builtin(self, command):
            calls.append(command)

    monkeypatch.setattr(defaults, "AdbJsonRpcClient", Rpc)
    monkeypatch.setattr(defaults, "AdbEventClient", Events)
    monkeypatch.setattr(defaults, "addon_details", lambda *_args: next(installed))
    monkeypatch.setattr(defaults.time, "sleep", lambda *_args: None)

    result = defaults.install_official_addon(
        "adb",
        5038,
        "device",
        "plugin.video.youtube",
        minimum_version="7.4.4",
        timeout=1,
    )

    assert result == "completed"
    assert "UpdateAddonRepos" in calls
    assert "InstallAddon(plugin.video.youtube)" in calls


def test_official_install_reenables_existing_addon_before_update(monkeypatch):
    calls = []

    class Rpc:
        def __init__(self, *_args):
            pass

        def __enter__(self):
            return self

        def __exit__(self, *_args):
            pass

        def call(self, method, params=None):
            calls.append((method, params))
            if method == "GUI.GetProperties":
                return {"currentwindow": {"id": 10000}}
            return "OK"

    class Events:
        def __init__(self, *_args):
            pass

        def execute_builtin(self, command):
            calls.append((command, None))

    observed = iter(
        [
            {"enabled": False, "version": "7.0.9.2"},
            {"enabled": True, "version": "7.4.4"},
        ]
    )
    monkeypatch.setattr(defaults, "AdbJsonRpcClient", Rpc)
    monkeypatch.setattr(defaults, "AdbEventClient", Events)
    monkeypatch.setattr(defaults, "addon_details", lambda *_args: next(observed))
    monkeypatch.setattr(defaults.time, "sleep", lambda *_args: None)

    result = defaults.install_official_addon(
        "adb",
        5038,
        "device",
        "plugin.video.youtube",
        minimum_version="7.4.4",
    )

    assert result == "completed"
    assert (
        "Addons.SetAddonEnabled",
        {"addonid": "plugin.video.youtube", "enabled": True},
    ) in calls


def test_official_install_refuses_preexisting_confirmation(monkeypatch):
    class Rpc:
        def __init__(self, *_args):
            pass

        def __enter__(self):
            return self

        def __exit__(self, *_args):
            pass

        def call(self, _method, _params=None):
            return {"currentwindow": {"id": defaults.YES_NO_DIALOG_ID}}

    monkeypatch.setattr(defaults, "AdbJsonRpcClient", Rpc)

    with pytest.raises(RuntimeError, match="already has a confirmation"):
        defaults.install_official_addon("adb", 5038, "device", "plugin.video.youtube")


def test_platform_dependency_rejects_unsupported_kodi_package_abi(
    monkeypatch, tmp_path
):
    addon = {
        "id": "plugin.video.youtube",
        "version": "7.4.4",
        "kind": "plugin",
        "url": "https://example.invalid/youtube.zip",
        "sha256": "0" * 64,
        "source": "https://example.invalid/source",
        "license": "GPL-2.0-only",
        "origin": "repository.xbmc.org",
        "install_mode": "kodi-native-official",
        "dependencies": ["inputstream.adaptive"],
        "dependency_requirements": {
            "inputstream.adaptive": {
                "minimum_version": "19.0.0",
                "type": "platform",
                "supported_android_abis": ["arm64-v8a", "armeabi-v7a"],
            }
        },
    }
    monkeypatch.setattr(
        defaults, "fetch_artifact", lambda *_args: tmp_path / "youtube.zip"
    )
    monkeypatch.setattr(defaults, "addon_details", lambda *_args: None)
    monkeypatch.setattr(defaults, "android_package_abi", lambda *_args: "x86")

    with pytest.raises(RuntimeError, match="Kodi package ABI x86"):
        defaults.reconcile_android(
            "adb", 5038, "device", {"addons": [addon]}, tmp_path
        )


def test_native_official_addon_rejects_non_official_origin(monkeypatch, tmp_path):
    addon = {
        "id": "plugin.video.youtube",
        "version": "7.4.4",
        "kind": "plugin",
        "url": "https://example.invalid/youtube.zip",
        "sha256": "0" * 64,
        "source": "https://example.invalid/source",
        "license": "GPL-2.0-only",
        "origin": "repository.xbmc.org",
        "install_mode": "kodi-native-official",
    }
    monkeypatch.setattr(
        defaults, "fetch_artifact", lambda *_args: tmp_path / "youtube.zip"
    )
    monkeypatch.setattr(
        defaults,
        "addon_details",
        lambda *_args: {"enabled": True, "version": "7.4.4"},
    )
    monkeypatch.setattr(
        defaults,
        "installed_addon_origins_in_kodi",
        lambda *_args, **_kwargs: {"plugin.video.youtube": "repository.third"},
    )

    with pytest.raises(RuntimeError, match="origin differs"):
        defaults.reconcile_android("adb", 5038, "device", {"addons": [addon]}, tmp_path)


def test_native_official_addon_repairs_same_version_byte_drift(
    monkeypatch, tmp_path
):
    addon = {
        "id": "plugin.video.youtube",
        "version": "7.4.4",
        "kind": "plugin",
        "url": "https://example.invalid/youtube.zip",
        "sha256": "0" * 64,
        "source": "https://example.invalid/source",
        "license": "GPL-2.0-only",
        "origin": "repository.xbmc.org",
        "install_mode": "kodi-native-official",
    }
    artifact = tmp_path / "youtube.zip"
    applied = []
    monkeypatch.setattr(defaults, "fetch_artifact", lambda *_args: artifact)
    monkeypatch.setattr(
        defaults,
        "addon_details",
        lambda *_args: {"enabled": True, "version": "7.4.4"},
    )
    monkeypatch.setattr(
        defaults,
        "installed_addon_origins_in_kodi",
        lambda *_args, **_kwargs: {"plugin.video.youtube": "repository.xbmc.org"},
    )
    monkeypatch.setattr(defaults, "installed_archive_matches", lambda *_args: False)
    monkeypatch.setattr(
        defaults,
        "rollout",
        lambda *_args, **_kwargs: applied.append(_args[4]) or {},
    )

    result = defaults.reconcile_android(
        "adb", 5038, "device", {"addons": [addon]}, tmp_path
    )

    assert applied == ["plugin.video.youtube"]
    assert result["actions"] == [
        {
            "addon": "plugin.video.youtube",
            "action": "repaired",
            "install_mode": "kodi-native-official",
            "version": "7.4.4",
        }
    ]


def test_fetch_artifact_verifies_digest_and_identity(tmp_path):
    payload = archive("repository.example", "1.2.3")
    addon = {
        "id": "repository.example",
        "version": "1.2.3",
        "sha256": hashlib.sha256(payload).hexdigest(),
        "url": "https://example.invalid/repository.zip",
    }

    class Response(io.BytesIO):
        def __enter__(self):
            return self

        def __exit__(self, *_args):
            self.close()

    path = defaults.fetch_artifact(
        addon, tmp_path, opener=lambda *_args, **_kwargs: Response(payload)
    )

    assert path.read_bytes() == payload


def test_fetch_artifact_rejects_digest_mismatch(tmp_path):
    payload = archive("repository.example", "1.2.3")
    addon = {
        "id": "repository.example",
        "version": "1.2.3",
        "sha256": "0" * 64,
        "url": "https://example.invalid/repository.zip",
    }

    class Response(io.BytesIO):
        def __enter__(self):
            return self

        def __exit__(self, *_args):
            self.close()

    with pytest.raises(ValueError, match="digest differs"):
        defaults.fetch_artifact(
            addon, tmp_path, opener=lambda *_args, **_kwargs: Response(payload)
        )


def test_official_dependency_repair_checks_archive_bytes(monkeypatch, tmp_path):
    dependency = {
        "id": "script.module.urllib3",
        "version": "2.2.3",
        "sha256": "a" * 64,
        "url": (
            "https://mirrors.kodi.tv/addons/omega/"
            "script.module.urllib3/script.module.urllib3-2.2.3.zip"
        ),
    }
    artifact = tmp_path / "urllib3.zip"
    artifact.write_bytes(b"candidate")
    applied = []
    monkeypatch.setattr(defaults, "fetch_artifact", lambda *_args: artifact)
    monkeypatch.setattr(
        defaults,
        "addon_details",
        lambda *_args: {"enabled": True, "version": "2.2.3"},
    )
    monkeypatch.setattr(
        defaults,
        "installed_archive_matches",
        lambda *_args: False,
    )
    monkeypatch.setattr(
        defaults,
        "rollout",
        lambda *_args, **_kwargs: applied.append(_args[4]) or {},
    )

    actions = defaults.reconcile_official_dependencies(
        "adb", 5038, "serial", [dependency], tmp_path, 180
    )

    assert applied == ["script.module.urllib3"]
    assert actions == [
        {
            "addon": "script.module.urllib3",
            "action": "repaired",
            "version": "2.2.3",
        }
    ]


def test_reconcile_repairs_only_a_database_absent_orphan(monkeypatch, tmp_path):
    addon = {
        "id": "repository.rapideo_pl",
        "version": "1.0.4",
        "kind": "repository",
        "url": "https://example.invalid/repository.zip",
        "sha256": "0" * 64,
        "source": "https://example.invalid/source",
        "license": "GPL-2.0-only",
    }
    current = {}
    repair_flags = []

    monkeypatch.setattr(
        defaults, "fetch_artifact", lambda *_args: tmp_path / "addon.zip"
    )
    monkeypatch.setattr(
        defaults,
        "addon_details",
        lambda *_args: current.get(addon["id"]),
    )

    def apply(*_args, **kwargs):
        repair = kwargs.get("repair_orphan", False)
        repair_flags.append(repair)
        if not repair:
            raise RuntimeError(
                "Kodi candidate apply failed: PermissionError at backup-installed-addon"
            )
        current[addon["id"]] = {
            "enabled": True,
            "version": addon["version"],
        }
        return {"repaired_orphan": True}

    monkeypatch.setattr(defaults, "rollout", apply)
    monkeypatch.setattr(
        defaults,
        "AdbEventClient",
        lambda *_args: type("Events", (), {"execute_builtin": lambda *_args: None})(),
    )
    monkeypatch.setattr(defaults.time, "sleep", lambda *_args: None)

    result = defaults.reconcile_android(
        "adb",
        5038,
        "serial",
        {"addons": [addon]},
        tmp_path,
        assign_origins=False,
    )

    assert repair_flags == [False, True]
    assert result["actions"][0]["repaired_orphan"] is True
