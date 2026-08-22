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
        scheduled, effective = _select_runs(runs)
        if not scheduled:
            result = {
                **config,
                "status": "missing",
                "healthy": False,
            }
        else:
            run = effective or scheduled
            scheduled_updated = _timestamp(scheduled["updated_at"])
            updated = _timestamp(run["updated_at"])
            age = now - updated
            scheduled_age = now - scheduled_updated
            conclusion = run.get("conclusion")
            active = run.get("status") in {"queued", "in_progress", "waiting"}
            healthy = (
                scheduled_age.total_seconds() <= config["max_age_seconds"]
                and age.total_seconds() <= config["max_age_seconds"]
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
        "command", choices=("check", "watch"), nargs="?", default="check"
    )
    parser.add_argument("--manifest", default="manifests/upstream-watchdog.json")
    parser.add_argument("--status")
    parser.add_argument("--interval-seconds", type=int, default=21600)
    parser.add_argument("--listen")
    parser.add_argument("--port", type=int, default=9445)
    parser.add_argument("--tls-cert")
    parser.add_argument("--tls-key")
    parser.add_argument("--client-ca")
    args = parser.parse_args()
    manifest = load_manifest(args.manifest)
    token = os.environ.get("GITHUB_TOKEN") or None
    state = StatusState()
    server = thread = None
    observer_values = (args.tls_cert, args.tls_key, args.client_ca)
    if args.listen:
        if args.command != "watch" or not all(observer_values):
            parser.error("observer requires watch mode and complete mTLS files")
        server, thread = start_observer(
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
        report = evaluate(manifest, token=token)
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
