#!/usr/bin/env python3
"""Policy and controlled QNAP lifecycle for the provider metadata relay."""

from __future__ import annotations

import argparse
import ipaddress
import json
import re
import shlex
import shutil
import subprocess
import time
from pathlib import Path, PurePosixPath

try:
    from qnap_profile_sync import connect, container_station, preflight
except ModuleNotFoundError:
    from tools.qnap_profile_sync import connect, container_station, preflight


IMAGE = re.compile(
    r"^ghcr\.io/mwodevelop/mwoscrapers-relay@sha256:([a-f0-9]{64})$"
)
PLACEHOLDER_IMAGE = (
    "ghcr.io/mwodevelop/mwoscrapers-relay"
    "@sha256:replace-with-release-digest"
)
RUN_ID = re.compile(r"^[a-z0-9][a-z0-9-]{2,47}$")
PROJECTS = {
    "production": "qnap-provider-relay",
    "smoke": "qnap-provider-relay-smoke",
}
PORTS = {"production": 18766, "smoke": 28766}


class RelayPolicyError(ValueError):
    pass


def _is_private_lan(address):
    return any(
        address in network
        for network in (
            ipaddress.ip_network("10.0.0.0/8"),
            ipaddress.ip_network("172.16.0.0/12"),
            ipaddress.ip_network("192.168.0.0/16"),
        )
    )


def validate_policy(document, mode, allow_placeholder=False):
    if mode not in PROJECTS:
        raise RelayPolicyError("unsupported relay deployment mode")
    if document.get("name") != PROJECTS[mode]:
        raise RelayPolicyError("unexpected Compose project name")
    services = document.get("services", {})
    if set(services) != {"provider-relay"}:
        raise RelayPolicyError("Compose must contain only provider-relay")
    service = services["provider-relay"]
    if "container_name" in service:
        raise RelayPolicyError("container_name is forbidden")
    image = service.get("image", "")
    match = IMAGE.fullmatch(image)
    if not match and not (allow_placeholder and image == PLACEHOLDER_IMAGE):
        raise RelayPolicyError("image must use the immutable GHCR digest")
    if service.get("read_only") is not True or service.get("init") is not True:
        raise RelayPolicyError("read-only root and init are required")
    if service.get("privileged") is True or service.get("network_mode") == "host":
        raise RelayPolicyError("privileged and host-network modes are forbidden")
    if set(service.get("cap_drop", [])) != {"ALL"}:
        raise RelayPolicyError("all capabilities must be dropped")
    if "no-new-privileges:true" not in service.get("security_opt", []):
        raise RelayPolicyError("no-new-privileges is required")
    if int(service.get("mem_limit", 0)) != 128 * 1024 * 1024:
        raise RelayPolicyError("memory limit must be 128 MiB")
    if int(service.get("pids_limit", 0)) != 64:
        raise RelayPolicyError("PID limit must be 64")
    if not re.fullmatch(
        r"[1-9][0-9]*:[1-9][0-9]*", str(service.get("user", ""))
    ):
        raise RelayPolicyError("numeric non-root UID:GID is required")
    if service.get("volumes"):
        raise RelayPolicyError("the stateless relay must not mount volumes")
    ports = service.get("ports", [])
    if len(ports) != 1:
        raise RelayPolicyError("exactly one published port is required")
    port = ports[0]
    if (
        int(port.get("target", 0)) != 8766
        or int(port.get("published", 0)) != PORTS[mode]
        or port.get("protocol") != "tcp"
    ):
        raise RelayPolicyError("unexpected relay port contract")
    try:
        bind = ipaddress.ip_address(port.get("host_ip", ""))
    except ValueError as error:
        raise RelayPolicyError("bind address must be an IP literal") from error
    if mode == "production":
        if not _is_private_lan(bind):
            raise RelayPolicyError("production bind must be a private LAN IP")
        if service.get("restart") != "unless-stopped":
            raise RelayPolicyError("production restart policy is invalid")
    else:
        if not bind.is_loopback:
            raise RelayPolicyError("smoke must bind to loopback")
        if service.get("restart") not in {"no", "none"}:
            raise RelayPolicyError("smoke restart policy must be disabled")
    if service.get("labels", {}).get(
        "io.mwodevelop.provider-relay.mode"
    ) != mode:
        raise RelayPolicyError("deployment mode label is invalid")
    environment = service.get("environment", {})
    if str(environment.get("MWO_RELAY_HOST")) != "0.0.0.0":
        raise RelayPolicyError("container listener contract changed")
    health = " ".join(
        str(item) for item in service.get("healthcheck", {}).get("test", [])
    )
    if "/health" not in health:
        raise RelayPolicyError("healthcheck must use /health")
    return {
        "bind": str(bind),
        "image_digest": match.group(1) if match else "placeholder",
        "mode": mode,
        "port": int(port["published"]),
        "project": document["name"],
    }


def render_policy(repository, mode, env_file, docker="docker"):
    compose = Path(repository) / "deploy/qnap-provider-relay/compose.yaml"
    arguments = [
        "--project-name",
        PROJECTS[mode],
        "--env-file",
        str(Path(env_file).resolve()),
        "-f",
        str(compose),
        "config",
        "--format",
        "json",
        "--no-normalize",
    ]
    command = [docker, "compose", *arguments]
    result = subprocess.run(command, capture_output=True, text=True, check=False)
    if result.returncode and docker == "docker":
        standalone = shutil.which("docker-compose")
        bundled = Path("/usr/libexec/docker/cli-plugins/docker-compose")
        if not standalone and bundled.is_file():
            standalone = str(bundled)
        if standalone:
            result = subprocess.run(
                [standalone, *arguments],
                capture_output=True,
                text=True,
                check=False,
            )
    if result.returncode:
        raise RelayPolicyError("docker compose config failed")
    try:
        return json.loads(result.stdout)
    except json.JSONDecodeError as error:
        raise RelayPolicyError("docker compose returned invalid JSON") from error


def _root(install, mode, run_id=None):
    share = PurePosixPath(install).parents[1]
    if not str(share).startswith("/share/"):
        raise RelayPolicyError("unsafe QNAP share root")
    if mode == "production":
        return share / "mwodevelop-provider-relay"
    if not run_id or not RUN_ID.fullmatch(run_id):
        raise RelayPolicyError("invalid smoke run id")
    return share / ".mwodevelop-smoke" / ("provider-relay-" + run_id)


def _compose(docker, root, mode):
    return (
        docker
        + " compose --project-name "
        + PROJECTS[mode]
        + " --env-file "
        + shlex.quote(str(root / "relay.env"))
        + " -f "
        + shlex.quote(str(root / "compose.yaml"))
    )


def _env(image, mode, bind):
    return "\n".join(
        (
            f"MWO_RELAY_IMAGE={image}",
            f"MWO_RELAY_BIND_HOST={bind}",
            f"MWO_RELAY_PORT={PORTS[mode]}",
            "MWO_RELAY_RESTART="
            + ("unless-stopped" if mode == "production" else "no"),
            f"MWO_RELAY_MODE={mode}",
            "MWO_RELAY_UID=10001",
            "MWO_RELAY_GID=10001",
            "MWO_RELAY_TIMEOUT=12",
            "MWO_RELAY_CACHE_TTL=%s" % (300 if mode == "production" else 30),
            "MWO_RELAY_CACHE_ENTRIES=%s"
            % (256 if mode == "production" else 16),
            "",
        )
    )


def status(session, mode):
    _install, docker = container_station(session)
    label = shlex.quote(
        f"label=com.docker.compose.project={PROJECTS[mode]}"
    )
    containers = session.execute(
        docker + " ps -a --filter " + label + " --format '{{.Status}}'"
    ).splitlines()
    networks = session.execute(
        docker + " network ls --filter " + label + " --format '{{.ID}}'"
    ).splitlines()
    volumes = session.execute(
        docker + " volume ls --filter " + label + " --format '{{.Name}}'"
    ).splitlines()
    return {
        "containers": len([item for item in containers if item]),
        "networks": len([item for item in networks if item]),
        "project": PROJECTS[mode],
        "states": [item for item in containers if item],
        "volumes": len([item for item in volumes if item]),
    }


def verify(session, mode, bind):
    endpoint = "127.0.0.1" if mode == "smoke" else bind
    for _attempt in range(30):
        health = session.execute(
            f"wget -qO- http://{endpoint}:{PORTS[mode]}/health",
            allowed=(0, 1, 4, 8),
            timeout=5,
        )
        if health:
            try:
                if json.loads(health).get("status") == "ok":
                    break
            except json.JSONDecodeError:
                pass
        time.sleep(2)
    else:
        raise RelayPolicyError("relay health check timed out")
    probe = (
        f"wget -qO- http://{endpoint}:{PORTS[mode]}"
        "/torrentio/stream/movie/tt1254207.json"
    )
    probe += (
        " | grep -Eq "
        + shlex.quote(
            '"streams"[[:space:]]*:[[:space:]]*'
            r"\[[[:space:]]*\{"
        )
        + " && printf nonempty"
    )
    provider_state = session.execute(probe, timeout=30)
    if provider_state != "nonempty":
        raise RelayPolicyError("relay provider smoke returned no streams")
    resources = status(session, mode)
    if resources["containers"] != 1 or resources["networks"] != 1:
        raise RelayPolicyError("relay project has unexpected resources")
    if resources["volumes"] != 0:
        raise RelayPolicyError("stateless relay created a volume")
    return {
        "health": "ok",
        "provider_metadata_nonempty": True,
        **resources,
    }


def deploy(session, repository, image, mode, bind, run_id=None):
    if not IMAGE.fullmatch(image):
        raise RelayPolicyError("relay image must use an immutable GHCR digest")
    address = ipaddress.ip_address(bind)
    if mode == "production" and not _is_private_lan(address):
        raise RelayPolicyError("production bind must be a private LAN IP")
    if mode == "smoke" and not address.is_loopback:
        raise RelayPolicyError("smoke bind must be loopback")
    report = preflight(session)
    install, docker = container_station(session)
    root = _root(install, mode, run_id)
    if mode == "smoke":
        session.execute("test ! -e " + shlex.quote(str(root)))
    session.execute("mkdir -p " + shlex.quote(str(root)))
    deployment = Path(repository) / "deploy/qnap-provider-relay"
    session.upload_text(
        str(root / "compose.yaml"),
        (deployment / "compose.yaml").read_text(encoding="utf-8"),
        0o600,
    )
    session.upload_text(str(root / "relay.env"), _env(image, mode, bind), 0o600)
    compose = _compose(docker, root, mode)
    rendered_payload = session.execute(
        compose + " config --format json --no-normalize"
    )
    rendered = json.loads(rendered_payload)
    policy = validate_policy(rendered, mode)
    try:
        session.execute(compose + " up -d --pull always", timeout=300)
        evidence = verify(session, mode, bind)
    except Exception:
        if mode == "smoke":
            destroy(session, mode, run_id)
        raise
    return {
        "evidence": evidence,
        "policy": policy,
        "preflight": report,
        "run_id": run_id,
    }


def destroy(session, mode, run_id=None):
    install, docker = container_station(session)
    root = _root(install, mode, run_id)
    exists = session.execute(
        f"test -d {shlex.quote(str(root))} && printf exists",
        allowed=(0, 1),
    )
    if exists:
        session.execute(
            _compose(docker, root, mode) + " down --remove-orphans",
            allowed=(0, 1),
            timeout=120,
        )
        session.execute("rm -rf -- " + shlex.quote(str(root)))
        session.execute(
            "rmdir " + shlex.quote(str(root.parent)), allowed=(0, 1)
        )
    remaining = status(session, mode)
    if any(remaining[key] for key in ("containers", "networks", "volumes")):
        raise RelayPolicyError("relay resources remain after cleanup")
    return {"removed": True, **remaining}


def main():
    repository = Path(__file__).resolve().parents[1]
    parser = argparse.ArgumentParser()
    parser.add_argument("--references", default=".env")
    sub = parser.add_subparsers(dest="command", required=True)
    policy = sub.add_parser("policy")
    policy.add_argument("--mode", choices=PROJECTS, required=True)
    policy.add_argument("--env-file", required=True)
    policy.add_argument("--allow-placeholder", action="store_true")
    status_parser = sub.add_parser("status")
    status_parser.add_argument("--mode", choices=PROJECTS, required=True)
    deploy_parser = sub.add_parser("deploy")
    deploy_parser.add_argument("--mode", choices=PROJECTS, required=True)
    deploy_parser.add_argument("--image", required=True)
    deploy_parser.add_argument("--bind", required=True)
    deploy_parser.add_argument("--run-id")
    destroy_parser = sub.add_parser("destroy")
    destroy_parser.add_argument("--mode", choices=PROJECTS, required=True)
    destroy_parser.add_argument("--run-id")
    args = parser.parse_args()
    if args.command == "policy":
        document = render_policy(repository, args.mode, args.env_file)
        result = validate_policy(
            document, args.mode, allow_placeholder=args.allow_placeholder
        )
    else:
        session = connect(repository, args.references)
        try:
            if args.command == "status":
                result = status(session, args.mode)
            elif args.command == "deploy":
                result = deploy(
                    session,
                    repository,
                    args.image,
                    args.mode,
                    args.bind,
                    args.run_id,
                )
            else:
                result = destroy(session, args.mode, args.run_id)
        finally:
            session.close()
    print(json.dumps(result, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
