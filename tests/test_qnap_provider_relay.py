import copy
from pathlib import Path

import pytest

from tools import qnap_provider_relay
from tools.qnap_provider_relay import (
    PLACEHOLDER_IMAGE,
    RelayPolicyError,
    render_policy,
    validate_policy,
    verify,
)

ROOT = Path(__file__).resolve().parents[1]


def render(mode, filename):
    return render_policy(
        ROOT,
        mode,
        ROOT / "deploy/qnap-provider-relay" / filename,
    )


def test_production_policy():
    document = render("production", "env.example")

    healthcheck = document["services"]["provider-relay"]["healthcheck"]
    assert healthcheck["timeout"] == "10s"
    assert "timeout=5" in " ".join(healthcheck["test"])
    assert validate_policy(
        document, "production", allow_placeholder=True
    ) == {
        "bind": "192.168.0.10",
        "image_digest": "placeholder",
        "mode": "production",
        "port": 18766,
        "project": "qnap-provider-relay",
    }


def test_smoke_policy():
    document = render("smoke", "smoke.env.example")

    assert validate_policy(document, "smoke", allow_placeholder=True) == {
        "bind": "127.0.0.1",
        "image_digest": "placeholder",
        "mode": "smoke",
        "port": 28766,
        "project": "qnap-provider-relay-smoke",
    }


def test_placeholder_is_not_deployable():
    document = render("smoke", "smoke.env.example")
    assert document["services"]["provider-relay"]["image"] == PLACEHOLDER_IMAGE

    with pytest.raises(RelayPolicyError, match="immutable GHCR digest"):
        validate_policy(document, "smoke")


def test_policy_rejects_public_bind_volume_and_host_network():
    original = render("production", "env.example")
    public = copy.deepcopy(original)
    public["services"]["provider-relay"]["ports"][0]["host_ip"] = "8.8.8.8"
    volume = copy.deepcopy(original)
    volume["services"]["provider-relay"]["volumes"] = ["/tmp:/data"]
    host = copy.deepcopy(original)
    host["services"]["provider-relay"]["network_mode"] = "host"

    with pytest.raises(RelayPolicyError, match="private LAN"):
        validate_policy(public, "production", allow_placeholder=True)
    with pytest.raises(RelayPolicyError, match="must not mount"):
        validate_policy(volume, "production", allow_placeholder=True)
    with pytest.raises(RelayPolicyError, match="host-network"):
        validate_policy(host, "production", allow_placeholder=True)


class TransientProviderSession:
    def __init__(self):
        self.provider_attempts = 0

    def execute(self, command, allowed=(0,), timeout=None):
        if "/health" in command:
            return '{"status":"ok"}'
        if "/torrentio/stream/" in command:
            assert allowed == (0, 1)
            assert timeout == 30
            self.provider_attempts += 1
            return "nonempty" if self.provider_attempts == 3 else ""
        if " ps -a " in command:
            return "Up 10 seconds (healthy)"
        if " network ls " in command:
            return "network-id"
        if " volume ls " in command:
            return ""
        raise AssertionError(command)


def test_verify_retries_transient_provider_probe(monkeypatch):
    session = TransientProviderSession()
    monkeypatch.setattr(
        qnap_provider_relay,
        "container_station",
        lambda _session: ("/share/install", "docker"),
    )
    monkeypatch.setattr(
        qnap_provider_relay.time,
        "sleep",
        lambda _seconds: None,
    )

    evidence = verify(session, "production", "192.168.1.39")

    assert session.provider_attempts == 3
    assert evidence["health"] == "ok"
    assert evidence["provider_metadata_nonempty"] is True
