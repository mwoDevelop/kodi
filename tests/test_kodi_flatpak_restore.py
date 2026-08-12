import pytest

from tools import kodi_flatpak_restore as restore
from tools.kodi_transports import CommandResult


class FlatpakTransport:
    def __init__(self, scopes):
        self.scopes = scopes

    def execute_read_only(self, command):
        argv = command.argv
        scope = "user" if "--user" in argv else "system"
        metadata = self.scopes.get(scope)
        if argv[1] == "list":
            output = ""
            if metadata:
                output = "%s\t%s\t%s\n" % (
                    metadata["app_id"],
                    metadata["architecture"],
                    metadata["version"],
                )
            return CommandResult(0, output, "")
        if not metadata:
            return CommandResult(1, "", "missing")
        field = {"--show-origin": "origin", "--show-ref": "ref"}[argv[3]]
        return CommandResult(0, metadata[field] + "\n", "")


def installer(scope="system"):
    return {
        "app_id": "tv.kodi.Kodi",
        "architecture": "x86_64",
        "origin": "flathub",
        "ref": "app/tv.kodi.Kodi/x86_64/stable",
        "scope": scope,
        "version": "21.3-Omega",
    }


def test_installer_probe_binds_exact_single_scope():
    observed = restore._installer_probe(
        FlatpakTransport({"system": installer()}), "tv.kodi.Kodi"
    )

    assert observed == installer()


def test_installer_probe_rejects_duplicate_scope():
    with pytest.raises(RuntimeError, match="both Flatpak scopes"):
        restore._installer_probe(
            FlatpakTransport(
                {"system": installer(), "user": installer("user")}
            ),
            "tv.kodi.Kodi",
        )


def test_installer_probe_rejects_ref_for_other_architecture():
    invalid = installer()
    invalid["ref"] = "app/tv.kodi.Kodi/aarch64/stable"

    with pytest.raises(RuntimeError, match="installer identity"):
        restore._installer_probe(
            FlatpakTransport({"system": invalid}), "tv.kodi.Kodi"
        )


def test_system_reset_preserves_shared_binary_and_removes_only_profile(
    monkeypatch, tmp_path
):
    target = {
        "device_id": "nuc-alek",
        "host_fingerprint": "a" * 64,
        "principal_uid": 1001,
        "data_root": "/home/alek/.var/app/tv.kodi.Kodi/data",
        "transport": object(),
    }
    manifest = {
        "device": {
            "logical_device_id": "nuc-alek",
            "host_fingerprint": "a" * 64,
            "principal_uid": 1001,
        },
        "installer": {"flatpak": installer()},
    }
    private = tmp_path / "private"
    receipt = private / "nuc-alek/installed.json"
    receipt.parent.mkdir(parents=True)
    receipt.write_text("{}")
    removed = []

    class Sftp:
        def close(self):
            pass

    class Client:
        def close(self):
            pass

    monkeypatch.setattr(
        restore,
        "preflight_target",
        lambda *_args, **_kwargs: {**target, "data_exists": True},
    )
    monkeypatch.setattr(
        restore, "_connect_sftp", lambda _transport: (Client(), Sftp())
    )
    monkeypatch.setattr(
        restore, "_remove_tree", lambda _sftp, path: removed.append(path)
    )
    monkeypatch.setattr(
        restore,
        "_remote_command",
        lambda *_args, **_kwargs: pytest.fail("system Flatpak was uninstalled"),
    )

    result = restore.reset_profile(target, manifest, private)

    assert result["binary_action"] == "PRESERVED_SHARED_SYSTEM_FLATPAK"
    assert removed == [target["data_root"]]
    assert not receipt.exists()


def test_user_reset_uses_user_scoped_uninstall(monkeypatch, tmp_path):
    target = {
        "device_id": "nuc-alek",
        "host_fingerprint": "a" * 64,
        "principal_uid": 1001,
        "data_root": "/home/alek/.var/app/tv.kodi.Kodi/data",
        "transport": object(),
    }
    manifest = {
        "device": {
            "logical_device_id": "nuc-alek",
            "host_fingerprint": "a" * 64,
            "principal_uid": 1001,
        },
        "installer": {"flatpak": installer("user")},
    }
    commands = []
    monkeypatch.setattr(
        restore,
        "preflight_target",
        lambda *_args, **_kwargs: {**target, "data_exists": True},
    )
    monkeypatch.setattr(
        restore,
        "_remote_command",
        lambda _transport, command, timeout: commands.append((command, timeout)),
    )

    result = restore.reset_profile(target, manifest, tmp_path / "private")

    assert result["binary_action"] == "UNINSTALLED_USER_FLATPAK"
    assert len(commands) == 1
    assert "uninstall --user --delete-data" in commands[0][0]
    assert "--system" not in commands[0][0]
