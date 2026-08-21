"""SQLite-backed encrypted secret-set lifecycle."""

from __future__ import annotations

import json
import os
import sqlite3
import time
from pathlib import Path

from cryptography.hazmat.primitives.ciphers.aead import ChaCha20Poly1305

from .model import canonical_json, validate_secret_set


class SecretStore:
    def __init__(self, database_path, master_key_path):
        self.database_path = Path(database_path)
        self.master_key_path = Path(master_key_path)
        self._migrate()

    def _key(self):
        payload = self.master_key_path.read_bytes()
        if len(payload.strip()) == 64:
            try:
                payload = bytes.fromhex(payload.decode("ascii").strip())
            except (UnicodeDecodeError, ValueError) as error:
                raise RuntimeError("broker master key encoding is invalid") from error
        if len(payload) != 32:
            raise RuntimeError("broker master key must contain exactly 32 bytes")
        if self.master_key_path.stat().st_mode & 0o077:
            raise RuntimeError("broker master key permissions are too broad")
        return payload

    def connect(self):
        database = sqlite3.connect(self.database_path)
        database.row_factory = sqlite3.Row
        database.execute("PRAGMA journal_mode=WAL")
        database.execute("PRAGMA busy_timeout=10000")
        return database

    def _migrate(self):
        self.database_path.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
        with self.connect() as database:
            database.executescript(
                """
                CREATE TABLE IF NOT EXISTS secret_sets (
                  secret_set_id TEXT NOT NULL,
                  generation INTEGER NOT NULL,
                  lifecycle TEXT NOT NULL,
                  nonce BLOB NOT NULL,
                  ciphertext BLOB NOT NULL,
                  created_at INTEGER NOT NULL,
                  PRIMARY KEY(secret_set_id, generation)
                );
                CREATE UNIQUE INDEX IF NOT EXISTS one_active_secret_set
                ON secret_sets(lifecycle) WHERE lifecycle='ACTIVE';
                PRAGMA user_version=1;
                """
            )

    def put(self, document):
        validate_secret_set(document)
        nonce = os.urandom(12)
        aad = canonical_json(
            {
                "secret_set_id": document["secret_set_id"],
                "generation": document["generation"],
            }
        )
        ciphertext = ChaCha20Poly1305(self._key()).encrypt(
            nonce, canonical_json(document), aad
        )
        with self.connect() as database:
            database.execute("BEGIN IMMEDIATE")
            database.execute(
                """
                INSERT INTO secret_sets (
                  secret_set_id, generation, lifecycle, nonce, ciphertext,
                  created_at
                ) VALUES (?, ?, ?, ?, ?, ?)
                """,
                (
                    document["secret_set_id"],
                    document["generation"],
                    document["lifecycle"],
                    nonce,
                    ciphertext,
                    int(time.time()),
                ),
            )
        return self.metadata(document["secret_set_id"], document["generation"])

    def metadata(self, secret_set_id, generation):
        with self.connect() as database:
            row = database.execute(
                """
                SELECT secret_set_id, generation, lifecycle, created_at
                FROM secret_sets WHERE secret_set_id=? AND generation=?
                """,
                (secret_set_id, generation),
            ).fetchone()
        if row is None:
            raise KeyError("secret set does not exist")
        return dict(row)

    def active(self):
        return self.deliver("active")

    def deliver(self, mode):
        lifecycles = {
            "shadow": ("PREPARED", "CANARY_VERIFIED", "ACTIVE"),
            "canary": ("CANARY_VERIFIED", "ACTIVE"),
            "active": ("ACTIVE",),
        }.get(mode)
        if lifecycles is None:
            raise ValueError("invalid secret delivery mode")
        placeholders = ",".join("?" for _item in lifecycles)
        with self.connect() as database:
            row = database.execute(
                "SELECT * FROM secret_sets WHERE lifecycle IN (%s) "
                "ORDER BY generation DESC LIMIT 1" % placeholders,
                lifecycles,
            ).fetchone()
        if row is None:
            raise KeyError("deliverable secret set does not exist")
        aad = canonical_json(
            {"secret_set_id": row["secret_set_id"], "generation": row["generation"]}
        )
        plaintext = ChaCha20Poly1305(self._key()).decrypt(
            row["nonce"], row["ciphertext"], aad
        )
        document = json.loads(plaintext)
        document = validate_secret_set(document)
        if document["lifecycle"] != row["lifecycle"]:
            document = dict(document)
            document["lifecycle"] = row["lifecycle"]
        return document

    def transition(self, secret_set_id, generation, lifecycle, expected):
        transitions = {
            "PREPARED": {"CANARY_VERIFIED"},
            "CANARY_VERIFIED": {"ACTIVE"},
            "ACTIVE": {"RETIRING"},
            "RETIRING": {"RETIRED"},
        }
        if lifecycle not in transitions.get(expected, set()):
            raise ValueError("invalid lifecycle transition target")
        with self.connect() as database:
            database.execute("BEGIN IMMEDIATE")
            changed = database.execute(
                """
                UPDATE secret_sets SET lifecycle=?
                WHERE secret_set_id=? AND generation=? AND lifecycle=?
                """,
                (lifecycle, secret_set_id, generation, expected),
            ).rowcount
            if changed != 1:
                raise RuntimeError("secret-set lifecycle CAS failed")
        return self.metadata(secret_set_id, generation)

    def readiness(self):
        self._key()
        with self.connect() as database:
            integrity = database.execute("PRAGMA quick_check").fetchone()[0]
        if integrity != "ok":
            raise RuntimeError("broker database integrity check failed")
        return {"status": "ready", "schema": 1}
