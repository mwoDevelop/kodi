#!/usr/bin/env python3
"""Prepare rescannable known-good Umbrella sources as a forward rollback."""

from __future__ import annotations

import argparse
import hashlib
import json
import re
import subprocess
from pathlib import Path, PurePosixPath
from xml.etree import ElementTree


COMPONENT = "plugin.video.umbrella"
SOURCE = "omega/" + COMPONENT
SHA40 = re.compile(r"^[0-9a-f]{40}$")
SAFE_ID = re.compile(r"^[a-z0-9][a-z0-9._-]{0,63}$")


def _git(checkout, *args, binary=False):
    return subprocess.check_output(
        ["git", "-C", str(checkout), *args], text=not binary
    )


def _version(value):
    if not isinstance(value, str) or not re.fullmatch(r"[0-9]+(?:\.[0-9]+)*", value):
        raise ValueError("Umbrella version must be numeric")
    return tuple(int(part) for part in value.split("."))


def _addon(checkout, commit):
    payload = _git(checkout, "show", "%s:%s/addon.xml" % (commit, SOURCE), binary=True)
    root = ElementTree.fromstring(payload)
    if root.get("id") != COMPONENT:
        raise ValueError("unexpected add-on identity")
    _version(root.get("version"))
    return payload, root.get("version")


def _base(checkout, commit):
    manifest = _git(checkout, "show", "%s:downstream-patches.yml" % commit)
    match = re.search(r'(?m)^  base: "([0-9a-f]{40})"$', manifest)
    if not match:
        raise ValueError("known-good source has no upstream base")
    base_commit = match.group(1)
    _payload, version = _addon(checkout, base_commit)
    return base_commit, version


def prepare(checkout, safe_commit, current_commit, new_version, incident_id, output):
    checkout = Path(checkout)
    output = Path(output)
    if not SHA40.fullmatch(safe_commit) or not SHA40.fullmatch(current_commit):
        raise ValueError("forward rollback requires exact source commits")
    if not SAFE_ID.fullmatch(incident_id):
        raise ValueError("incident ID is invalid")
    _safe_xml, safe_version = _addon(checkout, safe_commit)
    _current_xml, current_version = _addon(checkout, current_commit)
    if _version(new_version) <= _version(current_version):
        raise ValueError("forward rollback version must be newer than stable")
    if output.exists():
        raise ValueError("forward rollback output already exists")
    addon_root = output / COMPONENT
    addon_root.mkdir(parents=True)
    rows = _git(checkout, "ls-tree", "-r", safe_commit, "--", SOURCE).splitlines()
    if not rows:
        raise ValueError("known-good source tree is empty")
    for row in rows:
        metadata, full_path = row.split("\t", 1)
        mode, kind, _object = metadata.split()
        if kind != "blob" or mode == "120000":
            raise ValueError("known-good source contains an unsupported entry")
        relative = PurePosixPath(full_path).relative_to(PurePosixPath(SOURCE))
        if relative.is_absolute() or ".." in relative.parts:
            raise ValueError("known-good source path is unsafe")
        target = addon_root.joinpath(*relative.parts)
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_bytes(
            _git(checkout, "show", "%s:%s" % (safe_commit, full_path), binary=True)
        )
    addon_xml = addon_root / "addon.xml"
    payload = addon_xml.read_text(encoding="utf-8")
    payload, count = re.subn(
        r'(<addon\b[^>]*\bversion=")[^"]+("[^>]*>)',
        r"\g<1>%s\2" % new_version,
        payload,
        count=1,
        flags=re.DOTALL,
    )
    if count != 1:
        raise ValueError("could not replace the add-on version")
    addon_xml.write_text(payload, encoding="utf-8")
    parsed = ElementTree.parse(addon_xml).getroot()
    if parsed.get("version") != new_version:
        raise ValueError("forward rollback version replacement failed")
    base_commit, base_version = _base(checkout, safe_commit)
    inventory = {}
    for path in sorted(addon_root.rglob("*")):
        if path.is_symlink():
            raise ValueError("forward rollback cannot contain symlinks")
        if path.is_file():
            inventory[path.relative_to(output).as_posix()] = hashlib.sha256(
                path.read_bytes()
            ).hexdigest()
    document = {
        "schema": 1,
        "component": COMPONENT,
        "kind": "forward_rollback",
        "incident_id": incident_id,
        "known_good_commit": safe_commit,
        "known_good_version": safe_version,
        "replaces_commit": current_commit,
        "replaces_version": current_version,
        "release_version": new_version,
        "upstream_base_commit": base_commit,
        "upstream_base_version": base_version,
        "files": inventory,
    }
    (output / "forward-rollback.json").write_text(
        json.dumps(document, indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )
    return document


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--checkout", required=True)
    parser.add_argument("--safe-commit", required=True)
    parser.add_argument("--current-commit", required=True)
    parser.add_argument("--new-version", required=True)
    parser.add_argument("--incident-id", required=True)
    parser.add_argument("--output", required=True)
    args = parser.parse_args()
    value = prepare(
        args.checkout,
        args.safe_commit,
        args.current_commit,
        args.new_version,
        args.incident_id,
        args.output,
    )
    print(json.dumps(value, indent=2, sort_keys=True))


if __name__ == "__main__":
    main()
