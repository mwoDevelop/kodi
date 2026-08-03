import base64
import hashlib
import json
import stat

import pytest
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey

from tools.profile_sync_admin import (
    DOMAIN,
    canonical_json,
    request,
    sign_admin_request,
    sign_assignment_v2,
    sign_bootstrap_assignment,
    validate_base_url,
    write_private_document,
)


def test_admin_url_requires_https_or_loopback():
    assert validate_base_url("https://127.0.0.1:8766/") == (
        "https://127.0.0.1:8766"
    )
    assert validate_base_url("http://127.0.0.1:8765") == (
        "http://127.0.0.1:8765"
    )
    with pytest.raises(ValueError, match="loopback listener"):
        validate_base_url("http://private-nas:8765")
    with pytest.raises(ValueError, match="loopback listener"):
        validate_base_url("https://profiles.example.test")


def test_admin_rejects_ca_for_plain_loopback_http():
    with pytest.raises(ValueError, match="requires an HTTPS"):
        request(
            "http://127.0.0.1:8765",
            "GET",
            "/health",
            ca_certificate="ca.pem",
        )


def _b64(value):
    return base64.urlsafe_b64encode(value).rstrip(b"=").decode("ascii")


def test_bootstrap_assignment_uses_private_matching_offline_key(tmp_path):
    seed = b"s" * 32
    private = Ed25519PrivateKey.from_private_bytes(seed)
    public = private.public_key().public_bytes(
        serialization.Encoding.Raw, serialization.PublicFormat.Raw
    )
    seeds = tmp_path / "seeds.json"
    registry = tmp_path / "registry.json"
    seeds.write_text(json.dumps({"promoter-production": _b64(seed)}))
    registry.write_text(
        json.dumps(
            {
                "schema": 1,
                "keys": {
                    "promoter-production": {
                        "public_key": _b64(public),
                        "allowed_kinds": ["assignment", "promotion"],
                    }
                },
            }
        )
    )
    seeds.chmod(0o600)
    registry.chmod(0o600)
    document = sign_bootstrap_assignment(
        "home-stable",
        "enr:bootstrap-device-0001",
        "sha256:" + "a" * 64,
        ["linux-flatpak:x86_64", "home"],
        "promoter-production",
        seeds,
        registry,
    )
    unsigned = {key: value for key, value in document.items() if key != "signature"}
    signature = base64.urlsafe_b64decode(
        document["signature"]["value"] + "=="
    )
    private.public_key().verify(
        signature, DOMAIN + b"assignment\0" + canonical_json(unsigned)
    )
    assert document["target_tags"] == ["home", "linux-flatpak:x86_64"]

    output = tmp_path / "private" / "bootstrap.json"
    assert write_private_document(output, document) is True
    assert stat.S_IMODE(output.stat().st_mode) == 0o600
    assert json.loads(output.read_text()) == document
    assert write_private_document(output, document) is False
    output.write_text("{}\n")
    output.chmod(0o600)
    with pytest.raises(ValueError, match="already differs"):
        write_private_document(output, document)


def test_bootstrap_assignment_rejects_broad_permissions_and_wrong_key(tmp_path):
    seeds = tmp_path / "seeds.json"
    registry = tmp_path / "registry.json"
    seeds.write_text(json.dumps({"promoter": _b64(b"s" * 32)}))
    registry.write_text(
        json.dumps(
            {
                "keys": {
                    "promoter": {
                        "public_key": _b64(b"p" * 32),
                        "allowed_kinds": ["assignment"],
                    }
                }
            }
        )
    )
    seeds.chmod(0o644)
    registry.chmod(0o600)
    values = (
        "home-stable",
        "enr:bootstrap-device-0001",
        "sha256:" + "a" * 64,
        ["home"],
        "promoter",
        seeds,
        registry,
    )
    with pytest.raises(ValueError, match="permissions are too broad"):
        sign_bootstrap_assignment(*values)
    seeds.chmod(0o600)
    with pytest.raises(ValueError, match="does not match"):
        sign_bootstrap_assignment(*values)


def test_admin_request_binds_role_operation_idempotency_and_payload(tmp_path):
    seed = b"a" * 32
    private = Ed25519PrivateKey.from_private_bytes(seed)
    public = private.public_key().public_bytes(
        serialization.Encoding.Raw, serialization.PublicFormat.Raw
    )
    seeds = tmp_path / "seeds.json"
    registry = tmp_path / "registry.json"
    seeds.write_text(json.dumps({"publisher-admin": _b64(seed)}))
    registry.write_text(
        json.dumps(
            {
                "schema": 1,
                "keys": {
                    "publisher-admin": {
                        "public_key": _b64(public),
                        "allowed_kinds": ["admin_publish"],
                    }
                },
            }
        )
    )
    seeds.chmod(0o600)
    registry.chmod(0o600)

    document = sign_admin_request(
        "publish_candidate",
        {"revision_id": "sha256:" + "a" * 64},
        "publish",
        "publish-admin-0001",
        "publisher-admin",
        seeds,
        registry,
        now=1234,
        nonce="admin-request-nonce-0001",
    )

    unsigned = {
        key: value for key, value in document.items() if key != "signature"
    }
    signature = base64.urlsafe_b64decode(
        document["signature"]["value"] + "=="
    )
    private.public_key().verify(
        signature,
        DOMAIN + b"admin_publish\0" + canonical_json(unsigned),
    )
    assert document["actor_role"] == "publish"
    assert document["operation"] == "publish_candidate"
    assert document["idempotency_key"] == "publish-admin-0001"


def test_assignment_v2_has_deterministic_identity_and_signed_policy(tmp_path):
    seed = b"v" * 32
    private = Ed25519PrivateKey.from_private_bytes(seed)
    public = private.public_key().public_bytes(
        serialization.Encoding.Raw, serialization.PublicFormat.Raw
    )
    seeds = tmp_path / "seeds.json"
    registry = tmp_path / "registry.json"
    seeds.write_text(json.dumps({"assignment-production": _b64(seed)}))
    registry.write_text(
        json.dumps(
            {
                "keys": {
                    "assignment-production": {
                        "public_key": _b64(public),
                        "allowed_kinds": ["assignment"],
                    }
                }
            }
        )
    )
    seeds.chmod(0o600)
    registry.chmod(0o600)

    document = sign_assignment_v2(
        "home-stable",
        "enr:assignment-device-0001",
        3,
        7,
        "sha256:" + "b" * 64,
        ["home", "android:arm64"],
        "active",
        "observe",
        "assignment-production",
        seeds,
        registry,
        now=1000,
        ttl_seconds=3600,
        nonce="assignment-nonce-0001",
    )
    unsigned = {
        key: value for key, value in document.items() if key != "signature"
    }
    identity = {
        key: value for key, value in unsigned.items() if key != "assignment_id"
    }

    assert document["assignment_id"] == (
        "sha256:" + hashlib.sha256(canonical_json(identity)).hexdigest()
    )
    assert document["target_tags"] == ["android:arm64", "home"]
    assert document["apply_policy"] == "observe"
    private.public_key().verify(
        base64.urlsafe_b64decode(document["signature"]["value"] + "=="),
        DOMAIN + b"assignment\0" + canonical_json(unsigned),
    )
