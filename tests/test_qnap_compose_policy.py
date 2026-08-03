import copy

import pytest

from tools.qnap_compose_policy import (
    PLACEHOLDER_IMAGE,
    PolicyError,
    explicit_bind_targets,
    render_compose,
    validate_policy,
)


def render(repository, mode, filename):
    return render_compose(
        repository,
        mode,
        repository / "deploy" / "qnap-profile-sync" / filename,
    )


def test_production_compose_contract(repository_root):
    document = render(repository_root, "production", "env.example")

    summary = validate_policy(
        document,
        "production",
        allow_placeholder=True,
    )

    assert summary == {
        "image_digest": "placeholder",
        "mode": "production",
        "host_ip": "192.0.2.39",
        "port": 18765,
        "project": "qnap-profile-sync",
        "restart": "unless-stopped",
    }


def test_smoke_compose_contract(repository_root):
    document = render(repository_root, "smoke", "smoke.env.example")

    summary = validate_policy(document, "smoke", allow_placeholder=True)

    assert summary == {
        "image_digest": "placeholder",
        "mode": "smoke",
        "host_ip": "127.0.0.1",
        "port": 28765,
        "project": "qnap-profile-sync-smoke",
        "restart": "no",
    }


def test_placeholder_is_rejected_for_real_deployment(repository_root):
    document = render(repository_root, "smoke", "smoke.env.example")

    assert document["services"]["profile-sync"]["image"] == PLACEHOLDER_IMAGE
    with pytest.raises(PolicyError, match="immutable GHCR digest"):
        validate_policy(document, "smoke")


def test_old_compose_may_omit_explicit_false_from_render(repository_root):
    document = render(repository_root, "smoke", "smoke.env.example")
    for volume in document["services"]["profile-sync"]["volumes"]:
        volume["bind"] = {}

    summary = validate_policy(document, "smoke", allow_placeholder=True)

    assert summary["mode"] == "smoke"


def test_smoke_rejects_production_data_path(repository_root):
    document = render(repository_root, "smoke", "smoke.env.example")
    candidate = copy.deepcopy(document)
    candidate["services"]["profile-sync"]["volumes"][0][
        "source"
    ] = "/share/CACHEDEV3_DATA/.mwodevelop/profile-sync/data"

    with pytest.raises(PolicyError, match="production paths"):
        validate_policy(candidate, "smoke", allow_placeholder=True)


def test_policy_rejects_container_name_and_host_network(repository_root):
    document = render(repository_root, "production", "env.example")
    named = copy.deepcopy(document)
    named["services"]["profile-sync"]["container_name"] = "fixed"
    host_network = copy.deepcopy(document)
    host_network["services"]["profile-sync"]["network_mode"] = "host"

    with pytest.raises(PolicyError, match="container_name"):
        validate_policy(named, "production", allow_placeholder=True)
    with pytest.raises(PolicyError, match="host-network"):
        validate_policy(host_network, "production", allow_placeholder=True)


def test_production_policy_requires_private_tls_mounts(repository_root):
    document = render(repository_root, "production", "env.example")
    missing_key = copy.deepcopy(document)
    missing_key["services"]["profile-sync"]["volumes"] = [
        item
        for item in missing_key["services"]["profile-sync"]["volumes"]
        if item.get("target") != "/run/profile-sync/tls/server.key"
    ]

    with pytest.raises(PolicyError, match="bind mount target"):
        validate_policy(missing_key, "production", allow_placeholder=True)

    public_listener = copy.deepcopy(document)
    public_listener["services"]["profile-sync"]["ports"][0][
        "host_ip"
    ] = "0.0.0.0"
    with pytest.raises(PolicyError, match="explicit non-loopback"):
        validate_policy(public_listener, "production", allow_placeholder=True)


def test_source_audit_requires_explicit_false():
    valid = """
      - type: bind
        source: /safe
        target: /data
        bind:
          create_host_path: false
"""
    unsafe = valid.replace("false", "true")

    assert explicit_bind_targets(valid) == {"/data"}
    assert explicit_bind_targets(unsafe) == set()


def test_admin_listener_must_not_be_published(repository_root):
    document = render(repository_root, "production", "env.example")
    candidate = copy.deepcopy(document)
    candidate["services"]["profile-sync"]["ports"].append(
        {
            "target": 8766,
            "published": 18767,
            "host_ip": "127.0.0.1",
            "protocol": "tcp",
        }
    )

    with pytest.raises(PolicyError, match="exactly one entry"):
        validate_policy(candidate, "production", allow_placeholder=True)


@pytest.fixture
def repository_root():
    from pathlib import Path

    return Path(__file__).resolve().parents[1]
