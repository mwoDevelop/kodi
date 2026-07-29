#!/usr/bin/env python3
"""Build the stable promotion payload once, from the exact testing lock."""

import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from tools import build_repo


def prepare(testing_lock, output):
    testing = json.loads(Path(testing_lock).read_text(encoding="utf-8"))
    if testing.get("schema") != 1 or testing.get("channel") != "testing":
        raise ValueError("invalid testing lock")
    promoted = json.loads(json.dumps(testing))
    promoted["channel"] = "stable"
    return build_repo.build(output, lock_overrides={"stable": promoted})


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--testing-lock", required=True)
    parser.add_argument("--output", required=True)
    args = parser.parse_args()
    print(prepare(args.testing_lock, args.output))


if __name__ == "__main__":
    main()
