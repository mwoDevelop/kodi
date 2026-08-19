#!/usr/bin/env python3
"""Create immutable hermetic qualification attestations for Umbrella snapshots."""

import argparse
import datetime as dt
import hashlib
import json
import re
from pathlib import Path

from tools.snapshot_bundle import canonical_json, verify_bundle


SCHEMA = 2
COMPONENT = "plugin.video.umbrella"
TYPE = "hermetic_ci"
WORKFLOW = ".github/workflows/certify-umbrella-hermetic.yml@refs/heads/main"
SHA256 = re.compile(r"^[0-9a-f]{64}$")
NONCE = re.compile(r"^[0-9a-f]{32,128}$")


def _timestamp(value):
    parsed = dt.datetime.fromisoformat(value.replace("Z", "+00:00"))
    if parsed.tzinfo is None:
        raise ValueError("qualification timestamps must include a timezone")
    return parsed.astimezone(dt.timezone.utc)


def _validate_report(value):
    expected = {"schema", "qualification_type", "component", "result", "checks"}
    if set(value) != expected or value.get("schema") != 1:
        raise ValueError("qualification report shape is invalid")
    if (
        value["qualification_type"] != TYPE
        or value["component"] != COMPONENT
        or value["result"] != "passed"
        or not isinstance(value["checks"], list)
        or not value["checks"]
    ):
        raise ValueError("qualification report is not a passing Umbrella report")
    names = set()
    for check in value["checks"]:
        if (
            set(check) != {"name", "result", "evidence_sha256"}
            or not isinstance(check["name"], str)
            or not check["name"]
            or check["name"] in names
            or check["result"] != "passed"
            or not SHA256.fullmatch(check["evidence_sha256"])
        ):
            raise ValueError("qualification report contains an invalid check")
        names.add(check["name"])
    return value


def _report(path):
    return _validate_report(json.loads(Path(path).read_text(encoding="utf-8")))


def create(
    snapshot,
    report_path,
    repository,
    repository_commit,
    workflow_run_id,
    workflow_run_attempt,
    nonce,
    issued_at,
    expires_at,
    output,
):
    metadata = verify_bundle(snapshot)
    report = _report(report_path)
    if repository != "mwoDevelop/kodi":
        raise ValueError("qualification repository is invalid")
    if not re.fullmatch(r"[0-9a-f]{40}", repository_commit):
        raise ValueError("repository commit must be an exact SHA")
    if repository_commit != metadata["repository_commit"]:
        raise ValueError("qualification commit differs from snapshot")
    if not str(workflow_run_id).isdigit() or int(workflow_run_attempt) < 1:
        raise ValueError("workflow run identity is invalid")
    if not NONCE.fullmatch(nonce):
        raise ValueError("qualification nonce is invalid")
    issued = _timestamp(issued_at)
    expires = _timestamp(expires_at)
    if expires <= issued or expires - issued > dt.timedelta(days=7):
        raise ValueError("qualification lifetime must be positive and at most 7 days")
    identity = {
        "schema": SCHEMA,
        "qualification_type": TYPE,
        "component": COMPONENT,
        "snapshot_id": metadata["snapshot_id"],
        "repository": repository,
        "repository_commit": repository_commit,
        "workflow": WORKFLOW,
        "workflow_run_id": str(workflow_run_id),
        "workflow_run_attempt": int(workflow_run_attempt),
        "nonce": nonce,
        "issued_at": issued_at,
        "expires_at": expires_at,
        "report_sha256": hashlib.sha256(canonical_json(report)).hexdigest(),
        "report": report,
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
    identity_keys = {
        "schema",
        "qualification_type",
        "component",
        "snapshot_id",
        "repository",
        "repository_commit",
        "workflow",
        "workflow_run_id",
        "workflow_run_attempt",
        "nonce",
        "issued_at",
        "expires_at",
        "report_sha256",
        "report",
        "result",
    }
    if set(document) != identity_keys | {"attestation_id"}:
        raise ValueError("qualification attestation shape is invalid")
    if (
        document["schema"] != SCHEMA
        or document["qualification_type"] != TYPE
        or document["component"] != COMPONENT
        or document["snapshot_id"] != metadata["snapshot_id"]
        or document["repository"] != "mwoDevelop/kodi"
        or document["repository_commit"] != metadata["repository_commit"]
        or document["workflow"] != WORKFLOW
        or not document["workflow_run_id"].isdigit()
        or not isinstance(document["workflow_run_attempt"], int)
        or document["workflow_run_attempt"] < 1
        or not NONCE.fullmatch(document["nonce"])
        or document["result"] != "passed"
    ):
        raise ValueError("qualification attestation identity is invalid")
    report = _validate_report(document["report"])
    if hashlib.sha256(canonical_json(report)).hexdigest() != document["report_sha256"]:
        raise ValueError("qualification report digest mismatch")
    issued = _timestamp(document["issued_at"])
    expires = _timestamp(document["expires_at"])
    current = now or dt.datetime.now(dt.timezone.utc)
    if current.tzinfo is None or expires <= issued or current > expires:
        raise ValueError("qualification attestation is expired")
    identity = {key: document[key] for key in identity_keys}
    if hashlib.sha256(canonical_json(identity)).hexdigest() != document["attestation_id"]:
        raise ValueError("qualification attestation ID mismatch")
    return document


def main():
    parser = argparse.ArgumentParser()
    commands = parser.add_subparsers(dest="command", required=True)
    create_parser = commands.add_parser("create")
    create_parser.add_argument("--snapshot", required=True)
    create_parser.add_argument("--report", required=True)
    create_parser.add_argument("--repository", required=True)
    create_parser.add_argument("--repository-commit", required=True)
    create_parser.add_argument("--workflow-run-id", required=True)
    create_parser.add_argument("--workflow-run-attempt", type=int, required=True)
    create_parser.add_argument("--nonce", required=True)
    create_parser.add_argument("--issued-at", required=True)
    create_parser.add_argument("--expires-at", required=True)
    create_parser.add_argument("--output", required=True)
    verify_parser = commands.add_parser("verify")
    verify_parser.add_argument("--snapshot", required=True)
    verify_parser.add_argument("--attestation", required=True)
    args = parser.parse_args()
    if args.command == "create":
        value = create(
            args.snapshot,
            args.report,
            args.repository,
            args.repository_commit,
            args.workflow_run_id,
            args.workflow_run_attempt,
            args.nonce,
            args.issued_at,
            args.expires_at,
            args.output,
        )
    else:
        value = verify(args.attestation, args.snapshot)
    print(json.dumps(value, indent=2, sort_keys=True))


if __name__ == "__main__":
    main()
