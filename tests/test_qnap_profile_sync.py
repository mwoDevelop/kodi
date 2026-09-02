import json
from pathlib import PurePosixPath

import pytest

from tools.qnap_profile_sync import (
    CONTAINER_STATION_SOCKET,
    PRODUCTION_ROOT,
    QnapError,
    _raid_summary,
    container_station,
    production_root,
    production_environment,
    production_admin_request,
    production_pair_request,
    production_backup_paths,
    create_production_pairing,
    apply_production_revocation,
    plan_production_revocation,
    revoke_production_enrollment,
    set_production_playback_state,
    validate_production_files,
    verify_production,
    qnap_connection_settings,
    smoke_root,
)


class ReadyResponse:
    def __init__(self, database_schema):
        self.database_schema = database_schema

    def __enter__(self):
        return self

    def __exit__(self, *_args):
        return False

    def read(self):
        return json.dumps(
            {
                "api_version": "v1",
                "build": "test",
                "database_schema": self.database_schema,
                "mode": "verified-tls",
                "service": "kodi-profile-sync-server",
                "status": "ready",
                "version": "test",
            }
        ).encode("utf-8")


def test_production_readiness_accepts_additive_schema_upgrade(tmp_path, monkeypatch):
    ca = tmp_path / "ca.crt"
    ca.write_text("fixture", encoding="utf-8")
    monkeypatch.setattr(
        "tools.qnap_profile_sync.ssl.create_default_context", lambda **_kwargs: object()
    )
    monkeypatch.setattr(
        "tools.qnap_profile_sync.urlopen",
        lambda *_args, **_kwargs: ReadyResponse(7),
    )

    result = verify_production("192.168.1.39", ca, attempts=1)

    assert result["database_schema"] == 7


def test_production_readiness_rejects_legacy_schema(tmp_path, monkeypatch):
    ca = tmp_path / "ca.crt"
    ca.write_text("fixture", encoding="utf-8")
    monkeypatch.setattr(
        "tools.qnap_profile_sync.ssl.create_default_context", lambda **_kwargs: object()
    )
    monkeypatch.setattr(
        "tools.qnap_profile_sync.urlopen",
        lambda *_args, **_kwargs: ReadyResponse(4),
    )
    monkeypatch.setattr("tools.qnap_profile_sync.time.sleep", lambda _seconds: None)

    with pytest.raises(QnapError, match="production HTTPS readiness failed"):
        verify_production("192.168.1.39", ca, attempts=1)


class ContainerStationSession:
    def execute(self, command):
        assert command == (
            "getcfg container-station Install_Path -f /etc/config/qpkg.conf"
        )
        return "/share/CACHEDEV3_DATA/.qpkg/container-station"


def test_container_station_uses_gui_managed_docker_socket():
    install, docker = container_station(ContainerStationSession())

    assert install == "/share/CACHEDEV3_DATA/.qpkg/container-station"
    assert docker == (
        f"DOCKER_HOST=unix://{CONTAINER_STATION_SOCKET} "
        "/share/CACHEDEV3_DATA/.qpkg/container-station/bin/docker"
    )
    assert "system-docker.sock" not in docker


class PairingSession:
    def __init__(self):
        self.command = None

    def execute(self, command, timeout=30):
        self.command = command
        assert timeout == 120
        return (
            '{"channel":"home-stable","code":"12345678",'
            '"logical_device_id":"bluestacks1",'
            '"target_tags":["android-emulator:x86_64","home"]}'
        )


def test_production_root_is_fixed_and_never_derived_from_input():
    assert production_root() == PurePosixPath(
        "/share/CACHEDEV3_DATA/.mwodevelop/profile-sync"
    )
    assert production_root() == PRODUCTION_ROOT


def test_production_backup_paths_follow_data_bind_mount():
    container, host = production_backup_paths("production-initial-20260731")

    assert container == PurePosixPath("/data/backups/production-initial-20260731")
    assert host == PurePosixPath(
        "/share/CACHEDEV3_DATA/.mwodevelop/profile-sync/data/backups/production-initial-20260731"
    )


def test_production_pairing_writes_code_only_to_private_file(tmp_path, monkeypatch):
    monkeypatch.setattr(
        "tools.qnap_profile_sync.container_station",
        lambda _session: ("/container-station", "/usr/bin/docker"),
    )
    monkeypatch.setattr(
        "tools.qnap_profile_sync.production_compose_command",
        lambda _docker: "docker compose",
    )
    session = PairingSession()
    output = tmp_path / "pairing.json"

    result = create_production_pairing(
        session,
        "bluestacks1",
        "home-stable",
        ["home", "android-emulator:x86_64"],
        output,
    )

    assert result["code_written"] is True
    assert "12345678" not in str(result)
    assert output.stat().st_mode & 0o077 == 0
    assert '"code":"12345678"' in output.read_text()
    assert "--target-tag android-emulator:x86_64" in session.command


def test_production_revocation_uses_exact_host_only_enrollment(monkeypatch):
    class Session:
        command = None

        def execute(self, command, timeout=30):
            self.command = command
            assert timeout == 120
            return '{"enrollment_id":"enr:device-01234567","revoked":true}'

    monkeypatch.setattr(
        "tools.qnap_profile_sync.container_station",
        lambda _session: ("/container-station", "/usr/bin/docker"),
    )
    monkeypatch.setattr(
        "tools.qnap_profile_sync.production_compose_command",
        lambda _docker: "docker compose",
    )
    session = Session()

    result = revoke_production_enrollment(session, "enr:device-01234567")

    assert result == {
        "enrollment_id": "enr:device-01234567",
        "revoked": True,
    }
    assert "profile_sync_server.admin" in session.command
    assert session.command.endswith(" revoke enr:device-01234567")


def test_production_playback_state_uses_exact_host_only_enrollment(monkeypatch):
    class Session:
        command = None

        def execute(self, command, timeout=30):
            self.command = command
            assert timeout == 120
            return json.dumps(
                {
                    "enrollment_id": "enr:device-01234567",
                    "playback_state_enabled": True,
                    "playback_scope_id": "scope:home",
                }
            )

    monkeypatch.setattr(
        "tools.qnap_profile_sync.container_station",
        lambda _session: ("/container-station", "/usr/bin/docker"),
    )
    monkeypatch.setattr(
        "tools.qnap_profile_sync.production_compose_command",
        lambda _docker: "docker compose",
    )
    session = Session()

    result = set_production_playback_state(
        session, "enr:device-01234567", True, "scope:home"
    )

    assert result["playback_state_enabled"] is True
    assert " set-playback-state enr:device-01234567 " in session.command
    assert session.command.endswith("--enabled true --scope-id scope:home")


@pytest.mark.parametrize(
    "enrollment_id,enabled,scope_id",
    (
        ("device-1", True, "scope:home"),
        ("enr:device-01234567", "true", "scope:home"),
        ("enr:device-01234567", True, "../escape"),
    ),
)
def test_production_playback_state_rejects_invalid_input(
    enrollment_id, enabled, scope_id
):
    with pytest.raises(QnapError):
        set_production_playback_state(None, enrollment_id, enabled, scope_id)


def test_production_revocation_plan_download_and_apply_are_private(
    tmp_path, monkeypatch
):
    digest = "sha256:" + "a" * 64
    private_plan = {
        "schema": 1,
        "operation": "revoke_superseded_enrollments",
        "logical_device_id": "bluestacks1",
        "expected_highest_generation": 2,
        "minimum_last_seen_at": 1,
        "active_set_sha256": "sha256:" + "b" * 64,
        "targets": [{"enrollment_id": "enr:private-01234567", "generation": 1}],
        "created_at": 2,
        "plan_sha256": digest,
    }

    class Session:
        commands = []
        uploaded = None

        def execute(self, command, timeout=30):
            self.commands.append(command)
            if "plan-revoke-superseded" in command:
                return json.dumps(
                    {
                        "logical_device_id": "bluestacks1",
                        "expected_highest_generation": 2,
                        "target_generations": [1],
                        "target_count": 1,
                        "plan_sha256": digest,
                        "output": "/data/private.json",
                    }
                )
            if "apply-revoke-superseded" in command:
                return json.dumps(
                    {
                        "logical_device_id": "bluestacks1",
                        "plan_sha256": digest,
                        "revoked_generations": [1],
                        "revoked_count": 1,
                        "status": "applied",
                    }
                )
            return ""

        def download_file(self, _remote, local):
            local.write_text(json.dumps(private_plan), encoding="utf-8")
            local.chmod(0o600)

        def upload_text(self, remote, text, mode):
            self.uploaded = (remote, text, mode)

    monkeypatch.setattr(
        "tools.qnap_profile_sync.container_station",
        lambda _session: ("/container-station", "/usr/bin/docker"),
    )
    monkeypatch.setattr(
        "tools.qnap_profile_sync.production_compose_command",
        lambda _docker: "docker compose",
    )
    session = Session()
    output = tmp_path / "revocation.json"
    summary = plan_production_revocation(session, "bluestacks1", 900, output)
    assert summary["target_generations"] == [1]
    assert "enr:private-01234567" not in str(summary)
    assert output.stat().st_mode & 0o077 == 0

    result = apply_production_revocation(session, output, digest)
    assert result["revoked_generations"] == [1]
    assert session.uploaded[2] == 0o600
    assert "enr:private-01234567" not in str(result)


@pytest.mark.parametrize("enrollment_id", ("device-1", "../escape", "enr:x"))
def test_production_revocation_rejects_invalid_enrollment(enrollment_id):
    with pytest.raises(QnapError, match="invalid production enrollment"):
        revoke_production_enrollment(None, enrollment_id)


@pytest.mark.parametrize("backup_id", ("../escape", "/absolute", "x"))
def test_production_backup_paths_reject_unsafe_id(backup_id):
    with pytest.raises(QnapError, match="invalid backup id"):
        production_backup_paths(backup_id)


def test_production_environment_uses_explicit_tls_listener():
    rendered = production_environment(
        "ghcr.io/mwodevelop/kodi-profile-sync-server@sha256:" + "a" * 64,
        "192.168.1.39",
    )

    assert "PROFILE_SYNC_HOST_IP=192.168.1.39\n" in rendered
    assert (
        "PROFILE_SYNC_TLS_CERT=/share/CACHEDEV3_DATA/.mwodevelop/profile-sync/config/tls/server.crt\n"
        in rendered
    )
    assert (
        "PROFILE_SYNC_TLS_KEY=/share/CACHEDEV3_DATA/.mwodevelop/profile-sync/config/tls/server.key\n"
        in rendered
    )


def test_production_files_reject_nonprivate_tls_key(tmp_path, monkeypatch):
    registry = tmp_path / "key-registry.json"
    registry.write_text(
        '{"schema":1,"keys":{"publisher":{"public_key":"x","allowed_kinds":["revision"]}}}'
    )
    registry.chmod(0o600)
    certificate = tmp_path / "server.crt"
    certificate.write_text("certificate")
    key = tmp_path / "server.key"
    key.write_text("private key")
    key.chmod(0o644)
    authority = tmp_path / "favourites-authority.json"
    authority.write_text(
        '{"schema":1,"key_id":"favourites-authority-1",'
        '"seed":"AAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAA"}'
    )
    authority.chmod(0o600)
    monkeypatch.setattr(
        "ssl.SSLContext.load_cert_chain", lambda *_args, **_kwargs: None
    )

    with pytest.raises(QnapError, match="permissions are too broad"):
        validate_production_files(registry, certificate, key, authority)


def test_raid_summary_reports_degraded_recovery():
    mdstat = """
md1 : active raid1 sda3[3] sdb3[2]
      3897064256 blocks super 1.0 [2/1] [U_]
      [====>................] recovery = 28.3% finish=407.9min

md256 : active raid1 sdb2[1] sda2[0]
      530112 blocks super 1.0 [2/2] [UU]
"""

    assert _raid_summary(mdstat) == {
        "array": "U_",
        "recovery_percent": 28.3,
    }


def test_smoke_root_is_confined_to_container_station_share():
    root = smoke_root(
        "/share/CACHEDEV3_DATA/.qpkg/container-station",
        "profile-sync-20260727",
    )

    assert root == PurePosixPath(
        "/share/CACHEDEV3_DATA/.mwodevelop-smoke/profile-sync-20260727"
    )


@pytest.mark.parametrize(
    "run_id",
    ("../escape", "/absolute", "two/slashes", "UPPERCASE", "x"),
)
def test_smoke_root_rejects_unsafe_run_id(run_id):
    with pytest.raises(QnapError, match="invalid smoke run id"):
        smoke_root(
            "/share/CACHEDEV3_DATA/.qpkg/container-station",
            run_id,
        )


def test_qnap_connection_requires_private_key_and_pinned_host(tmp_path):
    identity = tmp_path / "id_ed25519"
    identity.write_text("private", encoding="utf-8")
    identity.chmod(0o600)
    known_hosts = tmp_path / "known_hosts"
    known_hosts.write_text("qnap ssh-ed25519 test\n", encoding="utf-8")
    known_hosts.chmod(0o600)

    settings = qnap_connection_settings(
        {
            "QNAP_HOST": "qnap",
            "QNAP_USER": "admin",
            "QNAP_SSH_KEY": str(identity),
            "QNAP_KNOWN_HOSTS": str(known_hosts),
            "QNAP_PASS": "must-not-be-used",
        }
    )

    assert settings["key_filename"] == str(identity)
    assert settings["known_hosts"] == str(known_hosts)
    assert "password" not in settings


def test_qnap_connection_rejects_broad_key_permissions(tmp_path):
    identity = tmp_path / "id_ed25519"
    identity.write_text("private", encoding="utf-8")
    identity.chmod(0o644)
    known_hosts = tmp_path / "known_hosts"
    known_hosts.write_text("qnap ssh-ed25519 test\n", encoding="utf-8")
    known_hosts.chmod(0o600)

    with pytest.raises(QnapError, match="permissions are too broad"):
        qnap_connection_settings(
            {
                "QNAP_HOST": "qnap",
                "QNAP_USER": "admin",
                "QNAP_SSH_KEY": str(identity),
                "QNAP_KNOWN_HOSTS": str(known_hosts),
            }
        )


def test_production_admin_uses_container_loopback_and_restricts_path(
    monkeypatch,
):
    class Session:
        command = None

        def execute(self, command, timeout=30):
            self.command = command
            assert timeout == 120
            return '{"revision_id":"sha256:' + "a" * 64 + '"}'

    monkeypatch.setattr(
        "tools.qnap_profile_sync.container_station",
        lambda _session: ("/container-station", "/usr/bin/docker"),
    )
    monkeypatch.setattr(
        "tools.qnap_profile_sync.production_compose_command",
        lambda _docker: "docker compose",
    )
    session = Session()

    result = production_admin_request(
        session,
        "/v1/revisions",
        {"schema": 1, "signature": {"value": "opaque"}},
        "admin-test-0001",
    )

    assert result["revision_id"] == "sha256:" + "a" * 64
    assert "exec -T profile-sync" in session.command
    assert "127.0.0.1:8766" in session.command
    assert "opaque" not in session.command
    with pytest.raises(QnapError, match="invalid production admin path"):
        production_admin_request(session, "/health", {}, "admin-test-0002")


def test_production_pairing_exchange_uses_private_container_loopback(
    monkeypatch,
):
    class Session:
        command = None

        def execute(self, command, timeout=30):
            self.command = command
            assert timeout == 120
            return '{"access_token":"secret","logical_device_id":"nuc-alek"}'

    monkeypatch.setattr(
        "tools.qnap_profile_sync.container_station",
        lambda _session: ("/container-station", "/usr/bin/docker"),
    )
    monkeypatch.setattr(
        "tools.qnap_profile_sync.production_compose_command",
        lambda _docker: "docker compose",
    )
    session = Session()

    result = production_pair_request(
        session,
        "12345678",
        "nuc-alek",
        "home-stable",
        "device-0123456789abcdef",
        "A" * 43,
    )

    assert result["logical_device_id"] == "nuc-alek"
    assert "exec -T profile-sync" in session.command
    assert "127.0.0.1:8765" in session.command
    assert "12345678" not in session.command


def test_production_pairing_forwards_optional_encryption_key(monkeypatch):
    captured = {}

    def request(_session, path, document, base_url):
        captured.update(
            {"path": path, "document": document, "base_url": base_url}
        )
        return {"status": "ok"}

    monkeypatch.setattr(
        "tools.qnap_profile_sync._production_loopback_post", request
    )

    result = production_pair_request(
        object(),
        "12345678",
        "nuc-alek",
        "home-stable",
        "device-0123456789abcdef",
        "A" * 43,
        "encryption-0123456789abcdef",
        "B" * 43,
    )

    assert result == {"status": "ok"}
    assert captured == {
        "path": "/v1/pair",
        "base_url": "https://127.0.0.1:8765",
        "document": {
            "code": "12345678",
            "logical_device_id": "nuc-alek",
            "channel": "home-stable",
            "key_id": "device-0123456789abcdef",
            "public_key": "A" * 43,
            "encryption_key_id": "encryption-0123456789abcdef",
            "encryption_public_key": "B" * 43,
        },
    }
