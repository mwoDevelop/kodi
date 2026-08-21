import os
import json

from tools.qnap_secret_broker import (
    environment,
    import_secret_set,
    private_files,
    validate_policy,
)


IMAGE = "ghcr.io/mwodevelop/kodi-secret-broker@sha256:" + "a" * 64


def test_environment_has_no_lan_port_or_plaintext_secret():
    rendered = environment(IMAGE)
    assert "SECRET_BROKER_IMAGE=" + IMAGE in rendered
    assert "PORT=" not in rendered
    assert "YOUTUBE" not in rendered


def test_private_files_require_master_key_and_private_modes(tmp_path):
    tls = tmp_path / "tls"
    tls.mkdir()
    (tmp_path / "broker-master-key").write_text(os.urandom(32).hex() + "\n")
    for name in ("server.key", "health.key"):
        (tls / name).write_text("not-a-real-key\n")
    for name in ("server.crt", "clients-ca.crt", "health.crt"):
        (tls / name).write_text("not-a-real-certificate\n")
    for path in tmp_path.rglob("*"):
        if path.is_file():
            path.chmod(0o600)

    # TLS parsing deliberately follows the filesystem/mode checks.
    try:
        private_files(tmp_path)
    except Exception as error:
        assert "certificate/key differs" in str(error)


def test_policy_rejects_published_port():
    document = {
        "services": {
            "secret-broker": {
                "image": IMAGE,
                "read_only": True,
                "user": "10002:10002",
                "cap_drop": ["ALL"],
                "volumes": [],
                "networks": {"control-plane": None},
                "ports": [{"target": 9444, "published": 19444}],
            }
        }
    }
    try:
        validate_policy(document)
    except Exception as error:
        assert "must not publish ports" in str(error)
    else:
        raise AssertionError("published Secret Broker port must be rejected")


def test_import_streams_secret_over_ssh_stdin_without_command_leak(monkeypatch):
    class Channel:
        def shutdown_write(self):
            pass

        def recv_exit_status(self):
            return 0

    class Stream:
        def __init__(self, payload=b""):
            self.payload = payload
            self.channel = Channel()

        def write(self, value):
            self.payload = value.encode("utf-8")

        def flush(self):
            pass

        def read(self):
            return self.payload

    class Client:
        def exec_command(self, command, timeout):
            self.command = command
            self.stdin = Stream()
            return self.stdin, Stream(b'{"generation":1}'), Stream()

    class Session:
        client = Client()

    monkeypatch.setattr(
        "tools.qnap_secret_broker.container_station",
        lambda _session: ("install", "/usr/bin/docker"),
    )
    document = {"secret": {"personal_refresh_token": "never-in-command"}}
    assert import_secret_set(Session(), document) == {"generation": 1}
    assert "never-in-command" not in Session.client.command
    assert json.loads(Session.client.stdin.payload) == document
