#!/usr/bin/env python3
"""Deploy and verify the read-only QNAP Kodi Control Plane."""

from __future__ import annotations

import ipaddress
import json
import re
import shlex
import ssl
import stat
import subprocess
import time
from pathlib import Path, PurePosixPath
from urllib.error import URLError
from urllib.request import urlopen

try:
    from qnap_compose_policy import explicit_bind_targets
    from qnap_profile_sync import container_station, preflight
except ModuleNotFoundError:
    from tools.qnap_compose_policy import explicit_bind_targets
    from tools.qnap_profile_sync import container_station, preflight


IMAGE = re.compile(
    r"^ghcr\.io/mwodevelop/kodi-control-plane@sha256:[a-f0-9]{64}$"
)
PROJECT = "qnap-control-plane"
NETWORK = "mwodevelop-control"
ROOT = PurePosixPath(
    "/share/CACHEDEV3_DATA/.mwodevelop/control-plane"
)
PORT = 19443


class ControlPlaneError(RuntimeError):
    pass


def _verify_certificate(ca, certificate, purpose):
    result = subprocess.run(
        (
            "openssl",
            "verify",
            "-purpose",
            purpose,
            "-CAfile",
            str(ca),
            str(certificate),
        ),
        capture_output=True,
        text=True,
    )
    if result.returncode != 0:
        raise ControlPlaneError("certificate trust chain differs")


def _local_file(path, description, private=False):
    path = Path(path).expanduser()
    try:
        metadata = path.lstat()
    except OSError as error:
        raise ControlPlaneError(f"{description} does not exist") from error
    if not stat.S_ISREG(metadata.st_mode) or path.is_symlink():
        raise ControlPlaneError(f"{description} must be a regular non-symlink file")
    if private and stat.S_IMODE(metadata.st_mode) & 0o077:
        raise ControlPlaneError(f"{description} permissions are too broad")
    return path.resolve()


def validate_private_files(private):
    private = Path(private)
    files = {
        "tls_certificate": _local_file(
            private / "tls/server.crt", "Control Plane TLS certificate"
        ),
        "tls_key": _local_file(
            private / "tls/server.key", "Control Plane TLS key", private=True
        ),
        "client_ca": _local_file(
            private / "tls/clients-ca.crt", "Control Plane client CA"
        ),
        "operator_certificate": _local_file(
            private / "tls/operator-client.crt", "operator client certificate"
        ),
        "operator_key": _local_file(
            private / "tls/operator-client.key", "operator client key", private=True
        ),
        "checkpoint_key": _local_file(
            private / "audit-checkpoint.key", "audit checkpoint key", private=True
        ),
        "profile_ca": _local_file(
            private / "profile-sync/ca.crt", "Profile Sync CA"
        ),
        "profile_client_certificate": _local_file(
            private / "profile-sync/client.crt", "Profile Sync client certificate"
        ),
        "profile_client_key": _local_file(
            private / "profile-sync/client.key", "Profile Sync client key", private=True
        ),
    }
    if len(files["checkpoint_key"].read_bytes()) < 32:
        raise ControlPlaneError("audit checkpoint key is too short")
    try:
        server = ssl.SSLContext(ssl.PROTOCOL_TLS_SERVER)
        server.load_cert_chain(files["tls_certificate"], files["tls_key"])
        operator = ssl.SSLContext(ssl.PROTOCOL_TLS_CLIENT)
        operator.load_cert_chain(
            files["operator_certificate"], files["operator_key"]
        )
        profile = ssl.SSLContext(ssl.PROTOCOL_TLS_CLIENT)
        profile.load_cert_chain(
            files["profile_client_certificate"], files["profile_client_key"]
        )
    except (OSError, ssl.SSLError) as error:
        raise ControlPlaneError("certificate and key pair differs") from error
    try:
        _verify_certificate(
            files["client_ca"], files["tls_certificate"], "sslserver"
        )
        _verify_certificate(
            files["client_ca"], files["operator_certificate"], "sslclient"
        )
        _verify_certificate(
            files["profile_ca"],
            files["profile_client_certificate"],
            "sslclient",
        )
    except OSError as error:
        raise ControlPlaneError("OpenSSL certificate verification failed") from error
    return files


def environment(image, host_ip):
    if not IMAGE.fullmatch(str(image)):
        raise ControlPlaneError("Control Plane image must use an immutable digest")
    try:
        address = ipaddress.ip_address(host_ip)
    except ValueError as error:
        raise ControlPlaneError("Control Plane listener must be an IP address") from error
    if not address.is_private or address.is_loopback or address.is_unspecified:
        raise ControlPlaneError("Control Plane listener must be a private LAN address")
    config = ROOT / "config"
    return "\n".join(
        (
            f"CONTROL_PLANE_IMAGE={image}",
            f"CONTROL_PLANE_PORT={PORT}",
            f"CONTROL_PLANE_HOST_IP={address}",
            f"CONTROL_PLANE_PROFILE_SYNC_SERVER_NAME={address}",
            f"CONTROL_PLANE_DATA={ROOT / 'data'}",
            f"CONTROL_PLANE_TLS_CERT={config / 'tls/server.crt'}",
            f"CONTROL_PLANE_TLS_KEY={config / 'tls/server.key'}",
            f"CONTROL_PLANE_CLIENT_CA={config / 'tls/clients-ca.crt'}",
            f"CONTROL_PLANE_CHECKPOINT_KEY={config / 'audit-checkpoint.key'}",
            f"CONTROL_PLANE_PROFILE_SYNC_CA={config / 'profile-sync/ca.crt'}",
            f"CONTROL_PLANE_PROFILE_SYNC_CLIENT_CERT={config / 'profile-sync/client.crt'}",
            f"CONTROL_PLANE_PROFILE_SYNC_CLIENT_KEY={config / 'profile-sync/client.key'}",
            f"CONTROL_PLANE_SCHEDULE_CATALOG={config / 'catalogs/control-plane-schedules.json'}",
            f"CONTROL_PLANE_STATUS_SOURCE_CATALOG={config / 'catalogs/control-plane-status-sources.json'}",
            "CONTROL_PLANE_UID=10001",
            "CONTROL_PLANE_GID=10001",
            "",
        )
    )


def compose_command(docker):
    return (
        docker
        + " compose --project-name "
        + PROJECT
        + " --env-file "
        + shlex.quote(str(ROOT / "app/control-plane.env"))
        + " -f "
        + shlex.quote(str(ROOT / "app/compose.yaml"))
    )


def _absolute_bind(item, target, source_targets):
    if item.get("type") != "bind" or item.get("target") != target:
        raise ControlPlaneError(f"{target} must be a bind mount")
    source = str(item.get("source", ""))
    if not PurePosixPath(source).is_absolute() or source == "/":
        raise ControlPlaneError(f"{target} source must be a safe absolute path")
    if item.get("bind", {}).get("create_host_path") is True or target not in source_targets:
        raise ControlPlaneError(f"{target} must disable host path creation")
    return source


def validate_policy(document):
    if document.get("name") != PROJECT:
        raise ControlPlaneError("unexpected Control Plane Compose project")
    services = document.get("services")
    if not isinstance(services, dict) or set(services) != {"control-plane"}:
        raise ControlPlaneError("unexpected Control Plane service set")
    service = services["control-plane"]
    if "container_name" in service or service.get("network_mode") == "host":
        raise ControlPlaneError("fixed container name and host network are forbidden")
    if not IMAGE.fullmatch(str(service.get("image", ""))):
        raise ControlPlaneError("Control Plane image is not immutable")
    if service.get("read_only") is not True or service.get("init") is not True:
        raise ControlPlaneError("Control Plane filesystem or init policy differs")
    if service.get("restart") != "unless-stopped":
        raise ControlPlaneError("Control Plane restart policy differs")
    if set(service.get("cap_drop", [])) != {"ALL"}:
        raise ControlPlaneError("Control Plane capabilities policy differs")
    if "no-new-privileges:true" not in service.get("security_opt", []):
        raise ControlPlaneError("Control Plane no-new-privileges policy differs")
    if service.get("privileged") is True:
        raise ControlPlaneError("Control Plane must not be privileged")
    if str(service.get("user")) != "10001:10001":
        raise ControlPlaneError("Control Plane user policy differs")
    if int(service.get("mem_limit", 0)) != 256 * 1024 * 1024:
        raise ControlPlaneError("Control Plane memory limit differs")
    if int(service.get("pids_limit", 0)) != 128:
        raise ControlPlaneError("Control Plane PID limit differs")
    ports = service.get("ports", [])
    if len(ports) != 1:
        raise ControlPlaneError("only the mTLS operator API may be published")
    port = ports[0]
    if (
        int(port.get("target", 0)) != 9443
        or int(port.get("published", 0)) != PORT
        or port.get("protocol") != "tcp"
    ):
        raise ControlPlaneError("Control Plane published API differs")
    address = ipaddress.ip_address(str(port.get("host_ip", "")))
    if not address.is_private or address.is_loopback or address.is_unspecified:
        raise ControlPlaneError("Control Plane API must bind one private LAN address")
    targets = {
        "/data",
        "/run/control-plane/tls/server.crt",
        "/run/control-plane/tls/server.key",
        "/run/control-plane/tls/clients-ca.crt",
        "/run/control-plane/audit-checkpoint.key",
        "/run/control-plane/profile-sync/ca.crt",
        "/run/control-plane/profile-sync/client.crt",
        "/run/control-plane/profile-sync/client.key",
        "/run/control-plane/catalogs/schedules.json",
        "/run/control-plane/catalogs/status-sources.json",
    }
    volumes = service.get("volumes", [])
    by_target = {item.get("target"): item for item in volumes}
    if set(by_target) != targets or len(volumes) != len(targets):
        raise ControlPlaneError("Control Plane bind mount set differs")
    source_targets = set(
        document.get("_mwodevelop_source_policy", {}).get(
            "bind_create_host_path_false", []
        )
    )
    for target in targets:
        source = _absolute_bind(by_target[target], target, source_targets)
        expected_root = str(ROOT / ("data" if target == "/data" else "config"))
        if not source.startswith(expected_root):
            raise ControlPlaneError(f"{target} is outside the managed root")
        if target != "/data" and by_target[target].get("read_only") is not True:
            raise ControlPlaneError("Control Plane configuration must be read-only")
    if any("docker.sock" in str(item) for item in volumes):
        raise ControlPlaneError("Control Plane must not mount a Docker socket")
    networks = service.get("networks", {})
    if set(networks) != {"control-plane"}:
        raise ControlPlaneError("Control Plane network set differs")
    configured_network = document.get("networks", {}).get("control-plane", {})
    if configured_network.get("name") != NETWORK or configured_network.get("external") is not True:
        raise ControlPlaneError("Control Plane shared network differs")
    command = " ".join(str(item) for item in service.get("command", []))
    for required in (
        "--tls-cert /run/control-plane/tls/server.crt",
        "--client-ca /run/control-plane/tls/clients-ca.crt",
        "--checkpoint-key /run/control-plane/audit-checkpoint.key",
        "--profile-sync-host profile-sync",
        "--profile-sync-port 8767",
        "--schedule-catalog /run/control-plane/catalogs/schedules.json",
        "--status-source-catalog /run/control-plane/catalogs/status-sources.json",
    ):
        if required not in command:
            raise ControlPlaneError("Control Plane command policy differs")
    health = " ".join(
        str(item) for item in service.get("healthcheck", {}).get("test", [])
    )
    if "127.0.0.1:9080/ready" not in health:
        raise ControlPlaneError("Control Plane healthcheck must remain on loopback")
    return {
        "image": service["image"],
        "host_ip": str(address),
        "port": PORT,
        "project": PROJECT,
        "network": NETWORK,
    }


def verify_api(host_ip, ca, client_certificate, client_key, attempts=30):
    context = ssl.create_default_context(cafile=str(ca))
    context.minimum_version = ssl.TLSVersion.TLSv1_2
    context.load_cert_chain(str(client_certificate), str(client_key))
    endpoint = f"https://{host_ip}:{PORT}/v1/services"
    last_error = None
    for _attempt in range(attempts):
        try:
            with urlopen(endpoint, timeout=5, context=context) as response:
                document = json.load(response)
            if (
                document.get("schema") == 1
                and isinstance(document.get("healthy"), bool)
                and document.get("schema") in {1, 2}
                and isinstance(document.get("services"), list)
                and isinstance(document.get("audit_sequence"), int)
            ):
                return document
        except (OSError, URLError, ssl.SSLError, json.JSONDecodeError) as error:
            last_error = error
        time.sleep(2)
    raise ControlPlaneError("Control Plane mTLS API verification failed") from last_error


def deploy(session, repository, image, host_ip, private):
    report = preflight(session)
    if report["raid"] != {"array": "UU", "recovery_percent": None}:
        raise ControlPlaneError("Control Plane deployment requires healthy RAID [UU]")
    files = validate_private_files(private)
    env = environment(image, host_ip)
    _install, docker = container_station(session)
    repository = Path(repository)
    deployment = repository / "deploy/qnap-control-plane"
    compose_source = (deployment / "compose.yaml").read_text(encoding="utf-8")
    app = ROOT / "app"
    data = ROOT / "data"
    config = ROOT / "config"
    marker = app / ".managed-by-mwodevelop"
    existing = session.execute(
        "test -e " + shlex.quote(str(ROOT)) + " && printf exists", allowed=(0, 1)
    )
    if existing:
        managed = session.execute(
            "test -f " + shlex.quote(str(marker)) + " && printf managed",
            allowed=(0, 1),
        )
        if not managed:
            raise ControlPlaneError("existing Control Plane root is not managed")
    session.execute(
        "mkdir -p "
        + " ".join(
            shlex.quote(str(path))
            for path in (
                app, data, ROOT / "backups", config / "tls",
                config / "profile-sync", config / "catalogs",
            )
        )
    )
    session.upload_text(str(app / "compose.yaml"), compose_source, 0o600)
    session.upload_text(str(app / "control-plane.env"), env, 0o600)
    session.upload_text(str(marker), "kodi-control-plane-readonly-v2\n", 0o600)
    uploads = {
        config / "tls/server.crt": (files["tls_certificate"], 0o400),
        config / "tls/server.key": (files["tls_key"], 0o400),
        config / "tls/clients-ca.crt": (files["client_ca"], 0o400),
        config / "audit-checkpoint.key": (files["checkpoint_key"], 0o400),
        config / "profile-sync/ca.crt": (files["profile_ca"], 0o400),
        config / "profile-sync/client.crt": (
            files["profile_client_certificate"], 0o400
        ),
        config / "profile-sync/client.key": (files["profile_client_key"], 0o400),
        config / "catalogs/control-plane-schedules.json": (
            repository / "manifests/control-plane-schedules.json",
            0o400,
        ),
        config / "catalogs/control-plane-status-sources.json": (
            repository / "manifests/control-plane-status-sources.json",
            0o400,
        ),
    }
    for destination, (source, mode) in uploads.items():
        session.upload_text(
            str(destination), source.read_text(encoding="utf-8"), mode
        )
    session.execute(
        "chown -R 10001:10001 "
        + " ".join(
            shlex.quote(str(path))
            for path in (data, ROOT / "backups", config)
        )
    )
    session.execute(
        docker
        + " network inspect "
        + NETWORK
        + " >/dev/null 2>&1 || "
        + docker
        + " network create --driver bridge --label io.mwodevelop.managed=true "
        + NETWORK
        + " >/dev/null"
    )
    compose = compose_command(docker)
    rendered = json.loads(
        session.execute(compose + " config --format json --no-normalize")
    )
    rendered["_mwodevelop_source_policy"] = {
        "bind_create_host_path_false": sorted(
            explicit_bind_targets(compose_source)
        )
    }
    policy = validate_policy(rendered)
    session.execute(compose + " up -d --pull always", timeout=360)
    api = verify_api(
        host_ip,
        files["client_ca"],
        files["operator_certificate"],
        files["operator_key"],
    )
    return {"policy": policy, "preflight": report, "api": api}
