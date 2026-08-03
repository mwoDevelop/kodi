#!/usr/bin/env python3
"""Render and validate the security policy of the QNAP Compose application."""

from __future__ import annotations

import argparse
import json
import ipaddress
import re
import shutil
import subprocess
from pathlib import Path, PurePosixPath


IMAGE = re.compile(
    r"^ghcr\.io/mwodevelop/kodi-profile-sync-server@sha256:([a-f0-9]{64})$"
)
PLACEHOLDER_IMAGE = (
    "ghcr.io/mwodevelop/kodi-profile-sync-server"
    "@sha256:replace-with-release-digest"
)
SMOKE_LABEL = "io.mwodevelop.profile-sync.mode"
KEY_TARGET = "/run/profile-sync/key-registry.json"
TLS_CERT_TARGET = "/run/profile-sync/tls/server.crt"
TLS_KEY_TARGET = "/run/profile-sync/tls/server.key"


class PolicyError(ValueError):
    pass


def _single(items, description):
    if not isinstance(items, list) or len(items) != 1:
        raise PolicyError("%s must contain exactly one entry" % description)
    return items[0]


def _absolute_source(volume, target, explicit_bind_targets):
    if volume.get("type") != "bind" or volume.get("target") != target:
        raise PolicyError("%s must be a bind mount" % target)
    source = volume.get("source")
    if (
        not isinstance(source, str)
        or not PurePosixPath(source).is_absolute()
        or source == "/"
    ):
        raise PolicyError("%s source must be a safe absolute path" % target)
    rendered_value = volume.get("bind", {}).get("create_host_path")
    if rendered_value is True or target not in explicit_bind_targets:
        raise PolicyError("%s must disable automatic host path creation" % target)
    return source


def explicit_bind_targets(compose_text):
    """Audit canonical source YAML when old Compose omits explicit false."""
    targets = set()
    lines = compose_text.splitlines()
    for index, line in enumerate(lines):
        if line != "      - type: bind":
            continue
        block = []
        for candidate in lines[index + 1 :]:
            if candidate.startswith("      - ") or (
                candidate and not candidate.startswith("       ")
            ):
                break
            block.append(candidate)
        target = next(
            (
                item.removeprefix("        target: ").strip()
                for item in block
                if item.startswith("        target: ")
            ),
            None,
        )
        if (
            target
            and "        bind:" in block
            and "          create_host_path: false" in block
        ):
            targets.add(target)
    return targets


def validate_policy(document, mode, allow_placeholder=False):
    if mode not in {"production", "smoke"}:
        raise PolicyError("unsupported deployment mode")
    if document.get("name") != (
        "qnap-profile-sync" if mode == "production"
        else "qnap-profile-sync-smoke"
    ):
        raise PolicyError("unexpected Compose project name")
    services = document.get("services")
    if not isinstance(services, dict) or set(services) != {"profile-sync"}:
        raise PolicyError("Compose must contain only profile-sync")
    service = services["profile-sync"]
    if "container_name" in service:
        raise PolicyError("container_name is forbidden")
    image = service.get("image")
    match = IMAGE.fullmatch(image or "")
    if not match and not (allow_placeholder and image == PLACEHOLDER_IMAGE):
        raise PolicyError("image must use the immutable GHCR digest")
    if service.get("read_only") is not True:
        raise PolicyError("root filesystem must be read-only")
    if service.get("init") is not True:
        raise PolicyError("init must be enabled")
    if service.get("privileged") is True or service.get("network_mode") == "host":
        raise PolicyError("privileged or host-network mode is forbidden")
    if set(service.get("cap_drop", [])) != {"ALL"}:
        raise PolicyError("all capabilities must be dropped")
    if "no-new-privileges:true" not in service.get("security_opt", []):
        raise PolicyError("no-new-privileges must be enabled")
    if int(service.get("mem_limit", 0)) != 256 * 1024 * 1024:
        raise PolicyError("memory limit must be 256 MiB")
    if int(service.get("pids_limit", 0)) != 128:
        raise PolicyError("PID limit must be 128")
    user = str(service.get("user", ""))
    if not re.fullmatch(r"[1-9][0-9]*:[1-9][0-9]*", user):
        raise PolicyError("container must use a numeric non-root UID:GID")
    ports = service.get("ports")
    if not isinstance(ports, list) or len(ports) != 2:
        raise PolicyError("exactly consumer and admin ports are required")
    by_target_port = {int(item.get("target", 0)): item for item in ports}
    if set(by_target_port) != {8765, 8766}:
        raise PolicyError("only consumer and admin listeners may be published")
    port = by_target_port[8765]
    admin_port = by_target_port[8766]
    host_ip = str(port.get("host_ip", ""))
    if (
        port.get("protocol") != "tcp"
    ):
        raise PolicyError("consumer API must publish its TLS listener")
    if (
        str(admin_port.get("host_ip", "")) not in {"127.0.0.1", "::1"}
        or admin_port.get("protocol") != "tcp"
    ):
        raise PolicyError("admin API must remain loopback-only")
    try:
        parsed_host = ipaddress.ip_address(host_ip)
    except ValueError as error:
        raise PolicyError("listener must use an explicit IP address") from error
    if mode == "production" and (
        parsed_host.is_loopback or parsed_host.is_unspecified
    ):
        raise PolicyError("production listener must use an explicit non-loopback IP")
    if mode == "smoke" and not parsed_host.is_loopback:
        raise PolicyError("smoke listener must remain on loopback")
    published = int(port.get("published", 0))
    admin_published = int(admin_port.get("published", 0))
    if (
        not 1024 <= published <= 65535
        or not 1024 <= admin_published <= 65535
        or admin_published == published
    ):
        raise PolicyError("published port must be unprivileged")
    volumes = service.get("volumes")
    if not isinstance(volumes, list) or len(volumes) != 4:
        raise PolicyError("exactly four bind mount targets are required")
    by_target = {item.get("target"): item for item in volumes}
    if set(by_target) != {
        "/data",
        KEY_TARGET,
        TLS_CERT_TARGET,
        TLS_KEY_TARGET,
    }:
        raise PolicyError("unexpected bind mount target")
    explicit_bind_targets_from_source = set(
        document.get("_mwodevelop_source_policy", {}).get(
            "bind_create_host_path_false",
            [],
        )
    )
    data_source = _absolute_source(
        by_target["/data"],
        "/data",
        explicit_bind_targets_from_source,
    )
    key_source = _absolute_source(
        by_target[KEY_TARGET],
        KEY_TARGET,
        explicit_bind_targets_from_source,
    )
    tls_cert_source = _absolute_source(
        by_target[TLS_CERT_TARGET],
        TLS_CERT_TARGET,
        explicit_bind_targets_from_source,
    )
    tls_key_source = _absolute_source(
        by_target[TLS_KEY_TARGET],
        TLS_KEY_TARGET,
        explicit_bind_targets_from_source,
    )
    for target in (KEY_TARGET, TLS_CERT_TARGET, TLS_KEY_TARGET):
        if by_target[target].get("read_only") is not True:
            raise PolicyError("security configuration must be read-only")
    tmpfs = service.get("tmpfs", [])
    if len(tmpfs) != 1 or not str(tmpfs[0]).startswith("/tmp:"):
        raise PolicyError("only the bounded /tmp tmpfs is allowed")
    health = service.get("healthcheck", {}).get("test", [])
    if "/ready" not in " ".join(str(token) for token in health):
        raise PolicyError("healthcheck must use readiness")
    restart = service.get("restart")
    labels = service.get("labels", {})
    if mode == "production":
        if restart != "unless-stopped":
            raise PolicyError("production restart policy must be unless-stopped")
        if not data_source.startswith("/share/ProfileSync/data"):
            raise PolicyError("production data path is outside ProfileSync")
        if not key_source.startswith("/share/ProfileSync/config/"):
            raise PolicyError("production key registry is outside ProfileSync")
        for source in (tls_cert_source, tls_key_source):
            if not source.startswith("/share/ProfileSync/config/tls/"):
                raise PolicyError("production TLS file is outside ProfileSync")
        if labels.get(SMOKE_LABEL) == "smoke":
            raise PolicyError("production cannot carry the smoke label")
    else:
        if restart not in {"no", "none"}:
            raise PolicyError("smoke restart policy must be disabled")
        if labels.get(SMOKE_LABEL) != "smoke":
            raise PolicyError("smoke label is missing")
        if published == 18765:
            raise PolicyError("smoke cannot use the production port")
        for source in (
            data_source,
            key_source,
            tls_cert_source,
            tls_key_source,
        ):
            if source.startswith("/share/ProfileSync"):
                raise PolicyError("smoke cannot use production paths")
            if ".mwodevelop-smoke" not in source:
                raise PolicyError("smoke path is not clearly isolated")
    return {
        "image_digest": match.group(1) if match else "placeholder",
        "host_ip": host_ip,
        "mode": mode,
        "admin_port": admin_published,
        "port": published,
        "project": document["name"],
        "restart": restart,
    }


def render_compose(repository, mode, env_file, docker="docker"):
    repository = Path(repository).resolve()
    deployment = repository / "deploy" / "qnap-profile-sync"
    arguments = [
        "--project-name",
        "qnap-profile-sync" if mode == "production"
        else "qnap-profile-sync-smoke",
        "--env-file",
        str(Path(env_file).resolve()),
        "-f",
        str(deployment / "compose.yaml"),
    ]
    if mode == "smoke":
        arguments.extend(["-f", str(deployment / "compose.smoke.yaml")])
    arguments.extend(["config", "--format", "json", "--no-normalize"])
    command = [docker, "compose", *arguments]
    result = subprocess.run(
        command,
        capture_output=True,
        text=True,
        check=False,
    )
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
        raise PolicyError("docker compose config failed")
    try:
        document = json.loads(result.stdout)
    except json.JSONDecodeError as error:
        raise PolicyError("docker compose returned invalid JSON") from error
    compose_text = (deployment / "compose.yaml").read_text(encoding="utf-8")
    document["_mwodevelop_source_policy"] = {
        "bind_create_host_path_false": sorted(
            explicit_bind_targets(compose_text)
        )
    }
    return document


def main():
    repository = Path(__file__).resolve().parents[1]
    parser = argparse.ArgumentParser()
    parser.add_argument("--mode", choices=("production", "smoke"), required=True)
    parser.add_argument("--env-file", required=True)
    parser.add_argument("--docker", default="docker")
    parser.add_argument("--allow-placeholder", action="store_true")
    args = parser.parse_args()
    document = render_compose(
        repository,
        args.mode,
        args.env_file,
        docker=args.docker,
    )
    summary = validate_policy(
        document,
        args.mode,
        allow_placeholder=args.allow_placeholder,
    )
    print(json.dumps(summary, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
