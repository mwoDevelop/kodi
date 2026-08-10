#!/usr/bin/env python3
"""Build, deploy and inspect all mwoDevelop Kodi QNAP images."""

from __future__ import annotations

import argparse
import datetime as dt
import ipaddress
import json
import re
import shlex
import subprocess
import tempfile
import time
from dataclasses import dataclass
from pathlib import Path, PurePosixPath

try:
    from qnap_profile_sync import (
        QnapError,
        connect,
        container_station,
        deploy_production,
        load_private_references,
        preflight,
    )
    from qnap_provider_relay import deploy as deploy_relay
except ModuleNotFoundError:
    from tools.qnap_profile_sync import (
        QnapError,
        connect,
        container_station,
        deploy_production,
        load_private_references,
        preflight,
    )
    from tools.qnap_provider_relay import deploy as deploy_relay


ROOT = Path(__file__).resolve().parents[1]
DEFAULT_STATE = ROOT / ".kodi-private/qnap-images.json"
IMAGE = re.compile(
    r"^ghcr\.io/mwodevelop/[a-z0-9-]+@sha256:[a-f0-9]{64}$"
)
WATCHDOG_IMAGE = re.compile(
    r"^ghcr\.io/mwodevelop/kodi-upstream-watchdog"
    r"@sha256:[a-f0-9]{64}$"
)
WATCHDOG_PROJECT = "qnap-upstream-watchdog"
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


def services(profile_sync_repository=None):
    profile = Path(
        profile_sync_repository
        or ROOT.parent / "kodi-profile-sync-server"
    ).expanduser().resolve()
    return {
        "profile-sync": Service(
            "profile-sync",
            "ghcr.io/mwodevelop/kodi-profile-sync-server",
            profile,
            Path("Dockerfile"),
            ("linux/amd64", "linux/arm/v7"),
            True,
        ),
        "provider-relay": Service(
            "provider-relay",
            "ghcr.io/mwodevelop/mwoscrapers-relay",
            ROOT / "mwoscrapers",
            Path("relay/Dockerfile"),
            ("linux/amd64", "linux/arm/v7"),
            True,
        ),
        "upstream-watchdog": Service(
            "upstream-watchdog",
            "ghcr.io/mwodevelop/kodi-upstream-watchdog",
            ROOT,
            Path("deploy/qnap-upstream-watchdog/Dockerfile"),
            ("linux/amd64", "linux/arm64", "linux/arm/v7"),
        ),
    }


def _run(argv, *, cwd=None, input_text=None, capture=True, check=True):
    return subprocess.run(
        [str(item) for item in argv],
        cwd=cwd,
        input=input_text,
        text=True,
        capture_output=capture,
        check=check,
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


def verify_platforms(reference, required):
    raw = _run(
        ("docker", "buildx", "imagetools", "inspect", reference, "--raw")
    ).stdout
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


def _watchdog_environment(image):
    if not WATCHDOG_IMAGE.fullmatch(image):
        raise ImageError("watchdog image must use its immutable GHCR digest")
    return "UPSTREAM_WATCHDOG_IMAGE=%s\n" % image


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
    if service.get("ports") or service.get("volumes"):
        raise ImageError("watchdog must not publish ports or mount volumes")
    if int(service.get("mem_limit", 0)) != 64 * 1024 * 1024:
        raise ImageError("watchdog memory limit differs")
    if int(service.get("pids_limit", 0)) != 32:
        raise ImageError("watchdog PID limit differs")
    if str(service.get("user")) != "10001:10001":
        raise ImageError("watchdog user differs")
    health = " ".join(
        str(item) for item in service.get("healthcheck", {}).get("test", [])
    )
    if "/run/watchdog/status.json" not in health:
        raise ImageError("watchdog healthcheck does not inspect its status")
    return {
        "image": service["image"],
        "project": document["name"],
    }


def deploy_watchdog(session, repository, image):
    report = preflight(session)
    if report["raid"] != {"array": "UU", "recovery_percent": None}:
        raise ImageError("watchdog deployment requires healthy RAID [UU]")
    _watchdog_environment(image)
    _install, docker = container_station(session)
    compose = _watchdog_compose(docker)
    deployment = Path(repository) / "deploy/qnap-upstream-watchdog"
    compose_text = (deployment / "compose.yaml").read_text(encoding="utf-8")
    prior_compose = session.execute(
        "cat " + shlex.quote(str(WATCHDOG_ROOT / "compose.yaml")),
        allowed=(0, 1),
    )
    prior_environment = session.execute(
        "cat " + shlex.quote(str(WATCHDOG_ROOT / "watchdog.env")),
        allowed=(0, 1),
    )
    session.execute("mkdir -p " + shlex.quote(str(WATCHDOG_ROOT)))
    try:
        session.upload_text(
            str(WATCHDOG_ROOT / "compose.yaml"), compose_text, 0o600
        )
        session.upload_text(
            str(WATCHDOG_ROOT / "watchdog.env"),
            _watchdog_environment(image),
            0o600,
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
                if (
                    candidate.get("schema") == 1
                    and len(candidate.get("workflows", [])) == 5
                ):
                    status = candidate
                    break
            time.sleep(5)
        if status is None:
            raise ImageError("watchdog did not publish five-workflow status")
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
        "runtime_healthy": status["healthy"],
        "workflows": len(status["workflows"]),
        "workflow_failures": [
            "%s/%s" % (item["repository"], item["workflow"])
            for item in status["workflows"]
            if not item.get("healthy")
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
            result = deploy_watchdog(session, repository, image)
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
            ("profile-sync", "qnap-profile-sync-profile-sync-1"),
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
            item = json.loads(raw)[0]
            rows[name] = {
                "health": item["State"].get("Health", {}).get("Status"),
                "image": item["Config"]["Image"],
                "started_at": item["State"]["StartedAt"],
                "status": item["State"]["Status"],
            }
        return rows
    finally:
        session.close()


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
    sub = parser.add_subparsers(dest="command", required=True)
    for command in ("build", "deploy", "update"):
        item = sub.add_parser(command)
        item.add_argument("services", nargs="*", default=["all"])
        item.add_argument("--builder", default="mwodevelop-kodi")
        item.add_argument("--dry-run", action="store_true")
    sub.add_parser("status")
    args = parser.parse_args()
    try:
        if args.command == "status":
            result = {"schema": 1, "services": status(args.references)}
        else:
            available = services(args.profile_sync_repository)
            names = selected_services(args.services, available)
            if args.command in {"build", "update"}:
                ensure_builder(args.builder, args.dry_run)
                login_ghcr(args.dry_run)
                existing = (
                    load_state(args.state)["images"]
                    if Path(args.state).is_file()
                    else {}
                )
                built = {
                    name: build(available[name], args.builder, args.dry_run)
                    for name in names
                }
                if args.dry_run:
                    result = {"schema": 1, "build": built, "dry_run": True}
                    print(json.dumps(result, indent=2, sort_keys=True))
                    return 0
                existing.update(built)
                save_state(args.state, existing)
            else:
                existing = load_state(args.state)["images"]
            deployed = {}
            if args.command in {"deploy", "update"}:
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
                    deployed[name] = deploy(
                        name, item["image"], args.references
                    )
            result = {
                "schema": 1,
                **({"build": built} if args.command == "build" else {}),
                **({"deploy": deployed} if deployed else {}),
            }
    except (ImageError, QnapError, OSError, subprocess.CalledProcessError) as error:
        parser.error(str(error))
    print(json.dumps(result, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
