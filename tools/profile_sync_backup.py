#!/usr/bin/env python3
"""Authenticated encryption for off-NAS Profile Sync database backups."""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import secrets
import tempfile
from pathlib import Path

from cryptography.exceptions import InvalidTag
from cryptography.hazmat.primitives.ciphers.aead import AESGCM


MAGIC = b"MWOPSBK1"
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


def main():
    parser = argparse.ArgumentParser()
    commands = parser.add_subparsers(dest="command", required=True)
    for name in ("encrypt", "decrypt"):
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
    else:
        result = decrypt_backup(args.input, args.output, key)
    print(json.dumps(result, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
