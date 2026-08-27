#!/usr/bin/env python3
"""Validate the canonical Control Plane schedule and status-source catalogs."""

from __future__ import annotations

import argparse
import json
import re
from pathlib import Path

CRON = re.compile(r"^[0-9*/,\-]+ [0-9*/,\-]+ \* \* \*$")
IDENTIFIER = re.compile(r"^[a-z0-9][a-z0-9-]{1,95}$")
REPOSITORY = re.compile(r"^[A-Za-z0-9_.-]+/[A-Za-z0-9_.-]+$")
WORKFLOW = re.compile(r"^[A-Za-z0-9_.-]+\.ya?ml$")


def _document(path):
    payload = json.loads(Path(path).read_text(encoding="utf-8"))
    if not isinstance(payload, dict):
        raise TypeError(f"{path}: document must be an object")
    return payload


def load_schedules(path):
    payload = _document(path)
    if set(payload) != {"schema", "timezone", "jobs"}:
        raise ValueError("invalid schedule catalog fields")
    if payload["schema"] != 1 or payload["timezone"] != "UTC":
        raise ValueError("unsupported schedule catalog")
    if not isinstance(payload["jobs"], list) or not payload["jobs"]:
        raise ValueError("schedule catalog must contain jobs")
    seen = set()
    for job in payload["jobs"]:
        if not isinstance(job, dict) or not IDENTIFIER.fullmatch(
            str(job.get("id", ""))
        ):
            raise ValueError("invalid schedule id")
        if job["id"] in seen:
            raise ValueError("duplicate schedule id")
        seen.add(job["id"])
        required = {
            "id",
            "kind",
            "owner",
            "grace_seconds",
            "timeout_seconds",
            "stale_after_seconds",
            "retry_policy",
            "dependencies",
        }
        if not required.issubset(job):
            raise ValueError(f"incomplete schedule {job['id']}")
        for field in ("grace_seconds", "timeout_seconds", "stale_after_seconds"):
            if not isinstance(job[field], int) or job[field] < 0:
                raise ValueError(f"invalid {field} in {job['id']}")
        if job["stale_after_seconds"] < job["grace_seconds"]:
            raise ValueError(f"stale threshold precedes grace in {job['id']}")
        if not isinstance(job["dependencies"], list) or not all(
            isinstance(item, str) and item for item in job["dependencies"]
        ):
            raise ValueError(f"invalid dependencies in {job['id']}")
        if job["kind"] == "github_actions":
            expected = required | {"repository", "workflow", "event", "cron"}
            window_policy = {
                "missed_windows_warning",
                "missed_windows_failure",
            }
            expected |= window_policy
            if set(job) != expected:
                raise ValueError(f"unexpected GitHub schedule fields in {job['id']}")
            if (
                not REPOSITORY.fullmatch(job["repository"])
                or not WORKFLOW.fullmatch(job["workflow"])
                or job["event"] != "schedule"
                or not isinstance(job["cron"], list)
                or not job["cron"]
                or not all(CRON.fullmatch(item) for item in job["cron"])
            ):
                raise ValueError(f"invalid GitHub schedule {job['id']}")
            warning = job["missed_windows_warning"]
            failure = job["missed_windows_failure"]
            if (
                not isinstance(warning, int)
                or not isinstance(failure, int)
                or warning < 1
                or failure < warning
                or failure > 96
            ):
                raise ValueError(f"invalid missed-window policy in {job['id']}")
        elif job["kind"] in {"internal_interval", "device_interval"}:
            expected = required | {"interval_seconds", "observer"}
            if set(job) != expected or not isinstance(job["interval_seconds"], int):
                raise ValueError(f"invalid interval schedule {job['id']}")
            if job["interval_seconds"] < 300:
                raise ValueError(f"interval too short in {job['id']}")
        else:
            raise ValueError(f"unsupported schedule kind in {job['id']}")
    return payload


def load_status_sources(path):
    payload = _document(path)
    if set(payload) != {"schema", "sources"} or payload["schema"] != 1:
        raise ValueError("unsupported status-source catalog")
    if not isinstance(payload["sources"], list) or not payload["sources"]:
        raise ValueError("status-source catalog must contain sources")
    fields = {
        "id",
        "owner",
        "adapter",
        "auth",
        "stale_after_seconds",
        "trust_level",
        "fallback",
        "reason_codes",
    }
    seen = set()
    for source in payload["sources"]:
        if not isinstance(source, dict) or set(source) != fields:
            raise ValueError("invalid status-source fields")
        if not IDENTIFIER.fullmatch(str(source["id"])) or source["id"] in seen:
            raise ValueError("invalid or duplicate status-source id")
        seen.add(source["id"])
        if (
            not isinstance(source["stale_after_seconds"], int)
            or not 60 <= source["stale_after_seconds"] <= 604800
        ):
            raise ValueError(f"invalid stale threshold in {source['id']}")
        if not isinstance(source["reason_codes"], list) or not source["reason_codes"]:
            raise ValueError(f"missing reason codes in {source['id']}")
        for field in ("owner", "adapter", "auth", "trust_level", "fallback"):
            if not isinstance(source[field], str) or not source[field]:
                raise ValueError(f"invalid {field} in {source['id']}")
    return payload


def load_severity_policy(path):
    payload = _document(path)
    if set(payload) != {"schema", "rules"} or payload["schema"] != 1:
        raise ValueError("unsupported severity policy")
    fields = {
        "condition_axis",
        "reason_code",
        "severity",
        "overall_state",
        "condition_family",
    }
    if not isinstance(payload["rules"], list) or not payload["rules"]:
        raise ValueError("severity policy must contain rules")
    seen = set()
    for rule in payload["rules"]:
        if not isinstance(rule, dict) or set(rule) != fields:
            raise ValueError("invalid severity policy fields")
        key = (rule["condition_axis"], rule["reason_code"])
        if (
            not IDENTIFIER.fullmatch(str(rule["condition_axis"]))
            or not re.fullmatch(r"^[A-Z][A-Z0-9_]{1,95}$", str(rule["reason_code"]))
            or not IDENTIFIER.fullmatch(str(rule["condition_family"]))
            or rule["severity"] not in {"none", "warning", "critical"}
            or rule["overall_state"] not in {"OK", "DEGRADED"}
            or key in seen
        ):
            raise ValueError("invalid severity policy rule")
        seen.add(key)
    return payload


def watchdog_entries(path):
    payload = _document(path)
    if payload.get("schema") != 2 or not isinstance(payload.get("workflows"), list):
        raise ValueError("unsupported watchdog catalog")
    return {
        (item["repository"], item["workflow"]): item["max_age_seconds"]
        for item in payload["workflows"]
    }


def compare_watchdog(schedules, watchdog_path):
    expected = {
        (job["repository"], job["workflow"]): job["stale_after_seconds"]
        for job in schedules["jobs"]
        if job["kind"] == "github_actions"
    }
    actual = watchdog_entries(watchdog_path)
    if actual != expected:
        raise ValueError("watchdog and schedule catalogs differ")


def main(argv=None):
    parser = argparse.ArgumentParser()
    parser.add_argument("--schedules", default="manifests/control-plane-schedules.json")
    parser.add_argument(
        "--status-sources", default="manifests/control-plane-status-sources.json"
    )
    parser.add_argument(
        "--severity-policy", default="manifests/control-plane-severity-policy.json"
    )
    parser.add_argument("--watchdog", default="manifests/upstream-watchdog.json")
    args = parser.parse_args(argv)
    schedules = load_schedules(args.schedules)
    status_sources = load_status_sources(args.status_sources)
    severity_policy = load_severity_policy(args.severity_policy)
    compare_watchdog(schedules, args.watchdog)
    print(
        json.dumps(
            {
                "schema": 1,
                "jobs": len(schedules["jobs"]),
                "sources": len(status_sources["sources"]),
                "severity_rules": len(severity_policy["rules"]),
                "status": "ok",
            },
            sort_keys=True,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
