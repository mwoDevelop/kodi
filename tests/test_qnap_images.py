import json
import stat

import pytest

from tools import qnap_images


IMAGE = (
    "ghcr.io/mwodevelop/kodi-upstream-watchdog@sha256:" + "a" * 64
)


def watchdog_policy(image=IMAGE):
    return {
        "name": "qnap-upstream-watchdog",
        "services": {
            "upstream-watchdog": {
                "image": image,
                "init": True,
                "read_only": True,
                "restart": "unless-stopped",
                "cap_drop": ["ALL"],
                "security_opt": ["no-new-privileges:true"],
                "mem_limit": "67108864",
                "pids_limit": 32,
                "user": "10001:10001",
                "tmpfs": [
                    "/run/watchdog:size=1m,mode=0700,uid=10001,gid=10001",
                    "/tmp:size=4m,mode=1777",
                ],
                "healthcheck": {
                    "test": [
                        "CMD",
                        "python",
                        "-c",
                        "assert open('/run/watchdog/status.json')",
                    ]
                },
            }
        },
    }


def test_watchdog_policy_accepts_hardened_immutable_service():
    assert qnap_images.validate_watchdog_policy(watchdog_policy()) == {
        "image": IMAGE,
        "project": "qnap-upstream-watchdog",
    }


@pytest.mark.parametrize(
    ("field", "value"),
    [
        ("image", "ghcr.io/mwodevelop/kodi-upstream-watchdog:latest"),
        ("read_only", False),
        ("restart", "always"),
        ("cap_drop", []),
        ("ports", ["8080:8080"]),
        ("volumes", ["/tmp:/tmp"]),
        ("user", "0:0"),
    ],
)
def test_watchdog_policy_rejects_unsafe_changes(field, value):
    document = watchdog_policy()
    document["services"]["upstream-watchdog"][field] = value
    with pytest.raises(qnap_images.ImageError):
        qnap_images.validate_watchdog_policy(document)


def test_private_build_state_round_trip(tmp_path):
    state = tmp_path / "qnap-images.json"
    images = {
        "upstream-watchdog": {
            "image": IMAGE,
            "source_commit": "b" * 40,
            "tag": "ghcr.io/mwodevelop/kodi-upstream-watchdog:sha-test",
        }
    }

    qnap_images.save_state(state, images)

    assert qnap_images.load_state(state) == {"schema": 1, "images": images}
    assert stat.S_IMODE(state.stat().st_mode) == 0o600


def test_build_dry_run_is_content_addressed(monkeypatch, tmp_path):
    service = qnap_images.Service(
        name="upstream-watchdog",
        image="ghcr.io/mwodevelop/kodi-upstream-watchdog",
        repository=tmp_path,
        dockerfile=tmp_path / "Dockerfile",
        platforms=("linux/amd64", "linux/arm/v7"),
    )
    monkeypatch.setattr(
        qnap_images,
        "source_identity",
        lambda _service, require_clean: {
            "commit": "c" * 40,
            "dirty": True,
        },
    )

    result = qnap_images.build(service, "builder", dry_run=True)

    assert result["source_dirty"] is True
    assert result["tag"].endswith(":sha-" + "c" * 40)
    assert "--push" in result["command"]
    assert "linux/amd64,linux/arm/v7" in result["command"]


def test_selected_services_is_ordered_and_strict():
    available = {"profile-sync": object(), "provider-relay": object()}
    assert qnap_images.selected_services(["all"], available) == [
        "profile-sync",
        "provider-relay",
    ]
    assert qnap_images.selected_services(
        ["provider-relay", "provider-relay"], available
    ) == ["provider-relay"]
    with pytest.raises(qnap_images.ImageError):
        qnap_images.selected_services(["all", "profile-sync"], available)
    with pytest.raises(qnap_images.ImageError):
        qnap_images.selected_services(["missing"], available)


def test_invalid_state_fails_closed(tmp_path):
    state = tmp_path / "qnap-images.json"
    state.write_text(
        json.dumps(
            {
                "schema": 1,
                "images": {
                    "watchdog": {
                        "image": "ghcr.io/mwodevelop/watchdog:latest"
                    }
                },
            }
        ),
        encoding="utf-8",
    )
    with pytest.raises(qnap_images.ImageError):
        qnap_images.load_state(state)
