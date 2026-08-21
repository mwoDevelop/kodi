import os

import pytest
from pyhpke import AEADId, CipherSuite, KDFId, KEMId

from kodi_secret_broker.crypto import open_envelope, seal
from kodi_secret_broker.model import envelope_aad
from kodi_secret_broker.store import SecretStore


def secret_set(lifecycle="PREPARED"):
    return {
        "schema": 1,
        "secret_type": "youtube-session-v1",
        "secret_set_id": "youtube-home",
        "generation": 1,
        "lifecycle": lifecycle,
        "addon_id": "plugin.video.youtube",
        "addon_version": "7.4.4",
        "adapter": "youtube-oauth-v1",
        "created_utc": "2026-08-21T12:00:00Z",
        "verified_utc": "2026-08-21T12:00:00Z",
        "secret": {
            "account_hint": "account@example.invalid",
            "api_key": "api",
            "client_id": "client",
            "client_secret": "secret",
            "tv_refresh_token": "tv",
            "personal_refresh_token": "personal",
            "vr_refresh_token": "vr",
            "expected_channel_id": "channel",
        },
    }


def metadata():
    return {
        "schema": 1,
        "envelope_type": "secret-envelope-v1",
        "secret_type": "youtube-session-v1",
        "secret_set_id": "youtube-home",
        "secret_set_generation": 1,
        "secret_lifecycle": "ACTIVE",
        "logical_device_id": "x88pro20",
        "enrollment_id": "enr:abcdefghijklmnop",
        "enrollment_generation": 2,
        "encryption_key_id": "x25519-key-1",
        "adapter": "youtube-oauth-v1",
        "addon_id": "plugin.video.youtube",
        "addon_version": "7.4.4",
        "nonce": "env-0123456789abcdef",
        "issued_at": 2_000_000_000,
        "expires_at": 2_000_000_900,
    }


def key_pair():
    suite = CipherSuite.new(
        KEMId.DHKEM_X25519_HKDF_SHA256,
        KDFId.HKDF_SHA256,
        AEADId.CHACHA20_POLY1305,
    )
    pair = suite.kem.derive_key_pair(b"k" * 32)
    from kodi_secret_broker.model import b64url_encode

    return (
        b64url_encode(pair.public_key.to_public_bytes()),
        b64url_encode(pair.private_key.to_private_bytes()),
    )


def test_hpke_round_trip_and_aad_tamper_rejected():
    public, private = key_pair()
    envelope = seal(metadata(), public, {"value": "canary"})
    assert open_envelope(envelope, private) == {"value": "canary"}
    envelope["logical_device_id"] = "other-device"
    with pytest.raises(Exception):
        open_envelope(envelope, private)


def test_store_encrypts_at_rest_and_uses_lifecycle_cas(tmp_path):
    key = tmp_path / "master.key"
    key.write_bytes(os.urandom(32))
    key.chmod(0o600)
    store = SecretStore(tmp_path / "broker.db", key)
    store.put(secret_set())
    raw = (tmp_path / "broker.db").read_bytes()
    assert b"personal" not in raw
    store.transition("youtube-home", 1, "CANARY_VERIFIED", "PREPARED")
    store.transition("youtube-home", 1, "ACTIVE", "CANARY_VERIFIED")
    assert store.active()["secret"]["tv_refresh_token"] == "tv"
    with pytest.raises(ValueError):
        store.transition("youtube-home", 1, "RETIRED", "PREPARED")


def test_delivery_modes_enforce_lifecycle(tmp_path):
    key = tmp_path / "master.key"
    key.write_bytes(os.urandom(32))
    key.chmod(0o600)
    store = SecretStore(tmp_path / "broker.db", key)
    store.put(secret_set())
    assert store.deliver("shadow")["lifecycle"] == "PREPARED"
    with pytest.raises(KeyError):
        store.deliver("canary")
    store.transition("youtube-home", 1, "CANARY_VERIFIED", "PREPARED")
    assert store.deliver("canary")["lifecycle"] == "CANARY_VERIFIED"
    with pytest.raises(KeyError):
        store.deliver("active")


def test_envelope_rejects_excessive_lifetime():
    value = metadata()
    value["expires_at"] = value["issued_at"] + 86401
    with pytest.raises(ValueError, match="lifetime"):
        envelope_aad(value)
