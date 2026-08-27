#!/usr/bin/env python3
"""Build, deploy and inspect all mwoDevelop Kodi QNAP images."""

from __future__ import annotations

import argparse
import datetime as dt
import hashlib
import ipaddress
import json
import os
import re
import shlex
import ssl
import stat
import subprocess
import tempfile
import time
from dataclasses import dataclass
from pathlib import Path, PurePosixPath
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen

try:
    from control_plane_device_inventory import build_inventory
    from qnap_control_plane import (
        create_browser_bootstrap,
    )
    from qnap_control_plane import (
        deploy as deploy_control_plane,
    )
    from qnap_profile_sync import (
        QnapError,
        connect,
        container_station,
        deploy_production,
        load_private_references,
        preflight,
    )
    from qnap_provider_relay import deploy as deploy_relay
    from qnap_secret_broker import deploy as deploy_secret_broker
except ModuleNotFoundError:
    from tools.control_plane_device_inventory import build_inventory
    from tools.qnap_control_plane import (
        create_browser_bootstrap,
    )
    from tools.qnap_control_plane import (
        deploy as deploy_control_plane,
    )
    from tools.qnap_profile_sync import (
        QnapError,
        connect,
        container_station,
        deploy_production,
        load_private_references,
        preflight,
    )
    from tools.qnap_provider_relay import deploy as deploy_relay
    from tools.qnap_secret_broker import deploy as deploy_secret_broker


ROOT = Path(__file__).resolve().parents[1]
DEFAULT_STATE = ROOT / ".kodi-private/qnap-images.json"
DEFAULT_STABLE_LOCK = ROOT / "manifests/locks/qnap-stable.json"
IMAGE = re.compile(
    r"^ghcr\.io/mwodevelop/[a-z0-9-]+@sha256:[a-f0-9]{64}$"
)
WATCHDOG_IMAGE = re.compile(
    r"^ghcr\.io/mwodevelop/kodi-upstream-watchdog"
    r"@sha256:[a-f0-9]{64}$"
)
WATCHDOG_PROJECT = "qnap-upstream-watchdog"
GITHUB_OWNER = "mwoDevelop"
WATCHDOG_ROOT = PurePosixPath(
    "/share/CACHEDEV3_DATA/.mwodevelop-services/upstream-watchdog-v1"
)


class ImageError(RuntimeError):
    pass


@dataclass(frozen=True)
class Service:
    name: str
    image: str
    repository: Path
    dockerfile: Path
    platforms: tuple[str, ...]
    build_revision: bool = False
    github_repository: str = ""
    github_workflow: str = ""
    github_tag: str = "sha-{commit}"
    github_inputs: tuple[tuple[str, str], ...] = ()
    input_paths: tuple[str, ...] = ()


def services(profile_sync_repository=None, control_plane_repository=None):
    profile = Path(
        profile_sync_repository
        or ROOT.parent / "kodi-profile-sync-server"
    ).expanduser().resolve()
    control_plane = Path(
        control_plane_repository
        or ROOT.parent / "kodi-control-plane"
    ).expanduser().resolve()
    return {
        "control-plane": Service(
            "control-plane",
            "ghcr.io/mwodevelop/kodi-control-plane",
            control_plane,
            Path("Dockerfile"),
            ("linux/amd64", "linux/arm/v7"),
            True,
            "mwoDevelop/kodi-control-plane",
            "container.yml",
            "sha-{commit}",
            (("publish_rc", "true"),),
            ("Dockerfile", "pyproject.toml", "README.md", "src"),
        ),
        "profile-sync": Service(
            "profile-sync",
            "ghcr.io/mwodevelop/kodi-profile-sync-server",
            profile,
            Path("Dockerfile"),
            ("linux/amd64", "linux/arm/v7"),
            True,
            "mwoDevelop/kodi-profile-sync-server",
            "container.yml",
            "sha-{commit}",
            (("publish_rc", "true"),),
            ("Dockerfile", "pyproject.toml", "README.md", "src"),
        ),
        "secret-broker": Service(
            "secret-broker",
            "ghcr.io/mwodevelop/kodi-secret-broker",
            ROOT,
            Path("secret-broker/Dockerfile"),
            ("linux/amd64", "linux/arm/v7"),
            False,
            "mwoDevelop/kodi",
            "build-secret-broker.yml",
            "{commit}",
            input_paths=(
                "secret-broker/Dockerfile",
                "secret-broker/pyproject.toml",
                "secret-broker/src",
            ),
        ),
        "provider-relay": Service(
            "provider-relay",
            "ghcr.io/mwodevelop/mwoscrapers-relay",
            ROOT / "mwoscrapers",
            Path("relay/Dockerfile"),
            ("linux/amd64", "linux/arm/v7"),
            True,
            "mwoDevelop/script.module.mwoscrapers",
            "relay-image.yml",
            input_paths=("relay/Dockerfile", "relay/mwoscrapers_relay"),
        ),
        "upstream-watchdog": Service(
            "upstream-watchdog",
            "ghcr.io/mwodevelop/kodi-upstream-watchdog",
            ROOT,
            Path("deploy/qnap-upstream-watchdog/Dockerfile"),
            ("linux/amd64", "linux/arm64", "linux/arm/v7"),
            False,
            "mwoDevelop/kodi",
            "build-upstream-watchdog.yml",
            "{commit}",
            input_paths=(
                "deploy/qnap-upstream-watchdog/Dockerfile",
                "tools/upstream_watchdog.py",
                "manifests/upstream-watchdog.json",
            ),
        ),
    }


def _run(
    argv,
    *,
    cwd=None,
    input_text=None,
    capture=True,
    check=True,
    env=None,
):
    return subprocess.run(
        [str(item) for item in argv],
        cwd=cwd,
        input=input_text,
        text=True,
        capture_output=capture,
        check=check,
        env=env,
    )


def _git(repository, *args):
    return _run(("git", "-C", repository, *args)).stdout.strip()


def source_identity(service, require_clean=True):
    if not service.repository.is_dir():
        raise ImageError(
            "%s source repository does not exist: %s"
            % (service.name, service.repository)
        )
    if not (service.repository / service.dockerfile).is_file():
        raise ImageError("%s Dockerfile is missing" % service.name)
    commit = _git(service.repository, "rev-parse", "HEAD")
    dirty = bool(
        _git(service.repository, "status", "--porcelain", "--untracked-files=all")
    )
    if require_clean and dirty:
        raise ImageError(
            "%s source repository is dirty; commit the exact build input first"
            % service.name
        )
    return {"commit": commit, "dirty": dirty}


def source_commit_is_ancestor(service, commit):
    """Return whether an approved source commit belongs to the current history."""
    exists = _run(
        ("git", "-C", service.repository, "cat-file", "-e", commit + "^{commit}"),
        check=False,
    )
    if exists.returncode:
        return False
    ancestor = _run(
        (
            "git",
            "-C",
            service.repository,
            "merge-base",
            "--is-ancestor",
            commit,
            "HEAD",
        ),
        check=False,
    )
    return ancestor.returncode == 0


def source_input_sha256(service, commit=None):
    """Hash exact tracked build inputs and build policy at an exact commit."""
    identity = source_identity(service, require_clean=False)
    commit = commit or identity["commit"]
    if not re.fullmatch(r"[0-9a-f]{40}", commit):
        raise ImageError("source commit is not exact")
    if not service.input_paths:
        raise ImageError("service has no declared build inputs: %s" % service.name)
    tree = subprocess.run(
        (
            "git",
            "-C",
            str(service.repository),
            "ls-tree",
            "-r",
            commit,
            "--",
            *service.input_paths,
        ),
        check=True,
        capture_output=True,
        text=True,
    ).stdout.encode("utf-8")
    if not tree:
        raise ImageError("declared build inputs did not resolve to tracked files")
    policy = json.dumps(
        {
            "dockerfile": str(service.dockerfile),
            "platforms": list(service.platforms),
            "build_revision": service.build_revision,
            "input_paths": list(service.input_paths),
        },
        sort_keys=True,
        separators=(",", ":"),
    ).encode("utf-8")
    return hashlib.sha256(policy + b"\0" + tree).hexdigest()


def ensure_builder(builder, dry_run=False):
    inspect = _run(
        ("docker", "buildx", "inspect", builder),
        check=False,
    )
    if inspect.returncode:
        if dry_run:
            return
        _run(
            (
                "docker",
                "buildx",
                "create",
                "--name",
                builder,
                "--driver",
                "docker-container",
            ),
            capture=False,
        )
    if not dry_run:
        _run(
            ("docker", "buildx", "inspect", builder, "--bootstrap"),
            capture=False,
        )


def login_ghcr(dry_run=False):
    if dry_run:
        return
    username = _run(("gh", "api", "user", "--jq", ".login")).stdout.strip()
    token = _run(("gh", "auth", "token")).stdout
    if not username or not token.strip():
        raise ImageError("GitHub CLI did not provide GHCR credentials")
    _run(
        (
            "docker",
            "login",
            "ghcr.io",
            "--username",
            username,
            "--password-stdin",
        ),
        input_text=token,
        capture=False,
    )


def build(service, builder, dry_run=False):
    identity = source_identity(service, require_clean=not dry_run)
    tag = "%s:sha-%s" % (service.image, identity["commit"])
    command = [
        "docker",
        "buildx",
        "build",
        "--builder",
        builder,
        "--file",
        str(service.repository / service.dockerfile),
        "--platform",
        ",".join(service.platforms),
        "--provenance=mode=max",
        "--sbom=true",
        "--push",
        "--tag",
        tag,
    ]
    if service.build_revision:
        command.extend(
            ("--build-arg", "BUILD_REVISION=git:%s" % identity["commit"])
        )
    if dry_run:
        return {
            "command": command + [str(service.repository)],
            "image": service.image,
            "source_commit": identity["commit"],
            "source_dirty": identity["dirty"],
            "tag": tag,
        }
    with tempfile.NamedTemporaryFile(
        prefix="qnap-image-", suffix=".json", delete=False
    ) as handle:
        metadata = Path(handle.name)
    try:
        _run(
            (*command, "--metadata-file", metadata, service.repository),
            capture=False,
        )
        document = json.loads(metadata.read_text(encoding="utf-8"))
        digest = document.get("containerimage.digest")
    finally:
        metadata.unlink(missing_ok=True)
    if not isinstance(digest, str) or not re.fullmatch(
        r"sha256:[a-f0-9]{64}", digest
    ):
        raise ImageError("Buildx did not return an immutable image digest")
    reference = "%s@%s" % (service.image, digest)
    verify_platforms(reference, service.platforms)
    return {
        "built_at": dt.datetime.now(dt.timezone.utc).isoformat(),
        "image": reference,
        "source_commit": identity["commit"],
        "tag": tag,
    }


def _remote_ref(service, commit):
    upstream = _run(
        (
            "git",
            "-C",
            service.repository,
            "rev-parse",
            "--abbrev-ref",
            "--symbolic-full-name",
            "@{upstream}",
        ),
        check=False,
    )
    candidates = []
    if upstream.returncode == 0 and upstream.stdout.strip().startswith(
        "origin/"
    ):
        candidates.append(upstream.stdout.strip().removeprefix("origin/"))
    containing = _run(
        (
            "git",
            "-C",
            service.repository,
            "for-each-ref",
            "--format=%(refname:short)",
            "--contains",
            commit,
            "refs/remotes/origin",
        )
    ).stdout.splitlines()
    candidates.extend(
        item.removeprefix("origin/")
        for item in containing
        if item.startswith("origin/") and item != "origin/HEAD"
    )
    for ref in dict.fromkeys(candidates):
        remote = _run(
            ("git", "ls-remote", "--exit-code", "origin", "refs/heads/" + ref),
            cwd=service.repository,
            check=False,
        )
        if remote.returncode == 0 and remote.stdout.split()[0] == commit:
            return ref
    raise ImageError(
        "%s commit is not the head of a pushed origin branch" % service.name
    )


def _workflow_run(service, commit, ref, started_at):
    command = [
        "gh",
        "workflow",
        "run",
        service.github_workflow,
        "--repo",
        service.github_repository,
        "--ref",
        ref,
    ]
    for key, value in service.github_inputs:
        command.extend(("--field", "%s=%s" % (key, value)))
    _run(command, capture=False)
    for _attempt in range(30):
        raw = _run(
            (
                "gh",
                "run",
                "list",
                "--repo",
                service.github_repository,
                "--workflow",
                service.github_workflow,
                "--event",
                "workflow_dispatch",
                "--branch",
                ref,
                "--limit",
                "10",
                "--json",
                "databaseId,headSha,createdAt,url",
            )
        ).stdout
        runs = json.loads(raw)
        matching = [
            item
            for item in runs
            if item.get("headSha") == commit
            and dt.datetime.fromisoformat(
                item["createdAt"].replace("Z", "+00:00")
            )
            >= started_at
        ]
        if matching:
            return max(matching, key=lambda item: item["databaseId"])
        time.sleep(2)
    raise ImageError("GitHub Actions run did not appear after dispatch")


def _imagetools_inspect(reference, raw=False):
    command = ["docker", "buildx", "imagetools", "inspect", reference]
    if raw:
        command.append("--raw")
    try:
        return _run(command)
    except subprocess.CalledProcessError as error:
        detail = "%s\n%s" % (error.stdout or "", error.stderr or "")
        if not (
            "error getting credentials" in detail
            and "executable file not found" in detail
        ):
            raise
        # Docker Desktop can leave a WSL config that names its Windows
        # credential helper even when the helper is absent from PATH. Images
        # published by this project are public, so retry the read-only registry
        # probe with an isolated anonymous config instead of mutating the
        # operator's Docker login state.
        with tempfile.TemporaryDirectory(prefix="kodi-docker-anonymous-") as config:
            environment = os.environ.copy()
            environment["DOCKER_CONFIG"] = config
            return _run(command, env=environment)


def _tag_digest(tag):
    output = _imagetools_inspect(tag).stdout
    match = re.search(r"^Digest:\s+(sha256:[a-f0-9]{64})$", output, re.MULTILINE)
    if not match:
        raise ImageError("could not resolve immutable digest for %s" % tag)
    return match.group(1)


def _published_reference(service, tag):
    last_error = None
    for _attempt in range(18):
        try:
            verify_platforms(tag, service.platforms)
            return "%s@%s" % (service.image, _tag_digest(tag))
        except (
            ImageError,
            json.JSONDecodeError,
            subprocess.CalledProcessError,
        ) as error:
            last_error = error
            time.sleep(5)
    raise ImageError(
        "published image did not become readable: %s (%s)"
        % (tag, last_error)
    )


def build_with_actions(service, dry_run=False, stream_progress=True):
    identity = source_identity(service, require_clean=not dry_run)
    commit = identity["commit"]
    ref = _remote_ref(service, commit)
    tag = "%s:%s" % (
        service.image,
        service.github_tag.format(commit=commit),
    )
    command = [
        "gh",
        "workflow",
        "run",
        service.github_workflow,
        "--repo",
        service.github_repository,
        "--ref",
        ref,
    ]
    for key, value in service.github_inputs:
        command.extend(("--field", "%s=%s" % (key, value)))
    if dry_run:
        return {
            "command": command,
            "image": service.image,
            "source_commit": commit,
            "source_dirty": identity["dirty"],
            "tag": tag,
        }
    started_at = dt.datetime.now(dt.timezone.utc) - dt.timedelta(seconds=5)
    run = _workflow_run(service, commit, ref, started_at)
    _run(
        (
            "gh",
            "run",
            "watch",
            str(run["databaseId"]),
            "--repo",
            service.github_repository,
            "--exit-status",
            "--interval",
            "5",
        ),
        capture=not stream_progress,
    )
    reference = _published_reference(service, tag)
    return {
        "built_at": dt.datetime.now(dt.timezone.utc).isoformat(),
        "image": reference,
        "source_commit": commit,
        "tag": tag,
        "workflow_run": run["url"],
        "workflow_run_id": str(run["databaseId"]),
    }


def verify_platforms(reference, required):
    raw = _imagetools_inspect(reference, raw=True).stdout
    document = json.loads(raw)
    observed = {
        "/".join(
            part
            for part in (
                item.get("platform", {}).get("os"),
                item.get("platform", {}).get("architecture"),
                item.get("platform", {}).get("variant"),
            )
            if part
        )
        for item in document.get("manifests", [])
        if item.get("platform", {}).get("os") != "unknown"
    }
    missing = set(required).difference(observed)
    if missing:
        raise ImageError(
            "image is missing required platforms: %s"
            % ", ".join(sorted(missing))
        )


def load_state(path):
    path = Path(path)
    if not path.is_file():
        raise ImageError("image state does not exist: %s" % path)
    document = json.loads(path.read_text(encoding="utf-8"))
    if document.get("schema") != 1 or not isinstance(
        document.get("images"), dict
    ):
        raise ImageError("invalid image state")
    for name, item in document["images"].items():
        if not isinstance(item, dict) or not IMAGE.fullmatch(
            str(item.get("image", ""))
        ):
            raise ImageError("invalid image state entry: %s" % name)
    return document


def save_state(path, images):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
    document = {"schema": 1, "images": images}
    temporary = path.with_suffix(path.suffix + ".tmp")
    temporary.write_text(
        json.dumps(document, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    temporary.chmod(0o600)
    temporary.replace(path)
    path.chmod(0o600)


def _github_identity(token):
    """Validate a GitHub API token without persisting or returning it."""
    request = Request(
        "https://api.github.com/user",
        headers={
            "Accept": "application/vnd.github+json",
            "Authorization": "Bearer " + token,
            "User-Agent": "mwoDevelop-kodi-watchdog-deploy/1",
            "X-GitHub-Api-Version": "2022-11-28",
        },
    )
    with urlopen(request, timeout=20) as response:
        document = json.load(response)
        return {
            "login": document.get("login"),
            "rate_limit": int(response.headers.get("X-RateLimit-Limit", 0)),
            "rate_remaining": int(
                response.headers.get("X-RateLimit-Remaining", 0)
            ),
            "oauth_scopes": sorted(
                item.strip()
                for item in response.headers.get("X-OAuth-Scopes", "").split(",")
                if item.strip()
            ),
        }


def watchdog_github_credentials(references):
    """Resolve a verified token for the configured GitHub account.

    ``GITHUB_PASS`` is accepted only when it is actually an API token. GitHub
    account passwords have not authenticated REST API calls since 2020. A
    matching local ``gh`` session is a migration fallback, allowing an
    existing operator login to repair the deployment without copying the
    account password into another store.
    """
    username = references.get("GITHUB_USER", "").strip()
    if not username:
        raise ImageError("GITHUB_USER is required for watchdog authentication")
    expected_logins = {username.casefold()}
    # Web sign-in accepts an account email, while REST identifies the account
    # only by login. For an email-shaped GITHUB_USER, bind the token to the
    # versioned repository owner instead of accepting an arbitrary account.
    if "@" in username:
        expected_logins.add(GITHUB_OWNER.casefold())
    candidates = []
    if references.get("GITHUB_TOKEN"):
        candidates.append(("GITHUB_TOKEN", references["GITHUB_TOKEN"]))
    password = references.get("GITHUB_PASS", "")
    if password.startswith(("ghp_", "github_pat_")):
        candidates.append(("GITHUB_PASS", password))
    try:
        local = _run(
            ("gh", "auth", "token", "--hostname", "github.com")
        ).stdout.strip()
    except (FileNotFoundError, subprocess.CalledProcessError):
        local = ""
    if local:
        candidates.append(("gh-cli", local))

    seen = set()
    for source, token in candidates:
        if not token or token in seen or any(char in token for char in "\r\n"):
            continue
        seen.add(token)
        try:
            identity = _github_identity(token)
        except (HTTPError, URLError, OSError, ValueError, json.JSONDecodeError):
            continue
        if str(identity.get("login", "")).casefold() not in expected_logins:
            continue
        if identity.get("rate_limit", 0) <= 60:
            continue
        # The remediation worker performs no repository writes, but GitHub
        # classifies workflow_dispatch as the classic PAT ``workflow`` scope.
        # Fine-grained tokens do not expose their permissions in response
        # headers, so reject them here instead of deploying an unprovable
        # capability that would fail only after a missed schedule.
        if "workflow" not in set(identity.get("oauth_scopes", [])):
            continue
        return {
            "token": token,
            "source": source,
            "login": identity["login"],
            "rate_limit": identity["rate_limit"],
            "rate_remaining": identity["rate_remaining"],
            "capability": "workflow_dispatch",
        }
    raise ImageError(
        "no authenticated GitHub token with workflow_dispatch capability "
        "matches GITHUB_USER; gh must hold a valid login with workflow scope"
    )


def _watchdog_environment(image, token):
    if not WATCHDOG_IMAGE.fullmatch(image):
        raise ImageError("watchdog image must use its immutable GHCR digest")
    if not token or any(char in token for char in "\r\n"):
        raise ImageError("watchdog GitHub token is missing or invalid")
    return (
        "UPSTREAM_WATCHDOG_IMAGE=%s\n"
        "UPSTREAM_WATCHDOG_GITHUB_TOKEN=%s\n"
        "UPSTREAM_WATCHDOG_TLS_CERT=%s\n"
        "UPSTREAM_WATCHDOG_TLS_KEY=%s\n"
        "UPSTREAM_WATCHDOG_CLIENT_CA=%s\n"
        % (
            image,
            token,
            WATCHDOG_ROOT / "config/server.crt",
            WATCHDOG_ROOT / "config/server.key",
            WATCHDOG_ROOT / "config/clients-ca.crt",
        )
    )


def _watchdog_private_files(private):
    private = Path(private)
    files = {
        "server_certificate": private / "server.crt",
        "server_key": private / "server.key",
        "client_ca": private / "clients-ca.crt",
    }
    for name, path in files.items():
        try:
            metadata = path.lstat()
        except OSError as error:
            raise ImageError("Watchdog observer credential is missing") from error
        if not stat.S_ISREG(metadata.st_mode) or path.is_symlink():
            raise ImageError("Watchdog observer credential must be a regular file")
        if name == "server_key" and stat.S_IMODE(metadata.st_mode) & 0o077:
            raise ImageError("Watchdog observer key permissions are too broad")
    try:
        context = ssl.SSLContext(ssl.PROTOCOL_TLS_SERVER)
        context.load_cert_chain(files["server_certificate"], files["server_key"])
    except (OSError, ssl.SSLError) as error:
        raise ImageError("Watchdog observer certificate and key differ") from error
    verified = subprocess.run(
        (
            "openssl",
            "verify",
            "-purpose",
            "sslserver",
            "-CAfile",
            str(files["client_ca"]),
            str(files["server_certificate"]),
        ),
        capture_output=True,
        check=False,
        text=True,
    )
    if verified.returncode != 0:
        raise ImageError("Watchdog observer certificate trust chain differs")
    return files


def _watchdog_compose(docker):
    return (
        docker
        + " compose --project-name "
        + WATCHDOG_PROJECT
        + " --env-file "
        + shlex.quote(str(WATCHDOG_ROOT / "watchdog.env"))
        + " -f "
        + shlex.quote(str(WATCHDOG_ROOT / "compose.yaml"))
    )


def validate_watchdog_policy(document):
    if document.get("name") != WATCHDOG_PROJECT:
        raise ImageError("unexpected watchdog Compose project")
    services = document.get("services")
    if not isinstance(services, dict) or set(services) != {
        "upstream-watchdog"
    }:
        raise ImageError("watchdog Compose service set differs")
    service = services["upstream-watchdog"]
    if not WATCHDOG_IMAGE.fullmatch(str(service.get("image", ""))):
        raise ImageError("watchdog Compose image is not immutable")
    if service.get("read_only") is not True or service.get("init") is not True:
        raise ImageError("watchdog filesystem or init policy differs")
    if service.get("restart") != "unless-stopped":
        raise ImageError("watchdog restart policy differs")
    if set(service.get("cap_drop", [])) != {"ALL"}:
        raise ImageError("watchdog capabilities policy differs")
    if "no-new-privileges:true" not in service.get("security_opt", []):
        raise ImageError("watchdog no-new-privileges policy differs")
    if service.get("ports"):
        raise ImageError("watchdog must not publish ports")
    volumes = service.get("volumes", [])
    if not isinstance(volumes, list) or any(
        not isinstance(item, dict) for item in volumes
    ):
        raise ImageError("watchdog observer mount set differs")
    expected_targets = {
        "/run/watchdog/tls/server.crt",
        "/run/watchdog/tls/server.key",
        "/run/watchdog/tls/clients-ca.crt",
    }
    by_target = {item.get("target"): item for item in volumes}
    if set(by_target) != expected_targets or len(volumes) != len(expected_targets):
        raise ImageError("watchdog observer mount set differs")
    for item in by_target.values():
        source = str(item.get("source", ""))
        if (
            item.get("type") != "bind"
            or item.get("read_only") is not True
            or not source.startswith(str(WATCHDOG_ROOT / "config"))
        ):
            raise ImageError("watchdog observer mount policy differs")
    environment = service.get("environment", {})
    if not isinstance(environment, dict) or not environment.get("GITHUB_TOKEN"):
        raise ImageError("watchdog authenticated GitHub API policy differs")
    if int(service.get("mem_limit", 0)) != 64 * 1024 * 1024:
        raise ImageError("watchdog memory limit differs")
    if int(service.get("pids_limit", 0)) != 32:
        raise ImageError("watchdog PID limit differs")
    if str(service.get("user")) != "10001:10001":
        raise ImageError("watchdog user differs")
    networks = service.get("networks", {})
    if set(networks) != {"control-plane"}:
        raise ImageError("watchdog private network differs")
    configured = document.get("networks", {}).get("control-plane", {})
    if configured.get("name") != "mwodevelop-control" or configured.get("external") is not True:
        raise ImageError("watchdog shared network differs")
    command = " ".join(str(item) for item in service.get("command", []))
    for required in (
        "--listen 0.0.0.0",
        "--port 9445",
        "--tls-cert /run/watchdog/tls/server.crt",
        "--client-ca /run/watchdog/tls/clients-ca.crt",
        "--interval-seconds 900",
        "--remediate",
    ):
        if required not in command:
            raise ImageError("watchdog observer command policy differs")
    health = " ".join(
        str(item) for item in service.get("healthcheck", {}).get("test", [])
    )
    if not all(
        item in health
        for item in (
            "tools/upstream_watchdog.py health",
            "--status /run/watchdog/status.json",
        )
    ):
        raise ImageError("watchdog healthcheck does not verify observer readiness")
    return {
        "image": service["image"],
        "project": document["name"],
    }


def watchdog_workflow_keys(repository):
    manifest_path = Path(repository) / "manifests/upstream-watchdog.json"
    document = json.loads(manifest_path.read_text(encoding="utf-8"))
    workflows = document.get("workflows")
    if document.get("schema") != 2 or not isinstance(workflows, list):
        raise ImageError("watchdog manifest contract is invalid")
    keys = {
        (item.get("repository"), item.get("workflow"))
        for item in workflows
        if isinstance(item, dict)
    }
    if len(keys) != len(workflows) or any(not all(key) for key in keys):
        raise ImageError("watchdog manifest contains invalid or duplicate workflows")
    return keys


def deploy_watchdog(session, repository, image, references, private):
    report = preflight(session)
    if report["raid"] != {"array": "UU", "recovery_percent": None}:
        raise ImageError("watchdog deployment requires healthy RAID [UU]")
    github = watchdog_github_credentials(references)
    private_files = _watchdog_private_files(private)
    environment = _watchdog_environment(image, github["token"])
    _install, docker = container_station(session)
    compose = _watchdog_compose(docker)
    deployment = Path(repository) / "deploy/qnap-upstream-watchdog"
    expected_workflows = watchdog_workflow_keys(repository)
    compose_text = (deployment / "compose.yaml").read_text(encoding="utf-8")
    prior_compose = session.execute(
        "cat " + shlex.quote(str(WATCHDOG_ROOT / "compose.yaml")),
        allowed=(0, 1),
    )
    prior_environment = session.execute(
        "cat " + shlex.quote(str(WATCHDOG_ROOT / "watchdog.env")),
        allowed=(0, 1),
    )
    session.execute(
        "mkdir -p "
        + shlex.quote(str(WATCHDOG_ROOT))
        + " "
        + shlex.quote(str(WATCHDOG_ROOT / "config"))
    )
    try:
        session.upload_text(
            str(WATCHDOG_ROOT / "compose.yaml"), compose_text, 0o600
        )
        session.upload_text(
            str(WATCHDOG_ROOT / "watchdog.env"),
            environment,
            0o600,
        )
        for destination, (source, mode) in {
            WATCHDOG_ROOT / "config/server.crt": (
                private_files["server_certificate"],
                0o400,
            ),
            WATCHDOG_ROOT / "config/server.key": (
                private_files["server_key"],
                0o400,
            ),
            WATCHDOG_ROOT / "config/clients-ca.crt": (
                private_files["client_ca"],
                0o400,
            ),
        }.items():
            session.upload_text(
                str(destination), source.read_text(encoding="utf-8"), mode
            )
        session.execute(
            "chown -R 10001:10001 "
            + shlex.quote(str(WATCHDOG_ROOT / "config"))
        )
        session.execute(
            docker
            + " network inspect mwodevelop-control >/dev/null 2>&1 || "
            + docker
            + " network create --driver bridge --label io.mwodevelop.managed=true "
            + "mwodevelop-control >/dev/null"
        )
        rendered = json.loads(
            session.execute(
                compose + " config --format json --no-normalize"
            )
        )
        policy = validate_watchdog_policy(rendered)
        session.execute(compose + " up -d --pull always", timeout=300)
        status = None
        for _attempt in range(18):
            raw = session.execute(
                docker
                + " exec qnap-upstream-watchdog-upstream-watchdog-1 "
                + "cat /run/watchdog/status.json",
                allowed=(0, 1),
                timeout=10,
            )
            if raw:
                candidate = json.loads(raw)
                observed_workflows = {
                    (item.get("repository"), item.get("workflow"))
                    for item in candidate.get("workflows", [])
                    if isinstance(item, dict)
                }
                if (
                    candidate.get("schema") == 2
                    and candidate.get("observer_ready") is True
                    and candidate.get("collection_state") == "READY"
                    and candidate.get("monitored_state")
                    in {"HEALTHY", "FAILED"}
                    and observed_workflows == expected_workflows
                    and len(candidate.get("workflows", []))
                    == len(expected_workflows)
                ):
                    status = candidate
                    break
            time.sleep(5)
        if status is None:
            raise ImageError(
                "watchdog did not publish the exact manifest workflow set"
            )
    except Exception:
        if prior_compose and prior_environment:
            session.upload_text(
                str(WATCHDOG_ROOT / "compose.yaml"), prior_compose + "\n", 0o600
            )
            session.upload_text(
                str(WATCHDOG_ROOT / "watchdog.env"),
                prior_environment + "\n",
                0o600,
            )
            session.execute(compose + " up -d", allowed=(0, 1), timeout=300)
        raise
    return {
        "policy": policy,
        "github_auth": {
            key: github[key]
            for key in (
                "source",
                "login",
                "rate_limit",
                "rate_remaining",
                "capability",
            )
        },
        # Compatibility alias retained for one N/N+1 generation.
        "runtime_healthy": status["healthy"],
        "observer_ready": status["observer_ready"],
        "collection_state": status["collection_state"],
        "monitored_state": status["monitored_state"],
        "workflows": len(status["workflows"]),
        "workflow_failures": [
            f'{item["repository"]}/{item["workflow"]}'
            for item in status["workflows"]
            if item.get("monitored_state") == "FAILED"
        ],
        "workflow_unknown": [
            f'{item["repository"]}/{item["workflow"]}'
            for item in status["workflows"]
            if item.get("monitored_state") == "UNKNOWN"
        ],
    }


def deploy(service_name, image, references, repository=ROOT):
    if not IMAGE.fullmatch(image):
        raise ImageError("deployment image must use an immutable GHCR digest")
    private_references = load_private_references(Path(repository) / references)
    host_ip = private_references.get("QNAP_HOST", "")
    try:
        address = ipaddress.ip_address(host_ip)
    except ValueError as error:
        raise ImageError("QNAP_HOST must be an IP address") from error
    if not address.is_private or address.is_loopback:
        raise ImageError("QNAP_HOST must be a private non-loopback address")
    session = connect(repository, references)
    try:
        if service_name == "profile-sync":
            private = Path(repository) / ".kodi-private/profile-sync-production"
            result = deploy_production(
                session,
                repository,
                image,
                host_ip,
                private / "key-registry.json",
                private / "tls/server.crt",
                private / "tls/server.key",
                private / "tls/ca.crt",
                Path(repository)
                / ".kodi-private/secret-broker/profile-sync",
            )
        elif service_name == "provider-relay":
            result = deploy_relay(
                session,
                repository,
                image,
                "production",
                host_ip,
            )
        elif service_name == "upstream-watchdog":
            result = deploy_watchdog(
                session,
                repository,
                image,
                private_references,
                Path(repository) / ".kodi-private/control-plane/watchdog",
            )
        elif service_name == "control-plane":
            github = watchdog_github_credentials(private_references)
            result = deploy_control_plane(
                session,
                repository,
                image,
                host_ip,
                Path(repository) / ".kodi-private/control-plane",
                Path(repository) / ".kodi-private/secret-broker/control-plane",
                Path(repository) / ".kodi-private/control-plane/watchdog",
                github["token"],
                build_inventory(private_references),
            )
        elif service_name == "secret-broker":
            result = deploy_secret_broker(
                session,
                repository,
                image,
                Path(repository) / ".kodi-private/secret-broker",
            )
        else:
            raise ImageError("unknown service: %s" % service_name)
    finally:
        session.close()
    return result


def status(references, repository=ROOT):
    session = connect(repository, references)
    try:
        _install, docker = container_station(session)
        rows = {}
        for name, container in (
            ("control-plane", "qnap-control-plane-control-plane-1"),
            (
                "control-plane-authz",
                "qnap-control-plane-control-plane-authz-1",
            ),
            (
                "control-plane-web",
                "qnap-control-plane-control-plane-web-1",
            ),
            ("profile-sync", "qnap-profile-sync-profile-sync-1"),
            ("secret-broker", "qnap-secret-broker-secret-broker-1"),
            ("provider-relay", "qnap-provider-relay-provider-relay-1"),
            (
                "upstream-watchdog",
                "qnap-upstream-watchdog-upstream-watchdog-1",
            ),
        ):
            raw = session.execute(
                docker + " inspect " + shlex.quote(container), allowed=(0, 1)
            )
            if not raw:
                rows[name] = {"status": "missing"}
                continue
            try:
                inspected = json.loads(raw)
            except json.JSONDecodeError:
                rows[name] = {"status": "invalid", "runtime_status": "invalid"}
                continue
            if not isinstance(inspected, list) or not inspected:
                rows[name] = {"status": "missing"}
                continue
            item = inspected[0]
            rows[name] = {
                "health": item["State"].get("Health", {}).get("Status"),
                "image": item["Config"]["Image"],
                "started_at": item["State"]["StartedAt"],
                "status": item["State"]["Status"],
            }
        watchdog = rows["upstream-watchdog"]
        if watchdog.get("status") != "missing":
            raw = session.execute(
                docker
                + " exec qnap-upstream-watchdog-upstream-watchdog-1 "
                + "cat /run/watchdog/status.json",
                allowed=(0, 1),
                timeout=10,
            )
            if raw:
                try:
                    document = json.loads(raw)
                except json.JSONDecodeError:
                    watchdog["runtime_status"] = "invalid"
                else:
                    workflows = document.get("workflows", [])
                    if document.get("schema") == 2 and isinstance(
                        workflows, list
                    ):
                        extended = all(
                            field in document
                            for field in (
                                "observer_ready",
                                "collection_state",
                                "monitored_state",
                            )
                        )
                        watchdog.update(
                            {
                                "checked_at": document.get("checked_at"),
                                # Compatibility alias for schema 2 N/N+1.
                                "runtime_healthy": document.get("healthy"),
                                "observer_ready": (
                                    document.get("observer_ready")
                                    if extended
                                    else True
                                ),
                                "collection_state": (
                                    document.get("collection_state")
                                    if extended
                                    else "READY"
                                ),
                                "monitored_state": (
                                    document.get("monitored_state")
                                    if extended
                                    else (
                                        "HEALTHY"
                                        if document.get("healthy") is True
                                        else "FAILED"
                                    )
                                ),
                                "workflow_failures": [
                                    f'{item["repository"]}/{item["workflow"]}'
                                    for item in workflows
                                    if item.get("monitored_state") == "FAILED"
                                    or (
                                        "monitored_state" not in item
                                        and item.get("healthy") is False
                                    )
                                ],
                                "workflow_unknown": [
                                    f'{item["repository"]}/{item["workflow"]}'
                                    for item in workflows
                                    if item.get("monitored_state") == "UNKNOWN"
                                ],
                                "workflows": len(workflows),
                            }
                        )
                    else:
                        watchdog["runtime_status"] = "invalid"
            else:
                watchdog["runtime_status"] = "not-ready"
        return rows
    finally:
        session.close()


def service_is_healthy(item):
    """Return whether a runtime row is ready for normal operation.

    The watchdog performs a relatively expensive Docker health check every five
    minutes.  Direct runtime evidence is already available sooner, so accept
    that evidence only while Docker still reports the initial ``starting``
    state.  An explicit Docker ``unhealthy`` state always remains a failure.
    """
    if item.get("status") != "running":
        return False
    health = item.get("health")
    if health in {None, "healthy"}:
        return True
    return health == "starting" and (
        item.get("observer_ready") is True
        or item.get("runtime_healthy") is True
    )


def service_is_operational(name, item):
    """Accept a watchdog security alert as evidence of a running monitor.

    ``healthy`` means that every monitored workflow is healthy.  A watchdog
    that successfully writes a current, structured list of failing workflows
    is operational even though Docker correctly marks the business result as
    unhealthy.  No other service receives this exception.
    """
    if service_is_healthy(item):
        return True
    if name != "upstream-watchdog":
        return False
    if item.get("status") != "running":
        return False
    if "observer_ready" in item:
        return (
            item.get("health") != "unhealthy"
            and item.get("observer_ready") is True
            and item.get("collection_state") == "READY"
            and item.get("monitored_state") in {"HEALTHY", "FAILED"}
        )
    # Legacy schema 2 compatibility: a complete structured failure report is
    # evidence that the older observer ran, even though its healthcheck coupled
    # Docker health to the monitored business result.
    failures = item.get("workflow_failures")
    return (
        item.get("runtime_healthy") is False
        and isinstance(item.get("checked_at"), str)
        and bool(item["checked_at"])
        and isinstance(failures, list)
        and bool(failures)
    )


def selected_services(values, available):
    values = values or ["all"]
    if "all" in values:
        if len(values) != 1:
            raise ImageError("all cannot be combined with named services")
        return list(available)
    unknown = sorted(set(values).difference(available))
    if unknown:
        raise ImageError("unknown services: %s" % ", ".join(unknown))
    return list(dict.fromkeys(values))


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--references", default=".env")
    parser.add_argument("--state", default=str(DEFAULT_STATE))
    parser.add_argument(
        "--profile-sync-repository",
        default=str(ROOT.parent / "kodi-profile-sync-server"),
    )
    parser.add_argument(
        "--control-plane-repository",
        default=str(ROOT.parent / "kodi-control-plane"),
    )
    sub = parser.add_subparsers(dest="command", required=True)
    for command in ("build", "update"):
        item = sub.add_parser(command)
        item.add_argument("services", nargs="*", default=["all"])
        item.add_argument("--builder", default="mwodevelop-kodi")
        item.add_argument(
            "--publisher",
            choices=("actions", "local"),
            default="actions",
        )
        item.add_argument("--dry-run", action="store_true")
        if command == "update":
            item.add_argument("--allow-unpromoted", action="store_true")
    deploy_parser = sub.add_parser("deploy")
    deploy_parser.add_argument("services", nargs="*", default=["all"])
    deploy_parser.add_argument("--lock", default=str(DEFAULT_STABLE_LOCK))
    deploy_parser.add_argument("--dry-run", action="store_true")
    deploy_parser.add_argument(
        "--reconcile",
        action="store_true",
        help="reapply selected stable runtime configuration even when image digest matches",
    )
    sub.add_parser("status")
    bootstrap_parser = sub.add_parser("browser-bootstrap")
    bootstrap_parser.add_argument(
        "--reset",
        action="store_true",
        help="invalidate the current operator and reopen one-time bootstrap",
    )
    args = parser.parse_args()
    try:
        if args.command == "status":
            result = {"schema": 1, "services": status(args.references)}
        elif args.command == "browser-bootstrap":
            session = connect(ROOT, args.references)
            try:
                result = {
                    "schema": 1,
                    "bootstrap": create_browser_bootstrap(session, args.reset),
                }
            finally:
                session.close()
        else:
            available = services(
                args.profile_sync_repository,
                args.control_plane_repository,
            )
            if args.command == "deploy":
                try:
                    from tools.qnap_lock import deploy as deploy_stable
                    from tools.qnap_lock import load_lock
                except ModuleNotFoundError:
                    from qnap_lock import deploy as deploy_stable
                    from qnap_lock import load_lock

                lock = load_lock(args.lock)
                names = (
                    list(lock["services"])
                    if not args.services or args.services == ["all"]
                    else selected_services(args.services, available)
                )
                missing_from_lock = sorted(set(names).difference(lock["services"]))
                if missing_from_lock:
                    raise ImageError(
                        "services are not promoted in the stable lock: %s"
                        % ", ".join(missing_from_lock)
                    )
                selected = {
                    name: lock["services"][name]["image"] for name in names
                }
                if args.dry_run:
                    result = {
                        "schema": 1,
                        "deploy": selected,
                        "channel": "stable",
                        "dry_run": True,
                    }
                else:
                    result = deploy_stable(
                        args.lock,
                        args.references,
                        repository=ROOT,
                        service_names=names,
                        reconcile_services=names if args.reconcile else None,
                    )
                print(json.dumps(result, indent=2, sort_keys=True))
                return 0
            names = selected_services(args.services, available)
            if args.command in {"build", "update"}:
                if args.command == "update" and not args.allow_unpromoted:
                    raise ImageError(
                        "update deploys an unpromoted build; pass "
                        "--allow-unpromoted only for controlled candidate testing"
                    )
                if args.publisher == "local":
                    ensure_builder(args.builder, args.dry_run)
                    login_ghcr(args.dry_run)
                existing = (
                    load_state(args.state)["images"]
                    if Path(args.state).is_file()
                    else {}
                )
                built = {
                    name: (
                        build(available[name], args.builder, args.dry_run)
                        if args.publisher == "local"
                        else build_with_actions(
                            available[name], args.dry_run
                        )
                    )
                    for name in names
                }
                if args.dry_run:
                    result = {"schema": 1, "build": built, "dry_run": True}
                    print(json.dumps(result, indent=2, sort_keys=True))
                    return 0
                existing.update(built)
                save_state(args.state, existing)
            deployed = {}
            if args.command == "update":
                if args.dry_run:
                    result = {
                        "schema": 1,
                        "deploy": {
                            name: existing.get(name, {}).get("image", "missing")
                            for name in names
                        },
                        "dry_run": True,
                    }
                    print(json.dumps(result, indent=2, sort_keys=True))
                    return 0
                for name in names:
                    item = existing.get(name)
                    if not item:
                        raise ImageError("no built image state for %s" % name)
                    try:
                        deployed[name] = deploy(
                            name, item["image"], args.references
                        )
                    except Exception as error:
                        raise ImageError(
                            "%s deployment failed: %s" % (name, error)
                        ) from error
            result = {
                "schema": 1,
                **({"build": built} if args.command == "build" else {}),
                **({"deploy": deployed} if deployed else {}),
            }
    except (
        ImageError,
        QnapError,
        ValueError,
        OSError,
        subprocess.CalledProcessError,
    ) as error:
        parser.error(str(error))
    print(json.dumps(result, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
