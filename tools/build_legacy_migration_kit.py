#!/usr/bin/env python3
"""Build a reproducible offline legacy migration kit."""

from __future__ import annotations

import argparse
import hashlib
import json
import zipfile
from pathlib import Path


ZIP_TIME = (2026, 1, 1, 0, 0, 0)


def _digest(payload):
    return hashlib.sha256(payload).hexdigest()


def build_kit(repository, output):
    repository = Path(repository).resolve()
    output = Path(output).resolve()
    sources = [
        repository / "tools/migrations/__init__.py",
        repository / "tools/migrations/README.md",
        repository / "tools/migrations/legacy_config.py",
        repository / "tools/migrations/legacy_policy.py",
        repository / "tools/migrations/watchnixtoons2_snapshot.py",
        repository / "tools/favourite_artwork.py",
        repository / "tools/kodi_profile.py",
        repository / "tools/kodi_devices.py",
        repository / "tools/legacy_inventory.py",
        repository / "tools/schema_lifecycle.py",
        repository / "manifests/schema-lifecycle.json",
    ]
    files = {}
    payloads = {}
    for source in sources:
        if not source.is_file() or source.is_symlink():
            raise ValueError("migration kit source is missing or unsafe: %s" % source)
        relative = source.relative_to(repository).as_posix()
        payload = source.read_bytes()
        payloads[relative] = payload
        files[relative] = {"sha256": _digest(payload), "size": len(payload)}
    manifest = {
        "schema": 1,
        "name": "mwodevelop-kodi-legacy-migration-kit",
        "python": ">=3.10",
        "files": files,
    }
    payloads["migration-kit-manifest.json"] = (
        json.dumps(manifest, indent=2, sort_keys=True) + "\n"
    ).encode("utf-8")
    output.parent.mkdir(parents=True, exist_ok=True)
    temporary = output.with_name(".%s.tmp" % output.name)
    with zipfile.ZipFile(temporary, "w", compression=zipfile.ZIP_DEFLATED, compresslevel=9) as archive:
        for relative, payload in sorted(payloads.items()):
            info = zipfile.ZipInfo(relative, ZIP_TIME)
            info.create_system = 3
            info.external_attr = 0o100644 << 16
            archive.writestr(info, payload, compress_type=zipfile.ZIP_DEFLATED, compresslevel=9)
    temporary.replace(output)
    return {"path": str(output), "sha256": _digest(output.read_bytes()), "files": len(files)}


def main():
    repository = Path(__file__).resolve().parents[1]
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--output",
        default=str(repository / "dist/mwodevelop-kodi-legacy-migration-kit.zip"),
    )
    args = parser.parse_args()
    print(json.dumps(build_kit(repository, args.output), indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
