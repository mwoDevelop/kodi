#!/usr/bin/env python3
"""Migrate a standalone Kodi profile policy from schema 1 to schema 2."""

from __future__ import annotations

import argparse
import json
import os
import tempfile
from pathlib import Path, PurePosixPath


def _glob_regex(pattern):
    import re

    result = ""
    index = 0
    while index < len(pattern):
        character = pattern[index]
        if character == "*":
            if index + 1 < len(pattern) and pattern[index + 1] == "*":
                result += ".*"
                index += 2
                continue
            result += "[^/]*"
        elif character == "?":
            result += "[^/]"
        else:
            result += re.escape(character)
        index += 1
    return re.compile("^" + result + "$")


def _included(relative, policy):
    relative = PurePosixPath(relative).as_posix()
    return any(_glob_regex(item).fullmatch(relative) for item in policy["include"]) and not any(
        _glob_regex(item).fullmatch(relative) for item in policy["exclude"]
    )


def _validate_legacy(document):
    if document.get("schema") != 1:
        raise ValueError("legacy policy migration requires schema 1")
    if not isinstance(document.get("include"), list) or not isinstance(
        document.get("exclude"), list
    ):
        raise ValueError("legacy policy must contain include and exclude lists")
    if any(not isinstance(item, str) or not item for item in document["include"] + document["exclude"]):
        raise ValueError("legacy policy contains an invalid pattern")


def migrate_policy_document(document, corpus=()):
    if document.get("schema") == 2:
        return document, False
    _validate_legacy(document)
    disaster = {key: value for key, value in document.items() if key != "schema"}
    migrated = {
        "schema": 2,
        "name": document.get("name", "migrated-kodi-profile"),
        "scopes": {
            "disaster_recovery": disaster,
            "routine": {
                "default": "excluded",
                "default_profile_only": True,
                "device_local_paths": [],
                "adapters": [],
            },
        },
    }
    for relative in corpus:
        if _included(relative, document) != _included(
            relative, migrated["scopes"]["disaster_recovery"]
        ):
            raise RuntimeError("policy migration changed decision for %s" % relative)
    return migrated, True


def _atomic_json(path, document):
    path = Path(path)
    descriptor, temporary = tempfile.mkstemp(prefix=".%s." % path.name, dir=path.parent)
    try:
        with os.fdopen(descriptor, "w", encoding="utf-8") as handle:
            json.dump(document, handle, indent=2, sort_keys=True)
            handle.write("\n")
            handle.flush()
            os.fsync(handle.fileno())
        os.chmod(temporary, 0o600)
        os.replace(temporary, path)
    finally:
        if os.path.exists(temporary):
            os.unlink(temporary)


def migrate_policy(path, apply=False, corpus=()):
    path = Path(path).resolve()
    document = json.loads(path.read_text(encoding="utf-8"))
    migrated, changed = migrate_policy_document(document, corpus=corpus)
    if changed and apply:
        backup = path.with_suffix(path.suffix + ".schema1.bak")
        if backup.exists() and json.loads(backup.read_text(encoding="utf-8")) != document:
            raise FileExistsError("policy migration backup differs from input")
        if not backup.exists():
            _atomic_json(backup, document)
        _atomic_json(path, migrated)
    return migrated, changed


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("policy")
    parser.add_argument("--apply", action="store_true")
    args = parser.parse_args()
    migrated, changed = migrate_policy(args.policy, apply=args.apply)
    print(json.dumps({"schema": migrated["schema"], "changed": changed, "applied": bool(changed and args.apply)}))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
