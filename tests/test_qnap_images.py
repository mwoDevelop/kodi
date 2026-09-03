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
                "environment": {"GITHUB_TOKEN": "test-token"},
                "command": [
                    "watch",
                    "--listen",
                    "0.0.0.0",
                    "--port",
                    "9445",
                    "--tls-cert",
                    "/run/watchdog/tls/server.crt",
                    "--tls-key",
                    "/run/watchdog/tls/server.key",
                    "--client-ca",
                    "/run/watchdog/tls/clients-ca.crt",
                    "--interval-seconds",
                    "900",
                    "--remediation-recheck-seconds",
                    "60",
                    "--remediate",
                ],
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
                        "tools/upstream_watchdog.py",
                        "health",
                        "--status",
                        "/run/watchdog/status.json",
                        "--max-status-age-seconds",
                        "3600",
                    ]
                },
                "volumes": [
                    {
                        "type": "bind",
                        "source": str(qnap_images.WATCHDOG_ROOT / "config/server.crt"),
                        "target": "/run/watchdog/tls/server.crt",
                        "read_only": True,
                    },
                    {
                        "type": "bind",
                        "source": str(qnap_images.WATCHDOG_ROOT / "config/server.key"),
                        "target": "/run/watchdog/tls/server.key",
                        "read_only": True,
                    },
                    {
                        "type": "bind",
                        "source": str(qnap_images.WATCHDOG_ROOT / "config/clients-ca.crt"),
                        "target": "/run/watchdog/tls/clients-ca.crt",
                        "read_only": True,
                    },
                ],
                "networks": {"control-plane": None},
            }
        },
        "networks": {
            "control-plane": {
                "name": "mwodevelop-control",
                "external": True,
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
                "schema": 2,
                "workflows": [
                    {"repository": "owner/repo", "workflow": "first.yml", "max_age_seconds": 3600},
                    {"repository": "owner/repo", "workflow": "second.yml", "max_age_seconds": 3600},
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
        ("environment", {}),
        ("user", "0:0"),
    ],
)
def test_watchdog_policy_rejects_unsafe_changes(field, value):
    document = watchdog_policy()
    document["services"]["upstream-watchdog"][field] = value
    with pytest.raises(qnap_images.ImageError):
        qnap_images.validate_watchdog_policy(document)


def test_watchdog_environment_contains_secret_without_logging_it():
    environment = qnap_images._watchdog_environment(IMAGE, "test-token")

    assert environment.splitlines() == [
        "UPSTREAM_WATCHDOG_IMAGE=" + IMAGE,
        "UPSTREAM_WATCHDOG_GITHUB_TOKEN=test-token",
        "UPSTREAM_WATCHDOG_TLS_CERT="
        + str(qnap_images.WATCHDOG_ROOT / "config/server.crt"),
        "UPSTREAM_WATCHDOG_TLS_KEY="
        + str(qnap_images.WATCHDOG_ROOT / "config/server.key"),
        "UPSTREAM_WATCHDOG_CLIENT_CA="
        + str(qnap_images.WATCHDOG_ROOT / "config/clients-ca.crt"),
    ]


def test_watchdog_credentials_accept_github_pass_only_when_it_is_a_token(
    monkeypatch,
):
    pat = "ghp_" + "a" * 36
    monkeypatch.setattr(
        qnap_images,
        "_github_identity",
        lambda token: {
            "login": "mwoDevelop" if token == pat else "",
            "rate_limit": 5000,
            "rate_remaining": 4999,
            "oauth_scopes": ["workflow"],
        },
    )
    monkeypatch.setattr(
        qnap_images,
        "_run",
        lambda *_args, **_kwargs: type("Result", (), {"stdout": ""})(),
    )

    credentials = qnap_images.watchdog_github_credentials(
        {"GITHUB_USER": "mwodevelop", "GITHUB_PASS": pat}
    )

    assert credentials == {
        "token": pat,
        "source": "GITHUB_PASS",
        "login": "mwoDevelop",
        "rate_limit": 5000,
        "rate_remaining": 4999,
        "capability": "workflow_dispatch",
    }


def test_watchdog_credentials_fall_back_to_matching_gh_session(monkeypatch):
    monkeypatch.setattr(
        qnap_images,
        "_github_identity",
        lambda token: (
            {
                "login": "mwoDevelop",
                "rate_limit": 5000,
                "rate_remaining": 4900,
                "oauth_scopes": ["repo", "workflow"],
            }
            if token == "gh-token"
            else (_ for _ in ()).throw(qnap_images.HTTPError(
                "https://api.github.com/user", 401, "bad", {}, None
            ))
        ),
    )
    monkeypatch.setattr(
        qnap_images,
        "_run",
        lambda *_args, **_kwargs: type(
            "Result", (), {"stdout": "gh-token\n"}
        )(),
    )

    credentials = qnap_images.watchdog_github_credentials(
        {"GITHUB_USER": "mwoDevelop", "GITHUB_PASS": "account-password"}
    )

    assert credentials["source"] == "gh-cli"
    assert credentials["token"] == "gh-token"
    assert credentials["rate_limit"] == 5000


def test_watchdog_credentials_skip_authenticated_read_only_token(monkeypatch):
    identities = {
        "read-token": {
            "login": "mwoDevelop",
            "rate_limit": 5000,
            "rate_remaining": 4900,
            "oauth_scopes": ["repo"],
        },
        "write-token": {
            "login": "mwoDevelop",
            "rate_limit": 5000,
            "rate_remaining": 4800,
            "oauth_scopes": ["repo", "workflow"],
        },
    }
    monkeypatch.setattr(qnap_images, "_github_identity", identities.__getitem__)
    monkeypatch.setattr(
        qnap_images,
        "_run",
        lambda *_args, **_kwargs: type(
            "Result", (), {"stdout": "write-token\n"}
        )(),
    )

    credentials = qnap_images.watchdog_github_credentials(
        {"GITHUB_USER": "mwoDevelop", "GITHUB_TOKEN": "read-token"}
    )

    assert credentials["source"] == "gh-cli"
    assert credentials["token"] == "write-token"
    assert credentials["capability"] == "workflow_dispatch"


def test_watchdog_credentials_bind_email_sign_in_to_repository_owner(
    monkeypatch,
):
    monkeypatch.setattr(
        qnap_images,
        "_github_identity",
        lambda _token: {
            "login": "mwoDevelop",
            "rate_limit": 5000,
            "rate_remaining": 4800,
            "oauth_scopes": ["workflow"],
        },
    )
    monkeypatch.setattr(
        qnap_images,
        "_run",
        lambda *_args, **_kwargs: type("Result", (), {"stdout": "gh-token"})(),
    )

    credentials = qnap_images.watchdog_github_credentials(
        {"GITHUB_USER": "operator@example.invalid", "GITHUB_PASS": "password"}
    )

    assert credentials["login"] == "mwoDevelop"


def test_watchdog_credentials_reject_email_with_foreign_account(monkeypatch):
    monkeypatch.setattr(
        qnap_images,
        "_github_identity",
        lambda _token: {
            "login": "different-owner",
            "rate_limit": 5000,
            "rate_remaining": 4800,
            "oauth_scopes": ["workflow"],
        },
    )
    monkeypatch.setattr(
        qnap_images,
        "_run",
        lambda *_args, **_kwargs: type("Result", (), {"stdout": "gh-token"})(),
    )

    with pytest.raises(qnap_images.ImageError, match="authenticated GitHub"):
        qnap_images.watchdog_github_credentials(
            {"GITHUB_USER": "operator@example.invalid"}
        )


def test_watchdog_credentials_fail_closed_without_authenticated_token(
    monkeypatch,
):
    monkeypatch.setattr(
        qnap_images,
        "_github_identity",
        lambda _token: {
            "login": "mwoDevelop",
            "rate_limit": 60,
            "rate_remaining": 59,
            "oauth_scopes": ["workflow"],
        },
    )
    monkeypatch.setattr(
        qnap_images,
        "_run",
        lambda *_args, **_kwargs: type("Result", (), {"stdout": ""})(),
    )

    with pytest.raises(qnap_images.ImageError, match="authenticated GitHub"):
        qnap_images.watchdog_github_credentials(
            {"GITHUB_USER": "mwoDevelop", "GITHUB_PASS": "password"}
        )


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
                    "schema": 2,
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

    status = qnap_images.status(".env")
    watchdog = status["upstream-watchdog"]

    assert watchdog["runtime_healthy"] is False
    assert watchdog["observer_ready"] is True
    assert watchdog["collection_state"] == "READY"
    assert watchdog["monitored_state"] == "FAILED"
    assert watchdog["workflows"] == 2
    assert watchdog["workflow_failures"] == [
        "mwoDevelop/repo/audit.yml"
    ]
    assert status["control-plane-authz"]["status"] == "running"
    assert status["control-plane-web"]["status"] == "running"


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
    assert qnap_images.service_is_healthy(
        {
            "status": "running",
            "health": "starting",
            "observer_ready": True,
            "monitored_state": "FAILED",
        }
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


def test_new_watchdog_business_failure_remains_operational():
    item = {
        "status": "running",
        "health": "starting",
        "checked_at": "2026-08-26T10:00:00+00:00",
        "runtime_healthy": False,
        "observer_ready": True,
        "collection_state": "READY",
        "monitored_state": "FAILED",
        "workflow_failures": ["example/reconcile.yml"],
    }

    assert qnap_images.service_is_healthy(item)
    assert qnap_images.service_is_operational("upstream-watchdog", item)

    item["health"] = "unhealthy"
    assert not qnap_images.service_is_healthy(item)
    assert not qnap_images.service_is_operational("upstream-watchdog", item)


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
