#!/usr/bin/env python3
"""Validate the machine-readable lifecycle of project-owned schemas."""

from __future__ import annotations

import argparse
import json
import re
from pathlib import Path


SCHEMA = 1
REQUIRED_FORMATS = {
    "audit_event",
    "control_plane_snapshot",
    "device_registry",
    "disaster_recovery_snapshot",
    "favourite_artwork_manifest",
    "portable_state",
    "profile_policy",
    "profile_sync_local_state",
    "profile_sync_revision",
    "reinstall_config",
    "stable_lock",
    "testing_lock",
}


def load_lifecycle(path):
    document = json.loads(Path(path).read_text(encoding="utf-8"))
    if set(document) != {"schema", "formats"} or document["schema"] != SCHEMA:
        raise ValueError("unsupported schema lifecycle manifest")
    formats = document["formats"]
    if not isinstance(formats, dict) or set(formats) != REQUIRED_FORMATS:
        raise ValueError("schema lifecycle manifest has an incomplete format set")
    for name, item in formats.items():
        if not isinstance(item, dict):
            raise ValueError("%s lifecycle entry must be an object" % name)
        required = {"current", "legacy", "production_reader"}
        optional = {"offline_migrator", "content_classifiers"}
        if not required.issubset(item) or not set(item).issubset(required | optional):
            raise ValueError("%s lifecycle entry has invalid fields" % name)
        current = item["current"]
        legacy = item["legacy"]
        if (
            not isinstance(current, list)
            or not current
            or len(current) != len(set(current))
            or any(not isinstance(value, int) or value < 1 for value in current)
            or not isinstance(legacy, list)
            or len(legacy) != len(set(legacy))
            or any(not isinstance(value, int) or value < 1 for value in legacy)
            or set(current).intersection(legacy)
        ):
            raise ValueError("%s has invalid current/legacy versions" % name)
        reader = item["production_reader"]
        if not isinstance(reader, str) or not reader:
            raise ValueError("%s lacks a production reader" % name)
    return document


def validate_markdown(path, document):
    content = Path(path).read_text(encoding="utf-8")
    rows = {}
    pattern = re.compile(
        r"^\| `([^`]+)` \| ([^|]+?) \| ([^|]+?) \|",
        re.MULTILINE,
    )
    for name, current, legacy in pattern.findall(content):
        rows[name] = (current.strip(), legacy.strip())
    expected = {
        name: (
            ", ".join(str(value) for value in item["current"]),
            ", ".join(str(value) for value in item["legacy"]) or "—",
        )
        for name, item in document["formats"].items()
    }
    if rows != expected:
        raise ValueError("schema lifecycle Markdown differs from manifest")
    return True


def main():
    repository = Path(__file__).resolve().parents[1]
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--manifest",
        default=str(repository / "manifests/schema-lifecycle.json"),
    )
    parser.add_argument(
        "--documentation",
        default=str(repository / "docs/schema-lifecycle.md"),
    )
    args = parser.parse_args()
    document = load_lifecycle(args.manifest)
    validate_markdown(args.documentation, document)
    print(json.dumps({"formats": sorted(document["formats"]), "status": "ok"}))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
