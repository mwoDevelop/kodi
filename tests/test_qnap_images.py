import json
import os
import stat
import subprocess

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


def test_watchdog_workflow_keys_follow_manifest(tmp_path):
    manifest = tmp_path / "manifests/upstream-watchdog.json"
    manifest.parent.mkdir()
    manifest.write_text(
        json.dumps(
            {
                "schema": 1,
                "workflows": [
                    {"repository": "owner/repo", "workflow": "first.yml"},
                    {"repository": "owner/repo", "workflow": "second.yml"},
                ],
            }
        ),
        encoding="utf-8",
    )

    assert qnap_images.watchdog_workflow_keys(tmp_path) == {
        ("owner/repo", "first.yml"),
        ("owner/repo", "second.yml"),
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


def test_default_stable_lock_is_versioned():
    assert qnap_images.DEFAULT_STABLE_LOCK == (
        qnap_images.ROOT / "manifests/locks/qnap-stable.json"
    )


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


def test_actions_build_dry_run_dispatches_exact_pushed_ref(monkeypatch, tmp_path):
    service = qnap_images.Service(
        name="profile-sync",
        image="ghcr.io/mwodevelop/kodi-profile-sync-server",
        repository=tmp_path,
        dockerfile=tmp_path / "Dockerfile",
        platforms=("linux/amd64", "linux/arm/v7"),
        github_repository="mwoDevelop/kodi-profile-sync-server",
        github_workflow="container.yml",
        github_inputs=(("publish_rc", "true"),),
    )
    monkeypatch.setattr(
        qnap_images,
        "source_identity",
        lambda _service, require_clean: {
            "commit": "d" * 40,
            "dirty": False,
        },
    )
    monkeypatch.setattr(qnap_images, "_remote_ref", lambda *_args: "main")

    result = qnap_images.build_with_actions(service, dry_run=True)

    assert result["tag"].endswith(":sha-" + "d" * 40)
    assert result["command"] == [
        "gh",
        "workflow",
        "run",
        "container.yml",
        "--repo",
        "mwoDevelop/kodi-profile-sync-server",
        "--ref",
        "main",
        "--field",
        "publish_rc=true",
    ]


def test_actions_build_can_capture_nested_workflow_progress(monkeypatch, tmp_path):
    service = qnap_images.Service(
        name="example",
        image="ghcr.io/mwodevelop/example",
        repository=tmp_path,
        dockerfile=tmp_path / "Dockerfile",
        platforms=("linux/amd64",),
        github_repository="mwoDevelop/example",
        github_workflow="container.yml",
    )
    monkeypatch.setattr(
        qnap_images,
        "source_identity",
        lambda *_args, **_kwargs: {"commit": "d" * 40, "dirty": False},
    )
    monkeypatch.setattr(qnap_images, "_remote_ref", lambda *_args: "main")
    monkeypatch.setattr(
        qnap_images,
        "_workflow_run",
        lambda *_args: {
            "databaseId": 123,
            "url": "https://example.invalid/run/123",
        },
    )
    monkeypatch.setattr(
        qnap_images,
        "_published_reference",
        lambda *_args: service.image + "@sha256:" + "e" * 64,
    )
    calls = []

    def run(argv, **kwargs):
        calls.append((tuple(argv), kwargs))
        return type("Result", (), {"stdout": ""})()

    monkeypatch.setattr(qnap_images, "_run", run)

    result = qnap_images.build_with_actions(service, stream_progress=False)

    assert result["workflow_run_id"] == "123"
    assert calls == [
        (
            (
                "gh",
                "run",
                "watch",
                "123",
                "--repo",
                "mwoDevelop/example",
                "--exit-status",
                "--interval",
                "5",
            ),
            {"capture": True},
        )
    ]


def test_tag_digest_extracts_manifest_digest(monkeypatch):
    monkeypatch.setattr(
        qnap_images,
        "_imagetools_inspect",
        lambda *_args, **_kwargs: type(
            "Result",
            (),
            {"stdout": "Name: test\nDigest: sha256:%s\n" % ("e" * 64)},
        )(),
    )

    assert qnap_images._tag_digest("example.invalid/image:test") == (
        "sha256:" + "e" * 64
    )


def test_imagetools_inspect_retries_missing_desktop_helper_anonymously(
    monkeypatch,
):
    calls = []

    def run(argv, **kwargs):
        calls.append((tuple(argv), kwargs))
        if len(calls) == 1:
            raise subprocess.CalledProcessError(
                1,
                argv,
                stderr=(
                    'error getting credentials - err: exec: '
                    '"docker-credential-desktop.exe": executable file not found'
                ),
            )
        return type("Result", (), {"stdout": "{}"})()

    monkeypatch.setattr(qnap_images, "_run", run)

    result = qnap_images._imagetools_inspect("ghcr.io/example/image:tag", raw=True)

    assert result.stdout == "{}"
    assert calls[0][0][-1] == "--raw"
    assert calls[0][1] == {}
    assert calls[1][0] == calls[0][0]
    assert calls[1][1]["env"]["DOCKER_CONFIG"] != os.environ.get(
        "DOCKER_CONFIG"
    )


def test_imagetools_inspect_preserves_non_credential_failure(monkeypatch):
    error = subprocess.CalledProcessError(
        1,
        ["docker"],
        stderr="registry unavailable",
    )
    monkeypatch.setattr(
        qnap_images,
        "_run",
        lambda *_args, **_kwargs: (_ for _ in ()).throw(error),
    )

    with pytest.raises(subprocess.CalledProcessError) as observed:
        qnap_images._imagetools_inspect("ghcr.io/example/image:tag")

    assert observed.value is error


def test_published_reference_retries_registry_propagation(monkeypatch):
    service = qnap_images.Service(
        name="service",
        image="ghcr.io/mwodevelop/service",
        repository=qnap_images.ROOT,
        dockerfile=qnap_images.Path("Dockerfile"),
        platforms=("linux/amd64",),
    )
    attempts = []

    def verify(*_args):
        attempts.append(True)
        if len(attempts) == 1:
            raise qnap_images.subprocess.CalledProcessError(1, "inspect")

    monkeypatch.setattr(qnap_images, "verify_platforms", verify)
    monkeypatch.setattr(
        qnap_images,
        "_tag_digest",
        lambda _tag: "sha256:" + "f" * 64,
    )
    monkeypatch.setattr(qnap_images.time, "sleep", lambda _seconds: None)

    assert qnap_images._published_reference(service, "image:tag") == (
        "ghcr.io/mwodevelop/service@sha256:" + "f" * 64
    )
    assert len(attempts) == 2


def test_all_services_have_action_publishers():
    for service in qnap_images.services().values():
        assert service.github_repository.startswith("mwoDevelop/")
        assert service.github_workflow.endswith(".yml")
        assert service.input_paths


def test_source_input_hash_ignores_unrelated_tracked_files(tmp_path):
    repository = tmp_path / "source"
    repository.mkdir()
    (repository / "Dockerfile").write_text("FROM scratch\n")
    (repository / "app.py").write_text("print('one')\n")
    (repository / "unrelated.txt").write_text("first\n")
    subprocess.run(("git", "init", "-q", repository), check=True)
    subprocess.run(("git", "-C", repository, "add", "."), check=True)
    subprocess.run(
        (
            "git", "-C", repository, "-c", "user.name=test",
            "-c", "user.email=test@example.invalid", "commit", "-qm", "one",
        ),
        check=True,
    )
    service = qnap_images.Service(
        "example",
        "ghcr.io/mwodevelop/example",
        repository,
        qnap_images.Path("Dockerfile"),
        ("linux/amd64",),
        input_paths=("Dockerfile", "app.py"),
    )
    first = qnap_images.source_input_sha256(service)
    (repository / "unrelated.txt").write_text("second\n")
    subprocess.run(("git", "-C", repository, "add", "."), check=True)
    subprocess.run(
        (
            "git", "-C", repository, "-c", "user.name=test",
            "-c", "user.email=test@example.invalid", "commit", "-qm", "two",
        ),
        check=True,
    )
    assert qnap_images.source_input_sha256(service) == first
    (repository / "app.py").write_text("print('two')\n")
    subprocess.run(("git", "-C", repository, "add", "."), check=True)
    subprocess.run(
        (
            "git", "-C", repository, "-c", "user.name=test",
            "-c", "user.email=test@example.invalid", "commit", "-qm", "three",
        ),
        check=True,
    )
    assert qnap_images.source_input_sha256(service) != first


class StatusSession:
    def execute(self, command, allowed=(0,), timeout=None):
        if " inspect " in command:
            container = command.rsplit(" ", 1)[-1]
            return json.dumps(
                [
                    {
                        "Config": {"Image": "ghcr.io/example/" + container},
                        "State": {
                            "Health": {"Status": "unhealthy"},
                            "StartedAt": "2026-08-10T00:00:00Z",
                            "Status": "running",
                        },
                    }
                ]
            )
        if "status.json" in command:
            assert allowed == (0, 1)
            assert timeout == 10
            return json.dumps(
                {
                    "schema": 1,
                    "checked_at": "2026-08-10T00:01:00Z",
                    "healthy": False,
                    "workflows": [
                        {
                            "repository": "mwoDevelop/repo",
                            "workflow": "audit.yml",
                            "healthy": False,
                        },
                        {
                            "repository": "mwoDevelop/repo",
                            "workflow": "sync.yml",
                            "healthy": True,
                        },
                    ],
                }
            )
        raise AssertionError(command)

    def close(self):
        pass


def test_status_explains_watchdog_health(monkeypatch):
    monkeypatch.setattr(
        qnap_images,
        "connect",
        lambda _repository, _references: StatusSession(),
    )
    monkeypatch.setattr(
        qnap_images,
        "container_station",
        lambda _session: ("/share/install", "docker"),
    )

    watchdog = qnap_images.status(".env")["upstream-watchdog"]

    assert watchdog["runtime_healthy"] is False
    assert watchdog["workflows"] == 2
    assert watchdog["workflow_failures"] == [
        "mwoDevelop/repo/audit.yml"
    ]


def test_status_treats_empty_docker_inspect_as_missing(monkeypatch):
    class Session(StatusSession):
        def execute(self, command, allowed=(0,), timeout=None):
            if "qnap-control-plane-control-plane-1" in command:
                return "[]"
            return super().execute(command, allowed=allowed, timeout=timeout)

    monkeypatch.setattr(
        qnap_images,
        "connect",
        lambda _repository, _references: Session(),
    )
    monkeypatch.setattr(
        qnap_images,
        "container_station",
        lambda _session: ("/share/install", "docker"),
    )

    assert qnap_images.status(".env")["control-plane"] == {
        "status": "missing"
    }


def test_service_health_accepts_initial_watchdog_runtime_evidence_only():
    assert qnap_images.service_is_healthy(
        {
            "status": "running",
            "health": "starting",
            "runtime_healthy": True,
        }
    )
    assert not qnap_images.service_is_healthy(
        {
            "status": "running",
            "health": "unhealthy",
            "runtime_healthy": True,
        }
    )
    assert not qnap_images.service_is_healthy(
        {"status": "running", "health": "starting"}
    )


def test_watchdog_alert_is_operational_but_not_healthy():
    item = {
        "status": "running",
        "health": "starting",
        "checked_at": "2026-08-18T00:00:00+00:00",
        "runtime_healthy": False,
        "workflow_failures": ["example/reconcile.yml"],
    }

    assert not qnap_images.service_is_healthy(item)
    assert qnap_images.service_is_operational("upstream-watchdog", item)
    assert not qnap_images.service_is_operational("profile-sync", item)


def test_watchdog_without_a_structured_alert_is_not_operational():
    base = {
        "status": "running",
        "health": "starting",
        "checked_at": "2026-08-18T00:00:00+00:00",
        "runtime_healthy": False,
    }

    assert not qnap_images.service_is_operational("upstream-watchdog", base)
    assert not qnap_images.service_is_operational(
        "upstream-watchdog", {**base, "workflow_failures": []}
    )


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
