#!/usr/bin/env python3
"""Configure one product repository without removing reviews or bypass actors."""

import argparse
import copy
import hashlib
import json
import os
import subprocess
import tempfile
from pathlib import Path

REPOSITORY = "mwoDevelop/script.module.mwoscrapers"
RULESET = 19742534
RULE_FIELDS = ("name", "target", "enforcement", "conditions", "rules", "bypass_actors")


def api(path, method="GET", body=None):
    args = ["gh", "api", ("repos/" + REPOSITORY + "/" + path).rstrip("/"), "--method", method]
    if body is not None:
        args += ["--input", "-"]
    result = subprocess.run(args, input=json.dumps(body) if body is not None else None,
                            capture_output=True, text=True, timeout=45)
    if result.returncode:
        raise RuntimeError("GitHub configuration request failed")
    return json.loads(result.stdout)


def snapshot(request=api):
    repo = request("")
    rule = request("rulesets/" + str(RULESET))
    return {"allow_auto_merge": repo["allow_auto_merge"],
            "ruleset": {field: rule[field] for field in RULE_FIELDS}}


def desired(before):
    result = copy.deepcopy(before)
    rules = result["ruleset"]["rules"]
    reviews = [r for r in rules if r["type"] == "pull_request"]
    checks = [r for r in rules if r["type"] == "required_status_checks"]
    if (result["ruleset"]["enforcement"] != "active" or len(reviews) != 1 or len(checks) != 1
            or reviews[0]["parameters"]["required_approving_review_count"] != 1
            or not reviews[0]["parameters"]["dismiss_stale_reviews_on_push"]
            or not checks[0]["parameters"]["strict_required_status_checks_policy"]):
        raise ValueError("Unexpected protection baseline; operator review required")
    contexts = checks[0]["parameters"]["required_status_checks"]
    if not any(c["context"] == "test" for c in contexts):
        raise ValueError("Required test is missing")
    if not any(c["context"] == "malware-scan" for c in contexts):
        contexts.append({"context": "malware-scan"})
    result["allow_auto_merge"] = True
    return result


def digest(document):
    return hashlib.sha256(json.dumps(document, sort_keys=True).encode()).hexdigest()


def configure(backup_dir, apply=False, request=api):
    before = snapshot(request)
    after = desired(before)
    result = {"repository": REPOSITORY, "state": "NO_CHANGE" if before == after else "DRY_RUN",
              "before_sha256": digest(before), "after_sha256": digest(after),
              "required_reviews": 1, "required_checks": ["test", "malware-scan"]}
    if before == after or not apply:
        return result
    backup_dir = Path(backup_dir)
    backup_dir.mkdir(parents=True, exist_ok=True, mode=0o700)
    fd, filename = tempfile.mkstemp(prefix="mwoscrapers-pr-policy-", suffix=".json", dir=backup_dir)
    with os.fdopen(fd, "w") as out:
        json.dump({"schema": 1, "repository": REPOSITORY, "ruleset_id": RULESET,
                   "before": before, "expected_after": after}, out, indent=2)
        out.flush()
        os.fsync(out.fileno())
    if snapshot(request) != before:
        raise RuntimeError("Protection changed after preflight; no mutation performed")
    # Strengthen checks first. Do not weaken review rules during configuration.
    request("rulesets/" + str(RULESET), "PUT", after["ruleset"])
    request("", "PATCH", {"allow_auto_merge": True})
    if snapshot(request) != after:
        raise RuntimeError("Configuration readback mismatch; preserve backup and inspect")
    return {**result, "state": "APPLIED", "backup": filename}


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--apply", action="store_true")
    parser.add_argument("--backup-dir", type=Path, default=Path(".kodi-private/github-policy-backups"))
    args = parser.parse_args()
    print(json.dumps(configure(args.backup_dir, args.apply), indent=2))


if __name__ == "__main__":
    main()
