#!/usr/bin/env python3
"""Render and validate the security policy of the QNAP Compose application."""

from __future__ import annotations

import argparse
import json
import re
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


class PolicyError(ValueError):
    pass


def _single(items, description):
    if not isinstance(items, list) or len(items) != 1:
        raise PolicyError("%s must contain exactly one entry" % description)
    return items[0]


def _absolute_source(volume, target):
    if volume.get("type") != "bind" or volume.get("target") != target:
        raise PolicyError("%s must be a bind mount" % target)
    source = volume.get("source")
    if (
        not isinstance(source, str)
        or not PurePosixPath(source).is_absolute()
        or source == "/"
    ):
        raise PolicyError("%s source must be a safe absolute path" % target)
    if volume.get("bind", {}).get("create_host_path") is not False:
        raise PolicyError("%s must disable automatic host path creation" % target)
    return source


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
    port = _single(service.get("ports"), "ports")
    if (
        port.get("host_ip") != "127.0.0.1"
        or int(port.get("target", 0)) != 8765
        or port.get("protocol") != "tcp"
    ):
        raise PolicyError("API must be published only on QNAP loopback")
    published = int(port.get("published", 0))
    if not 1024 <= published <= 65535:
        raise PolicyError("published port must be unprivileged")
    volumes = service.get("volumes")
    if not isinstance(volumes, list) or len(volumes) != 2:
        raise PolicyError("exactly two bind mounts are required")
    by_target = {item.get("target"): item for item in volumes}
    if set(by_target) != {"/data", KEY_TARGET}:
        raise PolicyError("unexpected bind mount target")
    data_source = _absolute_source(by_target["/data"], "/data")
    key_source = _absolute_source(by_target[KEY_TARGET], KEY_TARGET)
    if by_target[KEY_TARGET].get("read_only") is not True:
        raise PolicyError("key registry must be read-only")
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
        if labels.get(SMOKE_LABEL) == "smoke":
            raise PolicyError("production cannot carry the smoke label")
    else:
        if restart not in {"no", "none"}:
            raise PolicyError("smoke restart policy must be disabled")
        if labels.get(SMOKE_LABEL) != "smoke":
            raise PolicyError("smoke label is missing")
        if published == 18765:
            raise PolicyError("smoke cannot use the production port")
        for source in (data_source, key_source):
            if source.startswith("/share/ProfileSync"):
                raise PolicyError("smoke cannot use production paths")
            if ".mwodevelop-smoke" not in source:
                raise PolicyError("smoke path is not clearly isolated")
    return {
        "image_digest": match.group(1) if match else "placeholder",
        "mode": mode,
        "port": published,
        "project": document["name"],
        "restart": restart,
    }


def render_compose(repository, mode, env_file, docker="docker"):
    repository = Path(repository).resolve()
    deployment = repository / "deploy" / "qnap-profile-sync"
    command = [
        docker,
        "compose",
        "--project-name",
        "qnap-profile-sync" if mode == "production"
        else "qnap-profile-sync-smoke",
        "--env-file",
        str(Path(env_file).resolve()),
        "-f",
        str(deployment / "compose.yaml"),
    ]
    if mode == "smoke":
        command.extend(["-f", str(deployment / "compose.smoke.yaml")])
    command.extend(["config", "--format", "json", "--no-normalize"])
    result = subprocess.run(
        command,
        capture_output=True,
        text=True,
        check=False,
    )
    if result.returncode:
        raise PolicyError("docker compose config failed")
    try:
        return json.loads(result.stdout)
    except json.JSONDecodeError as error:
        raise PolicyError("docker compose returned invalid JSON") from error


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
