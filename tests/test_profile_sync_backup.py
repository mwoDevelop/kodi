import os

import pytest

from tools.profile_sync_backup import decrypt_backup, encrypt_backup


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
