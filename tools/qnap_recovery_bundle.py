#!/usr/bin/env python3
"""Create and cold-verify an encrypted cross-service QNAP recovery bundle."""

from __future__ import annotations

import argparse
import json
import shlex
import shutil
import subprocess
import sys
import tempfile
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from tools.kodi_inventory import load_private_references
from tools.qnap_control_plane import ROOT as CONTROL_ROOT
from tools.qnap_control_plane import compose_command as control_compose
from tools.qnap_control_plane import verify_api
from tools.qnap_images import status as image_status
from tools.qnap_profile_sync import (
    PRODUCTION_ROOT,
    backup_production,
    connect,
    container_station,
)
from tools.qnap_secret_broker import ROOT as BROKER_ROOT
from tools.qnap_secret_broker import compose_command as broker_compose
from tools.recovery_bundle import (
    canonical_json,
    cold_verify,
    encrypt_tree,
    ensure_key,
    replicate,
    sha256,
    write_manifest,
)


def epoch_id():
    return time.strftime("epoch-%Y%m%d-%H%M%S", time.gmtime())


def _remote_sqlite_backup(session, compose, service, source, target):
    program = (
        "import sqlite3,sys;"
        "source=sqlite3.connect(sys.argv[1]);"
        "target=sqlite3.connect(sys.argv[2]);"
        "source.backup(target);target.execute('PRAGMA wal_checkpoint(TRUNCATE)');"
        "target.close();source.close()"
    )
    session.execute(
        compose
        + " exec -T "
        + shlex.quote(service)
        + " python -c "
        + shlex.quote(program)
        + " "
        + shlex.quote(source)
        + " "
        + shlex.quote(target),
        timeout=120,
    )


def _copy_remote_tree(session, source, target):
    target = Path(target)
    if target.exists():
        raise ValueError("recovery staging target already exists")
    session.download_tree(str(source), target)


def _component(epoch, database, root):
    payload = Path(root, database).read_bytes()
    return {
        "backup_epoch_id": epoch,
        "database": database,
        "database_sha256": sha256(payload),
        "database_bytes": len(payload),
    }


def replicate_to_nuc(bundle, references):
    required = ("NUC_HOST", "NUC_USER_MWO", "NUC_SSH_KEY_MWO", "NUC_KNOWN_HOSTS")
    if any(not references.get(name) for name in required):
        raise ValueError("NUC recovery destination references are incomplete")
    bundle = Path(bundle)
    destination = ".local/share/mwodevelop-kodi-recovery/" + bundle.name
    ssh_options = [
        "-i",
        references["NUC_SSH_KEY_MWO"],
        "-o",
        "BatchMode=yes",
        "-o",
        "StrictHostKeyChecking=yes",
        "-o",
        "UserKnownHostsFile=" + references["NUC_KNOWN_HOSTS"],
    ]
    target = references["NUC_USER_MWO"] + "@" + references["NUC_HOST"]
    subprocess.run(
        [
            "ssh",
            *ssh_options,
            target,
            'install -d -m 700 "$HOME/.local/share/mwodevelop-kodi-recovery"',
        ],
        check=True,
        capture_output=True,
        text=True,
        timeout=30,
    )
    subprocess.run(
        ["scp", *ssh_options, str(bundle), target + ":" + destination],
        check=True,
        capture_output=True,
        text=True,
        timeout=120,
    )
    remote = subprocess.run(
        [
            "ssh",
            *ssh_options,
            target,
            'sha256sum "$HOME/' + destination + '"',
        ],
        check=True,
        capture_output=True,
        text=True,
        timeout=30,
    ).stdout.split()[0]
    expected = sha256(bundle.read_bytes())
    if remote != expected:
        raise ValueError("NUC recovery copy digest differs")
    return {"destination": "nuc-mwo", "path": destination, "sha256": remote}


def collect(repository, epoch, staging, references=".env"):
    staging = Path(staging)
    staging.mkdir(parents=True, exist_ok=False, mode=0o700)
    session = connect(repository, references)
    profile_remote = PRODUCTION_ROOT / "data/backups" / epoch
    control_remote = CONTROL_ROOT / "data/recovery" / epoch
    broker_remote = BROKER_ROOT / "data/recovery" / epoch
    try:
        _install, docker = container_station(session)
        for path, owner in (
            (control_remote, "10001:10001"),
            (broker_remote, "10002:10002"),
        ):
            session.execute("mkdir -p " + shlex.quote(str(path)))
            session.execute("chown " + owner + " " + shlex.quote(str(path)))
        _remote_sqlite_backup(
            session,
            control_compose(docker),
            "control-plane",
            "/data/control-plane.sqlite",
            f"/data/recovery/{epoch}/control-plane.sqlite",
        )
        _remote_sqlite_backup(
            session,
            broker_compose(docker),
            "secret-broker",
            "/data/secrets.db",
            f"/data/recovery/{epoch}/secrets.db",
        )

        profile = staging / "profile-sync/data"
        backup_production(session, epoch, profile)
        _copy_remote_tree(
            session, PRODUCTION_ROOT / "app", staging / "profile-sync/app"
        )
        _copy_remote_tree(
            session, PRODUCTION_ROOT / "config", staging / "profile-sync/config"
        )
        _copy_remote_tree(session, control_remote, staging / "control-plane/data")
        _copy_remote_tree(session, CONTROL_ROOT / "app", staging / "control-plane/app")
        _copy_remote_tree(
            session, CONTROL_ROOT / "config", staging / "control-plane/config"
        )
        _copy_remote_tree(session, broker_remote, staging / "secret-broker/data")
        _copy_remote_tree(session, BROKER_ROOT / "app", staging / "secret-broker/app")
        _copy_remote_tree(
            session, BROKER_ROOT / "config", staging / "secret-broker/config"
        )
    finally:
        for path in (profile_remote, control_remote, broker_remote):
            session.execute("rm -rf -- " + shlex.quote(str(path)), allowed=(0, 1))
        session.close()

    metadata = staging / "metadata"
    metadata.mkdir(mode=0o700)
    shutil.copy2(
        repository / "manifests/locks/qnap-stable.json", metadata / "qnap-stable.json"
    )
    shutil.copy2(
        repository / "manifests/locks/stable.json", metadata / "kodi-stable.json"
    )
    deployed = image_status(references, repository=repository)
    (metadata / "deployed-images.json").write_text(
        json.dumps(deployed, indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )
    for name in ("qnap-profile-sync", "qnap-control-plane", "qnap-secret-broker"):
        destination = metadata / "compose" / name
        destination.mkdir(parents=True, exist_ok=True)
        for source in sorted((repository / "deploy" / name).glob("*.yaml")):
            shutil.copy2(source, destination / source.name)

    references_map = load_private_references(repository / references)
    control = verify_api(
        references_map["QNAP_HOST"],
        repository / ".kodi-private/control-plane/tls/ca.crt",
        repository / ".kodi-private/control-plane/tls/operator-client.crt",
        repository / ".kodi-private/control-plane/tls/operator-client.key",
        attempts=1,
    )
    anchor = {
        "audit_sequence": control["audit_sequence"],
        "generated_at": control.get("generated_at"),
        "healthy": control["healthy"],
        "services_sha256": sha256(canonical_json(control["services"])),
    }
    components = {
        "profile-sync": _component(
            epoch, "state.sqlite", staging / "profile-sync/data"
        ),
        "control-plane": _component(
            epoch, "control-plane.sqlite", staging / "control-plane/data"
        ),
        "secret-broker": _component(
            epoch, "secrets.db", staging / "secret-broker/data"
        ),
    }
    return write_manifest(staging, epoch, components, anchor)


def create(repository, references, primary, secondary, key_path, epoch=None):
    epoch = epoch or epoch_id()
    key = ensure_key(key_path)
    with tempfile.TemporaryDirectory(prefix="mwo-recovery-stage-") as temporary:
        staging = Path(temporary) / epoch
        manifest = collect(repository, epoch, staging, references)
        primary_path = Path(primary) / (epoch + ".mwo-recovery")
        encrypted = encrypt_tree(staging, primary_path, key)
    secondary_copy = replicate(primary_path, Path(secondary) / primary_path.name)
    nuc_copy = replicate_to_nuc(
        primary_path, load_private_references(repository / references)
    )
    verification = cold_verify(primary_path, key, repository)
    if secondary_copy["sha256"] != encrypted["sha256"]:
        raise ValueError("recovery copies differ")
    return {
        "schema": 1,
        "result": "pass",
        "backup_epoch_id": epoch,
        "bundle_id": manifest["bundle_id"],
        "primary": encrypted,
        "secondary": secondary_copy,
        "off_host": nuc_copy,
        "cold_restore": verification,
    }


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--references", default=".env")
    commands = parser.add_subparsers(dest="command", required=True)
    created = commands.add_parser("create")
    created.add_argument("--epoch")
    created.add_argument("--primary", default=".kodi-private/recovery-bundles/primary")
    created.add_argument(
        "--secondary",
        default="/mnt/c/Users/PC/Documents/mwoDevelop-kodi-recovery",
    )
    created.add_argument("--key", default=".kodi-private/recovery-bundles/recovery.key")
    verified = commands.add_parser("cold-verify")
    verified.add_argument("bundle")
    verified.add_argument(
        "--key", default=".kodi-private/recovery-bundles/recovery.key"
    )
    args = parser.parse_args()
    if args.command == "create":
        result = create(
            ROOT,
            args.references,
            ROOT / args.primary
            if not Path(args.primary).is_absolute()
            else args.primary,
            ROOT / args.secondary
            if not Path(args.secondary).is_absolute()
            else args.secondary,
            ROOT / args.key if not Path(args.key).is_absolute() else args.key,
            args.epoch,
        )
    else:
        bundle = Path(args.bundle)
        key = Path(args.key)
        result = cold_verify(
            ROOT / bundle if not bundle.is_absolute() else bundle,
            ensure_key(ROOT / key if not key.is_absolute() else key),
            ROOT,
        )
    print(json.dumps(result, indent=2, sort_keys=True))


if __name__ == "__main__":
    main()
