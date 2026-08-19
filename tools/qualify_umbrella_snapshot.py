#!/usr/bin/env python3
"""Fail-closed isolation checks and reports for an Umbrella testing snapshot."""

from __future__ import annotations

import argparse
import hashlib
import json
import re
import subprocess
import sys
import xml.etree.ElementTree as ET
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from tools.snapshot_bundle import verify_bundle


COMPONENT = "plugin.video.umbrella"
SHA256 = re.compile(r"^[0-9a-f]{64}$")


def _load(path):
    return json.loads(Path(path).read_text(encoding="utf-8"))


def _version(checkout):
    addon = ET.parse(Path(checkout) / "omega" / COMPONENT / "addon.xml").getroot()
    if addon.get("id") != COMPONENT or not addon.get("version"):
        raise ValueError("Umbrella add-on metadata is invalid")
    return addon.get("version")


def validate(snapshot, stable_lock, umbrella_checkout):
    metadata = verify_bundle(snapshot)
    testing = metadata["testing_lock"]
    stable = _load(stable_lock)
    if stable.get("channel") != "stable" or stable.get("schema") not in (1, 2):
        raise ValueError("stable lock is invalid")
    testing_components = testing.get("components")
    stable_components = stable.get("components")
    if not isinstance(testing_components, dict) or not isinstance(stable_components, dict):
        raise ValueError("component locks are invalid")
    if set(testing_components) != set(stable_components):
        raise ValueError("testing and stable component sets differ")
    changed = sorted(
        component
        for component in testing_components
        if testing_components[component] != stable_components[component]
    )
    if changed != [COMPONENT]:
        raise ValueError("qualification requires an Umbrella-only snapshot delta")
    pin = testing_components[COMPONENT]
    commit = subprocess.check_output(
        ["git", "rev-parse", "HEAD"], cwd=umbrella_checkout, text=True
    ).strip()
    if commit != pin.get("commit"):
        raise ValueError("Umbrella checkout does not match the testing lock")
    if _version(umbrella_checkout) != pin.get("version"):
        raise ValueError("Umbrella source version does not match the testing lock")
    filename = "%s-%s.zip" % (COMPONENT, pin["version"])
    expected_path = "testing/omega/%s/%s" % (COMPONENT, filename)
    inventory = metadata.get("files", {})
    item = inventory.get(expected_path)
    if not item or item.get("sha256") != pin.get("zip_sha256"):
        raise ValueError("snapshot does not contain the locked Umbrella ZIP")
    return {
        "schema": 1,
        "component": COMPONENT,
        "snapshot_id": metadata["snapshot_id"],
        "repository_commit": metadata["repository_commit"],
        "component_commit": commit,
        "component_version": pin["version"],
        "component_zip_sha256": pin["zip_sha256"],
        "changed_components": changed,
    }


def report(context_path, checks, output):
    context = _load(context_path)
    if (
        context.get("schema") != 1
        or context.get("component") != COMPONENT
        or context.get("changed_components") != [COMPONENT]
    ):
        raise ValueError("qualification context is invalid")
    result = []
    seen = set()
    for spec in checks:
        name, separator, raw_path = spec.partition("=")
        path = Path(raw_path)
        if not separator or not name or name in seen or not path.is_file():
            raise ValueError("qualification evidence specification is invalid")
        digest = hashlib.sha256(path.read_bytes()).hexdigest()
        if not SHA256.fullmatch(digest):
            raise ValueError("qualification evidence digest is invalid")
        result.append({"name": name, "result": "passed", "evidence_sha256": digest})
        seen.add(name)
    if not result:
        raise ValueError("qualification requires evidence")
    document = {
        "schema": 1,
        "qualification_type": "hermetic_ci",
        "component": COMPONENT,
        "result": "passed",
        "checks": result,
    }
    Path(output).write_text(
        json.dumps(document, indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )
    return document


def main():
    parser = argparse.ArgumentParser()
    commands = parser.add_subparsers(dest="command", required=True)
    validate_parser = commands.add_parser("validate")
    validate_parser.add_argument("--snapshot", required=True)
    validate_parser.add_argument("--stable-lock", required=True)
    validate_parser.add_argument("--umbrella-checkout", required=True)
    validate_parser.add_argument("--output", required=True)
    report_parser = commands.add_parser("report")
    report_parser.add_argument("--context", required=True)
    report_parser.add_argument("--check", action="append", required=True)
    report_parser.add_argument("--output", required=True)
    args = parser.parse_args()
    if args.command == "validate":
        document = validate(args.snapshot, args.stable_lock, args.umbrella_checkout)
        Path(args.output).write_text(
            json.dumps(document, indent=2, sort_keys=True) + "\n", encoding="utf-8"
        )
    else:
        document = report(args.context, args.check, args.output)
    print(json.dumps(document, indent=2, sort_keys=True))


if __name__ == "__main__":
    main()
