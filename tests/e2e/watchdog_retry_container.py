#!/usr/bin/env python3
"""Offline E2E: published container code, persistent volume, process replacement."""

import argparse
import json
import subprocess
import uuid


def run(*args):
    return subprocess.check_output(["docker", *args], text=True).strip()


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--image", required=True, help="locally built or immutable watchdog image"
    )
    args = parser.parse_args()
    volume = "kodi-watchdog-e2e-" + uuid.uuid4().hex
    run("volume", "create", volume)
    base = [
        "run",
        "--rm",
        "--network",
        "none",
        "--read-only",
        "--cap-drop",
        "ALL",
        "--security-opt",
        "no-new-privileges",
        "--mount",
        "type=volume,source=" + volume + ",target=/var/lib/watchdog",
    ]
    try:
        run(
            *base,
            "--user",
            "0:0",
            "--cap-add",
            "CHOWN",
            "--entrypoint",
            "chown",
            args.image,
            "10001:10001",
            "/var/lib/watchdog",
        )
        run(
            *base,
            args.image,
            "init-ledger",
            "--remediation-ledger",
            "/var/lib/watchdog/attempts.json",
        )
        code = """
import datetime as dt, json
from tools.watchdog_remediation import RetryLedger
from tools.upstream_watchdog import evaluate
now = dt.datetime(2026, 9, 8, 12, tzinfo=dt.timezone.utc)
guard = RetryLedger('/var/lib/watchdog/attempts.json', classifier=lambda *a, **k: 'BILLING_BLOCKED')
manifest = {'workflows': [{'repository': 'example/test', 'workflow': 'test.yml', 'ref': 'main',
    'max_age_seconds': 129600, 'remediation_after_seconds': 90000, 'remediation_cooldown_seconds': 900}]}
runs = [{'id': 1, 'head_branch': 'main', 'status': 'completed', 'event': 'schedule',
    'conclusion': 'failure', 'updated_at': '2026-09-06T12:00:00Z'}]
calls = []
report = evaluate(manifest, fetcher=lambda *a, **k: runs, now=now, retry_ledger=guard,
    remediator=lambda *a, **k: calls.append(1))
assert report['observer_ready'] and report['remediation_ready'] and not report['healthy']
print(json.dumps({'posts': len(calls), 'state': report['workflows'][0]['remediation_state']}))
"""
        first = json.loads(run(*base, "--entrypoint", "python", args.image, "-c", code))
        second = json.loads(
            run(*base, "--entrypoint", "python", args.image, "-c", code)
        )
        assert first == {"posts": 1, "state": "DISPATCHED"}, first
        assert second == {"posts": 0, "state": "NOT_DUE"}, second
        print(
            json.dumps(
                {
                    "result": "PASS",
                    "first_process": first,
                    "replacement_process": second,
                    "network": "none",
                    "simulated_clock": True,
                }
            )
        )
    finally:
        run("volume", "rm", volume)


if __name__ == "__main__":
    main()
