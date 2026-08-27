#!/usr/bin/env python3
"""Validate and deploy only QNAP images approved by the versioned stable lock."""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import shlex
import tempfile
import time
import uuid
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from tools import qnap_images
from tools.qnap_profile_sync import connect


SHA256 = re.compile(r"^[0-9a-f]{64}$")
COMMIT = re.compile(r"^[0-9a-f]{40}$")
RUN_ID = re.compile(r"^[0-9]+$")
REMOTE_LOCK = "/share/CACHEDEV3_DATA/.mwodevelop-services/kodi-ops.lock"
APPROVAL_FIELDS = {
    "schema",
    "service",
    "image",
    "source_repository",
    "source_commit",
    "input_sha256",
    "platforms",
    "security_report_sha256",
    "workflow_run_id",
}


def load_lock(path):
    document = json.loads(Path(path).read_text(encoding="utf-8"))
    if set(document) != {"schema", "channel", "candidate_id", "services"}:
        raise ValueError("QNAP lock has unsupported fields")
    if document["schema"] != 1 or document["channel"] != "stable":
        raise ValueError("unsupported QNAP lock identity")
    if not SHA256.fullmatch(str(document["candidate_id"])):
        raise ValueError("invalid QNAP candidate ID")
    available = qnap_images.services()
    supported_sets = {
        frozenset(available),
        frozenset(set(available) - {"control-plane"}),
        frozenset(set(available) - {"secret-broker"}),
    }
    if frozenset(document["services"]) not in supported_sets:
        raise ValueError("QNAP lock service set differs from deployment policy")
    for name, item in document["services"].items():
        required = {
            "image",
            "source_repository",
            "source_commit",
            "input_sha256",
            "platforms",
            "security_report_sha256",
            "workflow_run_id",
        }
        if not isinstance(item, dict) or set(item) != required:
            raise ValueError("invalid QNAP lock entry: %s" % name)
        service = available[name]
        if not qnap_images.IMAGE.fullmatch(str(item["image"])):
            raise ValueError("QNAP image is not immutable: %s" % name)
        if item["source_repository"] != service.github_repository:
            raise ValueError("QNAP source repository differs: %s" % name)
        if not COMMIT.fullmatch(str(item["source_commit"])):
            raise ValueError("QNAP source commit is invalid: %s" % name)
        if not SHA256.fullmatch(str(item["input_sha256"])):
            raise ValueError("QNAP input digest is invalid: %s" % name)
        if item["platforms"] != list(service.platforms):
            raise ValueError("QNAP platforms differ: %s" % name)
        if not SHA256.fullmatch(str(item["security_report_sha256"])):
            raise ValueError("QNAP security report digest is invalid: %s" % name)
        if not RUN_ID.fullmatch(str(item["workflow_run_id"])):
            raise ValueError("QNAP workflow run ID is invalid: %s" % name)
    identity = {"schema": 1, "channel": "stable", "services": document["services"]}
    candidate = hashlib.sha256(
        json.dumps(identity, sort_keys=True, separators=(",", ":")).encode("utf-8")
    ).hexdigest()
    if candidate != document["candidate_id"]:
        raise ValueError("QNAP candidate ID mismatch")
    return document


def compose_lock(approval_paths):
    services = qnap_images.services()
    approvals = {}
    for raw_path in approval_paths:
        path = Path(raw_path)
        document = json.loads(path.read_text(encoding="utf-8"))
        if not isinstance(document, dict) or set(document) != APPROVAL_FIELDS:
            raise ValueError("QNAP approval has unsupported fields")
        name = document["service"]
        if document["schema"] != 1 or name in approvals or name not in services:
            raise ValueError("QNAP approval service is invalid or duplicated")
        service = services[name]
        if document["source_repository"] != service.github_repository:
            raise ValueError("QNAP approval source repository differs")
        current_commit = qnap_images.source_identity(
            service, require_clean=False
        )["commit"]
        if not qnap_images.source_commit_is_ancestor(
            service, document["source_commit"]
        ):
            raise ValueError("QNAP approval source commit is not in current history")
        approved_input = qnap_images.source_input_sha256(
            service, document["source_commit"]
        )
        current_input = qnap_images.source_input_sha256(service, current_commit)
        if (
            document["input_sha256"] != approved_input
            or document["input_sha256"] != current_input
        ):
            raise ValueError("QNAP approval build input digest differs")
        approvals[name] = {
            key: document[key]
            for key in APPROVAL_FIELDS.difference({"schema", "service"})
        }
    if set(approvals) != set(services):
        raise ValueError("QNAP approvals do not cover the complete service set")
    identity = {"schema": 1, "channel": "stable", "services": approvals}
    candidate_id = hashlib.sha256(
        json.dumps(identity, sort_keys=True, separators=(",", ":")).encode("utf-8")
    ).hexdigest()
    document = {**identity, "candidate_id": candidate_id}
    # Reuse the deployment validator as the final fail-closed contract.
    return document


def write_lock(path, document):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    descriptor, temporary = tempfile.mkstemp(prefix=".%s." % path.name, dir=path.parent)
    try:
        with os.fdopen(descriptor, "w", encoding="utf-8") as handle:
            json.dump(document, handle, indent=2, sort_keys=True)
            handle.write("\n")
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(temporary, path)
    finally:
        if os.path.exists(temporary):
            os.unlink(temporary)


class RemoteLock:
    def __init__(self, repository, references=".env"):
        self.session = connect(repository, references)
        self.operation_id = uuid.uuid4().hex
        self.acquired = False

    def __enter__(self):
        command = (
            "if mkdir "
            + shlex.quote(REMOTE_LOCK)
            + " 2>/dev/null; then printf acquired; else printf busy; fi"
        )
        if self.session.execute(command) != "acquired":
            self.session.close()
            raise RuntimeError("another operation owns the QNAP deployment lock")
        self.session.upload_text(
            REMOTE_LOCK + "/operation-id",
            self.operation_id + "\n",
            0o600,
        )
        self.acquired = True
        return self

    def __exit__(self, _type, _value, _traceback):
        try:
            if self.acquired:
                command = (
                    "test \"$(cat "
                    + shlex.quote(REMOTE_LOCK + "/operation-id")
                    + ")\" = "
                    + shlex.quote(self.operation_id)
                    + " && rm -rf "
                    + shlex.quote(REMOTE_LOCK)
                )
                self.session.execute(command)
        finally:
            self.session.close()


def deploy(
    lock_path,
    references=".env",
    repository=ROOT,
    service_names=None,
    reconcile_services=None,
):
    lock = load_lock(lock_path)
    requested = list(service_names or lock["services"])
    deployment_order = (
        "secret-broker",
        "profile-sync",
        "control-plane",
        "provider-relay",
        "upstream-watchdog",
    )
    selected = [name for name in deployment_order if name in requested]
    selected.extend(name for name in requested if name not in selected)
    unknown = sorted(set(requested).difference(lock["services"]))
    if unknown:
        raise ValueError("unknown QNAP stable services: %s" % ", ".join(unknown))
    reconcile = set(reconcile_services or ())
    invalid_reconcile = sorted(reconcile.difference(requested))
    if invalid_reconcile:
        raise ValueError(
            "reconciled services were not selected: %s"
            % ", ".join(invalid_reconcile)
        )
    expected = {
        name: lock["services"][name]["image"] for name in selected
    }
    before = qnap_images.status(references, repository=repository)
    actions = {}
    with RemoteLock(repository, references):
        observed = qnap_images.status(references, repository=repository)
        if {
            name: item.get("image") for name, item in observed.items()
        } != {name: item.get("image") for name, item in before.items()}:
            raise RuntimeError("QNAP runtime changed after preflight")
        for name, image in expected.items():
            image_matches = observed[name].get("image") == image
            if image_matches and name not in reconcile:
                actions[name] = "NO_CHANGE"
                continue
            qnap_images.deploy(name, image, references, repository=repository)
            actions[name] = "RECONCILED" if image_matches else "DEPLOYED"
        deadline = time.monotonic() + 120
        while True:
            after = qnap_images.status(references, repository=repository)
            pending = []
            for name, image in expected.items():
                if after[name].get("image") != image:
                    raise RuntimeError("QNAP post-deploy digest mismatch: %s" % name)
                if not qnap_images.service_is_operational(name, after[name]):
                    pending.append(name)
            if not pending:
                break
            if time.monotonic() >= deadline:
                raise RuntimeError(
                    "QNAP services did not become healthy: %s"
                    % ", ".join(sorted(pending))
                )
            time.sleep(3)
    return {
        "schema": 1,
        "candidate_id": lock["candidate_id"],
        "result": "NO_CHANGE" if set(actions.values()) == {"NO_CHANGE"} else "DEPLOYED",
        "services": actions,
    }


def main():
    parser = argparse.ArgumentParser()
    commands = parser.add_subparsers(dest="command", required=True)
    validate = commands.add_parser("validate")
    validate.add_argument("--lock", required=True)
    deploy_parser = commands.add_parser("deploy")
    deploy_parser.add_argument("--lock", required=True)
    deploy_parser.add_argument("--references", default=".env")
    deploy_parser.add_argument("--service", action="append")
    deploy_parser.add_argument("--reconcile-service", action="append")
    compose = commands.add_parser("compose")
    compose.add_argument("--approval", action="append", required=True)
    compose.add_argument("--output", required=True)
    args = parser.parse_args()
    if args.command == "validate":
        lock = load_lock(args.lock)
        result = {"schema": 1, "candidate_id": lock["candidate_id"], "services": sorted(lock["services"])}
    elif args.command == "compose":
        lock = compose_lock(args.approval)
        write_lock(args.output, lock)
        # Validate the serialized bytes as well as the in-memory document.
        lock = load_lock(args.output)
        result = {"schema": 1, "candidate_id": lock["candidate_id"], "services": sorted(lock["services"])}
    else:
        result = deploy(
            args.lock,
            args.references,
            service_names=args.service,
            reconcile_services=args.reconcile_service,
        )
    print(json.dumps(result, indent=2, sort_keys=True))


if __name__ == "__main__":
    main()
