import copy
import io
import json
import subprocess

import pytest

from tools.qnap_compose_policy import explicit_bind_targets
from tools.qnap_control_plane import (
    ControlPlaneError,
    environment,
    validate_policy,
    verify_api,
)


def render(repository_root, tmp_path):
    deployment = repository_root / "deploy/qnap-control-plane"
    env_file = tmp_path / "control-plane.env"
    env_file.write_text(
        (deployment / "env.example")
        .read_text(encoding="utf-8")
        .replace("replace-with-release-digest", "a" * 64),
        encoding="utf-8",
    )
    result = subprocess.run(
        (
            "docker",
            "compose",
            "--project-name",
            "qnap-control-plane",
            "--env-file",
            str(env_file),
            "-f",
            str(deployment / "compose.yaml"),
            "config",
            "--format",
            "json",
            "--no-normalize",
        ),
        check=True,
        capture_output=True,
        text=True,
    )
    document = json.loads(result.stdout)
    document["_mwodevelop_source_policy"] = {
        "bind_create_host_path_false": sorted(
            explicit_bind_targets(
                (deployment / "compose.yaml").read_text(encoding="utf-8")
            )
        )
    }
    return document


def test_control_plane_compose_is_read_only_mtls_and_private_network(
    repository_root, tmp_path
):
    summary = validate_policy(render(repository_root, tmp_path))

    assert summary == {
        "image": "ghcr.io/mwodevelop/kodi-control-plane@sha256:" + "a" * 64,
        "host_ip": "192.0.2.39",
        "port": 19443,
        "project": "qnap-control-plane",
        "network": "mwodevelop-control",
    }


def test_control_plane_policy_rejects_docker_socket_and_missing_client_ca(
    repository_root, tmp_path
):
    document = render(repository_root, tmp_path)
    socket_mount = copy.deepcopy(document)
    socket_mount["services"]["control-plane"]["volumes"][0]["source"] = (
        "/var/run/docker.sock"
    )
    with pytest.raises(ControlPlaneError, match="managed root"):
        validate_policy(socket_mount)

    missing_ca = copy.deepcopy(document)
    missing_ca["services"]["control-plane"]["command"] = [
        item
        for item in missing_ca["services"]["control-plane"]["command"]
        if item != "--client-ca"
    ]
    with pytest.raises(ControlPlaneError, match="command policy"):
        validate_policy(missing_ca)


def test_control_plane_environment_rejects_public_or_mutable_target():
    image = "ghcr.io/mwodevelop/kodi-control-plane@sha256:" + "a" * 64
    assert "CONTROL_PLANE_HOST_IP=192.168.1.39" in environment(
        image, "192.168.1.39"
    )
    with pytest.raises(ControlPlaneError, match="private LAN"):
        environment(image, "8.8.8.8")
    with pytest.raises(ControlPlaneError, match="immutable"):
        environment("ghcr.io/mwodevelop/kodi-control-plane:latest", "192.168.1.39")


@pytest.mark.parametrize("schema", (1, 2))
def test_control_plane_api_accepts_supported_response_schemas(
    monkeypatch, tmp_path, schema
):
    ca = tmp_path / "ca.crt"
    certificate = tmp_path / "client.crt"
    key = tmp_path / "client.key"
    for path in (ca, certificate, key):
        path.write_text("test", encoding="utf-8")

    class Context:
        minimum_version = None

        def load_cert_chain(self, _certificate, _key):
            return None

    class Response(io.BytesIO):
        def __enter__(self):
            return self

        def __exit__(self, *_args):
            return False

    payload = json.dumps(
        {
            "schema": schema,
            "healthy": True,
            "services": [],
            "audit_sequence": 1,
        }
    ).encode("utf-8")
    monkeypatch.setattr(
        "tools.qnap_control_plane.ssl.create_default_context", lambda **_kwargs: Context()
    )
    monkeypatch.setattr(
        "tools.qnap_control_plane.urlopen", lambda *_args, **_kwargs: Response(payload)
    )

    assert verify_api("192.168.1.39", ca, certificate, key, attempts=1)[
        "schema"
    ] == schema


@pytest.fixture
def repository_root():
    from pathlib import Path

    return Path(__file__).resolve().parents[1]
