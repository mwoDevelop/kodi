import hashlib
import importlib.util
import io
import json
import stat
import subprocess
import sys
import types
import zipfile
from pathlib import PurePosixPath
from xml.etree import ElementTree

import pytest

from tools import build_repo
from tools.kodi_flatpak_profile_sync_rollout import (
    DEFAULT_REQUIRED_ADDONS,
    _cleanup_command,
    _event_packets,
    _event_server_ready,
    _send_staged_event_builtin,
    _stage_event_packets,
    build_settings,
    extract_addon,
    official_dependency_artifacts,
    profile_sync_server_url,
    required_addon_artifacts,
    required_addons,
)


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


def test_flatpak_required_addons_cover_managed_settings_and_favourites():
    assert DEFAULT_REQUIRED_ADDONS == (
        "script.module.mwoscrapers",
        "script.mwoscrapers",
        "plugin.video.umbrella",
        "plugin.video.watchnixtoons2.mwodevelop",
    )


def test_flatpak_required_addons_are_exactly_pinned_by_stable_lock():
    result = required_addons(".")

    assert tuple(result) == DEFAULT_REQUIRED_ADDONS
    assert result["plugin.video.umbrella"] == "6.7.81.20"
    assert result["script.module.mwoscrapers"] == "0.1.10"
    assert result["script.mwoscrapers"] == "0.1.1"
    assert result["plugin.video.watchnixtoons2.mwodevelop"] == "0.27.1"


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
