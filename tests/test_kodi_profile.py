import json
import tarfile
from pathlib import Path
from types import SimpleNamespace

import pytest

from tools.kodi_profile import (
    AdbEventClient,
    RestoreCommandMayBeQueued,
    _addon_inventory,
    _activate_skin,
    _build_restore_archive,
    _quiesce_incomplete_restore,
    _read_marker,
    _run_restore_script,
    _selected_restore_files,
    _selective_addon_requirements,
    _validate_selective_addon_versions,
    _wait_for_kodi_ready,
    canonical_json,
    classify_snapshot_identity,
    contains_profile_sync_identity,
    digest,
    ensure_private_output,
    glob_regex,
    included_by_policy,
    kodi_versions_compatible,
    requires_direct_copy,
    sanitize_snapshot_identity,
    restore_snapshot,
    restore_snapshot_paths,
    recover_restore_lock,
    secure_private_tree,
    verify_snapshot,
)
from tools.kodi_profile_restore_device import (
    _apply_addon_settings,
    _claim_marker,
    _settings_digest,
    _verify_current,
)


def test_kodi_ready_uses_jsonrpc_when_scoped_storage_hides_userdata(
    monkeypatch,
):
    class Result:
        def __init__(self, returncode):
            self.returncode = returncode

    commands = []

    def command(*args, **_kwargs):
        commands.append(args[-1])
        if "guisettings.xml" in args[-1]:
            return Result(1)
        if ":9777" in args[-1]:
            return Result(0)
        raise AssertionError(args)

    class JsonRpc:
        def __init__(self, *_args):
            pass

        def __enter__(self):
            return self

        def __exit__(self, *_args):
            pass

        def call(self, method):
            assert method == "JSONRPC.Ping"
            return "pong"

    monkeypatch.setattr("tools.kodi_profile.adb_command", command)
    monkeypatch.setattr("tools.kodi_profile.AdbJsonRpcClient", JsonRpc)

    _wait_for_kodi_ready("adb", 5037, "serial", timeout=1)

    assert any("guisettings.xml" in item for item in commands)
    assert any(":9777" in item for item in commands)


def test_event_client_uses_ipv4_mapped_loopback_for_android_ipv6_listener(
    monkeypatch,
):
    commands = []
    monkeypatch.setattr(
        "tools.kodi_profile.adb_output",
        lambda *_args, **_kwargs: "udp6 0 0 :::9777 :::*",
    )
    def command(*args, **_kwargs):
        if "command -v nc" in args[-1]:
            return SimpleNamespace(stdout="/system/bin/nc\n")
        commands.append(args[-1])
        return SimpleNamespace(stdout="")

    monkeypatch.setattr("tools.kodi_profile.adb_command", command)

    AdbEventClient("adb", 5037, "serial").execute_builtin(
        "Notification(test,ready)"
    )

    assert len(commands) == 3
    assert all("nc -4 -u " in command for command in commands)
    assert all(" 127.0.0.1 9777" in command for command in commands)


def test_event_client_sends_from_host_when_tv_has_no_netcat(monkeypatch):
    def output(*args, **_kwargs):
        command = args[-1]
        if "netstat" in command:
            return "udp6 0 0 :::9777 :::*"
        raise AssertionError(command)

    def command(*args, **_kwargs):
        assert "command -v nc" in args[-1]
        return SimpleNamespace(stdout="")

    class Socket:
        def __init__(self, family, kind):
            assert family == 2
            assert kind == 2
            self.sent = []

        def __enter__(self):
            return self

        def __exit__(self, *_args):
            return None

        def sendto(self, packet, address):
            self.sent.append((packet, address))
            sent.extend(self.sent[-1:])

    sent = []
    monkeypatch.setattr("tools.kodi_profile.adb_output", output)
    monkeypatch.setattr("tools.kodi_profile.adb_command", command)
    monkeypatch.setattr("tools.kodi_profile.socket.socket", Socket)

    AdbEventClient(
        "adb", 5037, "192.168.1.12:5555"
    ).execute_builtin("Notification(test,ready)")

    assert len(sent) == 3
    assert all(address == ("192.168.1.12", 9777) for _packet, address in sent)
    assert all(packet.startswith(b"XBMC") for packet, _address in sent)


def test_event_client_can_explicitly_retry_from_host(monkeypatch):
    client = AdbEventClient("adb", 5037, "192.0.2.18:5555")
    sent = []
    monkeypatch.setattr(client, "_send_from_host", lambda packets: sent.extend(packets))

    client.execute_builtin_from_host("Notification(test,retry)")

    assert len(sent) == 3
    assert all(packet.startswith(b"XBMC") for packet in sent)


def test_profile_policy_includes_settings_and_excludes_cache():
    policy = json.loads(
        Path("manifests/kodi-profile-policy.json").read_text(encoding="utf-8")
    )
    assert included_by_policy(
        "userdata/addon_data/plugin.video.umbrella/settings.xml", policy
    )
    assert included_by_policy(
        "userdata/addon_data/skin.aeon.nox.silvo/settings.xml", policy
    )
    assert included_by_policy(
        "addons/plugin.video.umbrella/addon.xml", policy
    )
    assert not included_by_policy(
        "userdata/addon_data/plugin.video.umbrella/cache.db", policy
    )
    assert not included_by_policy(
        "userdata/addon_data/plugin.video.umbrella/providers.db", policy
    )
    assert not included_by_policy(
        "userdata/Thumbnails/a/asset.jpg", policy
    )
    assert included_by_policy(
        "userdata/favourite-artwork/portable.jpg", policy
    )
    assert not included_by_policy(
        "addons/packages/plugin.zip", policy
    )
    assert not included_by_policy(
        "userdata/addon_data/service.mwodevelop.profilesync/state.json",
        policy,
    )


def test_profile_sync_identity_is_classified_and_rejected_before_restore(
    tmp_path,
):
    relative = (
        "userdata/addon_data/service.mwodevelop.profilesync/state.json"
    )
    assert contains_profile_sync_identity([relative])
    snapshot = tmp_path / "snapshot"
    snapshot.mkdir()
    (snapshot / "manifest.json").write_text(
        json.dumps({"schema": 1, "files": {relative: {}}})
    )

    assert classify_snapshot_identity(snapshot)["identity_status"] == (
        "IDENTITY_CONTAMINATED"
    )
    with pytest.raises(ValueError, match="IDENTITY_CONTAMINATED"):
        verify_snapshot(snapshot)


def test_contaminated_snapshot_can_be_copied_to_verified_sanitized_form(
    tmp_path,
):
    snapshot = tmp_path / "source"
    payload = snapshot / "payload"
    identity_file = payload / (
        "userdata/addon_data/service.mwodevelop.profilesync/state.json"
    )
    portable_file = payload / "userdata/favourites.xml"
    identity_file.parent.mkdir(parents=True)
    portable_file.parent.mkdir(parents=True, exist_ok=True)
    identity_file.write_bytes(b"device-secret")
    portable_file.write_bytes(b"<favourites/>")
    installer = snapshot / "installer"
    installer.mkdir()
    apk = installer / "base.apk"
    apk.write_bytes(b"apk")
    files = {
        path.relative_to(payload).as_posix(): {
            "sha256": digest(path.read_bytes()),
            "size": path.stat().st_size,
        }
        for path in (identity_file, portable_file)
    }
    base = {
        "schema": 1,
        "policy_sha256": "policy",
        "device": {},
        "selected_skin": "skin.estuary",
        "addons": [],
        "files": files,
        "installer": {
            "apks": [
                {"name": "base.apk", "sha256": digest(b"apk"), "size": 3}
            ]
        },
    }
    manifest = {
        **base,
        "created_utc": "2026-08-03T00:00:00+00:00",
        "snapshot_id": digest(canonical_json(base)),
    }
    (snapshot / "manifest.json").write_bytes(canonical_json(manifest) + b"\n")

    output = tmp_path / "sanitized"
    result = sanitize_snapshot_identity(snapshot, output)

    assert result["sanitized_from"] == manifest["snapshot_id"]
    assert classify_snapshot_identity(output)["identity_status"] == (
        "IDENTITY_CLEAN"
    )
    assert verify_snapshot(output)["snapshot_id"] == result["snapshot_id"]
    assert portable_file.relative_to(snapshot).as_posix().replace(
        "payload/", ""
    ) in result["files"]
    assert not (
        output
        / "payload/userdata/addon_data/service.mwodevelop.profilesync"
    ).exists()


def test_single_star_does_not_cross_directory_boundaries():
    assert glob_regex("userdata/*.xml").fullmatch("userdata/guisettings.xml")
    assert not glob_regex("userdata/*.xml").fullmatch(
        "userdata/addon_data/example/settings.xml"
    )


def test_toybox_edge_case_is_copied_without_tar():
    assert requires_direct_copy(
        "addons/skin.aeon.nox.silvo/extras/moviegenres/default/...jpg"
    )
    assert not requires_direct_copy(
        "addons/skin.aeon.nox.silvo/media/Textures.xbt"
    )


def test_kodi_upgrade_compatibility_is_same_major_and_forward_only():
    assert kodi_versions_compatible("21.3", "21.3")
    assert kodi_versions_compatible("21.2", "21.3", allow_upgrade=True)
    assert not kodi_versions_compatible("21.3", "21.2", allow_upgrade=True)
    assert not kodi_versions_compatible("21.3", "22.0", allow_upgrade=True)
    assert not kodi_versions_compatible("21.2", "21.3")


def test_addon_inventory_skips_corrupt_manifest_but_leaves_payload(tmp_path):
    addons = tmp_path / "addons"
    good = addons / "plugin.video.good" / "addon.xml"
    corrupt = addons / "plugin.video.corrupt" / "addon.xml"
    good.parent.mkdir(parents=True)
    corrupt.parent.mkdir(parents=True)
    good.write_text(
        '<addon id="plugin.video.good" version="1.0.0"/>',
        encoding="utf-8",
    )
    corrupt.write_bytes(b"\0" * 32)

    inventory = _addon_inventory(
        tmp_path,
        {
            "plugin.video.good": {
                "enabled": True,
                "origin": "repository.example",
            }
        },
    )

    assert inventory == [
        {
            "id": "plugin.video.good",
            "version": "1.0.0",
            "enabled": True,
            "origin": "repository.example",
        }
    ]
    assert corrupt.read_bytes() == b"\0" * 32


def test_private_output_must_be_below_ignored_directory(
    tmp_path, monkeypatch
):
    repository = tmp_path / "repo"
    repository.mkdir()
    (repository / ".git").mkdir()
    private = repository / ".kodi-private"
    private.mkdir()

    class Result:
        returncode = 0

    monkeypatch.setattr(
        "tools.kodi_profile.subprocess.run", lambda *args, **kwargs: Result()
    )
    assert ensure_private_output(
        private / "snapshot", repository
    ) == (private / "snapshot").resolve()
    with pytest.raises(ValueError):
        ensure_private_output(repository / "tracked-snapshot", repository)


def test_private_tree_permissions_are_restricted(tmp_path):
    root = tmp_path / "snapshot"
    nested = root / "payload" / "userdata"
    nested.mkdir(parents=True)
    settings = nested / "settings.xml"
    settings.write_text("<settings/>", encoding="utf-8")
    root.chmod(0o755)
    nested.chmod(0o755)
    settings.chmod(0o644)

    secure_private_tree(root)

    assert root.stat().st_mode & 0o777 == 0o700
    assert nested.stat().st_mode & 0o777 == 0o700
    assert settings.stat().st_mode & 0o777 == 0o600


def test_verify_snapshot_rejects_payload_tampering(tmp_path):
    snapshot = tmp_path / "snapshot"
    payload = snapshot / "payload" / "userdata"
    installer = snapshot / "installer"
    payload.mkdir(parents=True)
    installer.mkdir()
    settings = payload / "guisettings.xml"
    settings.write_bytes(b"<settings/>")
    apk = installer / "base.apk"
    apk.write_bytes(b"apk")
    identity = {
        "schema": 1,
        "policy_sha256": "a" * 64,
        "device": {"kodi_version": "21.3"},
        "selected_skin": "skin.estuary",
        "addons": [],
        "files": {
            "userdata/guisettings.xml": {
                "sha256": digest(settings.read_bytes()),
                "size": settings.stat().st_size,
            }
        },
        "installer": {
            "apks": [
                {
                    "name": "base.apk",
                    "sha256": digest(apk.read_bytes()),
                    "size": apk.stat().st_size,
                }
            ]
        },
    }
    manifest = {
        **identity,
        "created_utc": "2026-07-27T00:00:00+00:00",
        "snapshot_id": digest(canonical_json(identity)),
    }
    (snapshot / "manifest.json").write_bytes(canonical_json(manifest))
    assert (
        verify_snapshot(snapshot)["snapshot_id"] == manifest["snapshot_id"]
    )
    settings.write_bytes(b"tampered")
    with pytest.raises(ValueError, match="payload inventory"):
        verify_snapshot(snapshot)


def test_activate_skin_accepts_only_the_expected_confirmation(monkeypatch):
    monkeypatch.setattr("tools.kodi_profile.time.sleep", lambda _seconds: None)

    class JsonRpc:
        def __init__(self):
            self.calls = []
            self.skin = "skin.estuary"

        def call(self, method, params=None):
            self.calls.append((method, params))
            if method == "Settings.SetSettingValue":
                self.skin = params["value"]
                return True
            if method == "GUI.GetProperties":
                return {
                    "currentwindow": {"id": 10100},
                    "currentcontrol": {"label": "No"},
                }
            if method == "Settings.GetSettingValue":
                return {"value": self.skin}
            return "OK"

    rpc = JsonRpc()
    _activate_skin(rpc, "skin.aeon.nox.silvo")
    methods = [method for method, _params in rpc.calls]
    assert methods.count("Settings.SetSettingValue") == 2
    assert ("Input.Left", None) in rpc.calls
    assert ("Input.Select", None) in rpc.calls


def test_restore_removes_device_staging_after_failure(monkeypatch):
    calls = []

    def fail(*_args, **_kwargs):
        raise RuntimeError("restore failed")

    def record(*args, **kwargs):
        calls.append((args, kwargs))
        return SimpleNamespace(returncode=0, stdout="")

    monkeypatch.setattr("tools.kodi_profile._restore_snapshot_inner", fail)
    monkeypatch.setattr("tools.kodi_profile.adb_command", record)
    monkeypatch.setattr(
        "tools.kodi_profile._acquire_restore_lock",
        lambda *_args: None,
    )
    monkeypatch.setattr(
        "tools.kodi_profile._release_restore_lock",
        lambda *_args: None,
    )
    monkeypatch.setattr(
        "tools.kodi_profile._quiesce_incomplete_restore",
        lambda *_args, **_kwargs: None,
    )

    with pytest.raises(RuntimeError, match="restore failed"):
        restore_snapshot("adb", 5038, "serial", "snapshot", "script")

    assert len(calls) == 1
    assert calls[0][0][3] == "shell"
    assert "mwo-kodi-profile-restore.tar" in calls[0][0][4]


def test_selective_restore_archive_contains_only_requested_verified_file(
    tmp_path, monkeypatch
):
    snapshot = tmp_path / "snapshot"
    payload = snapshot / "payload"
    first = payload / "userdata/addon_data/plugin.example/settings.xml"
    second = payload / "userdata/guisettings.xml"
    first.parent.mkdir(parents=True)
    first.write_bytes(b"<settings/>")
    second.write_bytes(b"<settings/>")
    manifest = {
        "snapshot_id": "a" * 64,
        "files": {
            first.relative_to(payload).as_posix(): {
                "sha256": digest(first.read_bytes()),
                "size": first.stat().st_size,
            },
            second.relative_to(payload).as_posix(): {
                "sha256": digest(second.read_bytes()),
                "size": second.stat().st_size,
            },
        },
    }
    monkeypatch.setattr(
        "tools.kodi_profile.verify_snapshot", lambda _snapshot: manifest
    )
    output = tmp_path / "restore.tar"

    _build_restore_archive(
        snapshot,
        output,
        ["userdata/addon_data/plugin.example/settings.xml"],
    )

    with tarfile.open(output) as archive:
        assert archive.getnames() == [
            "restore-manifest.json",
            "payload/userdata/addon_data/plugin.example/settings.xml",
        ]
        restore_manifest = json.load(
            archive.extractfile("restore-manifest.json")
        )
    assert list(restore_manifest["files"]) == [
        "userdata/addon_data/plugin.example/settings.xml"
    ]


def test_selective_addon_settings_archive_has_semantic_digest(
    tmp_path, monkeypatch
):
    snapshot = tmp_path / "snapshot"
    source = (
        snapshot
        / "payload/userdata/addon_data/plugin.example/settings.xml"
    )
    source.parent.mkdir(parents=True)
    source.write_text(
        '<settings version="2"><setting id="token">secret</setting>'
        '<setting id="enabled">true</setting></settings>',
        encoding="utf-8",
    )
    manifest = {
        "snapshot_id": "a" * 64,
        "files": {
            "userdata/addon_data/plugin.example/settings.xml": {
                "sha256": digest(source.read_bytes()),
                "size": source.stat().st_size,
            }
        },
    }
    monkeypatch.setattr(
        "tools.kodi_profile.verify_snapshot", lambda _snapshot: manifest
    )
    output = tmp_path / "restore.tar"

    built = _build_restore_archive(
        snapshot,
        output,
        list(manifest["files"]),
        operation_id="5" * 32,
        semantic_addon_settings=True,
    )

    metadata = built["files"][
        "userdata/addon_data/plugin.example/settings.xml"
    ]
    assert metadata["setting_ids"] == ["enabled", "token"]
    assert metadata["settings_sha256"] == _settings_digest(
        {"enabled": "true", "token": "secret"}
    )


@pytest.mark.parametrize(
    "path",
    [
        "../userdata/settings.xml",
        "/userdata/settings.xml",
        "userdata/../settings.xml",
        "userdata/missing.xml",
        "",
    ],
)
def test_selective_restore_rejects_unsafe_or_unverified_path(path):
    manifest = {
        "files": {
            "userdata/addon_data/plugin.example/settings.xml": {
                "sha256": "a" * 64,
                "size": 1,
            }
        }
    }
    with pytest.raises(ValueError):
        _selected_restore_files(manifest, [path])


def test_selective_restore_is_limited_to_userdata_and_binds_addon_version():
    manifest = {
        "addons": [
            {
                "id": "plugin.video.example",
                "version": "1.2.3",
            }
        ]
    }
    assert _selective_addon_requirements(
        manifest,
        {
            "userdata/addon_data/plugin.video.example/settings.xml": {
                "sha256": "a" * 64,
                "size": 1,
            }
        },
    ) == {"plugin.video.example": "1.2.3"}
    with pytest.raises(ValueError, match="limited to userdata"):
        _selective_addon_requirements(
            manifest,
            {
                "addons/plugin.video.example/addon.xml": {
                    "sha256": "a" * 64,
                    "size": 1,
                }
            },
        )


def test_selective_restore_requires_explicit_forward_addon_upgrade():
    class JsonRpc:
        def __init__(self, version):
            self.version = version

        def call(self, method, params):
            assert method == "Addons.GetAddonDetails"
            assert params["addonid"] == "plugin.video.example"
            return {
                "addon": {
                    "enabled": True,
                    "version": self.version,
                }
            }

    requirements = {"plugin.video.example": "1.2.3"}
    with pytest.raises(ValueError, match="differs from snapshot"):
        _validate_selective_addon_versions(
            JsonRpc("1.2.4"),
            requirements,
        )
    assert _validate_selective_addon_versions(
        JsonRpc("1.2.4"),
        requirements,
        allow_addon_upgrade=True,
    ) == {"plugin.video.example": "1.2.4"}
    with pytest.raises(ValueError, match="not a compatible forward upgrade"):
        _validate_selective_addon_versions(
            JsonRpc("1.2.2"),
            requirements,
            allow_addon_upgrade=True,
        )
    assert _validate_selective_addon_versions(
        JsonRpc("1.2.3+beta.6"),
        {"plugin.video.example": "1.2.3+beta.5"},
        allow_addon_upgrade=True,
    ) == {"plugin.video.example": "1.2.3+beta.6"}
    with pytest.raises(ValueError, match="not a compatible forward upgrade"):
        _validate_selective_addon_versions(
            JsonRpc("1.2.3~beta.6"),
            {"plugin.video.example": "1.2.3+beta.5"},
            allow_addon_upgrade=True,
        )


def test_selective_restore_removes_device_staging_after_failure(monkeypatch):
    calls = []

    def fail(*_args, **_kwargs):
        raise RuntimeError("restore failed")

    def record(*args, **kwargs):
        calls.append((args, kwargs))
        return SimpleNamespace(returncode=0, stdout="")

    monkeypatch.setattr(
        "tools.kodi_profile._restore_snapshot_paths_inner", fail
    )
    monkeypatch.setattr("tools.kodi_profile.adb_command", record)
    monkeypatch.setattr(
        "tools.kodi_profile._acquire_restore_lock",
        lambda *_args: None,
    )
    monkeypatch.setattr(
        "tools.kodi_profile._release_restore_lock",
        lambda *_args: None,
    )
    monkeypatch.setattr(
        "tools.kodi_profile._quiesce_incomplete_restore",
        lambda *_args, **_kwargs: None,
    )

    with pytest.raises(RuntimeError, match="restore failed"):
        restore_snapshot_paths(
            "adb",
            5038,
            "serial",
            "snapshot",
            "script",
            ["userdata/settings.xml"],
        )

    assert len(calls) == 1
    assert calls[0][0][3] == "shell"
    assert "mwo-kodi-profile-restore.tar" in calls[0][0][4]


def test_restore_does_not_touch_an_active_operation_when_lock_fails(
    monkeypatch,
):
    calls = []

    def locked(*_args):
        raise RuntimeError("another Kodi profile restore is active")

    monkeypatch.setattr(
        "tools.kodi_profile._acquire_restore_lock",
        locked,
    )
    monkeypatch.setattr(
        "tools.kodi_profile.adb_command",
        lambda *args, **kwargs: calls.append((args, kwargs)),
    )

    with pytest.raises(RuntimeError, match="another Kodi profile restore"):
        restore_snapshot_paths(
            "adb",
            5038,
            "serial",
            "snapshot",
            "script",
            ["userdata/settings.xml"],
        )

    assert calls == []


def test_incomplete_started_writer_is_stopped_before_unlock(monkeypatch):
    events = []

    class Result:
        def __init__(self, returncode=0, stdout=""):
            self.returncode = returncode
            self.stdout = stdout

    def command(*args, **_kwargs):
        shell = args[4]
        if shell.startswith("cat ") and "started" in shell:
            return Result(
                stdout=json.dumps(
                    {"operation_id": "4" * 32, "started": True}
                )
            )
        if shell.startswith("cat "):
            return Result(returncode=1)
        if shell.startswith("am force-stop"):
            events.append("force-stop")
        return Result()

    monkeypatch.setattr("tools.kodi_profile.adb_command", command)
    _quiesce_incomplete_restore("adb", 5038, "serial")

    assert events == ["force-stop"]


def test_cleanup_failure_retains_restore_lock(monkeypatch):
    released = []

    def fail(*_args):
        raise TimeoutError("cleanup transport timeout")

    monkeypatch.setattr(
        "tools.kodi_profile._restore_snapshot_inner",
        lambda *_args: {"ok": True},
    )
    monkeypatch.setattr(
        "tools.kodi_profile._acquire_restore_lock",
        lambda *_args: None,
    )
    monkeypatch.setattr(
        "tools.kodi_profile._cleanup_restore_staging",
        fail,
    )
    monkeypatch.setattr(
        "tools.kodi_profile._release_restore_lock",
        lambda *_args: released.append(True),
    )

    with pytest.raises(TimeoutError, match="cleanup transport timeout"):
        restore_snapshot("adb", 5038, "serial", "snapshot", "script")

    assert released == []


def test_unacknowledged_restore_is_stopped_before_cleanup(monkeypatch):
    events = []

    def fail(*_args):
        raise RestoreCommandMayBeQueued("not acknowledged")

    class Result:
        returncode = 0
        stdout = ""

    def command(*args, **_kwargs):
        shell = args[4]
        if shell.startswith("cat "):
            return Result()
        if shell.startswith("am force-stop"):
            events.append("force-stop")
        return Result()

    monkeypatch.setattr(
        "tools.kodi_profile._restore_snapshot_inner",
        fail,
    )
    monkeypatch.setattr(
        "tools.kodi_profile._acquire_restore_lock",
        lambda *_args: None,
    )
    monkeypatch.setattr(
        "tools.kodi_profile._release_restore_lock",
        lambda *_args: events.append("unlock"),
    )
    monkeypatch.setattr("tools.kodi_profile.adb_command", command)

    with pytest.raises(TimeoutError, match="not acknowledged"):
        restore_snapshot("adb", 5038, "serial", "snapshot", "script")

    assert events == ["force-stop", "unlock"]


def test_recover_lock_stops_kodi_before_cleanup_and_unlock(monkeypatch):
    commands = []

    class Result:
        returncode = 0
        stdout = ""

    def command(*args, **_kwargs):
        commands.append(args[4])
        return Result()

    monkeypatch.setattr("tools.kodi_profile.adb_command", command)

    assert recover_restore_lock("adb", 5038, "serial") == {
        "restore_lock_recovered": True
    }
    assert commands[0].startswith("test -d")
    assert commands[1].startswith("am force-stop")
    assert commands[2].startswith("rm -f")
    assert commands[3].startswith("rmdir")


def test_restore_script_retries_a_lost_startup_event(monkeypatch):
    sent = []
    deliveries = iter(
        [
            ("missing", None),
            ("complete", {"ok": True, "restored_files": 1}),
        ]
    )

    class EventClient:
        def __init__(self, *_args):
            pass

        def execute_builtin(self, command):
            sent.append(command)

    monkeypatch.setattr("tools.kodi_profile.AdbEventClient", EventClient)
    monkeypatch.setattr(
        "tools.kodi_profile._wait_for_restore_delivery",
        lambda *_args, **_kwargs: next(deliveries),
    )
    monkeypatch.setattr("tools.kodi_profile.time.sleep", lambda _seconds: None)

    result = _run_restore_script(
        "adb",
        5038,
        "serial",
        "1" * 32,
        attempts=2,
        delivery_timeout=1,
    )

    assert result == {"ok": True, "restored_files": 1}
    assert len(sent) == 2
    assert all(command.startswith("RunScript(") for command in sent)


def test_restore_script_does_not_retry_after_started_acknowledgement(
    monkeypatch,
):
    sent = []

    class EventClient:
        def __init__(self, *_args):
            pass

        def execute_builtin(self, command):
            sent.append(command)

    monkeypatch.setattr("tools.kodi_profile.AdbEventClient", EventClient)
    monkeypatch.setattr(
        "tools.kodi_profile._wait_for_restore_delivery",
        lambda *_args, **_kwargs: ("started", None),
    )
    monkeypatch.setattr(
        "tools.kodi_profile._wait_for_marker",
        lambda *_args, **_kwargs: {"ok": True, "restored_files": 4277},
    )

    result = _run_restore_script(
        "adb",
        5038,
        "serial",
        "2" * 32,
        attempts=4,
        delivery_timeout=1,
        completion_timeout=600,
    )

    assert result == {"ok": True, "restored_files": 4277}
    assert len(sent) == 1


@pytest.mark.parametrize("failure_point", ["dispatch", "wait"])
def test_restore_script_wraps_unknown_dispatch_outcome(
    monkeypatch, failure_point
):
    sent = []

    class EventClient:
        def __init__(self, *_args):
            pass

        def execute_builtin(self, command):
            sent.append(command)
            if failure_point == "dispatch":
                raise ConnectionError("BYE transport failed")

    monkeypatch.setattr("tools.kodi_profile.AdbEventClient", EventClient)

    def wait(*_args, **_kwargs):
        raise ConnectionError("marker transport failed")

    monkeypatch.setattr(
        "tools.kodi_profile._wait_for_restore_delivery",
        wait,
    )

    with pytest.raises(
        RestoreCommandMayBeQueued,
        match="outcome is unknown",
    ):
        _run_restore_script("adb", 5038, "serial", "2" * 32)

    assert len(sent) == 1


def test_read_marker_tolerates_partially_written_started_marker(monkeypatch):
    class Result:
        returncode = 0
        stdout = '{"operation_id":'

    monkeypatch.setattr(
        "tools.kodi_profile.adb_command",
        lambda *_args, **_kwargs: Result(),
    )

    assert _read_marker("adb", 5038, "serial", "started.json") is None


def test_device_restore_started_marker_is_an_atomic_single_writer_claim(
    tmp_path,
):
    marker = tmp_path / "restore-started.json"

    assert _claim_marker(marker, "3" * 32) is True
    assert _claim_marker(marker, "3" * 32) is False
    assert json.loads(marker.read_text(encoding="utf-8")) == {
        "operation_id": "3" * 32,
        "started": True,
    }


def test_device_post_restart_verifier_checks_size_and_digest(tmp_path):
    home = tmp_path / "home"
    target = home / "userdata/addon_data/plugin.example/settings.xml"
    target.parent.mkdir(parents=True)
    target.write_bytes(b"<settings/>")
    manifest = {
        "files": {
            "userdata/addon_data/plugin.example/settings.xml": {
                "sha256": digest(target.read_bytes()),
                "size": target.stat().st_size,
            }
        }
    }

    assert _verify_current(str(home), manifest) == 1
    target.write_bytes(b"reverted")
    with pytest.raises(ValueError, match="verification mismatch"):
        _verify_current(str(home), manifest)


def test_device_addon_settings_apply_and_semantic_verification(tmp_path):
    home = tmp_path / "home"
    target = home / "userdata/addon_data/plugin.example/settings.xml"
    target.parent.mkdir(parents=True)
    target.write_text(
        '<settings version="2"><setting id="token">wanted</setting>'
        '<setting id="enabled">true</setting>'
        '<setting id="newer-option">kept</setting></settings>',
        encoding="utf-8",
    )
    expected_values = {"enabled": "true", "token": "wanted"}
    manifest = {
        "files": {
            "userdata/addon_data/plugin.example/settings.xml": {
                "setting_ids": sorted(expected_values),
                "settings_sha256": _settings_digest(expected_values),
            }
        }
    }

    assert _verify_current(str(home), manifest) == 1
    target.write_text(
        '<settings version="2"><setting id="token">stale</setting>'
        '<setting id="enabled">true</setting></settings>',
        encoding="utf-8",
    )
    with pytest.raises(ValueError, match="settings verification mismatch"):
        _verify_current(str(home), manifest)

    calls = {}

    class Addon:
        def getSetting(self, setting_id):
            return calls.get(setting_id, "")

        def setSetting(self, setting_id, value):
            calls[setting_id] = value
            return True

    _apply_addon_settings(
        Addon(),
        (
            b'<settings version="2"><setting id="token">wanted</setting>'
            b'<setting id="enabled">true</setting></settings>'
        ),
        manifest["files"][
            "userdata/addon_data/plugin.example/settings.xml"
        ],
    )
    assert calls == expected_values


def test_device_addon_settings_roll_back_partial_api_failure():
    state = {"first": "old-a", "second": "old-b"}

    class Addon:
        def getSetting(self, setting_id):
            return state[setting_id]

        def setSetting(self, setting_id, value):
            if setting_id == "second" and value == "new-b":
                state[setting_id] = "partially-written"
                return False
            state[setting_id] = value
            return True

    payload = (
        b'<settings version="2"><setting id="first">new-a</setting>'
        b'<setting id="second">new-b</setting></settings>'
    )
    with pytest.raises(ValueError, match="rejected"):
        _apply_addon_settings(
            Addon(),
            payload,
            {"setting_ids": ["first", "second"]},
        )

    assert state == {"first": "old-a", "second": "old-b"}


def test_device_addon_settings_rollback_continues_after_one_failure():
    state = {"first": "old-a", "second": "old-b", "third": "old-c"}

    class Addon:
        def getSetting(self, setting_id):
            return state[setting_id]

        def setSetting(self, setting_id, value):
            if setting_id == "third" and value == "new-c":
                state[setting_id] = "partial-c"
                return False
            if setting_id == "second" and value == "old-b":
                raise RuntimeError("rollback rejected")
            state[setting_id] = value
            return True

    payload = (
        b'<settings version="2"><setting id="first">new-a</setting>'
        b'<setting id="second">new-b</setting>'
        b'<setting id="third">new-c</setting></settings>'
    )
    with pytest.raises(RuntimeError, match="rollback failed"):
        _apply_addon_settings(
            Addon(),
            payload,
            {"setting_ids": ["first", "second", "third"]},
        )

    assert state["first"] == "old-a"
    assert state["third"] == "old-c"
