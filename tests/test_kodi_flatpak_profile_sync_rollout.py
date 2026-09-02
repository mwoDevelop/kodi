import hashlib
import importlib.util
import io
import json
import sqlite3
import stat
import subprocess
import sys
import types
import zipfile
from pathlib import Path, PurePosixPath
from xml.etree import ElementTree

import pytest

from tools import build_repo
from tools.kodi_flatpak_profile_sync_rollout import (
    DEFAULT_REQUIRED_ADDONS,
    _cleanup_command,
    _event_packets,
    _event_server_ready,
    _installation_mode,
    _replace_private_document,
    _send_staged_event_builtin,
    _stage_event_packets,
    build_settings,
    extract_addon,
    official_default_addons,
    official_dependency_artifacts,
    profile_sync_server_url,
    required_addon_artifacts,
    required_addons,
    stable_profile_sync_zip,
    youtube_configuration_payload,
)


def _receipt(device="nuc-mwo", version="1.0.0"):
    artifact = {
        "filename": "service.test.zip",
        "sha256": "a" * 64,
        "version": version,
    }
    return {
        "logical_device_id": device,
        "profile_sync_version": "1.0.3",
        "repository_version": "1.0.0",
        "required_addons": {"service.test": version},
        "required_artifacts": {"service.test": artifact},
        "dependency_artifacts": {},
    }


def test_installation_receipt_allows_a_valid_stable_upgrade():
    previous = _receipt(version="1.0.0")
    expected = _receipt(version="2.0.0")
    legacy = _receipt(version="1.0.0")
    legacy.pop("dependency_artifacts")

    assert _installation_mode(previous, expected, "nuc-mwo") == "install"
    assert _installation_mode(legacy, expected, "nuc-mwo") == "install"
    assert _installation_mode(expected, expected, "nuc-mwo") == "sync"


def test_installation_receipt_rejects_wrong_identity_or_digest():
    expected = _receipt(version="2.0.0")
    wrong_device = _receipt(device="nuc-alek")
    invalid_digest = _receipt()
    invalid_digest["required_artifacts"]["service.test"]["sha256"] = "tampered"

    with pytest.raises(ValueError, match="installation receipt differs"):
        _installation_mode(wrong_device, expected, "nuc-mwo")
    with pytest.raises(ValueError, match="installation receipt differs"):
        _installation_mode(invalid_digest, expected, "nuc-mwo")


def _write_addon_zip(path, member="service.test/addon.xml"):
    with zipfile.ZipFile(path, "w") as archive:
        archive.writestr(
            member,
            '<addon id="service.test" version="1.2.3" />',
        )
    return hashlib.sha256(path.read_bytes()).hexdigest()


def test_extract_addon_checks_digest_identity_and_inventory(tmp_path):
    archive = tmp_path / "addon.zip"
    digest = _write_addon_zip(archive)

    root, version = extract_addon(
        archive,
        "service.test",
        digest,
        tmp_path / "output",
    )

    assert version == "1.2.3"
    assert (root / "addon.xml").is_file()
    assert stat.S_IMODE((root / "addon.xml").stat().st_mode) == 0o644


def test_extract_addon_rejects_path_traversal(tmp_path):
    archive = tmp_path / "unsafe.zip"
    digest = _write_addon_zip(archive, "service.test/../outside")

    with pytest.raises(ValueError, match="unsafe entry"):
        extract_addon(
            archive,
            "service.test",
            digest,
            tmp_path / "output",
        )


def test_build_settings_contains_only_non_secret_device_configuration(tmp_path):
    destination = tmp_path / "settings.xml"

    values = build_settings(
        destination,
        "https://profile-sync.invalid:8766",
        "nuc-test",
        "home-stable",
        {
            "startup_delay_seconds": "15",
            "interval_hours": "6",
            "read_only": "true",
        },
    )

    parsed = {
        node.get("id"): node.text
        for node in ElementTree.parse(destination).getroot()
    }
    assert parsed == values
    assert parsed["enabled"] == "false"
    assert "token" not in destination.read_text(encoding="utf-8").lower()
    assert stat.S_IMODE(destination.stat().st_mode) == 0o600


def test_flatpak_uses_published_profile_sync_port_unless_overridden():
    assert profile_sync_server_url("192.0.2.39") == (
        "https://192.0.2.39:18765"
    )
    assert profile_sync_server_url(
        "192.0.2.39", "https://sync.example.invalid:9443"
    ) == "https://sync.example.invalid:9443"


def test_flatpak_bootstrap_document_rotates_atomically_and_stays_private(
    tmp_path,
):
    destination = tmp_path / "bootstrap.json"

    assert _replace_private_document(destination, '{"revision":"old"}\n')
    assert stat.S_IMODE(destination.stat().st_mode) == 0o600
    assert _replace_private_document(destination, '{"revision":"new"}\n')
    assert destination.read_text(encoding="utf-8") == '{"revision":"new"}\n'
    assert not _replace_private_document(
        destination, '{"revision":"new"}\n'
    )


def test_flatpak_required_addons_cover_managed_settings_and_favourites():
    assert DEFAULT_REQUIRED_ADDONS == (
        "script.module.mwoscrapers",
        "script.mwoscrapers",
        "plugin.video.umbrella",
        "plugin.video.watchnixtoons2.mwodevelop",
        "service.subtitles.opensubtitles-com",
    )


def test_flatpak_required_addons_are_exactly_pinned_by_stable_lock():
    result = required_addons(".")
    stable = json.loads(
        Path("manifests/locks/stable.json").read_text(encoding="utf-8")
    )["components"]

    assert tuple(result) == tuple(
        addon_id
        for addon_id in DEFAULT_REQUIRED_ADDONS
        if addon_id in stable
    )
    assert result == {
        addon_id: stable[addon_id]["version"]
        for addon_id in DEFAULT_REQUIRED_ADDONS
        if addon_id in stable
    }


def test_flatpak_required_artifacts_match_stable_lock():
    required = required_addons(".")

    artifacts = required_addon_artifacts(".", required)

    assert set(artifacts) == set(required)
    for addon_id, artifact in artifacts.items():
        assert artifact["version"] == required[addon_id]
        assert artifact["filename"] == addon_id + ".zip"
        assert artifact["path"].is_file()
        assert len(artifact["sha256"]) == 64


def test_flatpak_builds_missing_stable_artifact_from_exact_lock(
    tmp_path, monkeypatch
):
    files = [
        (
            b'<addon id="service.test" version="1.2.3" />',
            PurePosixPath("addon.xml"),
        ),
        (b"payload\n", PurePosixPath("resources/value.txt")),
    ]
    expected = tmp_path / "expected.zip"
    build_repo.write_deterministic_zip(expected, "service.test", files)
    digest = hashlib.sha256(expected.read_bytes()).hexdigest()
    expected.unlink()
    manifests = tmp_path / "manifests/locks"
    manifests.mkdir(parents=True)
    (tmp_path / "manifests/components.json").write_text(
        json.dumps(
            {
                "components": {
                    "service.test": {
                        "repository": "example/service.test",
                        "source": "service.test",
                        "include": ["*"],
                    }
                }
            }
        ),
        encoding="utf-8",
    )
    (manifests / "stable.json").write_text(
        json.dumps(
            {
                "components": {
                    "service.test": {
                        "commit": "a" * 40,
                        "version": "1.2.3",
                        "zip_sha256": digest,
                    }
                }
            }
        ),
        encoding="utf-8",
    )
    monkeypatch.setattr(build_repo, "component_files", lambda *_args: files)

    artifacts = required_addon_artifacts(
        tmp_path, {"service.test": "1.2.3"}
    )

    archive = artifacts["service.test"]["path"]
    assert archive.read_bytes()
    assert artifacts["service.test"]["sha256"] == digest
    assert stat.S_IMODE(archive.stat().st_mode) == 0o600


def test_flatpak_official_dependencies_use_verified_private_cache(tmp_path):
    manifest = tmp_path / "manifests"
    manifest.mkdir()
    cache = tmp_path / ".kodi-private/candidates/kodi-official"
    cache.mkdir(parents=True)
    archive = cache / "script.module.one-1.2.3.zip"
    with zipfile.ZipFile(archive, "w") as payload:
        payload.writestr(
            "script.module.one/addon.xml",
            '<addon id="script.module.one" version="1.2.3" />',
        )
    digest = hashlib.sha256(archive.read_bytes()).hexdigest()
    (manifest / "kodi-official-dependencies.json").write_text(
        json.dumps(
            {
                "schema": 1,
                "dependencies": {
                    "script.module.one": {
                        "sha256": digest,
                        "url": (
                            "https://mirrors.kodi.tv/addons/omega/"
                            "script.module.one/script.module.one-1.2.3.zip"
                        ),
                        "version": "1.2.3",
                    }
                },
            }
        )
    )

    artifacts = official_dependency_artifacts(tmp_path)

    assert artifacts["script.module.one"]["path"] == archive
    assert artifacts["script.module.one"]["sha256"] == digest


def test_flatpak_native_official_addon_is_qualified_without_republishing(
    tmp_path, monkeypatch
):
    addon = {
        "id": "plugin.video.youtube",
        "version": "7.4.4",
        "kind": "plugin",
        "url": "https://mirrors.kodi.tv/addons/omega/plugin.video.youtube.zip",
        "sha256": "a" * 64,
        "source": "https://github.com/example/youtube",
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
    fetched = []
    monkeypatch.setattr(
        "tools.kodi_flatpak_profile_sync_rollout.load_manifest",
        lambda _path: {"addons": [addon]},
    )
    monkeypatch.setattr(
        "tools.kodi_flatpak_profile_sync_rollout.fetch_artifact",
        lambda item, cache: fetched.append((item["id"], cache)),
    )

    result = official_default_addons(tmp_path)

    assert result == {
        "plugin.video.youtube": {
            "version": "7.4.4",
            "origin": "repository.xbmc.org",
            "sha256": "a" * 64,
            "dependency_requirements": addon["dependency_requirements"],
        }
    }
    assert fetched == [
        (
            "plugin.video.youtube",
            tmp_path / ".kodi-private/cache/default-addons",
        )
    ]


def test_flatpak_youtube_payload_excludes_account_hint_and_password():
    references = {
        "YOUTUBE_API_KEY": "AIza" + "a" * 35,
        "YOUTUBE_CLIENT_ID": "123456789-example.apps.googleusercontent.com",
        "YOUTUBE_CLIENT_SECRET": "GOCSPX-private",
        "YOUTUBE_USER": "user@example.invalid",
        "YOUTUBE_PASS": "must-not-be-read",
    }

    payload = youtube_configuration_payload(references)

    assert payload == {
        "schema": 1,
        "addon_version": "7.4.4",
        "api_key": references["YOUTUBE_API_KEY"],
        "client_id": references["YOUTUBE_CLIENT_ID"],
        "client_secret": references["YOUTUBE_CLIENT_SECRET"],
    }
    assert references["YOUTUBE_USER"] not in json.dumps(payload)
    assert references["YOUTUBE_PASS"] not in json.dumps(payload)


def test_flatpak_youtube_payload_is_deferred_when_api_profile_is_absent():
    assert youtube_configuration_payload(
        {"YOUTUBE_USER": "user@example.invalid", "YOUTUBE_PASS": "unused"}
    ) is None


def test_flatpak_youtube_payload_uses_private_portable_session(tmp_path):
    session_path = tmp_path / ".kodi-private/youtube/session.json"
    session_path.parent.mkdir(parents=True)
    session = {
        "schema": 1,
        "addon_id": "plugin.video.youtube",
        "addon_version": "7.4.4",
        "account_hint": "user@example.invalid",
        "expected_channel_id": "UC" + "c" * 22,
        "api_key": "AIza" + "a" * 35,
        "client_id": "123456789-example.apps.googleusercontent.com",
        "client_secret": "GOCSPX-private",
        "tv_refresh_token": "tv_" + "t" * 30,
        "personal_refresh_token": "personal_" + "p" * 30,
        "vr_refresh_token": "vr_" + "v" * 30,
    }
    session_path.write_text(json.dumps(session) + "\n", encoding="utf-8")
    session_path.chmod(0o600)

    payload = youtube_configuration_payload(
        {"YOUTUBE_USER": session["account_hint"]}, tmp_path
    )

    assert payload == {
        "schema": 2,
        "addon_version": "7.4.4",
        "api_key": session["api_key"],
        "client_id": session["client_id"],
        "client_secret": session["client_secret"],
        "session": {
            "account_hint": session["account_hint"],
            "expected_channel_id": session["expected_channel_id"],
            "tv_refresh_token": session["tv_refresh_token"],
            "personal_refresh_token": session["personal_refresh_token"],
            "vr_refresh_token": session["vr_refresh_token"],
        },
    }


def test_cleanup_command_is_valid_shell_and_scopes_all_paths_to_operation():
    operation = "0123456789abcdef"
    command = _cleanup_command(operation)

    subprocess.run(["sh", "-n", "-c", command], check=True)
    assert command.count(operation) == 8
    assert "kill -TERM" in command
    assert "kill -KILL" in command
    assert "/tmp/mwo-kodi-" in command
    assert "/tmp/mwo-xvfb-" in command


def test_event_packets_encode_one_bounded_runscript_command():
    command = "RunScript(/tmp/bootstrap.py,/tmp/stage,install)"

    packets = _event_packets(command, 1234)

    assert len(packets) == 3
    assert all(packet.startswith(b"XBMC\x02\x00") for packet in packets)
    assert command.encode("utf-8") in packets[1]


def test_event_packets_are_staged_private_for_loopback_delivery():
    class Handle(io.BytesIO):
        def __init__(self, path, files):
            super().__init__()
            self.path = path
            self.files = files

        def close(self):
            self.files[self.path] = self.getvalue()
            super().close()

    class Sftp:
        def __init__(self):
            self.files = {}
            self.modes = {}

        def open(self, path, mode):
            assert mode == "wb"
            return Handle(path, self.files)

        def chmod(self, path, mode):
            self.modes[path] = mode

    sftp = Sftp()
    paths = _stage_event_packets(
        sftp,
        "/profile/temp/.mwodevelop-flatpak-operation",
        "RunScript(/tmp/bootstrap.py,/tmp/stage,install)",
    )

    assert paths == [
        "/profile/temp/.mwodevelop-flatpak-operation/.event-0.bin",
        "/profile/temp/.mwodevelop-flatpak-operation/.event-1.bin",
        "/profile/temp/.mwodevelop-flatpak-operation/.event-2.bin",
    ]
    assert all(sftp.modes[path] == 0o600 for path in paths)
    assert all(sftp.files[path].startswith(b"XBMC\x02\x00") for path in paths)


def test_staged_event_packets_are_sent_only_to_nuc_loopback(monkeypatch):
    observed = {}

    def fake_remote(transport, command, timeout=30):
        observed.update(transport=transport, command=command, timeout=timeout)

    monkeypatch.setattr(
        "tools.kodi_flatpak_profile_sync_rollout._remote_command", fake_remote
    )
    transport = object()
    paths = ["/stage/.event-%s.bin" % index for index in range(3)]

    _send_staged_event_builtin(transport, paths)

    assert observed["transport"] is transport
    assert observed["timeout"] == 10
    assert observed["command"].count("127.0.0.1 9777") == 3
    assert observed["command"].count("nc -u -w 1") == 3
    assert "192.168." not in observed["command"]


def test_event_server_readiness_requires_current_regular_kodi_log():
    class Sftp:
        def __init__(self, payload, mtime=2):
            self.payload = payload
            self.mtime = mtime

        def lstat(self, _path):
            return types.SimpleNamespace(
                st_mode=stat.S_IFREG | 0o600,
                st_size=len(self.payload),
                st_mtime=self.mtime,
            )

        def open(self, _path, _mode):
            return io.BytesIO(self.payload)

    assert _event_server_ready(
        Sftp(b"UDP: Listening on port 9777"),
        "/profile/temp/kodi.log",
        after_mtime=1,
    )
    assert not _event_server_ready(
        Sftp(b"Kodi is starting"), "/profile/temp/kodi.log"
    )
    assert not _event_server_ready(
        Sftp(b"UDP: Listening on port 9777", mtime=1),
        "/profile/temp/kodi.log",
        after_mtime=1,
    )


def test_documented_direct_cli_entrypoint_loads_repository_modules():
    result = subprocess.run(
        [
            sys.executable,
            "tools/kodi_flatpak_profile_sync_rollout.py",
            "--help",
        ],
        capture_output=True,
        text=True,
        check=False,
    )

    assert result.returncode == 0, result.stderr
    assert "--profile-sync-sha256" in result.stdout


def test_profile_sync_default_artifact_follows_stable_lock(tmp_path):
    lock = tmp_path / "manifests/locks/stable.json"
    lock.parent.mkdir(parents=True)
    lock.write_text(
        json.dumps(
            {
                "components": {
                    "service.mwodevelop.profilesync": {"version": "2.3.4"}
                }
            }
        ),
        encoding="utf-8",
    )

    assert stable_profile_sync_zip(tmp_path) == PurePosixPath(
        ".kodi-private/candidates/"
        "service.mwodevelop.profilesync-2.3.4-stable.zip"
    )


def test_script_path_does_not_duplicate_ssh_transport_class_identity():
    result = subprocess.run(
        [
            sys.executable,
            "-c",
            (
                "import sys; sys.path.insert(0, 'tools'); "
                "from tools.kodi_lifecycle import SshTransport as lifecycle; "
                "from tools.kodi_transports import SshTransport as transport; "
                "assert lifecycle is transport"
            ),
        ],
        capture_output=True,
        text=True,
        check=False,
    )

    assert result.returncode == 0, result.stderr


def test_in_kodi_recovery_restores_only_targets_already_moved(
    tmp_path, monkeypatch
):
    for name in ("xbmc", "xbmcaddon", "xbmcvfs"):
        monkeypatch.setitem(sys.modules, name, types.ModuleType(name))
    source = "tools/kodi_flatpak_profile_sync_device.py"
    spec = importlib.util.spec_from_file_location("flatpak_device_test", source)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)

    targets = {
        "untouched": tmp_path / "untouched",
        "moved": tmp_path / "moved",
        "new": tmp_path / "new",
    }
    backup = tmp_path / "backup"
    backup.mkdir()
    targets["untouched"].mkdir()
    (targets["untouched"] / "value").write_text("original")
    targets["moved"].mkdir()
    (targets["moved"] / "value").write_text("candidate")
    (backup / "moved").mkdir()
    (backup / "moved" / "value").write_text("original")
    targets["new"].mkdir()
    journal = tmp_path / "journal.json"
    journal.write_text(
        json.dumps(
            {"schema": 1, "existing": ["untouched", "moved"]}
        )
    )

    module._recover(journal, targets, backup)

    assert (targets["untouched"] / "value").read_text() == "original"
    assert (targets["moved"] / "value").read_text() == "original"
    assert not targets["new"].exists()
    assert not journal.exists()
    assert not backup.exists()


def test_in_kodi_new_addon_is_enabled_before_settings_are_opened(
    tmp_path, monkeypatch
):
    xbmc = types.ModuleType("xbmc")
    xbmc.sleep = lambda _milliseconds: None
    xbmcaddon = types.ModuleType("xbmcaddon")
    xbmcaddon.Addon = lambda addon_id: {"addon_id": addon_id}
    xbmcvfs = types.ModuleType("xbmcvfs")
    for name, module in (
        ("xbmc", xbmc),
        ("xbmcaddon", xbmcaddon),
        ("xbmcvfs", xbmcvfs),
    ):
        monkeypatch.setitem(sys.modules, name, module)
    source = "tools/kodi_flatpak_profile_sync_device.py"
    spec = importlib.util.spec_from_file_location("flatpak_device_enable", source)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    calls = []

    def enable(addon_id, timeout=30):
        calls.append((addon_id, timeout))

    def addon(addon_id):
        assert calls == [(addon_id, 7)]
        return {"addon_id": addon_id}

    monkeypatch.setattr(module, "_enable", enable)
    xbmcaddon.Addon = addon

    result = module._enabled_addon("service.test", timeout=7)

    assert result == {"addon_id": "service.test"}


def test_in_kodi_profile_sync_runs_dynamic_favourites_lifecycle(
    tmp_path, monkeypatch
):
    xbmc = types.ModuleType("xbmc")
    xbmc.executeJSONRPC = lambda _request: "{}"
    xbmcaddon = types.ModuleType("xbmcaddon")
    xbmcaddon.Addon = lambda _addon_id=None: object()
    xbmcvfs = types.ModuleType("xbmcvfs")
    for name, module_object in (
        ("xbmc", xbmc),
        ("xbmcaddon", xbmcaddon),
        ("xbmcvfs", xbmcvfs),
    ):
        monkeypatch.setitem(sys.modules, name, module_object)
    source = "tools/kodi_flatpak_profile_sync_device.py"
    spec = importlib.util.spec_from_file_location(
        "flatpak_device_favourites", source
    )
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)

    calls = []

    class Addon:
        def setSetting(self, key, value):
            calls.append(("setting", key, value))

    class StateStore:
        def __init__(self, profile):
            calls.append(("state", profile))

        def read(self):
            return {
                "enrollment": {"logical_device_id": "nuc-test"},
                "status": "NO_CHANGE",
                "assigned_revision": "sha256:" + "a" * 64,
                "applied_revision": "sha256:" + "a" * 64,
                "favourites_status": "HEALTHY",
                "favourites_cursor": 6,
                "favourites_pending_count": 0,
                "favourites_dynamic_fence": True,
            }

    class Recoverable:
        def __init__(self, *_args, **_kwargs):
            pass

        def recover(self):
            calls.append("recover")

    class ReadOnlySync:
        def __init__(self, *_args, **_kwargs):
            pass

        def __call__(self):
            calls.append("profile-sync")
            return {"status": "NO_CHANGE"}

    class FavouritesSync:
        def __init__(self, *_args, **_kwargs):
            calls.append("favourites-created")

        def __call__(self):
            calls.append("favourites-sync")
            return {"status": "HEALTHY"}

    class FavouritesTicker:
        def __init__(self, sync, _state):
            self.sync = sync

        def tick(self):
            return self.sync()

    modules = {
        "resources": types.ModuleType("resources"),
        "resources.lib": types.ModuleType("resources.lib"),
        "resources.lib.mwoprofilesync": types.ModuleType(
            "resources.lib.mwoprofilesync"
        ),
        "resources.lib.mwoprofilesync.apply": types.SimpleNamespace(
            KodiAddonSettings=lambda *_args: object(),
            TransactionalApplier=Recoverable,
        ),
        "resources.lib.mwoprofilesync.portable": types.SimpleNamespace(
            KodiFavourites=lambda *_args: object(),
            PortableFavouritesAdapter=lambda *_args: object(),
            PortableFavouritesExporter=lambda *_args: object(),
        ),
        "resources.lib.mwoprofilesync.state": types.SimpleNamespace(
            StateStore=StateStore
        ),
        "resources.lib.mwoprofilesync.sync": types.SimpleNamespace(
            ReadOnlySync=ReadOnlySync
        ),
        "resources.lib.mwoprofilesync.favourites_state": types.SimpleNamespace(
            FavouritesApplier=Recoverable,
            FavouritesJournal=lambda *_args: object(),
            FavouritesSync=FavouritesSync,
            FavouritesTicker=FavouritesTicker,
        ),
        "resources.lib.mwoprofilesync.playback": types.SimpleNamespace(
            KodiPlaybackAdapter=lambda *_args: object(),
            PlaybackJournal=lambda *_args: object(),
            PlaybackSync=FavouritesSync,
            PlaybackTicker=FavouritesTicker,
        ),
    }
    for name, fake in modules.items():
        monkeypatch.setitem(sys.modules, name, fake)
    monkeypatch.setattr(module, "_wait_favourites_api", lambda: None)
    monkeypatch.setattr(module, "_enable", lambda _addon_id: None)
    monkeypatch.setattr(module, "_enabled_addon", lambda _addon_id: Addon())

    result = module._sync(
        tmp_path / "profile", tmp_path / "addons", "1.4.2", "1.0.0"
    )

    assert result["sync_status"] == "NO_CHANGE"
    assert result["favourites_sync_status"] == "HEALTHY"
    assert result["favourites_status"] == "HEALTHY"
    assert result["favourites_cursor"] == 6
    assert result["favourites_pending_count"] == 0
    assert result["favourites_dynamic_fence"] is True
    assert result["playback_sync_status"] == "HEALTHY"
    assert result["playback_status"] is None
    assert calls.count("recover") == 2
    assert "favourites-sync" in calls
    assert ("setting", "enabled", "true") in calls


def test_in_kodi_reconciles_required_addons_before_profile_apply(
    monkeypatch,
):
    xbmc = types.ModuleType("xbmc")
    builtins = []
    xbmc.executebuiltin = builtins.append
    xbmc.sleep = lambda _milliseconds: None
    xbmcaddon = types.ModuleType("xbmcaddon")
    xbmcaddon.Addon = lambda addon_id: {"addon_id": addon_id}
    xbmcvfs = types.ModuleType("xbmcvfs")
    for name, module_object in (
        ("xbmc", xbmc),
        ("xbmcaddon", xbmcaddon),
        ("xbmcvfs", xbmcvfs),
    ):
        monkeypatch.setitem(sys.modules, name, module_object)
    source = "tools/kodi_flatpak_profile_sync_device.py"
    spec = importlib.util.spec_from_file_location(
        "flatpak_device_required", source
    )
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    enabled = []
    probes = {}

    monkeypatch.setattr(
        module,
        "_enable",
        lambda addon_id, timeout=30: enabled.append(addon_id),
    )

    def details(addon_id):
        probes[addon_id] = probes.get(addon_id, 0) + 1
        if probes[addon_id] == 1:
            return None
        return {"version": "1.2.3", "enabled": True}

    monkeypatch.setattr(module, "_addon_details", details)

    result = module._reconcile_required_addons(
        {"plugin.video.one": "1.2.3", "script.module.two": "1.2.3"}
    )

    assert enabled == ["repository.mwodevelop"]
    assert builtins == [
        "UpdateAddonRepos",
        "InstallAddon(plugin.video.one)",
        "InstallAddon(script.module.two)",
    ]
    assert result == {
        "plugin.video.one": "1.2.3",
        "script.module.two": "1.2.3",
    }


def test_in_kodi_reconciles_native_official_addon_and_platform_dependency(
    monkeypatch,
):
    xbmc = types.ModuleType("xbmc")
    builtins = []
    xbmc.executebuiltin = builtins.append
    xbmc.sleep = lambda _milliseconds: None
    xbmcaddon = types.ModuleType("xbmcaddon")
    xbmcaddon.Addon = lambda addon_id: {"addon_id": addon_id}
    xbmcvfs = types.ModuleType("xbmcvfs")
    for name, module_object in (
        ("xbmc", xbmc),
        ("xbmcaddon", xbmcaddon),
        ("xbmcvfs", xbmcvfs),
    ):
        monkeypatch.setitem(sys.modules, name, module_object)
    source = "tools/kodi_flatpak_profile_sync_device.py"
    spec = importlib.util.spec_from_file_location(
        "flatpak_device_official", source
    )
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    probes = {}
    enabled = []
    monkeypatch.setattr(
        module,
        "_enable",
        lambda addon_id, timeout=30: enabled.append(addon_id),
    )

    def details(addon_id):
        probes[addon_id] = probes.get(addon_id, 0) + 1
        if addon_id == "inputstream.adaptive":
            return {"version": "21.5.9", "enabled": True}
        if probes[addon_id] == 1:
            return None
        return {"version": "7.4.4", "enabled": True}

    monkeypatch.setattr(module, "_addon_details", details)
    monkeypatch.setattr(
        module,
        "_installed_origin",
        lambda _addon_id: "repository.xbmc.org",
    )

    result = module._reconcile_native_official(
        {
            "plugin.video.youtube": {
                "version": "7.4.4",
                "origin": "repository.xbmc.org",
                "sha256": "a" * 64,
                "dependency_requirements": {
                    "inputstream.adaptive": {
                        "minimum_version": "19.0.0",
                        "type": "platform",
                        "supported_android_abis": [
                            "arm64-v8a",
                            "armeabi-v7a",
                        ],
                    }
                },
            }
        }
    )

    assert enabled == ["repository.xbmc.org"]
    assert builtins == [
        "UpdateAddonRepos",
        "InstallAddon(plugin.video.youtube)",
    ]
    assert result == {"plugin.video.youtube": "7.4.4"}


def test_in_kodi_forgets_and_reassigns_native_official_origin(
    tmp_path, monkeypatch
):
    for name in ("xbmc", "xbmcaddon", "xbmcvfs"):
        monkeypatch.setitem(sys.modules, name, types.ModuleType(name))
    source = "tools/kodi_flatpak_profile_sync_device.py"
    spec = importlib.util.spec_from_file_location(
        "flatpak_device_official_database", source
    )
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    database = tmp_path / "Addons33.db"
    connection = sqlite3.connect(database)
    try:
        connection.executescript(
            """
            CREATE TABLE installed (addonID TEXT PRIMARY KEY, origin TEXT);
            CREATE TABLE update_rules (addonID TEXT);
            CREATE TABLE package (addonID TEXT);
            INSERT INTO installed VALUES ('plugin.video.youtube', 'repository.beta');
            INSERT INTO update_rules VALUES ('plugin.video.youtube');
            INSERT INTO package VALUES ('plugin.video.youtube');
            """
        )
        connection.commit()
    finally:
        connection.close()
    monkeypatch.setattr(module, "_addon_database", lambda: str(database))

    module._forget_native_official("plugin.video.youtube")
    connection = sqlite3.connect(database)
    try:
        assert connection.execute("SELECT * FROM installed").fetchall() == []
        assert connection.execute("SELECT * FROM update_rules").fetchall() == []
        assert connection.execute("SELECT * FROM package").fetchall() == []
        connection.execute(
            "INSERT INTO installed VALUES (?, ?)",
            ("plugin.video.youtube", ""),
        )
        connection.commit()
    finally:
        connection.close()

    module._set_installed_origin(
        "plugin.video.youtube", "repository.xbmc.org"
    )

    assert module._installed_origin("plugin.video.youtube") == (
        "repository.xbmc.org"
    )


def test_in_kodi_youtube_adapter_returns_explicit_unconfigured_status(
    tmp_path, monkeypatch
):
    for name in ("xbmc", "xbmcaddon", "xbmcvfs"):
        monkeypatch.setitem(sys.modules, name, types.ModuleType(name))
    source = "tools/kodi_flatpak_profile_sync_device.py"
    spec = importlib.util.spec_from_file_location(
        "flatpak_device_youtube_unconfigured", source
    )
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    (tmp_path / "youtube-configure.py").write_text("pass\n")

    assert module._configure_youtube(tmp_path) == {
        "ok": True,
        "status": "API_CONFIG_REQUIRED",
        "authorization": "AUTHORIZATION_REQUIRED",
    }


def test_in_kodi_youtube_adapter_accepts_only_sanitized_report(
    tmp_path, monkeypatch
):
    for name in ("xbmc", "xbmcaddon", "xbmcvfs"):
        monkeypatch.setitem(sys.modules, name, types.ModuleType(name))
    source = "tools/kodi_flatpak_profile_sync_device.py"
    spec = importlib.util.spec_from_file_location(
        "flatpak_device_youtube_configured", source
    )
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    (tmp_path / "youtube-configure.py").write_text("pass\n")
    (tmp_path / "youtube-config.json").write_text('{"schema":2}\n')

    def run(_path, run_name):
        assert run_name == "__main__"
        Path(sys.argv[2]).write_text(
            json.dumps(
                {
                    "ok": True,
                    "schema": 2,
                    "stage": "complete",
                    "authorization": "AUTHORIZATION_REQUIRED",
                    "personal_api_configured": True,
                }
            )
        )

    monkeypatch.setattr(module.runpy, "run_path", run)

    result = module._configure_youtube(tmp_path)

    assert result["personal_api_configured"] is True
    assert "private" not in json.dumps(result)


def test_in_kodi_required_artifacts_are_digest_and_version_pinned(
    tmp_path, monkeypatch
):
    xbmc = types.ModuleType("xbmc")
    xbmcaddon = types.ModuleType("xbmcaddon")
    xbmcvfs = types.ModuleType("xbmcvfs")
    for name, module_object in (
        ("xbmc", xbmc),
        ("xbmcaddon", xbmcaddon),
        ("xbmcvfs", xbmcvfs),
    ):
        monkeypatch.setitem(sys.modules, name, module_object)
    source = "tools/kodi_flatpak_profile_sync_device.py"
    spec = importlib.util.spec_from_file_location(
        "flatpak_device_artifacts", source
    )
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    stage = tmp_path / "stage"
    required = stage / "required"
    required.mkdir(parents=True)
    archive = required / "plugin.video.one.zip"
    with zipfile.ZipFile(archive, "w") as payload:
        payload.writestr(
            "plugin.video.one/addon.xml",
            '<addon id="plugin.video.one" version="1.2.3" />',
        )
    digest = hashlib.sha256(archive.read_bytes()).hexdigest()
    expected = {
        "required_addons": {"plugin.video.one": "1.2.3"},
        "required_artifacts": {
            "plugin.video.one": {
                "filename": "plugin.video.one.zip",
                "sha256": digest,
                "version": "1.2.3",
            }
        },
    }

    candidates = module._extract_required_candidates(
        stage, expected, tmp_path / "output"
    )

    assert candidates["plugin.video.one"].joinpath("addon.xml").is_file()
    archive.write_bytes(archive.read_bytes() + b"tampered")
    with pytest.raises(ValueError, match="digest differs"):
        module._extract_required_candidates(
            stage, expected, tmp_path / "output-two"
        )


def test_in_kodi_candidate_dependencies_exclude_managed_and_optional(
    tmp_path, monkeypatch
):
    for name in ("xbmc", "xbmcaddon", "xbmcvfs"):
        monkeypatch.setitem(sys.modules, name, types.ModuleType(name))
    source = "tools/kodi_flatpak_profile_sync_device.py"
    spec = importlib.util.spec_from_file_location(
        "flatpak_device_dependencies", source
    )
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    one = tmp_path / "plugin.video.one"
    two = tmp_path / "script.module.two"
    one.mkdir()
    two.mkdir()
    (one / "addon.xml").write_text(
        """<addon id="plugin.video.one" version="1.0">
        <requires>
          <import addon="xbmc.python" version="3.0.0"/>
          <import addon="script.module.two"/>
          <import addon="script.module.requests"/>
          <import addon="inputstream.adaptive" optional="true"/>
        </requires></addon>"""
    )
    (two / "addon.xml").write_text(
        '<addon id="script.module.two" version="1.0"/>'
    )

    dependencies = module._candidate_dependencies(
        {"plugin.video.one": one, "script.module.two": two}
    )

    assert dependencies == ["script.module.requests"]
