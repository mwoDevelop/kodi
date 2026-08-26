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
BROWSER_BACKEND_PORT = 19445
BROWSER_PATH = "/control-plane/"


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
        check=False,
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


def validate_private_files(
    private, secret_broker_private=None, watchdog_private=None
):
    private = Path(private)
    broker = Path(secret_broker_private or private / "secret-broker")
    watchdog = Path(watchdog_private or private / "watchdog")
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
        "web_core_ca": _local_file(private / "web/core-ca.crt", "browser core CA"),
        "web_core_client_certificate": _local_file(
            private / "web/core-client.crt", "browser core client certificate"
        ),
        "web_core_client_key": _local_file(
            private / "web/core-client.key", "browser core client key", private=True
        ),
        "web_authz_ca": _local_file(private / "web/authz-ca.crt", "browser authz CA"),
        "web_authz_client_certificate": _local_file(
            private / "web/authz-client.crt", "browser authz client certificate"
        ),
        "web_authz_client_key": _local_file(
            private / "web/authz-client.key", "browser authz client key", private=True
        ),
        "authz_key": _local_file(
            private / "authz/aead.key", "authz AEAD key", private=True
        ),
        "authz_tls_certificate": _local_file(
            private / "authz/server.crt", "authz TLS certificate"
        ),
        "authz_tls_key": _local_file(
            private / "authz/server.key", "authz TLS key", private=True
        ),
        "authz_client_ca": _local_file(
            private / "authz/clients-ca.crt", "authz client CA"
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
        "broker_ca": _local_file(broker / "ca.crt", "Secret Broker CA"),
        "broker_client_certificate": _local_file(
            broker / "client.crt", "Secret Broker client certificate"
        ),
        "broker_client_key": _local_file(
            broker / "client.key", "Secret Broker client key", private=True
        ),
        "watchdog_ca": _local_file(watchdog / "ca.crt", "Watchdog observer CA"),
        "watchdog_client_certificate": _local_file(
            watchdog / "client.crt", "Watchdog observer client certificate"
        ),
        "watchdog_client_key": _local_file(
            watchdog / "client.key", "Watchdog observer client key", private=True
        ),
    }
    if len(files["checkpoint_key"].read_bytes()) < 32:
        raise ControlPlaneError("audit checkpoint key is too short")
    auth_key = files["authz_key"].read_text(encoding="ascii")
    if not re.fullmatch(r"[a-f0-9]{64}", auth_key):
        raise ControlPlaneError("authz AEAD key is invalid")
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
        broker_client = ssl.SSLContext(ssl.PROTOCOL_TLS_CLIENT)
        broker_client.load_cert_chain(
            files["broker_client_certificate"], files["broker_client_key"]
        )
        watchdog_client = ssl.SSLContext(ssl.PROTOCOL_TLS_CLIENT)
        watchdog_client.load_cert_chain(
            files["watchdog_client_certificate"], files["watchdog_client_key"]
        )
        web_core = ssl.SSLContext(ssl.PROTOCOL_TLS_CLIENT)
        web_core.load_cert_chain(
            files["web_core_client_certificate"], files["web_core_client_key"]
        )
        web_authz = ssl.SSLContext(ssl.PROTOCOL_TLS_CLIENT)
        web_authz.load_cert_chain(
            files["web_authz_client_certificate"], files["web_authz_client_key"]
        )
        authz_server = ssl.SSLContext(ssl.PROTOCOL_TLS_SERVER)
        authz_server.load_cert_chain(
            files["authz_tls_certificate"], files["authz_tls_key"]
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
        _verify_certificate(
            files["broker_ca"],
            files["broker_client_certificate"],
            "sslclient",
        )
        _verify_certificate(
            files["watchdog_ca"],
            files["watchdog_client_certificate"],
            "sslclient",
        )
        _verify_certificate(
            files["web_core_ca"], files["web_core_client_certificate"], "sslclient"
        )
        _verify_certificate(
            files["web_authz_ca"], files["web_authz_client_certificate"], "sslclient"
        )
        _verify_certificate(
            files["authz_client_ca"], files["authz_tls_certificate"], "sslserver"
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
            f"CONTROL_PLANE_BROWSER_BACKEND_PORT={BROWSER_BACKEND_PORT}",
            f"CONTROL_PLANE_HOST_IP={address}",
            f"CONTROL_PLANE_BROWSER_HOST={address}",
            f"CONTROL_PLANE_BROWSER_ORIGIN=https://{address}",
            "CONTROL_PLANE_BROWSER_ALLOWED_NETWORK=172.16.0.0/12",
            f"CONTROL_PLANE_FRAME_ANCESTOR=https://{address}",
            f"CONTROL_PLANE_PROFILE_SYNC_SERVER_NAME={address}",
            f"CONTROL_PLANE_DATA={ROOT / 'data'}",
            f"CONTROL_PLANE_AUTHZ_DATA={ROOT / 'authz-data'}",
            f"CONTROL_PLANE_TLS_CERT={config / 'tls/server.crt'}",
            f"CONTROL_PLANE_TLS_KEY={config / 'tls/server.key'}",
            f"CONTROL_PLANE_CLIENT_CA={config / 'tls/clients-ca.crt'}",
            f"CONTROL_PLANE_WEB_CORE_CA={config / 'web/core-ca.crt'}",
            f"CONTROL_PLANE_WEB_CORE_CLIENT_CERT={config / 'web/core-client.crt'}",
            f"CONTROL_PLANE_WEB_CORE_CLIENT_KEY={config / 'web/core-client.key'}",
            f"CONTROL_PLANE_WEB_AUTHZ_CA={config / 'web/authz-ca.crt'}",
            f"CONTROL_PLANE_WEB_AUTHZ_CLIENT_CERT={config / 'web/authz-client.crt'}",
            f"CONTROL_PLANE_WEB_AUTHZ_CLIENT_KEY={config / 'web/authz-client.key'}",
            f"CONTROL_PLANE_AUTHZ_KEY={config / 'authz/aead.key'}",
            f"CONTROL_PLANE_AUTHZ_TLS_CERT={config / 'authz/server.crt'}",
            f"CONTROL_PLANE_AUTHZ_TLS_KEY={config / 'authz/server.key'}",
            f"CONTROL_PLANE_AUTHZ_CLIENT_CA={config / 'authz/clients-ca.crt'}",
            f"CONTROL_PLANE_CHECKPOINT_KEY={config / 'audit-checkpoint.key'}",
            f"CONTROL_PLANE_PROFILE_SYNC_CA={config / 'profile-sync/ca.crt'}",
            f"CONTROL_PLANE_PROFILE_SYNC_CLIENT_CERT={config / 'profile-sync/client.crt'}",
            f"CONTROL_PLANE_PROFILE_SYNC_CLIENT_KEY={config / 'profile-sync/client.key'}",
            f"CONTROL_PLANE_SECRET_BROKER_CA={config / 'secret-broker/ca.crt'}",
            f"CONTROL_PLANE_SECRET_BROKER_CLIENT_CERT={config / 'secret-broker/client.crt'}",
            f"CONTROL_PLANE_SECRET_BROKER_CLIENT_KEY={config / 'secret-broker/client.key'}",
            f"CONTROL_PLANE_WATCHDOG_CA={config / 'watchdog/ca.crt'}",
            f"CONTROL_PLANE_WATCHDOG_CLIENT_CERT={config / 'watchdog/client.crt'}",
            f"CONTROL_PLANE_WATCHDOG_CLIENT_KEY={config / 'watchdog/client.key'}",
            f"CONTROL_PLANE_GITHUB_TOKEN={config / 'github/token'}",
            f"CONTROL_PLANE_SCHEDULE_CATALOG={config / 'catalogs/control-plane-schedules.json'}",
            f"CONTROL_PLANE_STATUS_SOURCE_CATALOG={config / 'catalogs/control-plane-status-sources.json'}",
            f"CONTROL_PLANE_DEVICE_INVENTORY={config / 'catalogs/device-inventory.json'}",
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
    expected_services = {
        "control-plane",
        "control-plane-authz",
        "control-plane-web",
    }
    if not isinstance(services, dict) or set(services) != expected_services:
        raise ControlPlaneError("unexpected Control Plane service set")
    limits = {
        "control-plane": (256 * 1024 * 1024, 128),
        "control-plane-authz": (128 * 1024 * 1024, 64),
        "control-plane-web": (128 * 1024 * 1024, 64),
    }
    for name, service in services.items():
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
        if service.get("privileged") is True or str(service.get("user")) != "10001:10001":
            raise ControlPlaneError("Control Plane privilege policy differs")
        if (int(service.get("mem_limit", 0)), int(service.get("pids_limit", 0))) != limits[name]:
            raise ControlPlaneError("Control Plane resource policy differs")
        if any("docker.sock" in str(item) for item in service.get("volumes", [])):
            raise ControlPlaneError("Control Plane must not mount a Docker socket")

    core = services["control-plane"]
    web = services["control-plane-web"]
    authz = services["control-plane-authz"]
    if len(core.get("ports", [])) != 1 or len(web.get("ports", [])) != 1:
        raise ControlPlaneError("Control Plane published port set differs")
    if authz.get("ports", []):
        raise ControlPlaneError("authz must not publish a LAN port")
    core_port = core["ports"][0]
    web_port = web["ports"][0]
    if (
        int(core_port.get("target", 0)) != 9443
        or int(core_port.get("published", 0)) != PORT
        or int(web_port.get("target", 0)) != 9444
        or int(web_port.get("published", 0)) != BROWSER_BACKEND_PORT
        or core_port.get("protocol") != "tcp"
        or web_port.get("protocol") != "tcp"
    ):
        raise ControlPlaneError("Control Plane published API differs")
    address = ipaddress.ip_address(str(core_port.get("host_ip", "")))
    web_address = ipaddress.ip_address(str(web_port.get("host_ip", "")))
    if (
        not address.is_private
        or address.is_loopback
        or address.is_unspecified
        or not web_address.is_loopback
    ):
        raise ControlPlaneError(
            "Control Plane core must bind private LAN and browser backend loopback"
        )

    core_targets = {
        "/data",
        "/run/control-plane/tls/server.crt",
        "/run/control-plane/tls/server.key",
        "/run/control-plane/tls/clients-ca.crt",
        "/run/control-plane/tls/dashboard-client.crt",
        "/run/control-plane/audit-checkpoint.key",
        "/run/control-plane/profile-sync/ca.crt",
        "/run/control-plane/profile-sync/client.crt",
        "/run/control-plane/profile-sync/client.key",
        "/run/control-plane/secret-broker/ca.crt",
        "/run/control-plane/secret-broker/client.crt",
        "/run/control-plane/secret-broker/client.key",
        "/run/control-plane/watchdog/ca.crt",
        "/run/control-plane/watchdog/client.crt",
        "/run/control-plane/watchdog/client.key",
        "/run/control-plane/github/token",
        "/run/control-plane/catalogs/schedules.json",
        "/run/control-plane/catalogs/status-sources.json",
        "/run/control-plane/catalogs/device-inventory.json",
    }
    web_targets = {
        "/run/control-plane/web/core-ca.crt",
        "/run/control-plane/web/core-client.crt",
        "/run/control-plane/web/core-client.key",
        "/run/control-plane/web/authz-ca.crt",
        "/run/control-plane/web/authz-client.crt",
        "/run/control-plane/web/authz-client.key",
    }
    authz_targets = {
        "/data",
        "/run/control-plane/authz/aead.key",
        "/run/control-plane/authz/server.crt",
        "/run/control-plane/authz/server.key",
        "/run/control-plane/authz/clients-ca.crt",
    }
    source_targets = set(
        document.get("_mwodevelop_source_policy", {}).get(
            "bind_create_host_path_false", []
        )
    )
    for service, targets, data_root in (
        (core, core_targets, ROOT / "data"),
        (web, web_targets, None),
        (authz, authz_targets, ROOT / "authz-data"),
    ):
        volumes = service.get("volumes", [])
        by_target = {item.get("target"): item for item in volumes}
        if set(by_target) != targets or len(volumes) != len(targets):
            raise ControlPlaneError("Control Plane bind mount set differs")
        for target in targets:
            source = _absolute_bind(by_target[target], target, source_targets)
            expected = str(data_root if target == "/data" else ROOT / "config")
            if not source.startswith(expected):
                raise ControlPlaneError(f"{target} is outside the managed root")
            if target != "/data" and by_target[target].get("read_only") is not True:
                raise ControlPlaneError("Control Plane configuration must be read-only")

    if set(core.get("networks", {})) != {"control-plane"}:
        raise ControlPlaneError("core network set differs")
    if set(web.get("networks", {})) != {"control-plane", "browser-auth"}:
        raise ControlPlaneError("browser network set differs")
    if set(authz.get("networks", {})) != {"browser-auth"}:
        raise ControlPlaneError("authz network set differs")
    configured_network = document.get("networks", {}).get("control-plane", {})
    if configured_network.get("name") != NETWORK or configured_network.get("external") is not True:
        raise ControlPlaneError("Control Plane shared network differs")
    if document.get("networks", {}).get("browser-auth", {}).get("internal") is not True:
        raise ControlPlaneError("browser auth network must be internal")

    command = " ".join(str(item) for item in core.get("command", []))
    for required in (
        "--tls-cert /run/control-plane/tls/server.crt",
        "--client-ca /run/control-plane/tls/clients-ca.crt",
        "--dashboard-client-certificate /run/control-plane/tls/dashboard-client.crt",
        f"--frame-ancestor https://{address}",
        "--checkpoint-key /run/control-plane/audit-checkpoint.key",
        "--profile-sync-host profile-sync",
        "--profile-sync-port 8767",
        "--secret-broker-host secret-broker",
        "--secret-broker-port 9444",
        "--secret-broker-server-name secret-broker",
        "--watchdog-host upstream-watchdog",
        "--watchdog-port 9445",
        "--watchdog-server-name upstream-watchdog",
        "--github-token-file /run/control-plane/github/token",
        "--schedule-catalog /run/control-plane/catalogs/schedules.json",
        "--status-source-catalog /run/control-plane/catalogs/status-sources.json",
        "--device-inventory /run/control-plane/catalogs/device-inventory.json",
    ):
        if required not in command:
            raise ControlPlaneError("Control Plane command policy differs")
    web_command = " ".join(str(item) for item in web.get("command", []))
    for required in (
        "--plaintext-behind-loopback-proxy",
        f"--expected-host {address}",
        f"--expected-origin https://{address}",
        "--allowed-network 172.16.0.0/12",
        "--core-host control-plane",
        "--authz-host control-plane-authz",
    ):
        if required not in web_command:
            raise ControlPlaneError("browser command policy differs")
    authz_command = " ".join(str(item) for item in authz.get("command", []))
    for required in (
        "--database /data/authz.sqlite",
        "--auth-key /run/control-plane/authz/aead.key",
        "--client-ca /run/control-plane/authz/clients-ca.crt",
    ):
        if required not in authz_command:
            raise ControlPlaneError("authz command policy differs")
    for service, endpoint in (
        (core, "127.0.0.1:9080/ready"),
        (authz, "127.0.0.1:9082/ready"),
        (web, "127.0.0.1:9083/ready"),
    ):
        health = " ".join(
            str(item) for item in service.get("healthcheck", {}).get("test", [])
        )
        if endpoint not in health:
            raise ControlPlaneError("Control Plane healthcheck must remain on loopback")
    return {
        "image": core["image"],
        "host_ip": str(address),
        "port": PORT,
        "browser_backend_port": BROWSER_BACKEND_PORT,
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
                document.get("schema") in {1, 2}
                and isinstance(document.get("healthy"), bool)
                and isinstance(document.get("services"), list)
                and isinstance(document.get("audit_sequence"), int)
            ):
                return document
        except (OSError, URLError, ssl.SSLError, json.JSONDecodeError) as error:
            last_error = error
        time.sleep(2)
    raise ControlPlaneError("Control Plane mTLS API verification failed") from last_error


def verify_browser(host_ip, _ca=None, attempts=30):
    """Verify the browser facade through the QTS HTTPS gateway."""
    context = ssl._create_unverified_context()
    context.minimum_version = ssl.TLSVersion.TLSv1_2
    endpoint = f"https://{host_ip}{BROWSER_PATH}login"
    last_error = None
    for _attempt in range(attempts):
        try:
            with urlopen(endpoint, timeout=5, context=context) as response:
                payload = response.read(256 * 1024)
            if response.status == 200 and b"Kodi Control Plane" in payload:
                return {"status": "ready", "endpoint": endpoint}
        except (OSError, URLError, ssl.SSLError) as error:
            last_error = error
        time.sleep(2)
    raise ControlPlaneError(
        "Control Plane browser verification without client certificate failed"
    ) from last_error


def create_browser_bootstrap(session, reset=False):
    """Create a short-lived browser bootstrap code inside the private authz DB."""
    report = preflight(session)
    if report["raid"] != {"array": "UU", "recovery_percent": None}:
        raise ControlPlaneError("browser bootstrap requires healthy RAID [UU]")
    _install, docker = container_station(session)
    compose = compose_command(docker)
    command = (
        compose
        + " exec -T control-plane-authz python -m kodi_control_plane.admin"
        + " --database /data/authz.sqlite auth-bootstrap"
        + " --auth-key /run/control-plane/authz/aead.key"
        + (" --reset" if reset else "")
    )
    try:
        document = json.loads(session.execute(command, timeout=30))
    except json.JSONDecodeError as error:
        raise ControlPlaneError("browser bootstrap returned invalid JSON") from error
    if (
        not isinstance(document.get("code"), str)
        or not isinstance(document.get("expires_at"), int)
    ):
        raise ControlPlaneError("browser bootstrap response differs")
    return document


def deploy(
    session,
    repository,
    image,
    host_ip,
    private,
    secret_broker_private=None,
    watchdog_private=None,
    github_token=None,
    device_inventory=None,
):
    try:
        from qnap_control_plane_gateway import install as install_gateway
    except ModuleNotFoundError:
        from tools.qnap_control_plane_gateway import install as install_gateway

    report = preflight(session)
    if report["raid"] != {"array": "UU", "recovery_percent": None}:
        raise ControlPlaneError("Control Plane deployment requires healthy RAID [UU]")
    files = validate_private_files(
        private, secret_broker_private, watchdog_private
    )
    if not github_token or any(char in github_token for char in "\r\n"):
        raise ControlPlaneError("Control Plane GitHub token is missing or invalid")
    if (
        not isinstance(device_inventory, dict)
        or device_inventory.get("schema") != 1
        or not isinstance(device_inventory.get("devices"), list)
        or not device_inventory["devices"]
    ):
        raise ControlPlaneError("Control Plane device inventory is invalid")
    env = environment(image, host_ip)
    _install, docker = container_station(session)
    repository = Path(repository)
    deployment = repository / "deploy/qnap-control-plane"
    compose_source = (deployment / "compose.yaml").read_text(encoding="utf-8")
    app = ROOT / "app"
    data = ROOT / "data"
    authz_data = ROOT / "authz-data"
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
                app, data, authz_data, ROOT / "backups", config / "tls",
                config / "web", config / "authz",
                config / "profile-sync", config / "secret-broker", config / "watchdog",
                config / "github",
                config / "catalogs",
            )
        )
    )
    session.upload_text(str(app / "compose.yaml"), compose_source, 0o600)
    session.upload_text(str(app / "control-plane.env"), env, 0o600)
    session.upload_text(str(marker), "kodi-control-plane-browser-v3\n", 0o600)
    uploads = {
        config / "tls/server.crt": (files["tls_certificate"], 0o400),
        config / "tls/server.key": (files["tls_key"], 0o400),
        config / "tls/clients-ca.crt": (files["client_ca"], 0o400),
        config / "web/core-ca.crt": (files["web_core_ca"], 0o400),
        config / "web/core-client.crt": (
            files["web_core_client_certificate"], 0o400
        ),
        config / "web/core-client.key": (files["web_core_client_key"], 0o400),
        config / "web/authz-ca.crt": (files["web_authz_ca"], 0o400),
        config / "web/authz-client.crt": (
            files["web_authz_client_certificate"], 0o400
        ),
        config / "web/authz-client.key": (files["web_authz_client_key"], 0o400),
        config / "authz/aead.key": (files["authz_key"], 0o400),
        config / "authz/server.crt": (files["authz_tls_certificate"], 0o400),
        config / "authz/server.key": (files["authz_tls_key"], 0o400),
        config / "authz/clients-ca.crt": (files["authz_client_ca"], 0o400),
        config / "audit-checkpoint.key": (files["checkpoint_key"], 0o400),
        config / "profile-sync/ca.crt": (files["profile_ca"], 0o400),
        config / "profile-sync/client.crt": (
            files["profile_client_certificate"], 0o400
        ),
        config / "profile-sync/client.key": (files["profile_client_key"], 0o400),
        config / "secret-broker/ca.crt": (files["broker_ca"], 0o400),
        config / "secret-broker/client.crt": (
            files["broker_client_certificate"], 0o400
        ),
        config / "secret-broker/client.key": (files["broker_client_key"], 0o400),
        config / "watchdog/ca.crt": (files["watchdog_ca"], 0o400),
        config / "watchdog/client.crt": (
            files["watchdog_client_certificate"],
            0o400,
        ),
        config / "watchdog/client.key": (files["watchdog_client_key"], 0o400),
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
    session.upload_text(
        str(config / "catalogs/device-inventory.json"),
        json.dumps(device_inventory, indent=2, sort_keys=True) + "\n",
        0o400,
    )
    session.upload_text(str(config / "github/token"), github_token + "\n", 0o400)
    session.execute(
        "chown -R 10001:10001 "
        + " ".join(
            shlex.quote(str(path))
            for path in (data, authz_data, ROOT / "backups", config)
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
    gateway = install_gateway(session, repository)
    api = verify_api(
        host_ip,
        files["client_ca"],
        files["operator_certificate"],
        files["operator_key"],
    )
    browser = verify_browser(host_ip, files["client_ca"])
    return {
        "policy": policy,
        "preflight": report,
        "api": api,
        "browser": browser,
        "gateway": gateway,
    }
