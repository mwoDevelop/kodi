#!/usr/bin/env python3
"""Inject one post-activation failure and prove exact Android rollback."""

from __future__ import annotations

import argparse
import json
import sys
import tempfile
from pathlib import Path
from xml.etree import ElementTree
from zipfile import ZIP_DEFLATED, ZipFile

ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from tools.kodi_addon_candidate_rollout import rollout
from tools.kodi_default_addons import addon_details, installed_archive_matches


def synthetic_candidate(source, destination, addon_id, version):
    with ZipFile(source) as current, ZipFile(
        destination, "w", ZIP_DEFLATED
    ) as candidate:
        for member in current.infolist():
            payload = current.read(member)
            if member.filename == "%s/addon.xml" % addon_id:
                root = ElementTree.fromstring(payload)
                if root.attrib.get("id") != addon_id:
                    raise ValueError("source artifact identity differs")
                root.attrib["version"] = version
                payload = ElementTree.tostring(
                    root, encoding="utf-8", xml_declaration=True
                )
            candidate.writestr(member, payload)


def test_recovery(args):
    source = args.artifact.resolve()
    if not source.is_file():
        raise FileNotFoundError(source)
    before = addon_details(
        args.adb, args.adb_server_port, args.serial, args.addon_id
    )
    if (
        not before
        or not before.get("enabled")
        or str(before.get("version")) != args.current_version
    ):
        raise RuntimeError("pre-test add-on state differs")
    with tempfile.TemporaryDirectory(prefix="kodi-addon-rollback-") as temporary:
        candidate = Path(temporary) / "candidate.zip"
        synthetic_candidate(
            source, candidate, args.addon_id, args.synthetic_version
        )
        try:
            rollout(
                args.adb,
                args.adb_server_port,
                args.serial,
                candidate,
                args.addon_id,
                args.synthetic_version,
                args.timeout,
                runtime_platform=args.runtime_platform,
                inject_test_failure_after_activation=True,
            )
        except RuntimeError as error:
            if "injected failure after candidate activation" not in str(error):
                raise
        else:
            raise RuntimeError("failure injection unexpectedly committed")
    after = addon_details(
        args.adb, args.adb_server_port, args.serial, args.addon_id
    )
    exact_bytes = installed_archive_matches(
        args.adb,
        args.adb_server_port,
        args.serial,
        source,
        args.addon_id,
    )
    if (
        not after
        or not after.get("enabled")
        or str(after.get("version")) != args.current_version
        or not exact_bytes
    ):
        raise RuntimeError("rollback result differs from exact previous artifact")
    return {
        "schema": 1,
        "status": "ROLLED_BACK",
        "addon": args.addon_id,
        "restored_version": args.current_version,
        "exact_bytes": exact_bytes,
    }


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--artifact", type=Path, required=True)
    parser.add_argument("--addon-id", required=True)
    parser.add_argument("--current-version", required=True)
    parser.add_argument("--synthetic-version", required=True)
    parser.add_argument("--serial", required=True)
    parser.add_argument(
        "--runtime-platform",
        choices=("android", "android-emulator"),
        default="android",
    )
    parser.add_argument(
        "--adb", default="/home/mwo/android-sdk/platform-tools/adb"
    )
    parser.add_argument("--adb-server-port", type=int, default=5038)
    parser.add_argument("--timeout", type=float, default=180)
    args = parser.parse_args()
    print(json.dumps(test_recovery(args), indent=2, sort_keys=True))


if __name__ == "__main__":
    main()
