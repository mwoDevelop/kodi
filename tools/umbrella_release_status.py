#!/usr/bin/env python3
"""Create and validate the public, notification-only Umbrella release status."""

import argparse
import datetime as dt
import json
import re
import subprocess
import xml.etree.ElementTree as ET
from pathlib import Path


SCHEMA = 1
COMPONENT = "plugin.video.umbrella"
PIPELINE_STATES = {"in_sync", "detected", "qualifying", "blocked"}
RELEASE_HEALTH = {"healthy", "incident", "unknown"}
SHA40 = re.compile(r"^[0-9a-f]{40}$")
SHA64 = re.compile(r"^[0-9a-f]{64}$")
SAFE_CODE = re.compile(r"^[a-z0-9][a-z0-9_.-]{0,63}$")


def _timestamp(value):
    if not isinstance(value, str) or not value.endswith("Z"):
        raise ValueError("timestamp must use UTC Z form")
    try:
        parsed = dt.datetime.fromisoformat(value[:-1] + "+00:00")
    except ValueError as error:
        raise ValueError("invalid status timestamp") from error
    return parsed.astimezone(dt.timezone.utc)


def _version(value):
    if not isinstance(value, str) or not value:
        raise ValueError("release version is missing")
    parts = value.split(".")
    if any(not part.isdigit() for part in parts):
        raise ValueError("release version must be numeric")
    return tuple(int(part) for part in parts)


def validate(document, now=None):
    expected = {
        "schema",
        "component",
        "pipeline",
        "release",
        "versions",
        "upstream",
        "generated_at",
        "expires_at",
    }
    if not isinstance(document, dict) or set(document) != expected:
        raise ValueError("status contains unsupported or missing fields")
    if document["schema"] != SCHEMA or document["component"] != COMPONENT:
        raise ValueError("status identity is invalid")
    pipeline = document["pipeline"]
    release = document["release"]
    versions = document["versions"]
    upstream = document["upstream"]
    if set(pipeline) != {"state", "candidate_id", "failure_code"}:
        raise ValueError("pipeline status shape is invalid")
    if pipeline["state"] not in PIPELINE_STATES:
        raise ValueError("pipeline state is invalid")
    candidate = pipeline["candidate_id"]
    failure = pipeline["failure_code"]
    if candidate is not None and not SHA64.fullmatch(candidate):
        raise ValueError("candidate ID is invalid")
    if failure is not None and not SAFE_CODE.fullmatch(failure):
        raise ValueError("failure code is invalid")
    if set(release) != {"health"} or release["health"] not in RELEASE_HEALTH:
        raise ValueError("release health is invalid")
    if set(versions) != {"upstream", "stable", "stable_upstream_base"}:
        raise ValueError("version status shape is invalid")
    for value in versions.values():
        _version(value)
    if set(upstream) != {"commit", "stable_base_commit"}:
        raise ValueError("upstream status shape is invalid")
    if not all(SHA40.fullmatch(upstream[field]) for field in upstream):
        raise ValueError("upstream identity is invalid")
    generated = _timestamp(document["generated_at"])
    expires = _timestamp(document["expires_at"])
    if generated >= expires or expires - generated > dt.timedelta(hours=48):
        raise ValueError("status validity window is invalid")
    current = now or dt.datetime.now(dt.timezone.utc)
    if current.tzinfo is None or current > expires:
        raise ValueError("status is expired or verification time is naive")
    return document


def create(
    stable_lock,
    upstream_version,
    upstream_commit,
    stable_base_commit,
    stable_upstream_base,
    pipeline_state,
    release_health,
    generated_at,
    expires_at,
    candidate_id=None,
    failure_code=None,
):
    lock = json.loads(Path(stable_lock).read_text(encoding="utf-8"))
    if lock.get("channel") != "stable" or lock.get("schema") not in (1, 2):
        raise ValueError("invalid stable lock")
    stable = lock.get("components", {}).get(COMPONENT, {}).get("version")
    document = {
        "schema": SCHEMA,
        "component": COMPONENT,
        "pipeline": {
            "state": pipeline_state,
            "candidate_id": candidate_id,
            "failure_code": failure_code,
        },
        "release": {"health": release_health},
        "versions": {
            "upstream": upstream_version,
            "stable": stable,
            "stable_upstream_base": stable_upstream_base,
        },
        "upstream": {
            "commit": upstream_commit,
            "stable_base_commit": stable_base_commit,
        },
        "generated_at": generated_at,
        "expires_at": expires_at,
    }
    return validate(document, now=_timestamp(generated_at))


def stable_upstream_identity(stable_lock, umbrella_checkout):
    lock = json.loads(Path(stable_lock).read_text(encoding="utf-8"))
    pin = lock.get("components", {}).get(COMPONENT, {})
    downstream_commit = pin.get("commit")
    if not SHA40.fullmatch(str(downstream_commit)):
        raise ValueError("stable Umbrella commit is invalid")
    manifest = subprocess.check_output(
        ["git", "-C", str(umbrella_checkout), "show", "%s:downstream-patches.yml" % downstream_commit],
        text=True,
    )
    match = re.search(r"(?m)^\s{2}base:\s*[\"']?([0-9a-f]{40})[\"']?\s*$", manifest)
    if not match:
        raise ValueError("stable Umbrella upstream base is missing")
    base_commit = match.group(1)
    addon_xml = subprocess.check_output(
        [
            "git",
            "-C",
            str(umbrella_checkout),
            "show",
            "%s:omega/%s/addon.xml" % (base_commit, COMPONENT),
        ]
    )
    addon = ET.fromstring(addon_xml)
    version = addon.get("version")
    _version(version)
    return {"commit": base_commit, "version": version}


def write(document, output):
    Path(output).parent.mkdir(parents=True, exist_ok=True)
    Path(output).write_text(
        json.dumps(document, indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )


def main():
    parser = argparse.ArgumentParser()
    commands = parser.add_subparsers(dest="command", required=True)
    compose = commands.add_parser("compose")
    compose.add_argument("--stable-lock", default="manifests/locks/stable.json")
    compose.add_argument("--upstream-version", required=True)
    compose.add_argument("--upstream-commit", required=True)
    compose.add_argument("--stable-base-commit", required=True)
    compose.add_argument("--stable-upstream-base", required=True)
    compose.add_argument("--pipeline-state", choices=sorted(PIPELINE_STATES), required=True)
    compose.add_argument("--release-health", choices=sorted(RELEASE_HEALTH), required=True)
    compose.add_argument("--candidate-id")
    compose.add_argument("--failure-code")
    compose.add_argument("--generated-at", required=True)
    compose.add_argument("--expires-at", required=True)
    compose.add_argument("--output", required=True)
    check = commands.add_parser("validate")
    check.add_argument("--status", required=True)
    identify = commands.add_parser("stable-identity")
    identify.add_argument("--stable-lock", default="manifests/locks/stable.json")
    identify.add_argument("--umbrella-checkout", required=True)
    args = parser.parse_args()
    if args.command == "compose":
        document = create(
            args.stable_lock,
            args.upstream_version,
            args.upstream_commit,
            args.stable_base_commit,
            args.stable_upstream_base,
            args.pipeline_state,
            args.release_health,
            args.generated_at,
            args.expires_at,
            candidate_id=args.candidate_id,
            failure_code=args.failure_code,
        )
        write(document, args.output)
    elif args.command == "validate":
        document = validate(json.loads(Path(args.status).read_text(encoding="utf-8")))
    else:
        document = stable_upstream_identity(args.stable_lock, args.umbrella_checkout)
    print(json.dumps(document, indent=2, sort_keys=True))


if __name__ == "__main__":
    main()
