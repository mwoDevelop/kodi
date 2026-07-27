#!/usr/bin/env python3
"""Controlled QNAP Profile Sync smoke lifecycle over SSH."""

from __future__ import annotations

import argparse
import json
import re
import shlex
import time
from pathlib import Path, PurePosixPath

try:
    from kodi_inventory import load_private_references
    from qnap_compose_policy import IMAGE, render_compose, validate_policy
except ModuleNotFoundError:
    from tools.kodi_inventory import load_private_references
    from tools.qnap_compose_policy import IMAGE, render_compose, validate_policy


RUN_ID = re.compile(r"^[a-z0-9][a-z0-9-]{2,47}$")
INSTALL_PATH = re.compile(
    r"^/share/[A-Za-z0-9._-]+/\.qpkg/container-station$"
)
SMOKE_PORT = 28765
PROJECT = "qnap-profile-sync-smoke"
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

    def close(self):
        self.client.close()


def connect(repository, references_file):
    references = load_private_references(
        Path(repository) / references_file
    )
    missing = [
        name
        for name in ("QNAP_HOST", "QNAP_USER", "QNAP_PASS")
        if not references.get(name)
    ]
    if missing:
        raise QnapError("missing private QNAP references")
    try:
        import paramiko
    except ImportError as error:
        raise QnapError(
            "Paramiko is required in the host virtual environment"
        ) from error
    client = paramiko.SSHClient()
    client.load_system_host_keys()
    client.set_missing_host_key_policy(paramiko.RejectPolicy())
    try:
        client.connect(
            hostname=references["QNAP_HOST"],
            username=references["QNAP_USER"],
            password=references["QNAP_PASS"],
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
        "DOCKER_HOST=unix:///var/run/system-docker.sock "
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
    raid = _raid_summary(session.execute("cat /proc/mdstat"))
    return {
        "architecture": architecture,
        "compose_version": compose_version,
        "container_station": str(
            PurePosixPath(install).relative_to("/share")
        ),
        "docker_version": docker_version,
        "raid": raid,
        "storage_driver": engine[1],
    }


def status(session):
    _install, docker = container_station(session)
    label = shlex.quote("label=com.docker.compose.project=%s" % PROJECT)
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
        "project": PROJECT,
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


def compose_command(docker, root):
    root = str(root)
    return (
        docker
        + " compose --project-name "
        + PROJECT
        + " --env-file "
        + shlex.quote(root + "/smoke.env")
        + " -f "
        + shlex.quote(root + "/compose.yaml")
        + " -f "
        + shlex.quote(root + "/compose.smoke.yaml")
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
            "PROFILE_SYNC_DATA=%s" % data,
            "PROFILE_SYNC_KEY_REGISTRY=%s" % registry,
            "PROFILE_SYNC_UID=10001",
            "PROFILE_SYNC_GID=10001",
            "",
        )
    )
    deployment = Path(repository) / "deploy" / "qnap-profile-sync"
    import tempfile

    with tempfile.NamedTemporaryFile("w", encoding="utf-8") as handle:
        handle.write(env)
        handle.flush()
        rendered = render_compose(repository, "smoke", handle.name)
    policy = validate_policy(rendered, "smoke")
    quoted_root = shlex.quote(str(root))
    session.execute(
        "test ! -e {root} && mkdir -p {data}".format(
            root=quoted_root,
            data=shlex.quote(str(data)),
        )
    )
    try:
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
            "chown -R 10001:10001 {data} {registry}".format(
                data=shlex.quote(str(data)),
                registry=shlex.quote(str(registry)),
            )
        )
        compose = compose_command(docker, root)
        session.execute(compose + " config --quiet")
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
            "wget -qO- http://127.0.0.1:%s/ready" % SMOKE_PORT,
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
                and document.get("database_schema") == 2
            ):
                state = status(session)
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
        + shlex.quote("label=com.docker.compose.project=%s" % PROJECT)
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
        remaining = status(session)
        if remaining["containers"]:
            raise QnapError("smoke project exists without its control files")
        if ignore_missing:
            return {"project": PROJECT, "removed": True, "run_id": run_id}
        raise QnapError("smoke run directory does not exist")
    compose = compose_command(docker, root)
    session.execute(
        compose + " down --remove-orphans",
        allowed=(0, 1),
        timeout=120,
    )
    remaining = status(session)
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
    return {"project": PROJECT, "removed": True, "run_id": run_id}


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
        else:
            result = destroy_smoke(session, args.run_id)
    finally:
        session.close()
    print(json.dumps(result, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
