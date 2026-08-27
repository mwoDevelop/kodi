#!/usr/bin/env python3
"""Independent GitHub Actions heartbeat watchdog for upstream synchronization."""

import argparse
import datetime as dt
import http.server
import json
import os
import ssl
import threading
import time
from pathlib import Path
from urllib.parse import quote
from urllib.request import Request, urlopen

API = "https://api.github.com"
MONITORED_STATES = frozenset({"HEALTHY", "FAILED", "UNKNOWN"})


def _timestamp(value):
    return dt.datetime.fromisoformat(value.replace("Z", "+00:00")).astimezone(
        dt.timezone.utc
    )


def fetch_runs(repository, workflow, token=None):
    url = "{}/repos/{}/actions/workflows/{}/runs?per_page=20".format(
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


def dispatch_workflow(repository, workflow, ref="main", token=None):
    """Dispatch one allowlisted workflow without exposing the bearer token."""

    if not token:
        raise ValueError("GitHub token is required for workflow remediation")
    url = "{}/repos/{}/actions/workflows/{}/dispatches".format(
        API, quote(repository, safe="/"), quote(workflow, safe="")
    )
    headers = {
        "Accept": "application/vnd.github+json",
        "Authorization": "Bearer " + token,
        "Content-Type": "application/json",
        "User-Agent": "mwoDevelop-upstream-watchdog/1",
        "X-GitHub-Api-Version": "2022-11-28",
    }
    payload = json.dumps({"ref": ref}).encode("utf-8")
    request = Request(url, data=payload, headers=headers, method="POST")
    with urlopen(request, timeout=20) as response:
        if response.status != 204:
            raise OSError("unexpected workflow dispatch status")


def _safe_run(run):
    return {
        "id": run.get("id"),
        "event": run.get("event"),
        "status": run.get("status"),
        "conclusion": run.get("conclusion"),
        "updated_at": run.get("updated_at"),
    }


def _select_runs(runs):
    scheduled_index = next(
        (index for index, item in enumerate(runs) if item.get("event") == "schedule"),
        None,
    )
    scheduled = runs[scheduled_index] if scheduled_index is not None else None
    manual = next(
        (
            item
            for item in runs[:scheduled_index]
            if item.get("event") == "workflow_dispatch"
            and (
                item.get("status") in {"queued", "in_progress", "waiting"}
                or item.get("conclusion") == "success"
            )
        ),
        None,
    ) if scheduled_index is not None else None
    effective = manual or scheduled
    return scheduled, effective


def evaluate(
    manifest,
    fetcher=fetch_runs,
    now=None,
    token=None,
    remediator=None,
):
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
                    "monitored_state": "UNKNOWN",
                }
            )
            continue
        scheduled, effective = _select_runs(runs)
        if not scheduled:
            result = {
                **config,
                "status": "missing",
                "healthy": False,
                "monitored_state": "FAILED",
            }
        else:
            try:
                run = effective or scheduled
                updated = _timestamp(run["updated_at"])
                age = now - updated
                conclusion = run.get("conclusion")
                active = run.get("status") in {
                    "queued",
                    "in_progress",
                    "waiting",
                }
                healthy = (
                    age.total_seconds() <= config["max_age_seconds"]
                    and (active or conclusion == "success")
                )
                result = {
                    **config,
                    "status": run.get("status"),
                    "conclusion": conclusion,
                    "updated_at": run["updated_at"],
                    "age_seconds": max(0, int(age.total_seconds())),
                    "run_id": run["id"],
                    "run_event": run.get("event"),
                    "latest_scheduled_run": _safe_run(scheduled),
                    "healthy": healthy,
                    "monitored_state": "HEALTHY" if healthy else "FAILED",
                }
                remediation_state = "DISABLED"
                remediation_error_code = None
                if remediator is not None and not active:
                    age_seconds = max(0, int(age.total_seconds()))
                    threshold = config["remediation_after_seconds"]
                    cooldown = config["remediation_cooldown_seconds"]
                    due = (
                        conclusion == "success" and age_seconds >= threshold
                    ) or (
                        conclusion != "success" and age_seconds >= cooldown
                    )
                    if due:
                        try:
                            remediator(
                                config["repository"],
                                config["workflow"],
                                ref="main",
                                token=token,
                            )
                            remediation_state = "DISPATCHED"
                        except (OSError, ValueError) as error:
                            remediation_state = "FAILED"
                            remediation_error_code = type(error).__name__
                    else:
                        remediation_state = "NOT_DUE"
                result["remediation_state"] = remediation_state
                result["remediation_error_code"] = remediation_error_code
            except (KeyError, TypeError, ValueError):
                result = {
                    **config,
                    "status": "contract_error",
                    "healthy": False,
                    "monitored_state": "UNKNOWN",
                }
        results.append(result)
    unknown = sum(item["monitored_state"] == "UNKNOWN" for item in results)
    if unknown == 0:
        collection_state = "READY"
    elif unknown == len(results):
        collection_state = "ERROR"
    else:
        collection_state = "PARTIAL"
    if unknown:
        monitored_state = "UNKNOWN"
    elif all(item["monitored_state"] == "HEALTHY" for item in results):
        monitored_state = "HEALTHY"
    else:
        monitored_state = "FAILED"
    return {
        "schema": 2,
        "checked_at": now.isoformat(),
        "observer_ready": collection_state == "READY",
        "collection_state": collection_state,
        "monitored_state": monitored_state,
        # Compatibility alias for the N/N+1 migration window.
        "healthy": monitored_state == "HEALTHY",
        "workflows": results,
    }


def validate_status(
    report,
    manifest,
    now=None,
    max_age_seconds=28800,
    max_clock_skew_seconds=300,
):
    """Validate observer readiness without coupling it to workflow health."""

    now = now or dt.datetime.now(dt.timezone.utc)
    if (
        not isinstance(report, dict)
        or report.get("schema") != 2
        or report.get("observer_ready") is not True
        or report.get("collection_state") != "READY"
        or report.get("monitored_state") not in MONITORED_STATES
        or not isinstance(report.get("healthy"), bool)
        or report["healthy"] != (report["monitored_state"] == "HEALTHY")
        or not isinstance(report.get("workflows"), list)
    ):
        return False
    try:
        checked = _timestamp(report["checked_at"])
    except (KeyError, AttributeError, TypeError, ValueError):
        return False
    age = (now - checked).total_seconds()
    if age > max_age_seconds or age < -max_clock_skew_seconds:
        return False
    expected = {
        (item["repository"], item["workflow"])
        for item in manifest["workflows"]
    }
    observed = {
        (item.get("repository"), item.get("workflow"))
        for item in report["workflows"]
        if isinstance(item, dict)
    }
    if len(report["workflows"]) != len(expected) or observed != expected:
        return False
    return all(
        item.get("monitored_state") in MONITORED_STATES
        and isinstance(item.get("healthy"), bool)
        for item in report["workflows"]
    )


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
        if set(item) != {
            "repository",
            "workflow",
            "max_age_seconds",
            "remediation_after_seconds",
            "remediation_cooldown_seconds",
        }:
            raise ValueError("invalid watchdog workflow entry")
        identity = (item["repository"], item["workflow"])
        if (
            identity in seen
            or not all(isinstance(value, str) and value for value in identity)
            or not isinstance(item["max_age_seconds"], int)
            or not 900 <= item["max_age_seconds"] <= 604800
            or not isinstance(item["remediation_after_seconds"], int)
            or not 900 <= item["remediation_after_seconds"] <= item["max_age_seconds"]
            or not isinstance(item["remediation_cooldown_seconds"], int)
            or not 300 <= item["remediation_cooldown_seconds"] <= 86400
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


class StatusState:
    def __init__(self):
        self._lock = threading.Lock()
        self._report = None

    def set(self, report):
        with self._lock:
            self._report = report

    def get(self):
        with self._lock:
            return self._report


def start_observer(listen, port, certificate, key, client_ca, state):
    class Handler(http.server.BaseHTTPRequestHandler):
        def do_GET(self):
            if self.path != "/v1/status":
                self.send_error(404)
                return
            report = state.get()
            if report is None:
                payload = b'{"status":"not_ready"}\n'
                status = 503
            else:
                payload = (json.dumps(report, sort_keys=True) + "\n").encode("utf-8")
                status = 200
            self.send_response(status)
            self.send_header("Content-Type", "application/json")
            self.send_header("Cache-Control", "no-store")
            self.send_header("Content-Length", str(len(payload)))
            self.end_headers()
            self.wfile.write(payload)

        def log_message(self, _format, *_args):
            return

    server = http.server.ThreadingHTTPServer((listen, port), Handler)
    context = ssl.SSLContext(ssl.PROTOCOL_TLS_SERVER)
    context.minimum_version = ssl.TLSVersion.TLSv1_2
    context.load_cert_chain(certificate, key)
    context.load_verify_locations(client_ca)
    context.verify_mode = ssl.CERT_REQUIRED
    server.socket = context.wrap_socket(server.socket, server_side=True)
    thread = threading.Thread(
        target=server.serve_forever, name="watchdog-observer", daemon=True
    )
    thread.start()
    return server, thread


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "command", choices=("check", "watch", "health"), nargs="?", default="check"
    )
    parser.add_argument("--manifest", default="manifests/upstream-watchdog.json")
    parser.add_argument("--status")
    parser.add_argument("--interval-seconds", type=int, default=21600)
    parser.add_argument("--listen")
    parser.add_argument("--port", type=int, default=9445)
    parser.add_argument("--tls-cert")
    parser.add_argument("--tls-key")
    parser.add_argument("--client-ca")
    parser.add_argument("--max-status-age-seconds", type=int, default=28800)
    parser.add_argument("--max-clock-skew-seconds", type=int, default=300)
    parser.add_argument(
        "--remediate",
        action="store_true",
        help="dispatch allowlisted stale workflows using workflow_dispatch",
    )
    args = parser.parse_args()
    manifest = load_manifest(args.manifest)
    if args.command == "health":
        if not args.status:
            parser.error("health requires --status")
        try:
            report = json.loads(Path(args.status).read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            return 1
        return 0 if validate_status(
            report,
            manifest,
            max_age_seconds=args.max_status_age_seconds,
            max_clock_skew_seconds=args.max_clock_skew_seconds,
        ) else 1
    token = os.environ.get("GITHUB_TOKEN") or None
    state = StatusState()
    server = thread = None
    observer_values = (args.tls_cert, args.tls_key, args.client_ca)
    if args.listen:
        if args.command != "watch" or not all(observer_values):
            parser.error("observer requires watch mode and complete mTLS files")
        _server, _thread = start_observer(
            args.listen,
            args.port,
            args.tls_cert,
            args.tls_key,
            args.client_ca,
            state,
        )
    elif any(observer_values):
        parser.error("observer TLS files require --listen")
    while True:
        report = evaluate(
            manifest,
            token=token,
            remediator=dispatch_workflow if args.remediate else None,
        )
        state.set(report)
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
