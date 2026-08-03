#!/usr/bin/env python3
"""Administrative CLI for the Kodi profile-sync API."""

from __future__ import annotations

import argparse
import base64
import hashlib
import json
import os
import re
import secrets
import ssl
import stat
import tempfile
import time
from pathlib import Path
from urllib.error import HTTPError
from urllib.parse import urlencode, urlparse
from urllib.request import Request, urlopen


DOMAIN = b"mwo-profile-sync/signed-document/v1\0"
KEY_ID = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._:-]{0,127}$")
CHANNEL = re.compile(r"^[a-z0-9][a-z0-9._-]{0,63}$")
ENROLLMENT = re.compile(r"^enr:[A-Za-z0-9._-]{8,128}$")
REVISION = re.compile(r"^sha256:[a-f0-9]{64}$")
TARGET_TAG = re.compile(r"^[a-z0-9][a-z0-9._:-]{0,63}$")


def validate_base_url(value):
    parsed = urlparse(value)
    if parsed.scheme in {"http", "https"} and parsed.hostname in {
        "127.0.0.1",
        "::1",
        "localhost",
    }:
        return value.rstrip("/")
    raise ValueError("admin API must use a loopback listener or SSH forward")


def request(
    base,
    method,
    path,
    document=None,
    idempotency_key=None,
    ca_certificate=None,
):
    payload = None
    headers = {"Accept": "application/json"}
    if document is not None:
        payload = json.dumps(document).encode("utf-8")
        headers["Content-Type"] = "application/json"
    if idempotency_key:
        headers["Idempotency-Key"] = idempotency_key
    try:
        options = {"timeout": 15}
        if base.startswith("https://"):
            options["context"] = ssl.create_default_context(
                cafile=str(Path(ca_certificate).resolve())
                if ca_certificate
                else None
            )
        elif ca_certificate:
            raise ValueError("CA certificate requires an HTTPS admin API")
        with urlopen(
            Request(base + path, data=payload, headers=headers, method=method),
            **options,
        ) as response:
            return json.loads(response.read())
    except HTTPError as error:
        detail = error.read().decode("utf-8", "replace")
        raise RuntimeError(
            "profile-sync API returned HTTP %d: %s" % (error.code, detail)
        ) from error


def load_document(path):
    return json.loads(Path(path).read_text(encoding="utf-8"))


def canonical_json(value):
    return json.dumps(
        value, sort_keys=True, separators=(",", ":"), ensure_ascii=False
    ).encode("utf-8")


def _private_json(path):
    source = Path(path).expanduser().resolve()
    metadata = source.stat()
    if not stat.S_ISREG(metadata.st_mode):
        raise ValueError("private signing input must be a regular file")
    if stat.S_IMODE(metadata.st_mode) & 0o077:
        raise ValueError("private signing input permissions are too broad")
    return json.loads(source.read_text(encoding="utf-8"))


def _decode_base64url(value, size, label):
    if (
        not isinstance(value, str)
        or not value
        or "=" in value
        or not re.fullmatch(r"[A-Za-z0-9_-]+", value)
    ):
        raise ValueError("%s is not canonical base64url" % label)
    try:
        payload = base64.b64decode(
            value + "=" * (-len(value) % 4), altchars=b"-_", validate=True
        )
    except (ValueError, base64.binascii.Error) as error:
        raise ValueError("%s is not canonical base64url" % label) from error
    encoded = base64.urlsafe_b64encode(payload).rstrip(b"=").decode("ascii")
    if len(payload) != size or encoded != value:
        raise ValueError("%s has an invalid encoding or size" % label)
    return payload


def sign_with_registry(kind, document, key_id, seed_file, key_registry):
    if not KEY_ID.fullmatch(str(key_id)):
        raise ValueError("invalid signing key id")
    seeds = _private_json(seed_file)
    registry = _private_json(key_registry)
    record = registry.get("keys", {}).get(key_id)
    if (
        not isinstance(record, dict)
        or kind not in record.get("allowed_kinds", [])
    ):
        raise ValueError("signing key is not authorized for %s" % kind)
    seed = _decode_base64url(seeds.get(key_id), 32, "signing seed")
    expected_public = _decode_base64url(
        record.get("public_key"), 32, "registry public key"
    )
    try:
        from cryptography.hazmat.primitives import serialization
        from cryptography.hazmat.primitives.asymmetric.ed25519 import (
            Ed25519PrivateKey,
        )
    except ImportError as error:
        raise RuntimeError("cryptography is required for offline signing") from error
    private = Ed25519PrivateKey.from_private_bytes(seed)
    actual_public = private.public_key().public_bytes(
        serialization.Encoding.Raw,
        serialization.PublicFormat.Raw,
    )
    if actual_public != expected_public:
        raise ValueError("signing seed does not match the trusted registry")
    output = dict(document)
    payload = DOMAIN + kind.encode("ascii") + b"\0" + canonical_json(output)
    output["signature"] = {
        "algorithm": "Ed25519",
        "key_id": key_id,
        "value": base64.urlsafe_b64encode(private.sign(payload))
        .rstrip(b"=")
        .decode("ascii"),
    }
    return output


def sign_admin_request(
    operation,
    payload,
    role,
    idempotency_key,
    key_id,
    seed_file,
    key_registry,
    now=None,
    nonce=None,
):
    if role not in {"publish", "promote", "admin"}:
        raise ValueError("invalid admin actor role")
    if not isinstance(idempotency_key, str) or len(idempotency_key) < 8:
        raise ValueError("invalid idempotency key")
    now = int(time.time()) if now is None else int(now)
    document = {
        "schema": 1,
        "actor_role": role,
        "operation": operation,
        "idempotency_key": idempotency_key,
        "nonce": nonce or ("admin-" + secrets.token_urlsafe(18)),
        "issued_at": now,
        "expires_at": now + 120,
        "payload": payload,
    }
    kind = "admin" if role == "admin" else "admin_" + role
    return sign_with_registry(
        kind, document, key_id, seed_file, key_registry
    )


def sign_assignment_v2(
    channel,
    enrollment_id,
    enrollment_generation,
    channel_generation,
    revision_id,
    target_tags,
    assignment_kind,
    apply_policy,
    key_id,
    seed_file,
    key_registry,
    now=None,
    ttl_seconds=24 * 60 * 60,
    nonce=None,
):
    if not CHANNEL.fullmatch(str(channel)):
        raise ValueError("invalid channel")
    if not ENROLLMENT.fullmatch(str(enrollment_id)):
        raise ValueError("invalid enrollment")
    if not isinstance(enrollment_generation, int) or enrollment_generation < 1:
        raise ValueError("invalid enrollment generation")
    if not isinstance(channel_generation, int) or channel_generation < 0:
        raise ValueError("invalid channel generation")
    if not REVISION.fullmatch(str(revision_id)):
        raise ValueError("invalid revision")
    if assignment_kind not in {"candidate", "active"}:
        raise ValueError("invalid assignment kind")
    if apply_policy not in {"observe", "enforce"}:
        raise ValueError("invalid apply policy")
    if (
        len(target_tags) != len(set(target_tags))
        or len(target_tags) > 16
        or any(not TARGET_TAG.fullmatch(str(tag)) for tag in target_tags)
    ):
        raise ValueError("invalid target tags")
    if not isinstance(ttl_seconds, int) or not 60 <= ttl_seconds <= 7 * 86400:
        raise ValueError("invalid assignment TTL")
    now = int(time.time()) if now is None else int(now)
    identity = {
        "schema": 2,
        "enrollment_id": enrollment_id,
        "enrollment_generation": enrollment_generation,
        "channel": channel,
        "channel_generation": channel_generation,
        "revision_id": revision_id,
        "target_tags": sorted(target_tags),
        "assignment_kind": assignment_kind,
        "apply_policy": apply_policy,
        "nonce": nonce or ("assignment-" + secrets.token_urlsafe(18)),
        "issued_at": now,
        "expires_at": now + ttl_seconds,
    }
    document = {
        **identity,
        "assignment_id": "sha256:"
        + hashlib.sha256(canonical_json(identity)).hexdigest(),
    }
    return sign_with_registry(
        "assignment", document, key_id, seed_file, key_registry
    )


def sign_bootstrap_assignment(
    channel,
    enrollment_id,
    revision_id,
    target_tags,
    key_id,
    seed_file,
    key_registry,
):
    if not CHANNEL.fullmatch(str(channel)):
        raise ValueError("invalid channel")
    if not ENROLLMENT.fullmatch(str(enrollment_id)):
        raise ValueError("invalid enrollment")
    if not REVISION.fullmatch(str(revision_id)):
        raise ValueError("invalid revision")
    if not KEY_ID.fullmatch(str(key_id)):
        raise ValueError("invalid signing key id")
    if (
        len(target_tags) != len(set(target_tags))
        or len(target_tags) > 16
        or any(not TARGET_TAG.fullmatch(str(tag)) for tag in target_tags)
    ):
        raise ValueError("invalid target tags")
    document = {
        "channel": channel,
        "enrollment_id": enrollment_id,
        "revision_id": revision_id,
        "target_tags": sorted(target_tags),
    }
    return sign_with_registry(
        "assignment", document, key_id, seed_file, key_registry
    )


def write_private_document(path, document):
    destination = Path(path).expanduser().resolve()
    destination.parent.mkdir(parents=True, exist_ok=True)
    payload = canonical_json(document) + b"\n"
    if destination.exists():
        metadata = destination.lstat()
        if (
            not stat.S_ISREG(metadata.st_mode)
            or destination.is_symlink()
            or stat.S_IMODE(metadata.st_mode) & 0o077
        ):
            raise ValueError("existing bootstrap document is not private")
        if destination.read_bytes() != payload:
            raise ValueError("bootstrap document output already differs")
        return False
    descriptor, temporary_name = tempfile.mkstemp(
        prefix=".%s." % destination.name, dir=str(destination.parent)
    )
    temporary = Path(temporary_name)
    try:
        with os.fdopen(descriptor, "wb") as handle:
            handle.write(payload)
            handle.flush()
            os.fsync(handle.fileno())
        os.chmod(temporary, 0o600)
        try:
            os.link(temporary, destination)
        except FileExistsError as error:
            raise ValueError("bootstrap document output already exists") from error
    finally:
        temporary.unlink(missing_ok=True)
    return True


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--base", default="http://127.0.0.1:8766")
    parser.add_argument("--ca-certificate")
    parser.add_argument("--admin-key-id")
    parser.add_argument("--admin-seed-file")
    parser.add_argument("--admin-key-registry")
    subparsers = parser.add_subparsers(dest="command", required=True)
    subparsers.add_parser("health")
    revision = subparsers.add_parser("put-revision")
    revision.add_argument("manifest")
    revision.add_argument("--idempotency-key", required=True)
    blob = subparsers.add_parser("put-blob")
    blob.add_argument("path")
    blob.add_argument(
        "--media-type",
        choices=("image/jpeg", "image/png", "image/webp"),
        required=True,
    )
    blob.add_argument("--idempotency-key", required=True)
    publish = subparsers.add_parser("publish-candidate")
    publish.add_argument("channel")
    publish.add_argument("revision_id")
    publish.add_argument("--base-revision")
    publish.add_argument("--expected-candidate-head")
    publish.add_argument("--idempotency-key", required=True)
    assignment = subparsers.add_parser("assign")
    assignment.add_argument("channel")
    assignment.add_argument("document")
    assignment.add_argument("--idempotency-key", required=True)
    bootstrap = subparsers.add_parser("bootstrap-active")
    bootstrap.add_argument("channel")
    bootstrap.add_argument("enrollment_id")
    bootstrap.add_argument("revision_id")
    bootstrap.add_argument("--target-tag", action="append", default=[])
    bootstrap.add_argument("--key-id", required=True)
    bootstrap.add_argument("--seed-file", required=True)
    bootstrap.add_argument("--key-registry", required=True)
    bootstrap.add_argument("--document-output", required=True)
    bootstrap.add_argument("--idempotency-key", required=True)
    signed_assignment = subparsers.add_parser("sign-assignment-v2")
    signed_assignment.add_argument("channel")
    signed_assignment.add_argument("enrollment_id")
    signed_assignment.add_argument("enrollment_generation", type=int)
    signed_assignment.add_argument("channel_generation", type=int)
    signed_assignment.add_argument("revision_id")
    signed_assignment.add_argument(
        "--assignment-kind",
        choices=("candidate", "active"),
        required=True,
    )
    signed_assignment.add_argument(
        "--apply-policy", choices=("observe", "enforce"), required=True
    )
    signed_assignment.add_argument("--target-tag", action="append", default=[])
    signed_assignment.add_argument("--key-id", required=True)
    signed_assignment.add_argument("--seed-file", required=True)
    signed_assignment.add_argument("--key-registry", required=True)
    signed_assignment.add_argument("--document-output", required=True)
    signed_assignment.add_argument("--ttl-seconds", type=int, default=86400)
    report = subparsers.add_parser("report")
    report.add_argument("document")
    report.add_argument("--idempotency-key", required=True)
    lookup = subparsers.add_parser("assignment")
    lookup.add_argument("enrollment_id")
    lookup.add_argument("channel")
    promote = subparsers.add_parser("promote")
    promote.add_argument("channel")
    promote.add_argument("document")
    promote.add_argument("--idempotency-key", required=True)
    args = parser.parse_args()
    base = validate_base_url(args.base)

    def admin_document(operation, payload, role, idempotency_key):
        if not (
            args.admin_key_id
            and args.admin_seed_file
            and args.admin_key_registry
        ):
            raise ValueError(
                "mutating admin command requires --admin-key-id, "
                "--admin-seed-file and --admin-key-registry"
            )
        return sign_admin_request(
            operation,
            payload,
            role,
            idempotency_key,
            args.admin_key_id,
            args.admin_seed_file,
            args.admin_key_registry,
        )
    if args.command == "health":
        result = request(
            base, "GET", "/health", ca_certificate=args.ca_certificate
        )
    elif args.command == "put-revision":
        payload = load_document(args.manifest)
        result = request(
            base,
            "POST",
            "/v1/revisions",
            admin_document(
                "put_revision", payload, "publish", args.idempotency_key
            ),
            args.idempotency_key,
            ca_certificate=args.ca_certificate,
        )
    elif args.command == "put-blob":
        content = Path(args.path).read_bytes()
        digest = "sha256:" + hashlib.sha256(content).hexdigest()
        payload = {
            "content_base64": base64.urlsafe_b64encode(content)
            .rstrip(b"=")
            .decode("ascii"),
            "media_type": args.media_type,
        }
        result = request(
            base,
            "POST",
            "/v1/blobs/%s" % digest,
            admin_document("put_blob", payload, "publish", args.idempotency_key),
            args.idempotency_key,
            ca_certificate=args.ca_certificate,
        )
    elif args.command == "publish-candidate":
        payload = {
            "revision_id": args.revision_id,
            "base_revision": args.base_revision,
            "expected_candidate_head": args.expected_candidate_head,
        }
        result = request(
            base,
            "POST",
            "/v1/channels/%s/candidates" % args.channel,
            admin_document(
                "publish_candidate",
                payload,
                "publish",
                args.idempotency_key,
            ),
            args.idempotency_key,
            ca_certificate=args.ca_certificate,
        )
    elif args.command == "assign":
        payload = load_document(args.document)
        result = request(
            base,
            "POST",
            "/v1/channels/%s/assignments" % args.channel,
            admin_document(
                "assign_candidate",
                payload,
                "publish",
                args.idempotency_key,
            ),
            args.idempotency_key,
            ca_certificate=args.ca_certificate,
        )
    elif args.command == "bootstrap-active":
        document = sign_bootstrap_assignment(
            args.channel,
            args.enrollment_id,
            args.revision_id,
            args.target_tag,
            args.key_id,
            args.seed_file,
            args.key_registry,
        )
        write_private_document(args.document_output, document)
        result = request(
            base,
            "POST",
            "/v1/channels/%s/bootstrap-assignments" % args.channel,
            admin_document(
                "bootstrap_active",
                document,
                "publish",
                args.idempotency_key,
            ),
            args.idempotency_key,
            ca_certificate=args.ca_certificate,
        )
    elif args.command == "sign-assignment-v2":
        document = sign_assignment_v2(
            args.channel,
            args.enrollment_id,
            args.enrollment_generation,
            args.channel_generation,
            args.revision_id,
            args.target_tag,
            args.assignment_kind,
            args.apply_policy,
            args.key_id,
            args.seed_file,
            args.key_registry,
            ttl_seconds=args.ttl_seconds,
        )
        write_private_document(args.document_output, document)
        result = {
            "assignment_id": document["assignment_id"],
            "document": str(Path(args.document_output).expanduser().resolve()),
        }
    elif args.command == "report":
        result = request(
            base,
            "POST",
            "/v1/reports",
            load_document(args.document),
            args.idempotency_key,
            ca_certificate=args.ca_certificate,
        )
    elif args.command == "assignment":
        query = urlencode({"channel": args.channel})
        result = request(
            base,
            "GET",
            "/v1/enrollments/%s/assignment?%s"
            % (args.enrollment_id, query),
            ca_certificate=args.ca_certificate,
        )
    else:
        payload = load_document(args.document)
        result = request(
            base,
            "POST",
            "/v1/channels/%s/promote" % args.channel,
            admin_document(
                "promote", payload, "promote", args.idempotency_key
            ),
            args.idempotency_key,
            ca_certificate=args.ca_certificate,
        )
    print(json.dumps(result, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
