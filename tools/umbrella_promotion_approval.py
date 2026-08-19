#!/usr/bin/env python3
"""Verify the exact stable-promotion PR eligible for policy approval."""

from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from tools.umbrella_auto_approval import AUTHORS, COMPONENT, SHA40, SHA64, _version


BRANCH = re.compile(r"^automation/promote-stable-[0-9a-f]{12}$")
ALLOWED_FILES = {"manifests/locks/stable.json", "manifests/locks/qnap-stable.json"}


def _load(path):
    return json.loads(Path(path).read_text(encoding="utf-8"))


def verify(base_stable, head_stable, testing_lock, base_qnap, head_qnap, pr_path, checks_path):
    base = _load(base_stable)
    head = _load(head_stable)
    testing = _load(testing_lock)
    pr = _load(pr_path)
    checks = _load(checks_path)
    files = pr.get("files")
    if (
        pr.get("author") not in AUTHORS
        or pr.get("base") != "main"
        or not BRANCH.fullmatch(str(pr.get("head", "")))
        or pr.get("draft") is not False
        or not isinstance(files, list)
        or not files
        or not set(files).issubset(ALLOWED_FILES)
        or "manifests/locks/stable.json" not in files
        or not SHA40.fullmatch(str(pr.get("head_sha", "")))
    ):
        raise ValueError("stable promotion PR identity is not allowlisted")
    if base.get("channel") != "stable" or head.get("channel") != "stable":
        raise ValueError("stable lock channel is invalid")
    if head.get("schema") != 2 or testing.get("schema") != 1:
        raise ValueError("promotion lock schema is invalid")
    if head.get("components") != testing.get("components"):
        raise ValueError("stable promotion does not match current testing")
    if _load(base_qnap) != _load(head_qnap):
        raise ValueError("Umbrella promotion changed the QNAP lock")
    before = base.get("components", {})
    after = head.get("components", {})
    if set(before) != set(after):
        raise ValueError("stable component set changed")
    changed = sorted(name for name in before if before[name] != after[name])
    if changed != [COMPONENT]:
        raise ValueError("stable promotion is not Umbrella-only")
    if _version(after[COMPONENT]["version"]) <= _version(before[COMPONENT]["version"]):
        raise ValueError("stable Umbrella version did not move forward")
    if (
        head.get("attestation_kind") != "hermetic_ci"
        or head.get("promotion_kind") != "normal"
        or not SHA64.fullmatch(str(head.get("source_snapshot_id", "")))
        or not SHA64.fullmatch(str(head.get("attestation_id", "")))
        or not SHA64.fullmatch(str(head.get("attestation_sha256", "")))
    ):
        raise ValueError("stable promotion has invalid qualification provenance")
    current = [item for item in checks if item.get("head_sha") == pr["head_sha"]]
    if not any(
        item.get("name") == "e2e"
        and item.get("status") == "completed"
        and item.get("conclusion") == "success"
        for item in current
    ):
        raise ValueError("required stable-promotion e2e is not successful")
    if any(
        item.get("status") != "completed"
        or item.get("conclusion") not in {"success", "neutral", "skipped"}
        for item in current
    ):
        raise ValueError("stable-promotion checks are not successful")
    return {
        "schema": 1,
        "eligible": True,
        "number": int(pr["number"]),
        "head_sha": pr["head_sha"],
        "snapshot_id": head["source_snapshot_id"],
        "attestation_id": head["attestation_id"],
        "attestation_sha256": head["attestation_sha256"],
        "from_version": before[COMPONENT]["version"],
        "to_version": after[COMPONENT]["version"],
    }


def main():
    parser = argparse.ArgumentParser()
    for name in (
        "base-stable", "head-stable", "testing-lock", "base-qnap", "head-qnap", "pr", "checks"
    ):
        parser.add_argument("--" + name, required=True)
    parser.add_argument("--output")
    args = parser.parse_args()
    value = verify(
        args.base_stable,
        args.head_stable,
        args.testing_lock,
        args.base_qnap,
        args.head_qnap,
        args.pr,
        args.checks,
    )
    payload = json.dumps(value, indent=2, sort_keys=True) + "\n"
    if args.output:
        Path(args.output).write_text(payload, encoding="utf-8")
    print(payload, end="")


if __name__ == "__main__":
    main()
