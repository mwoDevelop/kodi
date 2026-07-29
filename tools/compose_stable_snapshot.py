#!/usr/bin/env python3
"""Compose current testing with an exact certified stable snapshot payload."""

import argparse
import hashlib
import json
import shutil
import sys
import tempfile
from pathlib import Path
from xml.etree import ElementTree

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from tools.build_repo import render_home
from tools.snapshot_bundle import extract_section, verify_bundle


def _sha256(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def _catalog(channel_root, repository_id):
    addons = ElementTree.fromstring(
        (channel_root / "addons.xml").read_bytes()
    )
    entries = list(addons)
    repository = next(
        (
            {
                "id": addon.attrib["id"],
                "name": addon.attrib["name"],
                "version": addon.attrib["version"],
            }
            for addon in entries
            if addon.attrib["id"] == repository_id
        ),
        None,
    )
    if repository is None:
        raise ValueError("repository add-on is absent from composed index")
    return {
        "repository": repository,
        "addons": [
            {
                "id": addon.attrib["id"],
                "name": addon.attrib["name"],
                "version": addon.attrib["version"],
            }
            for addon in sorted(entries, key=lambda node: node.attrib["id"])
            if addon.attrib["id"] != repository_id
        ],
    }


def _manifest(root):
    lines = []
    for path in sorted(Path(root).rglob("*")):
        if path.is_file() and path.name != "artifact-manifest.sha256":
            lines.append("%s  %s" % (_sha256(path), path.relative_to(root)))
    return "\n".join(lines) + "\n"


def compose(current_snapshot, promoted_snapshot, output):
    current = verify_bundle(current_snapshot)
    promoted = verify_bundle(promoted_snapshot)
    output = Path(output)
    if output.exists():
        raise ValueError("composer output already exists")
    with tempfile.TemporaryDirectory(prefix="kodi-stable-compose-") as temporary:
        promoted_root = Path(temporary) / "promoted"
        extract_section(current_snapshot, "payload", output)
        extract_section(promoted_snapshot, "promotion", promoted_root)

        shutil.rmtree(output / "stable")
        shutil.copytree(promoted_root / "stable", output / "stable")
        shutil.rmtree(output / "repo")
        shutil.copytree(promoted_root / "repo", output / "repo")
        for old in output.glob("repository.mwodevelop-*.zip"):
            old.unlink()
        stable_packages = sorted(
            promoted_root.glob("repository.mwodevelop-*.zip")
        )
        if len(stable_packages) != 1:
            raise ValueError("promoted payload has an ambiguous stable repository ZIP")
        shutil.copyfile(stable_packages[0], output / stable_packages[0].name)

        current_provenance = json.loads(
            (output / "build-provenance.json").read_text(encoding="utf-8")
        )
        promoted_provenance = json.loads(
            (promoted_root / "build-provenance.json").read_text(encoding="utf-8")
        )
        current_provenance["channels"]["stable"] = promoted_provenance[
            "channels"
        ]["stable"]
        (output / "build-provenance.json").write_text(
            json.dumps(current_provenance, indent=2, sort_keys=True) + "\n",
            encoding="utf-8",
        )
        catalog = {
            "stable": _catalog(
                output / "stable/omega", "repository.mwodevelop"
            ),
            "testing": _catalog(
                output / "testing/omega", "repository.mwodevelop.testing"
            ),
        }
        (output / "index.html").write_bytes(render_home(catalog))
        (output / "artifact-manifest.sha256").write_text(
            _manifest(output), encoding="ascii"
        )

        if (
            _sha256(output / "testing/omega/addons.xml")
            != current["testing_index_sha256"]
        ):
            raise ValueError("composer changed current testing")
        promoted_stable = promoted_root / "stable/omega/addons.xml"
        if (output / "stable/omega/addons.xml").read_bytes() != (
            promoted_stable.read_bytes()
        ):
            raise ValueError("composer changed promoted stable")
        for source in promoted_root.glob("stable/omega/**/*.zip"):
            target = output / source.relative_to(promoted_root)
            if target.read_bytes() != source.read_bytes():
                raise ValueError("composer changed a promoted component ZIP")
    return {
        "schema": 1,
        "current_testing_snapshot_id": current["snapshot_id"],
        "promoted_stable_snapshot_id": promoted["snapshot_id"],
        "testing_index_sha256": current["testing_index_sha256"],
        "stable_index_sha256": _sha256(output / "stable/omega/addons.xml"),
        "artifact_manifest_sha256": _sha256(
            output / "artifact-manifest.sha256"
        ),
    }


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--current-testing-snapshot", required=True)
    parser.add_argument("--promoted-stable-snapshot", required=True)
    parser.add_argument("--output", required=True)
    args = parser.parse_args()
    result = compose(
        args.current_testing_snapshot,
        args.promoted_stable_snapshot,
        args.output,
    )
    print(json.dumps(result, indent=2, sort_keys=True))


if __name__ == "__main__":
    main()
