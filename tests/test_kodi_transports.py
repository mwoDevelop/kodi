from types import SimpleNamespace

import pytest

from tools.kodi_devices import normalize_registry
from tools import kodi_inventory, kodi_lifecycle, kodi_transports
from tools.kodi_inventory import load_private_references
from tools.kodi_lifecycle import lifecycle_for_device
from tools.kodi_transports import (
    AdbTransport,
    ReadOnlyCommand,
    SshTransport,
    TransportError,
    transport_for_device,
)


def result(returncode=0, stdout="", stderr=""):
    return SimpleNamespace(
        returncode=returncode,
        stdout=stdout,
        stderr=stderr,
    )


def android_device():
    registry = {
        "schema": 2,
        "devices": {
            "android-tv": {
                "display_name": "Android TV",
                "physical_host_id": "android-tv-host",
                "principal_id": "principal-android-tv",
                "platform": "android",
                "roles": ["consumer"],
                "expected": {
                    "model": "TV MODEL",
                    "kodi_major": 21,
                    "abi": ["armeabi-v7a"],
                },
                "endpoints": {"adb": "private-tv:5555"},
                "profile_channel": "home-stable",
            }
        },
    }
    return normalize_registry(registry)["devices"]["android-tv"]


def linux_device(data_root=".var/app/tv.kodi.Kodi/data"):
    return {
        "display_name": "Linux Kodi",
        "physical_host_id": "linux-host",
        "principal_id": "principal-linux-01",
        "platform": "linux-flatpak",
        "roles": ["consumer"],
        "expected": {
            "model": "IP3 Tech TB20C",
            "kodi_major": 21,
            "abi": ["x86_64"],
            "flatpak_app_id": "tv.kodi.Kodi",
            "kodi_data_root": data_root,
        },
        "endpoints": {
            "ssh": {
                "host": "private-linux",
                "user_ref": "LINUX_USER",
                "credential_ref": "LINUX_KEY",
                "known_hosts_ref": "LINUX_KNOWN_HOSTS",
            }
        },
        "profile_channel": "home-stable",
    }


def private_ssh_files(tmp_path):
    identity = tmp_path / "id_ed25519"
    identity.write_text("private test key", encoding="utf-8")
    identity.chmod(0o600)
    known_hosts = tmp_path / "known_hosts"
    known_hosts.write_text("private-linux ssh-ed25519 test", encoding="utf-8")
    return identity, known_hosts


class FakeSshRunner:
    def __init__(self, responses):
        self.responses = responses
        self.calls = []

    def __call__(self, argv, **kwargs):
        self.calls.append((argv, kwargs))
        remote = argv[-1]
        try:
            value = self.responses[remote]
        except KeyError as error:
            raise AssertionError("unexpected SSH command: %s" % remote) from error
        if isinstance(value, tuple):
            return result(*value)
        return result(stdout=value)


def ssh_responses(canonical="/home/kodi/.var/app/tv.kodi.Kodi/data"):
    return {
        "id -u": "1000\n",
        "id -un": "kodi\n",
        "getent passwd kodi": (
            "kodi:x:1000:1000:Kodi:/home/kodi:/bin/bash\n"
        ),
        "uname -m": "x86_64\n",
        "cat /etc/machine-id": "machine-id\n",
        "cat /sys/class/dmi/id/product_name": "IP3 Tech TB20C\n",
        (
            "flatpak list --app "
            "--columns=application,arch,version"
        ): "tv.kodi.Kodi\tx86_64\t21.3-Omega\n",
        (
            "readlink -f -- "
            "/home/kodi/.var/app/tv.kodi.Kodi/data"
        ): canonical + "\n",
        (
            "stat -Lc '%u|%F' -- "
            + canonical
        ): "1000|directory\n",
        "pgrep -u 1000 -f 'tv.kodi.Kodi|/kodi( |$)'": (1, "", ""),
        "cat " + canonical + "/temp/kodi.log": (
            "2026-07-31 18:00:00 info: special://envhome/ is mapped to: /home/kodi\n"
            "2026-07-31 18:00:00 info: special://home/ is mapped to: "
            + canonical
            + "\n"
            "2026-07-31 18:00:00 info: special://masterprofile/ is mapped to: "
            + canonical
            + "/userdata\n"
            "2026-07-31 18:00:00 info: special://profile/ is mapped to: "
            "special://masterprofile/\n"
        ),
        "stat -Lc '%u|%F' -- " + canonical + "/temp/kodi.log": (
            "1000|regular file\n"
        ),
    }


def test_read_only_command_rejects_arbitrary_program():
    with pytest.raises(ValueError, match="read-only allowlist"):
        ReadOnlyCommand(("rm", "-rf", "anything"))


def test_ssh_transport_pins_identity_and_disables_agent(tmp_path):
    identity, known_hosts = private_ssh_files(tmp_path)
    runner = FakeSshRunner(ssh_responses())
    transport = SshTransport(
        "private-linux",
        "kodi",
        identity,
        known_hosts,
        runner=runner,
    )

    observed = transport.probe_identity()

    assert observed.user == "kodi"
    assert observed.uid == 1000
    assert observed.home == "/home/kodi"
    assert observed.model == "IP3 Tech TB20C"
    argv, kwargs = runner.calls[0]
    assert "BatchMode=yes" in argv
    assert "ForwardAgent=no" in argv
    assert "StrictHostKeyChecking=yes" in argv
    assert "UserKnownHostsFile=%s" % known_hosts in argv
    assert "IdentityFile=%s" % identity in argv
    assert kwargs["env"]["SSH_AUTH_SOCK"] == ""


def test_ssh_transport_rejects_broad_key_permissions(tmp_path):
    identity, known_hosts = private_ssh_files(tmp_path)
    identity.chmod(0o644)

    with pytest.raises(ValueError, match="permissions are too broad"):
        SshTransport(
            "private-linux",
            "kodi",
            identity,
            known_hosts,
        )


def test_flatpak_lifecycle_read_only_probe(tmp_path):
    identity, known_hosts = private_ssh_files(tmp_path)
    runner = FakeSshRunner(ssh_responses())
    device = linux_device()
    transport = SshTransport(
        "private-linux",
        "kodi",
        identity,
        known_hosts,
        runner=runner,
    )

    probe = lifecycle_for_device(device, transport).probe_kodi()

    assert probe["kodi_version"] == "21.3-Omega"
    assert probe["abi"] == ["x86_64"]
    assert probe["running"] is False
    assert probe["data_root"].startswith("/home/kodi/")
    assert probe["runtime_paths_qualified"] is True
    assert probe["runtime_path_status"] == "QUALIFIED_FROM_KODI_RUNTIME_LOG"


def test_flatpak_lifecycle_rejects_runtime_mapping_for_other_account(tmp_path):
    identity, known_hosts = private_ssh_files(tmp_path)
    responses = ssh_responses()
    responses[
        "cat /home/kodi/.var/app/tv.kodi.Kodi/data/temp/kodi.log"
    ] = responses[
        "cat /home/kodi/.var/app/tv.kodi.Kodi/data/temp/kodi.log"
    ].replace("special://envhome/ is mapped to: /home/kodi", "special://envhome/ is mapped to: /home/other")
    runner = FakeSshRunner(responses)
    transport = SshTransport(
        "private-linux", "kodi", identity, known_hosts, runner=runner
    )

    with pytest.raises(TransportError, match="runtime home differs"):
        lifecycle_for_device(linux_device(), transport).probe_kodi()


def test_flatpak_lifecycle_rejects_symlink_escape(tmp_path):
    identity, known_hosts = private_ssh_files(tmp_path)
    runner = FakeSshRunner(ssh_responses(canonical="/srv/shared/kodi"))
    transport = SshTransport(
        "private-linux",
        "kodi",
        identity,
        known_hosts,
        runner=runner,
    )

    with pytest.raises(TransportError, match="escapes account home"):
        lifecycle_for_device(linux_device(), transport).probe_kodi()


def test_android_lifecycle_uses_adb_without_ssh_concerns():
    calls = []

    def runner(argv, **_kwargs):
        calls.append(argv)
        suffix = tuple(argv[5:])
        responses = {
            ("get-state",): result(stdout="device\n"),
            ("shell", "getprop", "ro.product.model"): result(
                stdout="TV MODEL\n"
            ),
            ("shell", "getprop", "ro.serialno"): result(stdout="serial\n"),
            ("shell", "getprop", "ro.product.cpu.abilist"): result(
                stdout="armeabi-v7a,armeabi\n"
            ),
            (
                "shell",
                "dumpsys",
                "package",
                "org.xbmc.kodi",
            ): result(stdout="versionName=21.3-Omega\n"),
            ("shell", "pidof", "org.xbmc.kodi"): result(
                returncode=1,
            ),
        }
        return responses[suffix]

    device = android_device()
    transport = AdbTransport("private-tv:5555", runner=runner)

    probe = lifecycle_for_device(device, transport).probe_kodi()

    assert probe["platform"] == "android"
    assert probe["kodi_version"] == "21.3-Omega"
    assert probe["running"] is False
    assert all(call[0] == "adb" for call in calls)


def test_transport_factory_resolves_private_references(tmp_path):
    identity, known_hosts = private_ssh_files(tmp_path)
    device = linux_device()

    transport = transport_for_device(
        device,
        references={
            "LINUX_USER": "kodi",
            "LINUX_KEY": str(identity),
            "LINUX_KNOWN_HOSTS": str(known_hosts),
        },
        runner=FakeSshRunner({}),
    )

    assert isinstance(transport, SshTransport)
    assert transport.user == "kodi"


def test_private_reference_loader_rejects_duplicate_names(tmp_path):
    path = tmp_path / ".env"
    path.write_text(
        "NUC_USER=first\nNUC_USER=second\n",
        encoding="utf-8",
    )
    path.chmod(0o600)

    with pytest.raises(ValueError, match="duplicate private reference"):
        load_private_references(path)


def test_private_reference_loader_rejects_broad_permissions(tmp_path):
    path = tmp_path / ".env"
    path.write_text("NUC_USER=kodi\n", encoding="utf-8")
    path.chmod(0o644)

    with pytest.raises(ValueError, match="permissions are too broad"):
        load_private_references(path)


def test_package_imports_share_transport_class_identity():
    assert kodi_lifecycle.AdbTransport is kodi_transports.AdbTransport
    assert kodi_inventory.transport_for_device.__module__ == (
        "tools.kodi_transports"
    )
