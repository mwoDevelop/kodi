"""Strict public models for YouTube secret sets and HPKE envelopes."""

from __future__ import annotations

import base64
import datetime as dt
import json
import re


SECRET_TYPE = "youtube-session-v1"
ENVELOPE_TYPE = "secret-envelope-v1"
LIFECYCLE = {
    "PREPARED",
    "CANARY_VERIFIED",
    "ACTIVE",
    "RETIRING",
    "RETIRED",
}
ADDON_ID = "plugin.video.youtube"
IDENTIFIER = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._:-]{0,127}$")
ENROLLMENT = re.compile(r"^enr:[A-Za-z0-9_-]{16,64}$")
DELIVERY_MODES = {"shadow", "canary", "active"}


def canonical_json(value):
    return json.dumps(
        value, sort_keys=True, separators=(",", ":"), ensure_ascii=False
    ).encode("utf-8")


def b64url_encode(payload):
    return base64.urlsafe_b64encode(payload).rstrip(b"=").decode("ascii")


def b64url_decode(value, expected_size=None):
    if (
        not isinstance(value, str)
        or not value
        or "=" in value
        or not re.fullmatch(r"[A-Za-z0-9_-]+", value)
    ):
        raise ValueError("invalid canonical base64url")
    payload = base64.urlsafe_b64decode(value + "=" * (-len(value) % 4))
    if b64url_encode(payload) != value:
        raise ValueError("non-canonical base64url")
    if expected_size is not None and len(payload) != expected_size:
        raise ValueError("invalid base64url size")
    return payload


def utc_now():
    return (
        dt.datetime.now(dt.timezone.utc)
        .replace(microsecond=0)
        .isoformat()
        .replace("+00:00", "Z")
    )


def validate_secret_set(document):
    if not isinstance(document, dict) or document.get("schema") != 1:
        raise ValueError("unsupported YouTube secret-set schema")
    if document.get("secret_type") != SECRET_TYPE:
        raise ValueError("invalid secret type")
    if (
        not isinstance(document.get("secret_set_id"), str)
        or not IDENTIFIER.fullmatch(document["secret_set_id"])
        or not isinstance(document.get("generation"), int)
        or document["generation"] < 1
        or document.get("lifecycle") not in LIFECYCLE
        or document.get("addon_id") != ADDON_ID
        or not re.fullmatch(r"[0-9]+(?:\.[0-9]+){1,3}", str(document.get("addon_version", "")))
        or document.get("adapter") != "youtube-oauth-v1"
    ):
        raise ValueError("invalid YouTube secret-set metadata")
    secret = document.get("secret")
    required = {
        "account_hint",
        "api_key",
        "client_id",
        "client_secret",
        "tv_refresh_token",
        "personal_refresh_token",
        "vr_refresh_token",
        "expected_channel_id",
    }
    if (
        not isinstance(secret, dict)
        or set(secret) != required
        or any(not isinstance(secret[name], str) or not secret[name] for name in required)
    ):
        raise ValueError("invalid YouTube secret payload")
    for name in ("created_utc", "verified_utc"):
        if not isinstance(document.get(name), str) or not document[name].endswith("Z"):
            raise ValueError("invalid secret-set timestamp")
    return document


def validate_envelope_request(document):
    required = {
        "delivery_mode",
        "logical_device_id",
        "enrollment_id",
        "enrollment_generation",
        "encryption_key_id",
        "encryption_public_key",
    }
    if not isinstance(document, dict) or set(document) != required:
        raise ValueError("invalid envelope request fields")
    if document["delivery_mode"] not in DELIVERY_MODES:
        raise ValueError("invalid secret delivery mode")
    if not ENROLLMENT.fullmatch(str(document["enrollment_id"])):
        raise ValueError("invalid envelope enrollment")
    if (
        not isinstance(document["enrollment_generation"], int)
        or document["enrollment_generation"] < 1
    ):
        raise ValueError("invalid envelope enrollment generation")
    for name in ("logical_device_id", "encryption_key_id"):
        if not IDENTIFIER.fullmatch(str(document[name])):
            raise ValueError("invalid envelope request identifier")
    b64url_decode(document["encryption_public_key"], expected_size=32)
    return document


def envelope_aad(metadata):
    required = {
        "schema",
        "envelope_type",
        "secret_type",
        "secret_set_id",
        "secret_set_generation",
        "secret_lifecycle",
        "logical_device_id",
        "enrollment_id",
        "enrollment_generation",
        "encryption_key_id",
        "adapter",
        "addon_id",
        "addon_version",
        "nonce",
        "issued_at",
        "expires_at",
    }
    if not isinstance(metadata, dict) or set(metadata) != required:
        raise ValueError("invalid envelope metadata fields")
    if metadata["schema"] != 1 or metadata["envelope_type"] != ENVELOPE_TYPE:
        raise ValueError("invalid envelope schema")
    if metadata["secret_type"] != SECRET_TYPE:
        raise ValueError("invalid envelope secret type")
    if metadata["secret_lifecycle"] not in LIFECYCLE:
        raise ValueError("invalid envelope lifecycle")
    if not ENROLLMENT.fullmatch(str(metadata["enrollment_id"])):
        raise ValueError("invalid envelope enrollment")
    if any(
        not isinstance(metadata[name], int) or metadata[name] < 1
        for name in ("secret_set_generation", "enrollment_generation")
    ):
        raise ValueError("invalid envelope generation")
    if (
        not isinstance(metadata["issued_at"], int)
        or not isinstance(metadata["expires_at"], int)
        or metadata["expires_at"] <= metadata["issued_at"]
        or metadata["expires_at"] - metadata["issued_at"] > 86400
    ):
        raise ValueError("invalid envelope lifetime")
    for name in (
        "secret_set_id",
        "logical_device_id",
        "encryption_key_id",
        "nonce",
    ):
        if not IDENTIFIER.fullmatch(str(metadata[name])):
            raise ValueError("invalid envelope identifier")
    return canonical_json(metadata)
