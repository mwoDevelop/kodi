#!/usr/bin/env python3
"""Content-bound encrypted recovery_bundle_v1 primitives."""

from __future__ import annotations

import hashlib
import io
import json
import os
import sqlite3
import struct
import sys
import tarfile
import tempfile
import time
from pathlib import Path, PurePosixPath

from cryptography.hazmat.primitives.asymmetric.x25519 import X25519PrivateKey
from cryptography.hazmat.primitives.ciphers.aead import AESGCM
from cryptography.hazmat.primitives.serialization import (
    Encoding,
    NoEncryption,
    PrivateFormat,
    PublicFormat,
)

MAGIC = b"MWOKRB1\0"
SCHEMA = 1


def canonical_json(value):
    return json.dumps(value, sort_keys=True, separators=(",", ":")).encode("utf-8")


def sha256(payload):
    return hashlib.sha256(payload).hexdigest()


def ensure_key(path):
    path = Path(path)
    if path.exists():
        if not path.is_file() or path.is_symlink() or path.stat().st_mode & 0o077:
            raise ValueError("recovery key is unsafe")
        payload = path.read_bytes()
    else:
        path.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
        descriptor = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
        with os.fdopen(descriptor, "wb") as handle:
            handle.write(os.urandom(32))
            handle.flush()
            os.fsync(handle.fileno())
        payload = path.read_bytes()
    if len(payload) != 32:
        raise ValueError("recovery key must contain exactly 32 bytes")
    return payload


def _files(root):
    result = {}
    for path in sorted(Path(root).rglob("*")):
        if path.is_symlink():
            raise ValueError("recovery input cannot contain symlinks")
        if not path.is_file() or path.name == "recovery-manifest.json":
            continue
        relative = path.relative_to(root).as_posix()
        payload = path.read_bytes()
        result[relative] = {"bytes": len(payload), "sha256": sha256(payload)}
    return result


def write_manifest(root, epoch_id, components, audit_anchor):
    root = Path(root)
    if not epoch_id or any(
        character not in "abcdefghijklmnopqrstuvwxyz0123456789-"
        for character in epoch_id
    ):
        raise ValueError("invalid backup epoch id")
    if set(components) != {"profile-sync", "control-plane", "secret-broker"}:
        raise ValueError("recovery component set differs")
    if any(value.get("backup_epoch_id") != epoch_id for value in components.values()):
        raise ValueError("mixed recovery epochs are forbidden")
    files = _files(root)
    manifest = {
        "schema": SCHEMA,
        "bundle_type": "recovery_bundle_v1",
        "backup_epoch_id": epoch_id,
        "created_at": int(time.time()),
        "components": components,
        "audit_anchor": audit_anchor,
        "files": files,
    }
    identity = dict(manifest)
    manifest["bundle_id"] = "sha256:" + sha256(canonical_json(identity))
    path = root / "recovery-manifest.json"
    path.write_text(
        json.dumps(manifest, indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )
    path.chmod(0o600)
    return manifest


def validate_tree(root, expected_epoch=None):
    root = Path(root)
    manifest = json.loads((root / "recovery-manifest.json").read_text(encoding="utf-8"))
    identity = {key: value for key, value in manifest.items() if key != "bundle_id"}
    if (
        manifest.get("schema") != SCHEMA
        or manifest.get("bundle_type") != "recovery_bundle_v1"
        or manifest.get("bundle_id") != "sha256:" + sha256(canonical_json(identity))
        or (
            expected_epoch is not None
            and manifest.get("backup_epoch_id") != expected_epoch
        )
        or set(manifest.get("components", {}))
        != {"profile-sync", "control-plane", "secret-broker"}
        or any(
            value.get("backup_epoch_id") != manifest.get("backup_epoch_id")
            for value in manifest.get("components", {}).values()
        )
        or manifest.get("files") != _files(root)
    ):
        raise ValueError("recovery bundle manifest differs")
    return manifest


def _tar_payload(root):
    output = io.BytesIO()
    with tarfile.open(fileobj=output, mode="w", format=tarfile.PAX_FORMAT) as archive:
        for path in sorted(Path(root).rglob("*")):
            if not path.is_file():
                continue
            relative = path.relative_to(root).as_posix()
            payload = path.read_bytes()
            info = tarfile.TarInfo(relative)
            info.size = len(payload)
            info.mode = 0o600
            info.mtime = 0
            archive.addfile(info, io.BytesIO(payload))
    return output.getvalue()


def encrypt_tree(root, output, key):
    manifest = validate_tree(root)
    tar_payload = _tar_payload(root)
    header = canonical_json(
        {
            "schema": SCHEMA,
            "bundle_type": "recovery_bundle_v1",
            "backup_epoch_id": manifest["backup_epoch_id"],
            "bundle_id": manifest["bundle_id"],
            "plaintext_sha256": sha256(tar_payload),
        }
    )
    nonce = os.urandom(12)
    encrypted = AESGCM(key).encrypt(nonce, tar_payload, header)
    payload = MAGIC + struct.pack(">I", len(header)) + header + nonce + encrypted
    output = Path(output)
    output.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
    descriptor = os.open(output, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
    with os.fdopen(descriptor, "wb") as handle:
        handle.write(payload)
        handle.flush()
        os.fsync(handle.fileno())
    return {
        "path": str(output),
        "sha256": sha256(payload),
        "bytes": len(payload),
        **json.loads(header),
    }


def decrypt_bundle(bundle, output, key):
    payload = Path(bundle).read_bytes()
    if not payload.startswith(MAGIC) or len(payload) < len(MAGIC) + 4 + 12 + 16:
        raise ValueError("invalid encrypted recovery bundle")
    offset = len(MAGIC)
    header_size = struct.unpack(">I", payload[offset : offset + 4])[0]
    offset += 4
    if header_size < 2 or header_size > 16384:
        raise ValueError("invalid recovery header size")
    header = payload[offset : offset + header_size]
    offset += header_size
    metadata = json.loads(header)
    nonce = payload[offset : offset + 12]
    plaintext = AESGCM(key).decrypt(nonce, payload[offset + 12 :], header)
    if sha256(plaintext) != metadata.get("plaintext_sha256"):
        raise ValueError("recovery plaintext digest differs")
    output = Path(output)
    output.mkdir(parents=True, exist_ok=False, mode=0o700)
    with tarfile.open(fileobj=io.BytesIO(plaintext), mode="r:") as archive:
        members = archive.getmembers()
        for member in members:
            relative = PurePosixPath(member.name)
            if (
                member.isdir()
                or relative.is_absolute()
                or ".." in relative.parts
                or not member.isfile()
            ):
                raise ValueError("unsafe recovery archive member")
        archive.extractall(output, members=members, filter="data")
    manifest = validate_tree(output, metadata.get("backup_epoch_id"))
    if manifest["bundle_id"] != metadata.get("bundle_id"):
        raise ValueError("recovery bundle identity differs")
    return manifest


def _quick_check(path):
    with sqlite3.connect(path) as database:
        result = database.execute("PRAGMA quick_check").fetchone()[0]
    if result != "ok":
        raise ValueError("restored SQLite database failed quick_check")


def cold_verify(bundle, key, repository):
    with tempfile.TemporaryDirectory(prefix="mwo-recovery-cold-") as temporary:
        root = Path(temporary) / "restore"
        manifest = decrypt_bundle(bundle, root, key)
        databases = {
            "profile-sync": root / "profile-sync/data/state.sqlite",
            "control-plane": root / "control-plane/data/control-plane.sqlite",
            "secret-broker": root / "secret-broker/data/secrets.db",
        }
        for path in databases.values():
            _quick_check(path)
        sys.path.insert(0, str(Path(repository) / "secret-broker/src"))
        from kodi_secret_broker.crypto import open_envelope, seal
        from kodi_secret_broker.model import b64url_encode
        from kodi_secret_broker.store import SecretStore

        key_path = root / "secret-broker/config/broker-master-key"
        key_path.chmod(0o600)
        store = SecretStore(databases["secret-broker"], key_path)
        secret_set = store.deliver("canary")
        recipient = X25519PrivateKey.generate()
        private = recipient.private_bytes(
            Encoding.Raw, PrivateFormat.Raw, NoEncryption()
        )
        public = recipient.public_key().public_bytes(Encoding.Raw, PublicFormat.Raw)
        now = int(time.time())
        metadata = {
            "schema": 1,
            "envelope_type": "secret-envelope-v1",
            "secret_type": "youtube-session-v1",
            "secret_set_id": secret_set["secret_set_id"],
            "secret_set_generation": secret_set["generation"],
            "secret_lifecycle": secret_set["lifecycle"],
            "logical_device_id": "cold-restore-test",
            "enrollment_id": "enr:ColdRestoreVerification1",
            "enrollment_generation": 1,
            "encryption_key_id": "cold-restore-key",
            "adapter": secret_set["adapter"],
            "addon_id": secret_set["addon_id"],
            "addon_version": secret_set["addon_version"],
            "nonce": "cold-restore-nonce",
            "issued_at": now,
            "expires_at": now + 900,
        }
        envelope = seal(metadata, b64url_encode(public), secret_set["secret"])
        recovered = open_envelope(envelope, b64url_encode(private))
        if not secrets_equal(secret_set["secret"], recovered):
            raise ValueError("cold-restored HPKE envelope differs")
        secret_set["secret"].clear()
        recovered.clear()
        return {
            "schema": 1,
            "result": "pass",
            "backup_epoch_id": manifest["backup_epoch_id"],
            "bundle_id": manifest["bundle_id"],
            "databases": sorted(databases),
            "broker_generation": envelope["secret_set_generation"],
            "hpke": "verified",
        }


def secrets_equal(left, right):
    return (
        hashlib.sha256(canonical_json(left)).digest()
        == hashlib.sha256(canonical_json(right)).digest()
    )


def replicate(source, destination):
    source = Path(source)
    destination = Path(destination)
    destination.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
    if destination.exists():
        if sha256(destination.read_bytes()) != sha256(source.read_bytes()):
            raise ValueError("immutable recovery copy already differs")
    else:
        descriptor = os.open(destination, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
        with os.fdopen(descriptor, "wb") as handle:
            handle.write(source.read_bytes())
            handle.flush()
            os.fsync(handle.fileno())
    return {"path": str(destination), "sha256": sha256(destination.read_bytes())}
