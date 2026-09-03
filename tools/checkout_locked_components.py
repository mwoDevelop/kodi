#!/usr/bin/env python3
"""Fetch only commits referenced by Kodi channel locks."""

import argparse
import contextlib
import json
import os
import subprocess
import tempfile
from pathlib import Path

ROOT = Path(__file__).parents[1]


@contextlib.contextmanager
def git_environment():
    """Provide non-persistent credentials for private component repositories."""
    token = os.environ.get("KODI_COMPONENTS_TOKEN", "").strip()
    if not token:
        yield None
        return
    with tempfile.TemporaryDirectory(prefix="kodi-git-askpass-") as directory:
        askpass = Path(directory) / "askpass.sh"
        askpass.write_text(
            "#!/bin/sh\n"
            "case \"$1\" in\n"
            "  *Username*) printf '%s\\n' x-access-token ;;\n"
            "  *) printf '%s\\n' \"$KODI_COMPONENTS_TOKEN\" ;;\n"
            "esac\n",
            encoding="utf-8",
        )
        askpass.chmod(0o700)
        environment = os.environ.copy()
        environment.update(
            {
                "GIT_ASKPASS": str(askpass),
                "GIT_TERMINAL_PROMPT": "0",
            }
        )
        yield environment


def load_json(path):
    return json.loads(Path(path).read_text(encoding="utf-8"))


def checkout_locked_components(output):
    components = load_json(ROOT / "manifests/components.json")["components"]
    channels = load_json(ROOT / "manifests/channels.json")["channels"]
    commits = {}
    for channel in channels.values():
        lock = load_json(ROOT / channel["lock"])
        for addon_id, pin in lock["components"].items():
            checkout = components[addon_id]["source"].split("/", 1)[0]
            commits.setdefault(checkout, set()).add(pin["commit"])

    output = Path(output)
    output.mkdir(parents=True, exist_ok=True)
    with git_environment() as environment:
        for addon_id, component in components.items():
            checkout = component["source"].split("/", 1)[0]
            if checkout not in commits:
                continue
            target = output / checkout
            if not (target / ".git").is_dir():
                target.mkdir(parents=True, exist_ok=True)
                subprocess.run(
                    ["git", "-C", str(target), "init", "-q"],
                    check=True,
                    env=environment,
                )
                subprocess.run(
                    [
                        "git",
                        "-C",
                        str(target),
                        "remote",
                        "add",
                        "origin",
                        "https://github.com/%s.git" % component["repository"],
                    ],
                    check=True,
                    env=environment,
                )
            for commit in sorted(commits[checkout]):
                subprocess.run(
                    [
                        "git",
                        "-C",
                        str(target),
                        "fetch",
                        "--depth",
                        "1",
                        "origin",
                        "%s:refs/locked/%s" % (commit, commit),
                    ],
                    check=True,
                    env=environment,
                )
    return commits


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--output", required=True)
    args = parser.parse_args()
    checkout_locked_components(args.output)


if __name__ == "__main__":
    main()
