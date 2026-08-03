#!/usr/bin/env python3
"""Authenticated encryption for off-NAS Profile Sync database backups."""

from __future__ import annotations

import argparse
import hashlib
import io
import json
import os
import re
import secrets
import shutil
import tempfile
import zipfile
from pathlib import Path

from cryptography.exceptions import InvalidTag
from cryptography.hazmat.primitives.ciphers.aead import AESGCM


MAGIC = b"MWOPSBK1"
EPOCH_MAGIC = b"MWOPSE01"
NONCE_BYTES = 12
MAX_BACKUP_BYTES = 512 * 1024 * 1024


def _key(value):
    value = bytes(value)
    if len(value) != 32:
        raise ValueError("backup encryption key must contain exactly 32 bytes")
    return value


def _read_bounded(path):
    path = Path(path)
    size = path.stat().st_size
    if size > MAX_BACKUP_BYTES:
        raise ValueError("backup exceeds the encrypted backup size limit")
    return path.read_bytes()


def _publish_private(path, payload):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    if path.exists():
        raise FileExistsError(path)
    descriptor, temporary_name = tempfile.mkstemp(
        prefix=".%s." % path.name, dir=str(path.parent)
    )
    temporary = Path(temporary_name)
    try:
        os.fchmod(descriptor, 0o600)
        with os.fdopen(descriptor, "wb") as handle:
            handle.write(payload)
            handle.flush()
            os.fsync(handle.fileno())
        try:
            os.link(temporary, path)
        except FileExistsError:
            raise FileExistsError(path) from None
        path.chmod(0o600)
    finally:
        temporary.unlink(missing_ok=True)


def encrypt_backup(source, output, key):
    plaintext = _read_bounded(source)
    nonce = secrets.token_bytes(NONCE_BYTES)
    ciphertext = AESGCM(_key(key)).encrypt(nonce, plaintext, MAGIC)
    _publish_private(output, MAGIC + nonce + ciphertext)
    return {
        "encrypted_sha256": hashlib.sha256(
            MAGIC + nonce + ciphertext
        ).hexdigest(),
        "plaintext_sha256": hashlib.sha256(plaintext).hexdigest(),
        "bytes": len(plaintext),
    }


def decrypt_backup(source, output, key):
    payload = _read_bounded(source)
    if len(payload) < len(MAGIC) + NONCE_BYTES + 16 or not payload.startswith(
        MAGIC
    ):
        raise ValueError("invalid encrypted backup format")
    nonce = payload[len(MAGIC) : len(MAGIC) + NONCE_BYTES]
    ciphertext = payload[len(MAGIC) + NONCE_BYTES :]
    try:
        plaintext = AESGCM(_key(key)).decrypt(nonce, ciphertext, MAGIC)
    except InvalidTag as error:
        raise ValueError("encrypted backup authentication failed") from error
    _publish_private(output, plaintext)
    return {
        "plaintext_sha256": hashlib.sha256(plaintext).hexdigest(),
        "bytes": len(plaintext),
    }


def _validated_epoch_files(source):
    source = Path(source).resolve()
    inventory_payload = (source / "inventory.json").read_bytes()
    inventory = json.loads(inventory_payload)
    database = (source / "state.sqlite").read_bytes()
    metadata = inventory.get("database")
    if (
        inventory.get("schema") != 1
        or not isinstance(metadata, dict)
        or metadata.get("file") != "state.sqlite"
        or metadata.get("bytes") != len(database)
        or metadata.get("sha256") != hashlib.sha256(database).hexdigest()
        or not isinstance(inventory.get("blobs"), list)
    ):
        raise ValueError("invalid backup epoch inventory")
    files = {
        "inventory.json": inventory_payload,
        "state.sqlite": database,
    }
    for blob in inventory["blobs"]:
        digest = blob.get("sha256", "")
        value = digest.removeprefix("sha256:")
        if not re.fullmatch(r"[a-f0-9]{64}", value):
            raise ValueError("invalid backup epoch blob digest")
        relative = "blobs/%s/%s" % (value[:2], value)
        payload = (source / relative).read_bytes()
        if (
            blob.get("size") != len(payload)
            or hashlib.sha256(payload).hexdigest() != value
        ):
            raise ValueError("invalid backup epoch blob")
        files[relative] = payload
    actual = {
        path.relative_to(source).as_posix()
        for path in source.rglob("*")
        if path.is_file()
    }
    if actual != set(files) or any(path.is_symlink() for path in source.rglob("*")):
        raise ValueError("backup epoch contains unexpected files")
    if sum(len(payload) for payload in files.values()) > MAX_BACKUP_BYTES:
        raise ValueError("backup exceeds the encrypted backup size limit")
    return files


def _epoch_archive(files):
    output = io.BytesIO()
    with zipfile.ZipFile(output, "w", compression=zipfile.ZIP_STORED) as archive:
        for name, payload in sorted(files.items()):
            entry = zipfile.ZipInfo(name, date_time=(1980, 1, 1, 0, 0, 0))
            entry.compress_type = zipfile.ZIP_STORED
            entry.create_system = 3
            entry.external_attr = 0o100600 << 16
            archive.writestr(entry, payload)
    return output.getvalue()


def encrypt_epoch(source, output, key):
    plaintext = _epoch_archive(_validated_epoch_files(source))
    nonce = secrets.token_bytes(NONCE_BYTES)
    ciphertext = AESGCM(_key(key)).encrypt(nonce, plaintext, EPOCH_MAGIC)
    payload = EPOCH_MAGIC + nonce + ciphertext
    _publish_private(output, payload)
    return {
        "encrypted_sha256": hashlib.sha256(payload).hexdigest(),
        "plaintext_sha256": hashlib.sha256(plaintext).hexdigest(),
        "bytes": len(plaintext),
    }


def decrypt_epoch(source, output, key):
    payload = _read_bounded(source)
    if len(payload) < len(EPOCH_MAGIC) + NONCE_BYTES + 16 or not payload.startswith(
        EPOCH_MAGIC
    ):
        raise ValueError("invalid encrypted epoch format")
    nonce = payload[len(EPOCH_MAGIC) : len(EPOCH_MAGIC) + NONCE_BYTES]
    try:
        plaintext = AESGCM(_key(key)).decrypt(
            nonce, payload[len(EPOCH_MAGIC) + NONCE_BYTES :], EPOCH_MAGIC
        )
    except InvalidTag as error:
        raise ValueError("encrypted epoch authentication failed") from error
    with zipfile.ZipFile(io.BytesIO(plaintext), "r") as archive:
        names = archive.namelist()
        if len(names) != len(set(names)) or any(
            name.startswith("/") or ".." in Path(name).parts for name in names
        ):
            raise ValueError("encrypted epoch contains unsafe paths")
        extracted = {name: archive.read(name) for name in names}
    output = Path(output).resolve()
    if output.exists():
        raise FileExistsError(output)
    output.parent.mkdir(parents=True, exist_ok=True)
    temporary = Path(
        tempfile.mkdtemp(prefix=".%s." % output.name, dir=str(output.parent))
    )
    try:
        for name, content in extracted.items():
            destination = temporary / name
            destination.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
            _publish_private(destination, content)
        _validated_epoch_files(temporary)
        for directory in (
            path for path in temporary.rglob("*") if path.is_dir()
        ):
            directory.chmod(0o700)
        temporary.chmod(0o700)
        temporary.rename(output)
    except BaseException:
        shutil.rmtree(temporary, ignore_errors=True)
        raise
    return {
        "plaintext_sha256": hashlib.sha256(plaintext).hexdigest(),
        "bytes": len(plaintext),
        "epoch": str(output),
    }


def main():
    parser = argparse.ArgumentParser()
    commands = parser.add_subparsers(dest="command", required=True)
    for name in ("encrypt", "decrypt", "encrypt-epoch", "decrypt-epoch"):
        command = commands.add_parser(name)
        command.add_argument("--input", required=True)
        command.add_argument("--output", required=True)
        command.add_argument("--key-file", required=True)
    args = parser.parse_args()
    key_path = Path(args.key_file)
    if key_path.stat().st_mode & 0o077:
        raise SystemExit("backup key permissions are too broad")
    key = key_path.read_bytes()
    if args.command == "encrypt":
        result = encrypt_backup(args.input, args.output, key)
    elif args.command == "decrypt":
        result = decrypt_backup(args.input, args.output, key)
    elif args.command == "encrypt-epoch":
        result = encrypt_epoch(args.input, args.output, key)
    else:
        result = decrypt_epoch(args.input, args.output, key)
    print(json.dumps(result, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
