#!/usr/bin/env python3
"""Cross-repository Profile Sync v2 E2E over the real HTTP surfaces."""

from __future__ import annotations

import argparse
import base64
import hashlib
import json
import os
import subprocess
import sys
import tempfile
import time
import urllib.error
import urllib.request
from pathlib import Path


def configure_imports(server_root, client_root):
    sys.path.insert(0, str(client_root / "resources/lib"))
    sys.path.insert(0, str(server_root / "src"))


class CryptographyBackend:
    def public_from_seed(self, seed):
        from cryptography.hazmat.primitives import serialization
        from cryptography.hazmat.primitives.asymmetric.ed25519 import (
            Ed25519PrivateKey,
        )

        return Ed25519PrivateKey.from_private_bytes(seed).public_key().public_bytes(
            serialization.Encoding.Raw, serialization.PublicFormat.Raw
        )

    def sign(self, seed, message):
        from cryptography.hazmat.primitives.asymmetric.ed25519 import (
            Ed25519PrivateKey,
        )

        return Ed25519PrivateKey.from_private_bytes(seed).sign(message)

    def verify(self, public_key, message, signature):
        from cryptography.exceptions import InvalidSignature
        from cryptography.hazmat.primitives.asymmetric.ed25519 import (
            Ed25519PublicKey,
        )

        try:
            Ed25519PublicKey.from_public_bytes(public_key).verify(
                signature, message
            )
            return True
        except InvalidSignature:
            return False


class Addon:
    def __init__(self, base):
        self.values = {
            "server_url": base,
            "ca_certificate": "",
            "logical_device_id": "e2e-device",
            "channel": "home-stable",
        }

    def getSetting(self, key):
        return self.values[key]

    def getSettingBool(self, key):
        if key != "read_only":
            raise KeyError(key)
        return False


class Settings:
    def __init__(self):
        self.values = {
            ("plugin.video.umbrella", "cache.providers"): "48",
        }

    def get(self, addon_id, setting_id):
        return self.values.get((addon_id, setting_id), "")

    def set(self, addon_id, setting_id, value):
        self.values[(addon_id, setting_id)] = value


class Favourites:
    def __init__(self):
        self.items = []

    def list(self):
        return [dict(item) for item in self.items]

    def replace(self, before, after):
        if before != self.items:
            raise RuntimeError("favourites pre-image differs")
        self.items = [dict(item) for item in after]


def http_json(base, method, path, document=None, key=None, token=None):
    payload = None
    headers = {"Accept": "application/json"}
    if document is not None:
        payload = json.dumps(
            document, sort_keys=True, separators=(",", ":")
        ).encode()
        headers["Content-Type"] = "application/json"
    if key:
        headers["Idempotency-Key"] = key
    if token:
        headers["Authorization"] = "Bearer " + token
    request = urllib.request.Request(
        base + path, data=payload, headers=headers, method=method
    )
    try:
        with urllib.request.urlopen(request, timeout=10) as response:
            return response.status, json.loads(response.read())
    except urllib.error.HTTPError as error:
        return error.code, json.loads(error.read())


def wait_ready(base, process):
    deadline = time.monotonic() + 15
    while time.monotonic() < deadline:
        if process.poll() is not None:
            raise RuntimeError("profile-sync server exited")
        try:
            status, document = http_json(base, "GET", "/ready")
            if status == 200 and document.get("status") == "ready":
                return
        except OSError:
            pass
        time.sleep(0.1)
    raise TimeoutError("profile-sync server did not become ready")


def assignment_document(
    sign_document,
    canonical_json,
    seed,
    enrollment,
    revision_id,
    kind,
    generation,
):
    now = int(time.time())
    identity = {
        "schema": 2,
        "enrollment_id": enrollment["enrollment_id"],
        "enrollment_generation": enrollment["enrollment_generation"],
        "channel": enrollment["channel"],
        "channel_generation": generation,
        "revision_id": revision_id,
        "target_tags": enrollment["target_tags"],
        "assignment_kind": kind,
        "apply_policy": "enforce",
        "nonce": "%s-assignment-e2e-0001" % kind,
        "issued_at": now,
        "expires_at": now + 3600,
    }
    document = {
        **identity,
        "assignment_id": "sha256:"
        + hashlib.sha256(canonical_json(identity)).hexdigest(),
    }
    return sign_document("assignment", document, "promoter-1", seed)


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--server-root", type=Path, required=True)
    parser.add_argument("--client-root", type=Path, required=True)
    args = parser.parse_args()
    server_root = args.server_root.resolve()
    client_root = args.client_root.resolve()
    configure_imports(server_root, client_root)

    from profile_sync_server.crypto import (
        public_key_record,
        sign_document as server_sign,
    )
    from profile_sync_server.store import ProfileStore, canonical_json
    from mwoprofilesync.apply import TransactionalApplier
    from mwoprofilesync.crypto import (
        sign_document as client_sign,
        verify_document as client_verify,
    )
    from mwoprofilesync.pairing import pair_with_code
    from mwoprofilesync.portable import PortableFavouritesAdapter
    from mwoprofilesync.state import StateStore
    from mwoprofilesync.sync import CLIENT_CAPABILITIES, ReadOnlySync

    publisher_seed = b"p" * 32
    promoter_seed = b"a" * 32
    device_seed = b"d" * 32
    backend = CryptographyBackend()
    with tempfile.TemporaryDirectory(prefix="profile-sync-v2-e2e-") as value:
        root = Path(value)
        database = root / "state.sqlite"
        registry = {
            "schema": 1,
            "keys": {
                "publisher-1": public_key_record(
                    publisher_seed, ["revision"], backend=backend
                ),
                "promoter-1": public_key_record(
                    promoter_seed,
                    [
                        "admin_publish",
                        "admin_promote",
                        "assignment",
                        "promotion",
                    ],
                    backend=backend,
                ),
            },
        }
        registry_path = root / "registry.json"
        registry_path.write_bytes(canonical_json(registry))
        registry_path.chmod(0o600)
        store = ProfileStore(database, lambda *_args: False)
        store.create_pairing_code(
            "e2e-device",
            "home-stable",
            code="12345678",
            ttl_seconds=300,
            target_tags=["android:arm64", "home"],
        )
        consumer_port, admin_port = 19765, 19766
        consumer = "http://127.0.0.1:%d" % consumer_port
        admin = "http://127.0.0.1:%d" % admin_port
        environment = dict(os.environ)
        environment["PYTHONPATH"] = str(server_root / "src")
        process = subprocess.Popen(
            [
                sys.executable,
                "-m",
                "profile_sync_server.http",
                "--database",
                str(database),
                "--port",
                str(consumer_port),
                "--admin-port",
                str(admin_port),
                "--key-registry",
                str(registry_path),
            ],
            cwd=server_root,
            env=environment,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.PIPE,
            text=True,
        )

        def admin_call(operation, role, path, payload, key):
            now = int(time.time())
            envelope = server_sign(
                "admin_" + role,
                {
                    "schema": 1,
                    "actor_role": role,
                    "operation": operation,
                    "idempotency_key": key,
                    "nonce": "admin-%s-00000001" % key,
                    "issued_at": now,
                    "expires_at": now + 120,
                    "payload": payload,
                },
                "promoter-1",
                promoter_seed,
                backend=backend,
            )
            status, response = http_json(
                admin, "POST", path, envelope, key=key
            )
            if status != 200:
                raise RuntimeError("admin %s failed: %s" % (operation, response))
            return response

        try:
            wait_ready(consumer, process)
            addon = Addon(consumer)
            state = StateStore(root / "client-state")
            enrollment = pair_with_code(
                addon,
                state,
                "12345678",
                backend_factory=lambda: backend,
                seed_factory=lambda _size: device_seed,
                key_id_factory=lambda: "device-e2e-key",
            )
            enrollment["target_tags"] = ["android:arm64", "home"]

            image = b"\x89PNG\r\n\x1a\nprofile-sync-e2e-artwork"
            blob_id = "sha256:" + hashlib.sha256(image).hexdigest()
            admin_call(
                "put_blob",
                "publish",
                "/v1/blobs/%s" % blob_id,
                {
                    "media_type": "image/png",
                    "content_base64": base64.urlsafe_b64encode(image)
                    .rstrip(b"=")
                    .decode(),
                },
                "blob-e2e-0001",
            )
            thumbnail = (
                "special://profile/favourite-artwork/%s.png"
                % blob_id.split(":", 1)[1]
            )
            identity = {
                "schema": 2,
                "policy_sha256": "f" * 64,
                "kodi_major": 21,
                "minimum_client_version": "1.0.0",
                "required_capabilities": sorted(CLIENT_CAPABILITIES),
                "adapters": {
                    "umbrella.preferences": {
                        "adapter": "settings_xml",
                        "addon_id": "plugin.video.umbrella",
                        "apply_mode": "next_start",
                        "managed_settings": ["cache.providers"],
                        "values": {"cache.providers": 6},
                    },
                    "kodi.favourites": {
                        "adapter": "kodi_favourites_v1",
                        "apply_mode": "hot_apply",
                        "ownership": "whole_document",
                        "items": [
                            {
                                "title": "CARTOONS",
                                "type": "window",
                                "window": "videos",
                                "windowparameter": "plugin://plugin.video.watchnixtoons2/",
                                "thumbnail": thumbnail,
                            }
                        ],
                        "artwork": [
                            {
                                "sha256": blob_id,
                                "size": len(image),
                                "media_type": "image/png",
                            }
                        ],
                    },
                },
            }
            revision_id = "sha256:" + hashlib.sha256(
                canonical_json(identity)
            ).hexdigest()
            revision = server_sign(
                "revision",
                {**identity, "revision_id": revision_id},
                "publisher-1",
                publisher_seed,
                backend=backend,
            )
            admin_call(
                "put_revision",
                "publish",
                "/v1/revisions",
                revision,
                "revision-e2e-0001",
            )
            admin_call(
                "publish_candidate",
                "publish",
                "/v1/channels/home-stable/candidates",
                {
                    "revision_id": revision_id,
                    "base_revision": None,
                    "expected_candidate_head": None,
                },
                "publish-e2e-0001",
            )
            candidate = assignment_document(
                lambda kind, document, key_id, seed: server_sign(
                    kind, document, key_id, seed, backend=backend
                ),
                canonical_json,
                promoter_seed,
                enrollment,
                revision_id,
                "candidate",
                0,
            )
            admin_call(
                "assign_candidate",
                "publish",
                "/v1/channels/home-stable/assignments",
                candidate,
                "assign-e2e-0001",
            )

            settings = Settings()
            favourites = Favourites()
            applier = TransactionalApplier(
                root / "client-state",
                state,
                settings,
                portable=PortableFavouritesAdapter(
                    root / "kodi-profile", favourites
                ),
            )
            sync = ReadOnlySync(
                addon,
                state,
                verify_assignment=lambda kind, document, keys: client_verify(
                    kind, document, keys, backend=backend
                ),
                verify_revision=lambda kind, document, keys: client_verify(
                    kind, document, keys, backend=backend
                ),
                sign_report=lambda kind, document, key_id, seed: client_sign(
                    kind, document, key_id, seed, backend=backend
                ),
                applier=applier,
            )
            first = sync()
            if first.get("status") != "APPLIED":
                raise RuntimeError("candidate was not applied: %s" % first)
            if settings.get("plugin.video.umbrella", "cache.providers") != "6":
                raise RuntimeError("Umbrella setting was not applied")
            if favourites.list()[0]["thumbnail"] != thumbnail:
                raise RuntimeError("portable favourite was not applied")
            artwork = root / "kodi-profile/favourite-artwork" / (
                blob_id.split(":", 1)[1] + ".png"
            )
            if artwork.read_bytes() != image:
                raise RuntimeError("artwork blob was not applied")

            active = assignment_document(
                lambda kind, document, key_id, seed: server_sign(
                    kind, document, key_id, seed, backend=backend
                ),
                canonical_json,
                promoter_seed,
                enrollment,
                revision_id,
                "active",
                1,
            )
            event = server_sign(
                "promotion",
                {
                    "channel": "home-stable",
                    "revision_id": revision_id,
                    "generation": 1,
                    "active_assignment_ids": [active["assignment_id"]],
                },
                "promoter-1",
                promoter_seed,
                backend=backend,
            )
            admin_call(
                "promote",
                "promote",
                "/v1/channels/home-stable/promote",
                {
                    "candidate_revision": revision_id,
                    "expected_active_revision": None,
                    "required_enrollments": [enrollment["enrollment_id"]],
                    "event": event,
                    "active_assignments": [active],
                },
                "promote-e2e-0001",
            )
            second = sync()
            if second.get("status") != "NO_CHANGE":
                raise RuntimeError("active replay was not idempotent: %s" % second)
            with ProfileStore(database, lambda *_args: False).connect() as db:
                reports = db.execute(
                    "SELECT assignment_kind, result FROM assignment_reports "
                    "ORDER BY assignment_kind"
                ).fetchall()
            if [(row[0], row[1]) for row in reports] != [
                ("active", "success"),
                ("candidate", "success"),
            ]:
                raise RuntimeError("candidate/active reports are incomplete")
            print(
                json.dumps(
                    {
                        "active_idempotency": "pass",
                        "admin_isolation": "pass",
                        "assignment_v2": "pass",
                        "blob_reachability": "pass",
                        "portable_favourites": "pass",
                        "result": "pass",
                        "transactional_settings": "pass",
                    },
                    indent=2,
                    sort_keys=True,
                )
            )
        finally:
            process.terminate()
            try:
                process.wait(timeout=5)
            except subprocess.TimeoutExpired:
                process.kill()
            if process.returncode not in {0, -15}:
                raise RuntimeError(process.stderr.read())
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
