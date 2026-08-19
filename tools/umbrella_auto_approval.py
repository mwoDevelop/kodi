#!/usr/bin/env python3
"""Verify the narrow PR shape eligible for Umbrella auto-approval."""

from __future__ import annotations

import argparse
import json
import re
from pathlib import Path


COMPONENT = "plugin.video.umbrella"
LOCK_PATH = "manifests/locks/testing.json"
SHA40 = re.compile(r"^[0-9a-f]{40}$")
SHA64 = re.compile(r"^[0-9a-f]{64}$")
BRANCH = "automation/testing-lock-plugin-video-umbrella"
AUTHORS = {"app/github-actions", "github-actions"}


def _load(path):
    return json.loads(Path(path).read_text(encoding="utf-8"))


def _version(value):
    if not isinstance(value, str) or not re.fullmatch(r"[0-9]+(?:\.[0-9]+)*", value):
        raise ValueError("component version is invalid")
    return tuple(int(part) for part in value.split("."))


def verify(base_lock, head_lock, pr_path, checks_path):
    base = _load(base_lock)
    head = _load(head_lock)
    pr = _load(pr_path)
    checks = _load(checks_path)
    if (
        pr.get("author") not in AUTHORS
        or pr.get("base") != "main"
        or pr.get("head") != BRANCH
        or pr.get("draft") is not False
        or pr.get("files") != [LOCK_PATH]
        or not SHA40.fullmatch(str(pr.get("head_sha", "")))
    ):
        raise ValueError("pull request identity is not allowlisted")
    for lock, channel in ((base, "testing"), (head, "testing")):
        if lock.get("schema") != 1 or lock.get("channel") != channel:
            raise ValueError("testing lock shape is invalid")
    if set(base.get("components", {})) != set(head.get("components", {})):
        raise ValueError("component set changed")
    changed = [
        name
        for name in sorted(base["components"])
        if base["components"][name] != head["components"][name]
    ]
    if changed != [COMPONENT]:
        raise ValueError("PR is not an Umbrella-only lock update")
    before = base["components"][COMPONENT]
    after = head["components"][COMPONENT]
    if set(after) != {"commit", "version", "zip_sha256"}:
        raise ValueError("Umbrella pin shape changed")
    if (
        not SHA40.fullmatch(str(after["commit"]))
        or not SHA64.fullmatch(str(after["zip_sha256"]))
        or _version(after["version"]) <= _version(before["version"])
    ):
        raise ValueError("Umbrella pin is not a valid forward update")
    if not isinstance(checks, list) or not checks:
        raise ValueError("check runs are missing")
    current = [item for item in checks if item.get("head_sha") == pr["head_sha"]]
    if not current:
        raise ValueError("no checks are bound to the current PR head")
    failed = [
        item.get("name", "unknown")
        for item in current
        if item.get("status") != "completed"
        or item.get("conclusion") not in {"success", "neutral", "skipped"}
    ]
    if failed:
        raise ValueError("checks are not successful: %s" % ", ".join(failed))
    required = [item for item in current if item.get("name") == "e2e"]
    if not required or not any(item.get("conclusion") == "success" for item in required):
        raise ValueError("required e2e check is not successful")
    return {
        "schema": 1,
        "eligible": True,
        "number": int(pr["number"]),
        "head_sha": pr["head_sha"],
        "component": COMPONENT,
        "from_version": before["version"],
        "to_version": after["version"],
    }


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--base-lock", required=True)
    parser.add_argument("--head-lock", required=True)
    parser.add_argument("--pr", required=True)
    parser.add_argument("--checks", required=True)
    parser.add_argument("--output")
    args = parser.parse_args()
    value = verify(args.base_lock, args.head_lock, args.pr, args.checks)
    payload = json.dumps(value, indent=2, sort_keys=True) + "\n"
    if args.output:
        Path(args.output).write_text(payload, encoding="utf-8")
    print(payload, end="")


if __name__ == "__main__":
    main()
