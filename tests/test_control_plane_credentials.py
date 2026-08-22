import subprocess

import pytest

from tools.control_plane_credentials import CredentialError, extend_existing, generate
from tools.qnap_control_plane import ControlPlaneError, validate_private_files
from tools.secret_broker_credentials import initialize as initialize_broker


def test_generates_isolated_server_operator_and_profile_sync_credentials(tmp_path):
    profile = tmp_path / "profile-sync-tls"
    profile.mkdir()
    subprocess.run(
        (
            "openssl",
            "req",
            "-x509",
            "-newkey",
            "rsa:2048",
            "-nodes",
            "-days",
            "1",
            "-subj",
            "/CN=Test Profile Sync CA",
            "-keyout",
            str(profile / "ca.key"),
            "-out",
            str(profile / "ca.crt"),
        ),
        check=True,
        capture_output=True,
        text=True,
    )
    (profile / "ca.key").chmod(0o600)
    output = tmp_path / "control-plane"

    result = generate(profile, output, "192.168.1.39")

    assert result["host_ip"] == "192.168.1.39"
    assert set(result["files"]) == {
        "audit-checkpoint.key",
        "authz/aead.key",
        "authz/clients-ca.crt",
        "authz/server.crt",
        "authz/server.key",
        "profile-sync/ca.crt",
        "profile-sync/client.crt",
        "profile-sync/client.key",
        "tls/clients-ca.crt",
        "tls/ca.crt",
        "tls/ca.key",
        "tls/operator-client.crt",
        "tls/operator-client.key",
        "tls/server.crt",
        "tls/server.key",
        "watchdog/ca.crt",
        "watchdog/client.crt",
        "watchdog/client.key",
        "watchdog/clients-ca.crt",
        "watchdog/server.crt",
        "watchdog/server.key",
        "web/authz-ca.crt",
        "web/authz-client.crt",
        "web/authz-client.key",
        "web/core-ca.crt",
        "web/core-client.crt",
        "web/core-client.key",
    }
    for relative in (
        "audit-checkpoint.key",
        "authz/aead.key",
        "authz/server.key",
        "profile-sync/client.key",
        "tls/ca.key",
        "tls/operator-client.key",
        "tls/server.key",
        "watchdog/client.key",
        "watchdog/server.key",
        "web/authz-client.key",
        "web/core-client.key",
    ):
        assert (output / relative).stat().st_mode & 0o077 == 0
    certificate = subprocess.run(
        (
            "openssl",
            "x509",
            "-in",
            str(output / "tls/server.crt"),
            "-noout",
            "-ext",
            "subjectAltName",
        ),
        check=True,
        capture_output=True,
        text=True,
    ).stdout
    assert "192.168.1.39" in certificate
    assert "DNS:control-plane" in certificate
    subprocess.run(
        (
            "openssl",
            "verify",
            "-CAfile",
            str(output / "tls/clients-ca.crt"),
            str(output / "tls/operator-client.crt"),
        ),
        check=True,
        capture_output=True,
        text=True,
    )
    rejected = subprocess.run(
        (
            "openssl",
            "verify",
            "-CAfile",
            str(output / "profile-sync/ca.crt"),
            str(output / "tls/operator-client.crt"),
        ),
        capture_output=True,
        text=True,
    )
    assert rejected.returncode != 0
    broker = tmp_path / "secret-broker"
    initialize_broker(broker)
    validate_private_files(output, broker / "control-plane")
    extension = extend_existing(output, "192.168.1.39")
    assert extension["extended"] is True
    validate_private_files(output, broker / "control-plane")
    (output / "tls/clients-ca.crt").write_bytes(
        (output / "profile-sync/ca.crt").read_bytes()
    )
    with pytest.raises(ControlPlaneError, match="trust chain"):
        validate_private_files(output, broker / "control-plane")
    with pytest.raises(CredentialError, match="already exists"):
        generate(profile, output, "192.168.1.39")
