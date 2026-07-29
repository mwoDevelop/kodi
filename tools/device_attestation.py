#!/usr/bin/env python3
"""Create and verify redacted, replay-resistant Kodi device attestations."""

import argparse
import datetime as dt
import hashlib
import json
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from tools.snapshot_bundle import canonical_json, verify_bundle


SCHEMA = 1
SHA256 = re.compile(r"^[0-9a-f]{64}$")
NONCE = re.compile(r"^[0-9a-f]{32,128}$")
REQUIRED_CLASSES = {"android-emulator", "android-tv"}
WORKFLOW = ".github/workflows/certify-testing.yml@refs/heads/main"


def _timestamp(value):
    parsed = dt.datetime.fromisoformat(value.replace("Z", "+00:00"))
    if parsed.tzinfo is None:
        raise ValueError("attestation timestamps must include a timezone")
    return parsed.astimezone(dt.timezone.utc)


def _validate_matrix(matrix):
    if (
        matrix.get("schema") != 1
        or matrix.get("result") != "passed"
        or not isinstance(matrix.get("devices"), list)
        or not matrix["devices"]
    ):
        raise ValueError("device matrix is missing a passing result")
    classes = set()
    logical_ids = set()
    for device in matrix["devices"]:
        if set(device) != {
            "logical_device_id",
            "device_class",
            "kodi_version",
            "addons",
            "checks",
        }:
            raise ValueError("device matrix contains unsupported fields")
        logical_id = device["logical_device_id"]
        if (
            not isinstance(logical_id, str)
            or not logical_id
            or logical_id in logical_ids
        ):
            raise ValueError("device matrix contains an invalid logical ID")
        logical_ids.add(logical_id)
        classes.add(device["device_class"])
        if not isinstance(device["kodi_version"], str) or not device["kodi_version"]:
            raise ValueError("device matrix lacks a Kodi version")
        if not isinstance(device["addons"], dict) or not device["addons"]:
            raise ValueError("device matrix lacks add-on versions")
        checks = device["checks"]
        if (
            not isinstance(checks, list)
            or not checks
            or any(
                set(check) != {"name", "result", "evidence_sha256"}
                or check["result"] != "passed"
                or not SHA256.fullmatch(check["evidence_sha256"])
                for check in checks
            )
        ):
            raise ValueError("device matrix contains an invalid check")
    if not REQUIRED_CLASSES.issubset(classes):
        raise ValueError("device matrix lacks the required canary classes")
    return matrix


def _load_matrix(path):
    return _validate_matrix(json.loads(Path(path).read_text(encoding="utf-8")))


def create(
    snapshot,
    matrix_path,
    repository,
    repository_commit,
    workflow_run_id,
    workflow_run_attempt,
    runner_name,
    nonce,
    issued_at,
    expires_at,
    output,
):
    metadata = verify_bundle(snapshot)
    matrix = _load_matrix(matrix_path)
    if not re.fullmatch(r"[0-9a-f]{40}", repository_commit):
        raise ValueError("repository commit must be an exact SHA")
    if repository_commit != metadata["repository_commit"]:
        raise ValueError("runner commit differs from snapshot repository commit")
    if not NONCE.fullmatch(nonce):
        raise ValueError("nonce must be lowercase hexadecimal")
    issued = _timestamp(issued_at)
    expires = _timestamp(expires_at)
    if expires <= issued or expires - issued > dt.timedelta(days=7):
        raise ValueError("attestation validity must be positive and at most 7 days")
    identity = {
        "schema": SCHEMA,
        "snapshot_id": metadata["snapshot_id"],
        "repository": repository,
        "repository_commit": repository_commit,
        "workflow": WORKFLOW,
        "workflow_run_id": str(workflow_run_id),
        "workflow_run_attempt": int(workflow_run_attempt),
        "runner_name": runner_name,
        "nonce": nonce,
        "issued_at": issued_at,
        "expires_at": expires_at,
        "matrix_sha256": hashlib.sha256(canonical_json(matrix)).hexdigest(),
        "matrix": matrix,
        "result": "passed",
    }
    document = {
        **identity,
        "attestation_id": hashlib.sha256(canonical_json(identity)).hexdigest(),
    }
    Path(output).write_text(
        json.dumps(document, indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )
    return document


def verify(attestation_path, snapshot, now=None):
    metadata = verify_bundle(snapshot)
    document = json.loads(Path(attestation_path).read_text(encoding="utf-8"))
    expected_keys = {
        "schema",
        "snapshot_id",
        "repository",
        "repository_commit",
        "workflow",
        "workflow_run_id",
        "workflow_run_attempt",
        "runner_name",
        "nonce",
        "issued_at",
        "expires_at",
        "matrix_sha256",
        "matrix",
        "result",
        "attestation_id",
    }
    if set(document) != expected_keys:
        raise ValueError("attestation contains unsupported or missing fields")
    if (
        document["schema"] != SCHEMA
        or document["snapshot_id"] != metadata["snapshot_id"]
        or document["repository_commit"] != metadata["repository_commit"]
        or document["repository"] != "mwoDevelop/kodi"
        or document["workflow"] != WORKFLOW
        or document["result"] != "passed"
        or not document["workflow_run_id"].isdigit()
        or not isinstance(document["workflow_run_attempt"], int)
        or document["workflow_run_attempt"] < 1
        or not isinstance(document["runner_name"], str)
        or not document["runner_name"]
        or not NONCE.fullmatch(document["nonce"])
        or not SHA256.fullmatch(document["matrix_sha256"])
    ):
        raise ValueError("attestation identity is invalid")
    matrix = _validate_matrix(document["matrix"])
    if hashlib.sha256(canonical_json(matrix)).hexdigest() != document["matrix_sha256"]:
        raise ValueError("attestation matrix digest mismatch")
    issued = _timestamp(document["issued_at"])
    expires = _timestamp(document["expires_at"])
    current = now or dt.datetime.now(dt.timezone.utc)
    if current.tzinfo is None:
        raise ValueError("verification time must include a timezone")
    if expires <= issued or expires - issued > dt.timedelta(days=7) or current > expires:
        raise ValueError("attestation is expired or has an invalid lifetime")
    identity = {key: document[key] for key in expected_keys - {"attestation_id"}}
    if hashlib.sha256(canonical_json(identity)).hexdigest() != document["attestation_id"]:
        raise ValueError("attestation ID mismatch")
    return document


def main():
    parser = argparse.ArgumentParser()
    commands = parser.add_subparsers(dest="command", required=True)
    create_parser = commands.add_parser("create")
    create_parser.add_argument("--snapshot", required=True)
    create_parser.add_argument("--matrix", required=True)
    create_parser.add_argument("--repository", required=True)
    create_parser.add_argument("--repository-commit", required=True)
    create_parser.add_argument("--workflow-run-id", required=True)
    create_parser.add_argument("--workflow-run-attempt", required=True, type=int)
    create_parser.add_argument("--runner-name", required=True)
    create_parser.add_argument("--nonce", required=True)
    create_parser.add_argument("--issued-at", required=True)
    create_parser.add_argument("--expires-at", required=True)
    create_parser.add_argument("--output", required=True)
    verify_parser = commands.add_parser("verify")
    verify_parser.add_argument("--snapshot", required=True)
    verify_parser.add_argument("--attestation", required=True)
    args = parser.parse_args()
    if args.command == "create":
        result = create(
            args.snapshot,
            args.matrix,
            args.repository,
            args.repository_commit,
            args.workflow_run_id,
            args.workflow_run_attempt,
            args.runner_name,
            args.nonce,
            args.issued_at,
            args.expires_at,
            args.output,
        )
    else:
        result = verify(args.attestation, args.snapshot)
    print(json.dumps(result, indent=2, sort_keys=True))


if __name__ == "__main__":
    main()
