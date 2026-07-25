"""Command line interface for local and GitHub Actions discovery."""

import argparse
import json
from pathlib import Path

from .candidate_bundle import verify_bundle
from .config import load_manifest, load_release_groups
from .engine import discover_all, render_markdown
from .versioning import KodiVersion, next_downstream_version


ROOT = Path(__file__).parents[2]


def main(argv=None):
    parser = argparse.ArgumentParser()
    subparsers = parser.add_subparsers(dest="command", required=True)

    validate = subparsers.add_parser("validate-config")
    validate.add_argument(
        "--manifest", default=str(ROOT / "manifests/upstreams.json")
    )
    validate.add_argument(
        "--release-groups", default=str(ROOT / "manifests/release-groups.json")
    )

    discover = subparsers.add_parser("discover")
    discover.add_argument(
        "--manifest", default=str(ROOT / "manifests/upstreams.json")
    )
    discover.add_argument("--output", required=True)
    discover.add_argument("--markdown")

    verify = subparsers.add_parser("verify-candidate")
    verify.add_argument("bundle")

    version = subparsers.add_parser("next-version")
    version.add_argument("upstream")
    version.add_argument("--current")

    compare = subparsers.add_parser("compare-version")
    compare.add_argument("left")
    compare.add_argument("right")

    args = parser.parse_args(argv)
    if args.command == "validate-config":
        load_manifest(args.manifest)
        load_release_groups(args.release_groups)
        return 0
    if args.command == "discover":
        report = discover_all(ROOT, args.manifest)
        Path(args.output).write_text(
            json.dumps(report, indent=2, sort_keys=True) + "\n", encoding="utf-8"
        )
        if args.markdown:
            Path(args.markdown).write_text(render_markdown(report), encoding="utf-8")
        return 0
    if args.command == "verify-candidate":
        document = verify_bundle(args.bundle)
        print(document["candidate_id"])
        return 0
    if args.command == "next-version":
        print(next_downstream_version(args.upstream, args.current))
        return 0
    left = KodiVersion(args.left)
    right = KodiVersion(args.right)
    print(-1 if left < right else 1 if left > right else 0)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
