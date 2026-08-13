#!/usr/bin/env python3
"""Controlled QNAP Profile Sync smoke lifecycle over SSH."""

from __future__ import annotations

import argparse
import base64
import hashlib
import ipaddress
import json
import os
import re
import shlex
import stat
import tempfile
import time
from pathlib import Path, PurePosixPath
from urllib.request import urlopen
import ssl

try:
    from kodi_inventory import load_private_references
    from qnap_compose_policy import (
        IMAGE,
        explicit_bind_targets,
        validate_policy,
    )
except ModuleNotFoundError:
    from tools.kodi_inventory import load_private_references
    from tools.qnap_compose_policy import (
        IMAGE,
        explicit_bind_targets,
        validate_policy,
    )


RUN_ID = re.compile(r"^[a-z0-9][a-z0-9-]{2,47}$")
SAFE_ID = re.compile(r"^[a-z0-9][a-z0-9._-]{0,63}$")
TARGET_TAG = re.compile(r"^[a-z0-9][a-z0-9._:-]{0,63}$")
ENROLLMENT = re.compile(r"^enr:[A-Za-z0-9._-]{8,128}$")
ADMIN_PATH = re.compile(
    r"^/v1/(?:revisions|blobs/sha256:[a-f0-9]{64}|"
    r"channels/[a-z0-9][a-z0-9._-]{0,63}/"
    r"(?:candidates|assignments|bootstrap-assignments|promote))$"
)
INSTALL_PATH = re.compile(
    r"^/share/[A-Za-z0-9._-]+/\.qpkg/container-station$"
)
SMOKE_PORT = 28765
PRODUCTION_PORT = 18765
CONTAINER_STATION_SOCKET = "/var/run/docker.sock"
SMOKE_PROJECT = "qnap-profile-sync-smoke"
PRODUCTION_PROJECT = "qnap-profile-sync"
PRODUCTION_ROOT = PurePosixPath(
    "/share/CACHEDEV3_DATA/.mwodevelop/profile-sync"
)
SYNTHETIC_REGISTRY = {
    "schema": 1,
    "keys": {
        "smoke-revision": {
            "public_key": "AAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAA",
            "allowed_kinds": ["revision"],
        }
    },
}


class QnapError(RuntimeError):
    pass


class QnapSession:
    def __init__(self, client):
        self.client = client

    def execute(self, command, allowed=(0,), timeout=30):
        _stdin, stdout, stderr = self.client.exec_command(
            command,
            timeout=timeout,
        )
        code = stdout.channel.recv_exit_status()
        output = stdout.read().decode("utf-8", "replace").strip()
        error_output = stderr.read().decode("utf-8", "replace").strip()
        if code not in allowed:
            detail = ""
            if error_output:
                last_line = error_output.splitlines()[-1][:300]
                last_line = re.sub(
                    r"(?i)(token|password|authorization)[^ ]*",
                    r"\1=<redacted>",
                    last_line,
                )
                detail = ": " + last_line
            raise QnapError(
                "remote command failed with exit code %s%s" % (code, detail)
            )
        return output

    def upload_text(self, remote_path, text, mode):
        with self.client.open_sftp() as sftp:
            with sftp.open(remote_path, "w") as handle:
                handle.write(text)
            sftp.chmod(remote_path, mode)

    def download_file(self, remote_path, local_path):
        local_path = Path(local_path)
        local_path.parent.mkdir(parents=True, exist_ok=True)
        if local_path.exists():
            raise QnapError("local download target already exists")
        descriptor, temporary_name = tempfile.mkstemp(
            prefix=".%s." % local_path.name,
            dir=str(local_path.parent),
        )
        temporary = Path(temporary_name)
        os.close(descriptor)
        try:
            with self.client.open_sftp() as sftp:
                sftp.get(remote_path, str(temporary))
            temporary.chmod(0o600)
            try:
                os.link(temporary, local_path)
            except FileExistsError:
                raise QnapError("local download target already exists") from None
        finally:
            temporary.unlink(missing_ok=True)

    def download_tree(self, remote_path, local_path):
        """Download a regular-file tree without following remote links."""
        remote_path = str(PurePosixPath(remote_path))
        local_path = Path(local_path)
        if local_path.exists():
            raise QnapError("local download target already exists")
        local_path.mkdir(parents=True, mode=0o700)
        try:
            with self.client.open_sftp() as sftp:
                pending = [(PurePosixPath(remote_path), local_path)]
                while pending:
                    remote, local = pending.pop()
                    for attribute in sftp.listdir_attr(str(remote)):
                        name = attribute.filename
                        if name in {"", ".", ".."} or "/" in name:
                            raise QnapError("remote backup has an unsafe entry")
                        remote_entry = remote / name
                        local_entry = local / name
                        if stat.S_ISDIR(attribute.st_mode):
                            local_entry.mkdir(mode=0o700)
                            pending.append((remote_entry, local_entry))
                        elif stat.S_ISREG(attribute.st_mode):
                            sftp.get(str(remote_entry), str(local_entry))
                            local_entry.chmod(0o600)
                        else:
                            raise QnapError(
                                "remote backup contains a non-regular entry"
                            )
        except Exception:
            import shutil

            shutil.rmtree(local_path, ignore_errors=True)
            raise

    def close(self):
        self.client.close()


def qnap_connection_settings(references):
    required = (
        "QNAP_HOST",
        "QNAP_USER",
        "QNAP_SSH_KEY",
        "QNAP_KNOWN_HOSTS",
    )
    if any(not references.get(name) for name in required):
        raise QnapError("missing private QNAP SSH key references")
    identity = Path(references["QNAP_SSH_KEY"]).expanduser().resolve()
    known_hosts = Path(
        references["QNAP_KNOWN_HOSTS"]
    ).expanduser().resolve()
    if not identity.is_file() or not known_hosts.is_file():
        raise QnapError("QNAP SSH key files do not exist")
    if stat.S_IMODE(identity.stat().st_mode) & 0o077:
        raise QnapError("QNAP SSH private key permissions are too broad")
    if stat.S_IMODE(known_hosts.stat().st_mode) & 0o077:
        raise QnapError("QNAP known_hosts permissions are too broad")
    return {
        "hostname": references["QNAP_HOST"],
        "username": references["QNAP_USER"],
        "key_filename": str(identity),
        "known_hosts": str(known_hosts),
    }


def connect(repository, references_file):
    references = load_private_references(
        Path(repository) / references_file
    )
    settings = qnap_connection_settings(references)
    try:
        import paramiko
    except ImportError as error:
        raise QnapError(
            "Paramiko is required in the host virtual environment"
        ) from error
    client = paramiko.SSHClient()
    client.load_host_keys(settings["known_hosts"])
    client.set_missing_host_key_policy(paramiko.RejectPolicy())
    try:
        client.connect(
            hostname=settings["hostname"],
            username=settings["username"],
            key_filename=settings["key_filename"],
            timeout=8,
            banner_timeout=8,
            auth_timeout=8,
            allow_agent=False,
            look_for_keys=False,
        )
    except Exception as error:
        raise QnapError(
            "QNAP SSH connection or pinned host key verification failed"
        ) from error
    return QnapSession(client)


def container_station(session):
    install = session.execute(
        "getcfg container-station Install_Path -f /etc/config/qpkg.conf"
    )
    if not INSTALL_PATH.fullmatch(install):
        raise QnapError("unexpected Container Station installation path")
    docker = "%s/bin/docker" % install
    prefix = (
        "DOCKER_HOST=unix://%s " % CONTAINER_STATION_SOCKET
        + shlex.quote(docker)
    )
    return install, prefix


def _raid_summary(mdstat):
    array = re.search(
        r"(?ms)^md1\s*:.*?^\s+\d+.*?\[(U+_*)\](.*?)(?=^\S|\Z)",
        mdstat,
    )
    if not array:
        return {"array": "unknown", "recovery_percent": None}
    recovery = re.search(r"recovery\s*=\s*([0-9.]+)%", array.group(2))
    return {
        "array": array.group(1),
        "recovery_percent": float(recovery.group(1)) if recovery else None,
    }


def preflight(session):
    install, docker = container_station(session)
    architecture = session.execute("uname -m")
    docker_version = session.execute(
        docker + " version --format '{{.Server.Version}}'"
    )
    compose_version = session.execute(docker + " compose version --short")
    engine = session.execute(
        docker
        + " info --format '{{.Architecture}}|{{.Driver}}|{{.DockerRootDir}}'"
    ).split("|")
    if architecture != "armv7l" or engine[:2] != ["armv7l", "overlay2"]:
        raise QnapError("QNAP container architecture or storage driver differs")
    docker_root = PurePosixPath(engine[2]) if len(engine) == 3 else None
    expected_suffix = PurePosixPath(
        "Container/container-station-data/lib/docker"
    )
    if docker_root is None or not docker_root.is_relative_to(
        PurePosixPath("/share")
    ) or docker_root.parts[-4:] != expected_suffix.parts:
        raise QnapError(
            "QNAP Docker engine is not managed by Container Station GUI"
        )
    raid = _raid_summary(session.execute("cat /proc/mdstat"))
    return {
        "architecture": architecture,
        "compose_version": compose_version,
        "container_station": str(
            PurePosixPath(install).relative_to("/share")
        ),
        "docker_version": docker_version,
        "docker_root": str(docker_root),
        "raid": raid,
        "storage_driver": engine[1],
    }


def status(session, project=SMOKE_PROJECT):
    _install, docker = container_station(session)
    label = shlex.quote("label=com.docker.compose.project=%s" % project)
    output = session.execute(
        docker + " ps -a --filter " + label + " --format '{{.Status}}'"
    )
    networks = session.execute(
        docker + " network ls --filter " + label + " --format '{{.ID}}'"
    )
    volumes = session.execute(
        docker + " volume ls --filter " + label + " --format '{{.Name}}'"
    )
    states = [line for line in output.splitlines() if line]
    return {
        "containers": len(states),
        "networks": len([line for line in networks.splitlines() if line]),
        "project": project,
        "states": states,
        "volumes": len([line for line in volumes.splitlines() if line]),
    }


def smoke_root(install, run_id):
    if not RUN_ID.fullmatch(run_id):
        raise QnapError("invalid smoke run id")
    share = PurePosixPath(install).parents[1]
    if not str(share).startswith("/share/"):
        raise QnapError("unsafe QNAP share root")
    return share / ".mwodevelop-smoke" / run_id


def production_root():
    return PRODUCTION_ROOT


def production_environment(image, host_ip):
    if not IMAGE.fullmatch(image):
        raise QnapError("production image must use an immutable GHCR digest")
    try:
        address = ipaddress.ip_address(host_ip)
    except ValueError as error:
        raise QnapError("production listener is not an IP address") from error
    if address.is_loopback or address.is_unspecified:
        raise QnapError("production listener must be explicit and non-loopback")
    root = production_root()
    return "\n".join(
        (
            "PROFILE_SYNC_IMAGE=%s" % image,
            "PROFILE_SYNC_PORT=%s" % PRODUCTION_PORT,
            "PROFILE_SYNC_HOST_IP=%s" % address,
            "PROFILE_SYNC_DATA=%s" % (root / "data"),
            "PROFILE_SYNC_KEY_REGISTRY=%s"
            % (root / "config" / "key-registry.json"),
            "PROFILE_SYNC_TLS_CERT=%s"
            % (root / "config" / "tls" / "server.crt"),
            "PROFILE_SYNC_TLS_KEY=%s"
            % (root / "config" / "tls" / "server.key"),
            "PROFILE_SYNC_UID=10001",
            "PROFILE_SYNC_GID=10001",
            "",
        )
    )


def _local_regular_file(path, description, private=False):
    path = Path(path).expanduser()
    try:
        metadata = path.lstat()
    except OSError as error:
        raise QnapError("%s does not exist" % description) from error
    if not stat.S_ISREG(metadata.st_mode) or path.is_symlink():
        raise QnapError("%s must be a regular non-symlink file" % description)
    if private and stat.S_IMODE(metadata.st_mode) & 0o077:
        raise QnapError("%s permissions are too broad" % description)
    return path.resolve()


def validate_production_files(key_registry, tls_certificate, tls_key):
    registry = _local_regular_file(
        key_registry, "key registry", private=True
    )
    certificate = _local_regular_file(tls_certificate, "TLS certificate")
    key = _local_regular_file(tls_key, "TLS key", private=True)
    try:
        document = json.loads(registry.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as error:
        raise QnapError("key registry is invalid JSON") from error
    if (
        not isinstance(document, dict)
        or document.get("schema") != 1
        or not isinstance(document.get("keys"), dict)
        or not document["keys"]
    ):
        raise QnapError("key registry has an invalid contract")
    try:
        context = ssl.SSLContext(ssl.PROTOCOL_TLS_SERVER)
        context.load_cert_chain(str(certificate), str(key))
    except (OSError, ssl.SSLError) as error:
        raise QnapError("TLS certificate and key do not form a valid pair") from error
    return {
        "key_registry": registry,
        "tls_certificate": certificate,
        "tls_key": key,
    }


def compose_command(docker, root):
    root = str(root)
    return (
        docker
        + " compose --project-name "
        + SMOKE_PROJECT
        + " --env-file "
        + shlex.quote(root + "/smoke.env")
        + " -f "
        + shlex.quote(root + "/compose.yaml")
        + " -f "
        + shlex.quote(root + "/compose.smoke.yaml")
    )


def production_compose_command(docker):
    root = production_root()
    return (
        docker
        + " compose --project-name "
        + PRODUCTION_PROJECT
        + " --env-file "
        + shlex.quote(str(root / "app" / "production.env"))
        + " -f "
        + shlex.quote(str(root / "app" / "compose.yaml"))
    )


def verify_production(host_ip, ca_certificate, attempts=45):
    ca_certificate = _local_regular_file(
        ca_certificate, "TLS CA certificate"
    )
    context = ssl.create_default_context(cafile=str(ca_certificate))
    endpoint = "https://%s:%s/ready" % (host_ip, PRODUCTION_PORT)
    last_error = None
    for _attempt in range(attempts):
        try:
            with urlopen(endpoint, timeout=5, context=context) as response:
                document = json.loads(response.read())
            if (
                document.get("status") == "ready"
                and document.get("mode") == "verified-tls"
                and document.get("database_schema") == 3
                and document.get("service") == "kodi-profile-sync-server"
            ):
                return {
                    key: document[key]
                    for key in (
                        "api_version",
                        "build",
                        "database_schema",
                        "mode",
                        "service",
                        "status",
                        "version",
                    )
                }
        except Exception as error:
            last_error = error
        time.sleep(2)
    raise QnapError("production HTTPS readiness failed") from last_error


def deploy_production(
    session,
    repository,
    image,
    host_ip,
    key_registry,
    tls_certificate,
    tls_key,
    ca_certificate,
):
    report = preflight(session)
    if report["raid"] != {"array": "UU", "recovery_percent": None}:
        raise QnapError("production deployment requires healthy RAID [UU]")
    security = validate_production_files(
        key_registry, tls_certificate, tls_key
    )
    _local_regular_file(ca_certificate, "TLS CA certificate")
    _install, docker = container_station(session)
    root = production_root()
    app = root / "app"
    data = root / "data"
    backups = root / "backups"
    config = root / "config"
    tls = config / "tls"
    marker = app / ".managed-by-mwodevelop"
    exists = session.execute(
        "test -e {root} && printf exists".format(
            root=shlex.quote(str(root))
        ),
        allowed=(0, 1),
    )
    if exists:
        managed = session.execute(
            "test -f {marker} && printf managed".format(
                marker=shlex.quote(str(marker))
            ),
            allowed=(0, 1),
        )
        if not managed:
            raise QnapError("existing production root is not managed")
    session.execute(
        "mkdir -p {app} {data} {backups} {tls}".format(
            app=shlex.quote(str(app)),
            data=shlex.quote(str(data)),
            backups=shlex.quote(str(backups)),
            tls=shlex.quote(str(tls)),
        )
    )
    deployment = Path(repository) / "deploy" / "qnap-profile-sync"
    compose_source = (deployment / "compose.yaml").read_text(
        encoding="utf-8"
    )
    session.upload_text(str(app / "compose.yaml"), compose_source, 0o600)
    session.upload_text(
        str(app / "production.env"),
        production_environment(image, host_ip),
        0o600,
    )
    session.upload_text(str(marker), "profile-sync-production-v1\n", 0o600)
    session.upload_text(
        str(config / "key-registry.json"),
        security["key_registry"].read_text(encoding="utf-8"),
        0o400,
    )
    session.upload_text(
        str(tls / "server.crt"),
        security["tls_certificate"].read_text(encoding="utf-8"),
        0o400,
    )
    session.upload_text(
        str(tls / "server.key"),
        security["tls_key"].read_text(encoding="utf-8"),
        0o400,
    )
    session.execute(
        "chown -R 10001:10001 {data} {backups} "
        "&& chown 10001:10001 {registry} {cert} {key}".format(
            data=shlex.quote(str(data)),
            backups=shlex.quote(str(backups)),
            registry=shlex.quote(str(config / "key-registry.json")),
            cert=shlex.quote(str(tls / "server.crt")),
            key=shlex.quote(str(tls / "server.key")),
        )
    )
    compose = production_compose_command(docker)
    rendered_payload = session.execute(
        compose + " config --format json --no-normalize"
    )
    try:
        rendered = json.loads(rendered_payload)
    except json.JSONDecodeError as error:
        raise QnapError("remote Compose returned invalid policy JSON") from error
    rendered["_mwodevelop_source_policy"] = {
        "bind_create_host_path_false": sorted(
            explicit_bind_targets(compose_source)
        )
    }
    policy = validate_policy(rendered, "production")
    session.execute(compose + " up -d --pull always", timeout=360)
    ready = verify_production(host_ip, ca_certificate)
    resources = status(session, PRODUCTION_PROJECT)
    if (
        resources["containers"] != 1
        or resources["networks"] != 1
        or resources["volumes"] != 0
    ):
        raise QnapError("production project has unexpected resources")
    return {
        "policy": policy,
        "preflight": report,
        "ready": ready,
        "resources": resources,
    }


def backup_production(session, backup_id, output):
    if not RUN_ID.fullmatch(backup_id):
        raise QnapError("invalid backup id")
    output = Path(output)
    if output.exists():
        raise QnapError("local backup output already exists")
    _install, docker = container_station(session)
    compose = production_compose_command(docker)
    remote_container_path = "/data/backups/%s" % backup_id
    result_payload = session.execute(
        compose
        + " exec -T profile-sync python -m profile_sync_server.admin "
        + "--database /data/state.sqlite backup-epoch --output "
        + shlex.quote(remote_container_path),
        timeout=120,
    )
    try:
        result = json.loads(result_payload)
    except json.JSONDecodeError as error:
        raise QnapError("production backup returned invalid JSON") from error
    return download_production_backup(
        session,
        backup_id,
        output,
        expected_database_sha256=result.get("database_sha256"),
        expected_blob_count=result.get("blob_count"),
    )


def production_backup_paths(backup_id):
    if not RUN_ID.fullmatch(backup_id):
        raise QnapError("invalid backup id")
    return (
        PurePosixPath("/data/backups") / backup_id,
        production_root() / "data" / "backups" / backup_id,
    )


def download_production_backup(
    session,
    backup_id,
    output,
    expected_database_sha256=None,
    expected_blob_count=None,
):
    _container_path, host_path = production_backup_paths(backup_id)
    output = Path(output)
    if output.exists():
        raise QnapError("local backup output already exists")
    session.download_tree(str(host_path), output)
    try:
        epoch = json.loads(
            (output / "inventory.json").read_text(encoding="utf-8")
        )
        database_path = output / "state.sqlite"
        digest = hashlib.sha256(database_path.read_bytes()).hexdigest()
        database = epoch.get("database")
        if (
            epoch.get("schema") != 1
            or not isinstance(database, dict)
            or database.get("file") != "state.sqlite"
            or database.get("sha256") != digest
            or database.get("bytes") != database_path.stat().st_size
            or (
                expected_database_sha256 is not None
                and expected_database_sha256 != digest
            )
            or not isinstance(epoch.get("blobs"), list)
        ):
            raise QnapError("downloaded backup epoch differs")
        for blob in epoch["blobs"]:
            value = blob.get("sha256", "").removeprefix("sha256:")
            path = output / "blobs" / value[:2] / value
            payload = path.read_bytes()
            if (
                not re.fullmatch(r"[a-f0-9]{64}", value)
                or len(payload) != blob.get("size")
                or hashlib.sha256(payload).hexdigest() != value
            ):
                raise QnapError("downloaded backup blob differs")
        if (
            expected_blob_count is not None
            and expected_blob_count != len(epoch["blobs"])
        ):
            raise QnapError("downloaded backup blob inventory differs")
    except Exception:
        import shutil

        shutil.rmtree(output, ignore_errors=True)
        raise
    return {
        "backup_id": backup_id,
        "blob_count": len(epoch["blobs"]),
        "database_sha256": digest,
        "epoch": str(output),
    }


def create_production_pairing(
    session, logical_device_id, channel, target_tags, output
):
    if not SAFE_ID.fullmatch(logical_device_id):
        raise QnapError("invalid logical device id")
    if not SAFE_ID.fullmatch(channel):
        raise QnapError("invalid profile sync channel")
    target_tags = sorted(set(target_tags))
    if any(not TARGET_TAG.fullmatch(tag) for tag in target_tags):
        raise QnapError("invalid profile sync target tag")
    output = Path(output)
    if output.exists():
        raise QnapError("pairing output already exists")
    _install, docker = container_station(session)
    command = (
        production_compose_command(docker)
        + " exec -T profile-sync python -m profile_sync_server.admin"
        + " --database /data/state.sqlite create-pairing"
        + " --logical-device-id "
        + shlex.quote(logical_device_id)
        + " --channel "
        + shlex.quote(channel)
    )
    for target_tag in target_tags:
        command += " --target-tag " + shlex.quote(target_tag)
    payload = session.execute(command, timeout=120)
    try:
        document = json.loads(payload)
    except json.JSONDecodeError as error:
        raise QnapError("production pairing returned invalid JSON") from error
    if (
        document.get("logical_device_id") != logical_device_id
        or document.get("channel") != channel
        or document.get("target_tags") != target_tags
        or not isinstance(document.get("code"), str)
        or not re.fullmatch(r"[0-9]{8}", document["code"])
    ):
        raise QnapError("production pairing returned invalid identity")
    output.parent.mkdir(parents=True, exist_ok=True)
    descriptor = os.open(
        output,
        os.O_WRONLY | os.O_CREAT | os.O_EXCL,
        0o600,
    )
    with os.fdopen(descriptor, "w", encoding="utf-8") as handle:
        json.dump(document, handle, sort_keys=True, separators=(",", ":"))
        handle.write("\n")
        handle.flush()
        os.fsync(handle.fileno())
    return {
        "logical_device_id": logical_device_id,
        "channel": channel,
        "target_tags": target_tags,
        "pairing_file": str(output),
        "code_written": True,
    }


def revoke_production_enrollment(session, enrollment_id):
    """Revoke one exact production enrollment through the host-only CLI."""

    if not ENROLLMENT.fullmatch(enrollment_id):
        raise QnapError("invalid production enrollment id")
    _install, docker = container_station(session)
    command = (
        production_compose_command(docker)
        + " exec -T profile-sync python -m profile_sync_server.admin"
        + " --database /data/state.sqlite revoke "
        + shlex.quote(enrollment_id)
    )
    payload = session.execute(command, timeout=120)
    try:
        document = json.loads(payload)
    except json.JSONDecodeError as error:
        raise QnapError("production revocation returned invalid JSON") from error
    if document != {"enrollment_id": enrollment_id, "revoked": True}:
        raise QnapError("production revocation returned invalid identity")
    return document


def _production_loopback_post(
    session,
    path,
    document,
    idempotency_key=None,
    base_url="http://127.0.0.1:8766",
):
    if base_url not in {
        "http://127.0.0.1:8766",
        "https://127.0.0.1:8765",
    }:
        raise QnapError("invalid production loopback endpoint")
    payload = base64.urlsafe_b64encode(
        json.dumps(
            document, sort_keys=True, separators=(",", ":")
        ).encode("utf-8")
    ).rstrip(b"=").decode("ascii")
    _install, docker = container_station(session)
    program = (
        "import base64,json,ssl,sys,urllib.request;"
        "raw=base64.urlsafe_b64decode(sys.argv[1]+'='*(-len(sys.argv[1])%4));"
        "headers={'Content-Type':'application/json'};"
        "headers.update({} if sys.argv[3]=='-' else "
        "{'Idempotency-Key':sys.argv[3]});"
        "request=urllib.request.Request(sys.argv[4]+sys.argv[2],"
        "data=raw,headers=headers,method='POST');"
        "context=(ssl._create_unverified_context() "
        "if sys.argv[4].startswith('https:') else None);"
        "print(urllib.request.urlopen(request,timeout=15,context=context)"
        ".read().decode())"
    )
    command = (
        production_compose_command(docker)
        + " exec -T profile-sync python -c "
        + shlex.quote(program)
        + " "
        + shlex.quote(payload)
        + " "
        + shlex.quote(path)
        + " "
        + shlex.quote(idempotency_key or "-")
        + " "
        + shlex.quote(base_url)
    )
    try:
        response = json.loads(session.execute(command, timeout=120))
    except json.JSONDecodeError as error:
        raise QnapError("production admin returned invalid JSON") from error
    if not isinstance(response, dict):
        raise QnapError("production loopback returned an invalid document")
    return response


def production_pair_request(
    session,
    code,
    logical_device_id,
    channel,
    key_id,
    public_key,
):
    """Exchange one pairing code without exposing the production listener."""
    if not isinstance(code, str) or not re.fullmatch(r"[0-9]{8}", code):
        raise QnapError("invalid production pairing code")
    if any(
        not SAFE_ID.fullmatch(str(value))
        for value in (logical_device_id, channel, key_id)
    ):
        raise QnapError("invalid production pairing identity")
    if not isinstance(public_key, str) or not re.fullmatch(
        r"[A-Za-z0-9_-]{43}", public_key
    ):
        raise QnapError("invalid production pairing public key")
    return _production_loopback_post(
        session,
        "/v1/pair",
        {
            "code": code,
            "logical_device_id": logical_device_id,
            "channel": channel,
            "key_id": key_id,
            "public_key": public_key,
        },
        base_url="https://127.0.0.1:8765",
    )


def production_admin_request(
    session, path, document, idempotency_key
):
    """Submit an already signed request through SSH and container loopback."""
    if not ADMIN_PATH.fullmatch(str(path)):
        raise QnapError("invalid production admin path")
    if not isinstance(document, dict):
        raise QnapError("production admin request must be an object")
    if not isinstance(idempotency_key, str) or len(idempotency_key) < 8:
        raise QnapError("invalid production admin idempotency key")
    return _production_loopback_post(
        session, path, document, idempotency_key
    )


def smoke_deploy(session, repository, image, run_id):
    if not IMAGE.fullmatch(image):
        raise QnapError("smoke image must use an immutable GHCR digest")
    report = preflight(session)
    install, docker = container_station(session)
    root = smoke_root(install, run_id)
    data = root / "data"
    registry = root / "key-registry.json"
    env = "\n".join(
        (
            "PROFILE_SYNC_IMAGE=%s" % image,
            "PROFILE_SYNC_PORT=%s" % SMOKE_PORT,
            "PROFILE_SYNC_HOST_IP=127.0.0.1",
            "PROFILE_SYNC_DATA=%s" % data,
            "PROFILE_SYNC_KEY_REGISTRY=%s" % registry,
            "PROFILE_SYNC_TLS_CERT=%s" % (root / "server.crt"),
            "PROFILE_SYNC_TLS_KEY=%s" % (root / "server.key"),
            "PROFILE_SYNC_UID=10001",
            "PROFILE_SYNC_GID=10001",
            "",
        )
    )
    deployment = Path(repository) / "deploy" / "qnap-profile-sync"
    compose_source = (deployment / "compose.yaml").read_text(encoding="utf-8")
    quoted_root = shlex.quote(str(root))
    session.execute(
        "test ! -e {root} && mkdir -p {data}".format(
            root=quoted_root,
            data=shlex.quote(str(data)),
        )
    )
    try:
        session.execute(
            "openssl req -x509 -newkey rsa:2048 -nodes -days 1 "
            "-subj /CN=127.0.0.1 "
            "-keyout {key} -out {cert} >/dev/null 2>&1".format(
                key=shlex.quote(str(root / "server.key")),
                cert=shlex.quote(str(root / "server.crt")),
            )
        )
        session.upload_text(
            str(root / "compose.yaml"),
            (deployment / "compose.yaml").read_text(encoding="utf-8"),
            0o600,
        )
        session.upload_text(
            str(root / "compose.smoke.yaml"),
            (deployment / "compose.smoke.yaml").read_text(encoding="utf-8"),
            0o600,
        )
        session.upload_text(str(root / "smoke.env"), env, 0o600)
        session.upload_text(
            str(registry),
            json.dumps(SYNTHETIC_REGISTRY, sort_keys=True) + "\n",
            0o400,
        )
        session.execute(
            "chown -R 10001:10001 {data} {registry} {cert} {key}".format(
                data=shlex.quote(str(data)),
                registry=shlex.quote(str(registry)),
                cert=shlex.quote(str(root / "server.crt")),
                key=shlex.quote(str(root / "server.key")),
            )
        )
        compose = compose_command(docker, root)
        rendered_payload = session.execute(
            compose + " config --format json --no-normalize"
        )
        try:
            rendered = json.loads(rendered_payload)
        except json.JSONDecodeError as error:
            raise QnapError(
                "remote Compose returned invalid policy JSON"
            ) from error
        rendered["_mwodevelop_source_policy"] = {
            "bind_create_host_path_false": sorted(
                explicit_bind_targets(compose_source)
            )
        }
        policy = validate_policy(rendered, "smoke")
        session.execute(compose + " up -d --pull always", timeout=240)
        ready = verify(session)
    except Exception:
        destroy_smoke(session, run_id, ignore_missing=True)
        raise
    return {
        "mode": "synthetic-loopback-smoke",
        "policy": policy,
        "preflight": report,
        "ready": ready,
        "run_id": run_id,
    }


def verify(session):
    _install, docker = container_station(session)
    for _attempt in range(30):
        payload = session.execute(
            "wget --no-check-certificate -qO- https://127.0.0.1:%s/ready"
            % SMOKE_PORT,
            allowed=(0, 1, 4, 8),
            timeout=5,
        )
        if payload:
            try:
                document = json.loads(payload)
            except json.JSONDecodeError:
                document = {}
            if (
                document.get("status") == "ready"
                and document.get("service") == "kodi-profile-sync-server"
                and document.get("database_schema") == 3
            ):
                state = status(session, SMOKE_PROJECT)
                if (
                    state["containers"] != 1
                    or state["networks"] != 1
                    or state["volumes"] != 0
                ):
                    raise QnapError("smoke project has unexpected resources")
                return {
                    key: document[key]
                    for key in (
                        "api_version",
                        "build",
                        "database_schema",
                        "mode",
                        "service",
                        "status",
                        "version",
                    )
                }
        time.sleep(2)
    diagnostics = session.execute(
        docker
        + " ps -a --filter "
        + shlex.quote("label=com.docker.compose.project=%s" % SMOKE_PROJECT)
        + " --format '{{.Status}}'",
        allowed=(0,),
    )
    raise QnapError(
        "smoke readiness timed out; container state: %s"
        % (diagnostics or "missing")
    )


def destroy_smoke(session, run_id, ignore_missing=False):
    install, docker = container_station(session)
    root = smoke_root(install, run_id)
    exists = session.execute(
        "test -d {root} && printf exists".format(
            root=shlex.quote(str(root))
        ),
        allowed=(0, 1),
    )
    if not exists:
        remaining = status(session, SMOKE_PROJECT)
        if remaining["containers"]:
            raise QnapError("smoke project exists without its control files")
        if ignore_missing:
            return {
                "project": SMOKE_PROJECT,
                "removed": True,
                "run_id": run_id,
            }
        raise QnapError("smoke run directory does not exist")
    compose = compose_command(docker, root)
    session.execute(
        compose + " down --remove-orphans",
        allowed=(0, 1),
        timeout=120,
    )
    remaining = status(session, SMOKE_PROJECT)
    if any(
        remaining[key]
        for key in ("containers", "networks", "volumes")
    ):
        raise QnapError("smoke resources remain after Compose down")
    if not ignore_missing:
        session.execute("test -d " + shlex.quote(str(root)))
    session.execute(
        "rm -rf -- " + shlex.quote(str(root)),
        allowed=(0, 1),
    )
    session.execute(
        "test ! -e " + shlex.quote(str(root))
    )
    session.execute(
        "rmdir " + shlex.quote(str(root.parent)),
        allowed=(0, 1),
    )
    return {
        "project": SMOKE_PROJECT,
        "removed": True,
        "run_id": run_id,
    }


def main():
    repository = Path(__file__).resolve().parents[1]
    parser = argparse.ArgumentParser()
    parser.add_argument("--references", default=".env")
    subparsers = parser.add_subparsers(dest="command", required=True)
    subparsers.add_parser("preflight")
    subparsers.add_parser("status")
    deploy = subparsers.add_parser("smoke-deploy")
    deploy.add_argument("--image", required=True)
    deploy.add_argument("--run-id", required=True)
    subparsers.add_parser("verify")
    production = subparsers.add_parser("deploy-production")
    production.add_argument("--image", required=True)
    production.add_argument("--host-ip", required=True)
    production.add_argument("--key-registry", required=True)
    production.add_argument("--tls-certificate", required=True)
    production.add_argument("--tls-key", required=True)
    production.add_argument("--ca-certificate", required=True)
    production_verify = subparsers.add_parser("verify-production")
    production_verify.add_argument("--host-ip", required=True)
    production_verify.add_argument("--ca-certificate", required=True)
    subparsers.add_parser("production-status")
    backup = subparsers.add_parser("backup-production")
    backup.add_argument("--backup-id", required=True)
    backup.add_argument("--output", required=True)
    download_backup = subparsers.add_parser("download-production-backup")
    download_backup.add_argument("--backup-id", required=True)
    download_backup.add_argument("--output", required=True)
    pairing = subparsers.add_parser("create-production-pairing")
    pairing.add_argument("--logical-device-id", required=True)
    pairing.add_argument("--channel", required=True)
    pairing.add_argument("--target-tag", action="append", default=[])
    pairing.add_argument("--output", required=True)
    revoke = subparsers.add_parser("revoke-production-enrollment")
    revoke.add_argument("--enrollment-id", required=True)
    admin_request = subparsers.add_parser("admin-request")
    admin_request.add_argument("--path", required=True)
    admin_request.add_argument("--document", required=True)
    admin_request.add_argument("--idempotency-key", required=True)
    destroy = subparsers.add_parser("destroy-smoke")
    destroy.add_argument("--run-id", required=True)
    args = parser.parse_args()
    session = connect(repository, args.references)
    try:
        if args.command == "preflight":
            result = preflight(session)
        elif args.command == "status":
            result = status(session)
        elif args.command == "smoke-deploy":
            result = smoke_deploy(
                session,
                repository,
                args.image,
                args.run_id,
            )
        elif args.command == "verify":
            result = verify(session)
        elif args.command == "deploy-production":
            result = deploy_production(
                session,
                repository,
                args.image,
                args.host_ip,
                args.key_registry,
                args.tls_certificate,
                args.tls_key,
                args.ca_certificate,
            )
        elif args.command == "verify-production":
            result = verify_production(
                args.host_ip, args.ca_certificate
            )
        elif args.command == "production-status":
            result = status(session, PRODUCTION_PROJECT)
        elif args.command == "backup-production":
            result = backup_production(
                session, args.backup_id, args.output
            )
        elif args.command == "download-production-backup":
            result = download_production_backup(
                session, args.backup_id, args.output
            )
        elif args.command == "create-production-pairing":
            result = create_production_pairing(
                session,
                args.logical_device_id,
                args.channel,
                args.target_tag,
                args.output,
            )
        elif args.command == "revoke-production-enrollment":
            result = revoke_production_enrollment(
                session,
                args.enrollment_id,
            )
        elif args.command == "admin-request":
            result = production_admin_request(
                session,
                args.path,
                json.loads(Path(args.document).read_text(encoding="utf-8")),
                args.idempotency_key,
            )
        else:
            result = destroy_smoke(session, args.run_id)
    finally:
        session.close()
    print(json.dumps(result, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
