import copy

import pytest

from tools.qnap_compose_policy import (
    PLACEHOLDER_IMAGE,
    PolicyError,
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
        "port": 28765,
        "project": "qnap-profile-sync-smoke",
        "restart": "no",
    }


def test_placeholder_is_rejected_for_real_deployment(repository_root):
    document = render(repository_root, "smoke", "smoke.env.example")

    assert document["services"]["profile-sync"]["image"] == PLACEHOLDER_IMAGE
    with pytest.raises(PolicyError, match="immutable GHCR digest"):
        validate_policy(document, "smoke")


def test_smoke_rejects_production_data_path(repository_root):
    document = render(repository_root, "smoke", "smoke.env.example")
    candidate = copy.deepcopy(document)
    candidate["services"]["profile-sync"]["volumes"][0][
        "source"
    ] = "/share/ProfileSync/data"

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


@pytest.fixture
def repository_root():
    from pathlib import Path

    return Path(__file__).resolve().parents[1]
