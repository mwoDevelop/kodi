import hashlib
import json
import os

import pytest

from tools.profile_sync_backup import (
    decrypt_backup,
    decrypt_epoch,
    encrypt_backup,
    encrypt_epoch,
)


def test_encrypted_backup_round_trip_is_private_and_authenticated(tmp_path):
    source = tmp_path / "state.sqlite"
    source.write_bytes(b"sqlite backup payload")
    key = bytes(range(32))
    encrypted = tmp_path / "state.sqlite.mwobak"
    restored = tmp_path / "restored.sqlite"

    encrypted_result = encrypt_backup(source, encrypted, key)
    restored_result = decrypt_backup(encrypted, restored, key)

    assert encrypted.read_bytes() != source.read_bytes()
    assert restored.read_bytes() == source.read_bytes()
    assert encrypted_result["plaintext_sha256"] == restored_result[
        "plaintext_sha256"
    ]
    assert os.stat(encrypted).st_mode & 0o777 == 0o600
    assert os.stat(restored).st_mode & 0o777 == 0o600


def test_encrypted_backup_rejects_tampering_and_overwrite(tmp_path):
    source = tmp_path / "state.sqlite"
    source.write_bytes(b"payload")
    encrypted = tmp_path / "state.mwobak"
    encrypt_backup(source, encrypted, b"k" * 32)

    damaged = bytearray(encrypted.read_bytes())
    damaged[-1] ^= 1
    encrypted.write_bytes(damaged)
    with pytest.raises(ValueError, match="authentication failed"):
        decrypt_backup(encrypted, tmp_path / "restored.sqlite", b"k" * 32)

    with pytest.raises(FileExistsError):
        encrypt_backup(source, encrypted, b"k" * 32)


def test_encrypted_epoch_round_trip_validates_database_and_blobs(tmp_path):
    source = tmp_path / "epoch"
    blob = b"\x89PNG\r\n\x1a\nartwork"
    digest = hashlib.sha256(blob).hexdigest()
    (source / "blobs" / digest[:2]).mkdir(parents=True)
    (source / "blobs" / digest[:2] / digest).write_bytes(blob)
    database = b"sqlite epoch payload"
    (source / "state.sqlite").write_bytes(database)
    (source / "inventory.json").write_text(
        json.dumps(
            {
                "schema": 1,
                "database": {
                    "file": "state.sqlite",
                    "bytes": len(database),
                    "sha256": hashlib.sha256(database).hexdigest(),
                },
                "blobs": [
                    {
                        "sha256": "sha256:" + digest,
                        "size": len(blob),
                        "media_type": "image/png",
                    }
                ],
            },
            sort_keys=True,
            separators=(",", ":"),
        )
        + "\n"
    )
    encrypted = tmp_path / "epoch.mwobak"
    restored = tmp_path / "restored"

    encrypted_result = encrypt_epoch(source, encrypted, b"e" * 32)
    restored_result = decrypt_epoch(encrypted, restored, b"e" * 32)

    assert encrypted_result["plaintext_sha256"] == restored_result[
        "plaintext_sha256"
    ]
    assert (restored / "state.sqlite").read_bytes() == database
    assert (restored / "blobs" / digest[:2] / digest).read_bytes() == blob
    assert not any(path.stat().st_mode & 0o077 for path in restored.rglob("*"))
