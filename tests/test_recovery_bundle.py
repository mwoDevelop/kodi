import json
import sqlite3

import pytest
from cryptography.exceptions import InvalidTag

from tools.recovery_bundle import (
    decrypt_bundle,
    encrypt_tree,
    ensure_key,
    validate_tree,
    write_manifest,
)


def _database(path, statement="CREATE TABLE state(value TEXT)"):
    path.parent.mkdir(parents=True, exist_ok=True)
    with sqlite3.connect(path) as database:
        database.execute(statement)


def _tree(tmp_path):
    root = tmp_path / "tree"
    _database(root / "profile-sync/data/state.sqlite")
    _database(root / "control-plane/data/control-plane.sqlite")
    _database(
        root / "secret-broker/data/secrets.db",
        "CREATE TABLE secret_sets(secret_set_id TEXT)",
    )
    key = root / "secret-broker/config/broker-master-key"
    key.parent.mkdir(parents=True)
    key.write_text("00" * 32 + "\n", encoding="ascii")
    key.chmod(0o600)
    epoch = "e2e-20260821"
    components = {
        name: {"backup_epoch_id": epoch, "database": database}
        for name, database in (
            ("profile-sync", "state.sqlite"),
            ("control-plane", "control-plane.sqlite"),
            ("secret-broker", "secrets.db"),
        )
    }
    write_manifest(root, epoch, components, {"audit_sequence": 1})
    return root, epoch


def test_encrypted_bundle_round_trip_is_content_bound(tmp_path):
    root, epoch = _tree(tmp_path)
    key = ensure_key(tmp_path / "key")
    bundle = tmp_path / "bundle.mwo-recovery"

    encrypted = encrypt_tree(root, bundle, key)
    restored = tmp_path / "restored"
    manifest = decrypt_bundle(bundle, restored, key)

    assert encrypted["backup_epoch_id"] == epoch
    assert manifest["backup_epoch_id"] == epoch
    assert validate_tree(restored)["bundle_id"] == manifest["bundle_id"]


def test_manifest_rejects_mixed_epochs_and_modified_file(tmp_path):
    root, epoch = _tree(tmp_path)
    manifest = json.loads((root / "recovery-manifest.json").read_text())
    manifest["components"]["secret-broker"]["backup_epoch_id"] = "other"
    (root / "recovery-manifest.json").write_text(json.dumps(manifest))

    with pytest.raises(ValueError, match="manifest differs"):
        validate_tree(root, epoch)


def test_encrypted_bundle_rejects_wrong_key(tmp_path):
    root, _epoch = _tree(tmp_path)
    bundle = tmp_path / "bundle.mwo-recovery"
    encrypt_tree(root, bundle, ensure_key(tmp_path / "key-a"))

    with pytest.raises(InvalidTag):
        decrypt_bundle(
            bundle,
            tmp_path / "restored",
            ensure_key(tmp_path / "key-b"),
        )
