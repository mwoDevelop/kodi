#!/usr/bin/env python3
"""Build a deterministic Kodi add-on candidate from a local worktree."""

import argparse
import json
import subprocess
import sys
from pathlib import Path, PurePosixPath

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from tools import build_repo


def build(addon_id, output, root=ROOT):
    root = Path(root).resolve()
    components = json.loads(
        (root / "manifests/components.json").read_text(encoding="utf-8")
    )["components"]
    if addon_id not in components:
        raise ValueError(f"unknown component: {addon_id}")
    component = components[addon_id]
    source_path = PurePosixPath(component["source"])
    if source_path.is_absolute() or ".." in source_path.parts:
        raise ValueError("unsafe component source")
    source = root.joinpath(*source_path.parts).resolve()
    if root not in source.parents:
        raise ValueError("component source escapes repository")

    files = list(build_repo.addon_files(source, component["include"]))
    by_name = {PurePosixPath(relative).as_posix(): path for path, relative in files}
    if "addon.xml" not in by_name:
        raise ValueError("component has no addon.xml")
    _addon, parsed_id, version = build_repo.parse_addon(by_name["addon.xml"])
    if parsed_id != addon_id:
        raise ValueError("component ID drift")

    output = Path(output).resolve()
    if output == root or output in root.parents:
        raise ValueError("unsafe candidate output")
    if output == source or source in output.parents:
        raise ValueError("candidate output must be outside component source")
    build_repo.write_deterministic_zip(output, addon_id, files)
    checkout = root / source_path.parts[0]
    commit = subprocess.check_output(
        ["git", "-C", str(checkout), "rev-parse", "HEAD"], text=True
    ).strip()
    dirty = bool(
        subprocess.check_output(
            ["git", "-C", str(checkout), "status", "--porcelain"],
            text=True,
        ).strip()
    )
    return {
        "schema": 1,
        "addon_id": addon_id,
        "version": version,
        "zip": str(output),
        "zip_sha256": build_repo.sha256(output),
        "source_commit": commit,
        "source_dirty": dirty,
        "files": len(files),
    }


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("addon_id")
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    print(json.dumps(build(args.addon_id, args.output), indent=2, sort_keys=True))


if __name__ == "__main__":
    main()
