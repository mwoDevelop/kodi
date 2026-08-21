#!/usr/bin/env python3
"""Deploy and validate the private QNAP Secret Broker."""

from __future__ import annotations

import argparse
import json
import re
import shlex
import ssl
import stat
from pathlib import Path, PurePosixPath

try:
    from qnap_compose_policy import explicit_bind_targets
    from qnap_profile_sync import connect, container_station, preflight
except ModuleNotFoundError:
    from tools.qnap_compose_policy import explicit_bind_targets
    from tools.qnap_profile_sync import connect, container_station, preflight


IMAGE = re.compile(
    r"^ghcr\.io/mwodevelop/kodi-secret-broker@sha256:[a-f0-9]{64}$"
)
PROJECT = "qnap-secret-broker"
NETWORK = "mwodevelop-control"
ROOT = PurePosixPath("/share/CACHEDEV3_DATA/.mwodevelop/secret-broker")


class SecretBrokerError(RuntimeError):
    pass


def _file(path, private=False):
    path = Path(path)
    metadata = path.lstat()
    if not stat.S_ISREG(metadata.st_mode) or path.is_symlink():
        raise SecretBrokerError("Secret Broker input must be a regular file")
    if private and stat.S_IMODE(metadata.st_mode) & 0o077:
        raise SecretBrokerError("Secret Broker private file permissions are too broad")
    return path.resolve()


def private_files(root):
    root = Path(root)
    result = {
        "master": _file(root / "broker-master-key", True),
        "server_cert": _file(root / "tls/server.crt"),
        "server_key": _file(root / "tls/server.key", True),
        "client_ca": _file(root / "tls/clients-ca.crt"),
        "health_cert": _file(root / "tls/health.crt"),
        "health_key": _file(root / "tls/health.key", True),
    }
    try:
        master = bytes.fromhex(
            result["master"].read_text(encoding="ascii").strip()
        )
    except (OSError, UnicodeDecodeError, ValueError) as error:
        raise SecretBrokerError("Secret Broker master key is invalid") from error
    if len(master) != 32:
        raise SecretBrokerError("Secret Broker master key must contain 32 bytes")
    try:
        context = ssl.SSLContext(ssl.PROTOCOL_TLS_SERVER)
        context.load_cert_chain(result["server_cert"], result["server_key"])
        client = ssl.SSLContext(ssl.PROTOCOL_TLS_CLIENT)
        client.load_cert_chain(result["health_cert"], result["health_key"])
    except (OSError, ssl.SSLError) as error:
        raise SecretBrokerError("Secret Broker certificate/key differs") from error
    return result


def environment(image):
    if not IMAGE.fullmatch(str(image)):
        raise SecretBrokerError("Secret Broker image must use an immutable digest")
    config = ROOT / "config"
    return "\n".join(
        (
            "SECRET_BROKER_IMAGE=" + str(image),
            "SECRET_BROKER_DATA=" + str(ROOT / "data"),
            "SECRET_BROKER_MASTER_KEY=" + str(config / "broker-master-key"),
            "SECRET_BROKER_TLS_CERT=" + str(config / "tls/server.crt"),
            "SECRET_BROKER_TLS_KEY=" + str(config / "tls/server.key"),
            "SECRET_BROKER_CLIENT_CA=" + str(config / "tls/clients-ca.crt"),
            "SECRET_BROKER_HEALTH_CERT=" + str(config / "tls/health.crt"),
            "SECRET_BROKER_HEALTH_KEY=" + str(config / "tls/health.key"),
            "",
        )
    )


def compose_command(docker):
    return (
        docker
        + " compose --project-name "
        + PROJECT
        + " --env-file "
        + shlex.quote(str(ROOT / "app/broker.env"))
        + " -f "
        + shlex.quote(str(ROOT / "app/compose.yaml"))
    )


def validate_policy(document):
    service = document.get("services", {}).get("secret-broker", {})
    if set(document.get("services", {})) != {"secret-broker"}:
        raise SecretBrokerError("unexpected Secret Broker service set")
    if not IMAGE.fullmatch(str(service.get("image", ""))):
        raise SecretBrokerError("Secret Broker image is not immutable")
    if service.get("ports"):
        raise SecretBrokerError("Secret Broker must not publish ports")
    if service.get("read_only") is not True or str(service.get("user")) != "10002:10002":
        raise SecretBrokerError("Secret Broker isolation policy differs")
    if set(service.get("cap_drop", [])) != {"ALL"}:
        raise SecretBrokerError("Secret Broker capabilities policy differs")
    if any("docker.sock" in str(item) for item in service.get("volumes", [])):
        raise SecretBrokerError("Secret Broker must not mount Docker socket")
    if set(service.get("networks", {})) != {"control-plane"}:
        raise SecretBrokerError("Secret Broker network differs")
    return {"image": service["image"], "project": PROJECT, "network": NETWORK}


def deploy(session, repository, image, private):
    report = preflight(session)
    if report["raid"] != {"array": "UU", "recovery_percent": None}:
        raise SecretBrokerError("Secret Broker deployment requires healthy RAID [UU]")
    files = private_files(private)
    _install, docker = container_station(session)
    app, data, config = ROOT / "app", ROOT / "data", ROOT / "config"
    session.execute(
        "mkdir -p " + " ".join(shlex.quote(str(item)) for item in (app, data, config / "tls"))
    )
    compose_source = (
        Path(repository) / "deploy/qnap-secret-broker/compose.yaml"
    ).read_text(encoding="utf-8")
    session.upload_text(str(app / "compose.yaml"), compose_source, 0o600)
    session.upload_text(str(app / "broker.env"), environment(image), 0o600)
    session.upload_text(str(app / ".managed-by-mwodevelop"), "secret-broker-v1\n", 0o600)
    uploads = {
        config / "broker-master-key": files["master"],
        config / "tls/server.crt": files["server_cert"],
        config / "tls/server.key": files["server_key"],
        config / "tls/clients-ca.crt": files["client_ca"],
        config / "tls/health.crt": files["health_cert"],
        config / "tls/health.key": files["health_key"],
    }
    for target, source in uploads.items():
        session.upload_text(
            str(target), source.read_text(encoding="utf-8"), 0o400
        )
    session.execute("chown -R 10002:10002 " + shlex.quote(str(ROOT)))
    session.execute(
        docker + " network inspect " + NETWORK + " >/dev/null 2>&1 || "
        + docker + " network create --driver bridge --label io.mwodevelop.managed=true "
        + NETWORK + " >/dev/null"
    )
    compose = compose_command(docker)
    rendered = json.loads(session.execute(compose + " config --format json --no-normalize"))
    rendered["_mwodevelop_source_policy"] = {
        "bind_create_host_path_false": sorted(explicit_bind_targets(compose_source))
    }
    policy = validate_policy(rendered)
    session.execute(compose + " up -d --pull always", timeout=360)
    return {"policy": policy, "preflight": report}


def _execute_input(session, command, input_text, timeout=30):
    stdin, stdout, stderr = session.client.exec_command(command, timeout=timeout)
    stdin.write(input_text)
    stdin.flush()
    stdin.channel.shutdown_write()
    code = stdout.channel.recv_exit_status()
    output = stdout.read().decode("utf-8", "replace").strip()
    stderr.read()
    if code != 0:
        raise SecretBrokerError(
            "Secret Broker admin command failed with exit code %s" % code
        )
    try:
        return json.loads(output)
    except (TypeError, ValueError) as error:
        raise SecretBrokerError("Secret Broker returned invalid admin JSON") from error


def import_secret_set(session, document):
    if not isinstance(document, dict):
        raise SecretBrokerError("Secret Broker import must be a JSON object")
    _install, docker = container_station(session)
    command = (
        compose_command(docker)
        + " exec -T secret-broker kodi-secret-broker "
        + "--database /data/secrets.db --master-key /run/secrets/broker-master-key "
        + "import --input -"
    )
    return _execute_input(
        session,
        command,
        json.dumps(document, sort_keys=True, separators=(",", ":")),
    )


def transition(session, secret_set_id, generation, expected, lifecycle):
    if not re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9._:-]{0,127}", secret_set_id):
        raise SecretBrokerError("invalid Secret Broker set identifier")
    if not isinstance(generation, int) or generation < 1:
        raise SecretBrokerError("invalid Secret Broker generation")
    _install, docker = container_station(session)
    command = (
        compose_command(docker)
        + " exec -T secret-broker kodi-secret-broker "
        + "--database /data/secrets.db --master-key /run/secrets/broker-master-key "
        + "transition "
        + shlex.quote(secret_set_id)
        + " "
        + str(generation)
        + " --from "
        + shlex.quote(expected)
        + " --to "
        + shlex.quote(lifecycle)
    )
    output = session.execute(command)
    try:
        return json.loads(output)
    except (TypeError, ValueError) as error:
        raise SecretBrokerError("Secret Broker returned invalid transition JSON") from error


def main(argv=None):
    parser = argparse.ArgumentParser()
    parser.add_argument("--references", default=".env")
    sub = parser.add_subparsers(dest="command", required=True)
    imported = sub.add_parser("import")
    imported.add_argument("--input", required=True)
    changed = sub.add_parser("transition")
    changed.add_argument("secret_set_id")
    changed.add_argument("generation", type=int)
    changed.add_argument("--from", dest="expected", required=True)
    changed.add_argument("--to", dest="lifecycle", required=True)
    args = parser.parse_args(argv)
    repository = Path(__file__).resolve().parents[1]
    session = connect(repository, args.references)
    try:
        if args.command == "import":
            document = json.loads(Path(args.input).read_text(encoding="utf-8"))
            result = import_secret_set(session, document)
        else:
            result = transition(
                session,
                args.secret_set_id,
                args.generation,
                args.expected,
                args.lifecycle,
            )
    finally:
        session.close()
    print(json.dumps(result, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
