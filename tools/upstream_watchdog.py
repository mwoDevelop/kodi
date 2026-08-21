#!/usr/bin/env python3
"""Independent GitHub Actions heartbeat watchdog for upstream synchronization."""

import argparse
import datetime as dt
import json
import os
import time
from pathlib import Path
from urllib.parse import quote
from urllib.request import Request, urlopen

API = "https://api.github.com"


def _timestamp(value):
    return dt.datetime.fromisoformat(value.replace("Z", "+00:00")).astimezone(
        dt.timezone.utc
    )


def fetch_runs(repository, workflow, token=None):
    url = "{}/repos/{}/actions/workflows/{}/runs?event=schedule&per_page=1".format(
        API, quote(repository, safe="/"), quote(workflow, safe="")
    )
    headers = {
        "Accept": "application/vnd.github+json",
        "User-Agent": "mwoDevelop-upstream-watchdog/1",
        "X-GitHub-Api-Version": "2022-11-28",
    }
    if token:
        headers["Authorization"] = "Bearer " + token
    with urlopen(Request(url, headers=headers), timeout=20) as response:
        return json.load(response).get("workflow_runs", [])


def evaluate(manifest, fetcher=fetch_runs, now=None, token=None):
    now = now or dt.datetime.now(dt.timezone.utc)
    results = []
    for config in manifest["workflows"]:
        try:
            runs = fetcher(
                config["repository"], config["workflow"], token=token
            )
        except (OSError, ValueError):
            # Availability of the monitoring API is itself observable health.
            # Preserve the complete configured workflow set and fail closed
            # without persisting response bodies, URLs, or credentials.
            results.append(
                {
                    **config,
                    "status": "api_error",
                    "healthy": False,
                }
            )
            continue
        if not runs:
            result = {
                **config,
                "status": "missing",
                "healthy": False,
            }
        else:
            run = runs[0]
            updated = _timestamp(run["updated_at"])
            age = now - updated
            conclusion = run.get("conclusion")
            active = run.get("status") in {"queued", "in_progress", "waiting"}
            healthy = age.total_seconds() <= config["max_age_seconds"] and (
                active or conclusion == "success"
            )
            result = {
                **config,
                "status": run.get("status"),
                "conclusion": conclusion,
                "updated_at": run["updated_at"],
                "age_seconds": max(0, int(age.total_seconds())),
                "run_id": run["id"],
                "healthy": healthy,
            }
        results.append(result)
    return {
        "schema": 2,
        "checked_at": now.isoformat(),
        "healthy": all(item["healthy"] for item in results),
        "workflows": results,
    }


def load_manifest(path):
    payload = json.loads(Path(path).read_text(encoding="utf-8"))
    if (
        payload.get("schema") != 2
        or not isinstance(payload.get("workflows"), list)
        or not payload["workflows"]
    ):
        raise ValueError("invalid watchdog manifest")
    seen = set()
    for item in payload["workflows"]:
        if set(item) != {"repository", "workflow", "max_age_seconds"}:
            raise ValueError("invalid watchdog workflow entry")
        identity = (item["repository"], item["workflow"])
        if (
            identity in seen
            or not all(isinstance(value, str) and value for value in identity)
            or not isinstance(item["max_age_seconds"], int)
            or not 900 <= item["max_age_seconds"] <= 604800
        ):
            raise ValueError("invalid or duplicate watchdog workflow")
        seen.add(identity)
    return payload


def write_status(path, report):
    target = Path(path)
    target.parent.mkdir(parents=True, exist_ok=True)
    temporary = target.with_suffix(target.suffix + ".tmp")
    temporary.write_text(
        json.dumps(report, indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )
    temporary.replace(target)


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "command", choices=("check", "watch"), nargs="?", default="check"
    )
    parser.add_argument("--manifest", default="manifests/upstream-watchdog.json")
    parser.add_argument("--status")
    parser.add_argument("--interval-seconds", type=int, default=21600)
    args = parser.parse_args()
    manifest = load_manifest(args.manifest)
    token = os.environ.get("GITHUB_TOKEN") or None
    while True:
        report = evaluate(manifest, token=token)
        if args.status:
            write_status(args.status, report)
        print(json.dumps(report, indent=2, sort_keys=True), flush=True)
        if args.command == "check":
            return 0 if report["healthy"] else 1
        if args.interval_seconds < 300:
            raise ValueError("watch interval must be at least 300 seconds")
        time.sleep(args.interval_seconds)


if __name__ == "__main__":
    raise SystemExit(main())
