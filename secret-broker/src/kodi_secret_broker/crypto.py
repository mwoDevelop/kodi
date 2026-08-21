"""RFC 9180 HPKE suite fixed by ADR-0005."""

from __future__ import annotations

from pyhpke import AEADId, CipherSuite, KDFId, KEMId

from .model import b64url_decode, b64url_encode, canonical_json, envelope_aad


SUITE = CipherSuite.new(
    KEMId.DHKEM_X25519_HKDF_SHA256,
    KDFId.HKDF_SHA256,
    AEADId.CHACHA20_POLY1305,
)
INFO = b"mwo-kodi/secret-envelope-v1"


def seal(metadata, recipient_public_key, payload):
    aad = envelope_aad(metadata)
    public_key = SUITE.kem.deserialize_public_key(
        b64url_decode(recipient_public_key, 32)
    )
    encapsulated, context = SUITE.create_sender_context(
        public_key, info=INFO
    )
    ciphertext = context.seal(canonical_json(payload), aad=aad)
    return {
        **metadata,
        "suite": "DHKEM_X25519_HKDF_SHA256/HKDF_SHA256/CHACHA20_POLY1305",
        "enc": b64url_encode(encapsulated),
        "ciphertext": b64url_encode(ciphertext),
    }


def open_envelope(document, recipient_private_key):
    metadata = {
        key: value
        for key, value in document.items()
        if key not in {"suite", "enc", "ciphertext"}
    }
    if document.get("suite") != (
        "DHKEM_X25519_HKDF_SHA256/HKDF_SHA256/CHACHA20_POLY1305"
    ):
        raise ValueError("unsupported HPKE suite")
    private_key = SUITE.kem.deserialize_private_key(
        b64url_decode(recipient_private_key, 32)
    )
    context = SUITE.create_recipient_context(
        b64url_decode(document["enc"], 32),
        private_key,
        info=INFO,
    )
    plaintext = context.open(
        b64url_decode(document["ciphertext"]),
        aad=envelope_aad(metadata),
    )
    import json

    result = json.loads(plaintext)
    if not isinstance(result, dict):
        raise ValueError("decrypted secret is not an object")
    return result
