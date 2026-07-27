#!/usr/bin/env python3
"""Administrative CLI for the Kodi profile-sync API."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
from urllib.error import HTTPError
from urllib.parse import urlencode, urlparse
from urllib.request import Request, urlopen


def validate_base_url(value):
    parsed = urlparse(value)
    if parsed.scheme == "https" and parsed.netloc:
        return value.rstrip("/")
    if (
        parsed.scheme == "http"
        and parsed.hostname in {"127.0.0.1", "::1", "localhost"}
    ):
        return value.rstrip("/")
    raise ValueError("admin API must use HTTPS or loopback HTTP")


def request(base, method, path, document=None, idempotency_key=None):
    payload = None
    headers = {"Accept": "application/json"}
    if document is not None:
        payload = json.dumps(document).encode("utf-8")
        headers["Content-Type"] = "application/json"
    if idempotency_key:
        headers["Idempotency-Key"] = idempotency_key
    try:
        with urlopen(
            Request(base + path, data=payload, headers=headers, method=method),
            timeout=15,
        ) as response:
            return json.loads(response.read())
    except HTTPError as error:
        detail = error.read().decode("utf-8", "replace")
        raise RuntimeError(
            "profile-sync API returned HTTP %d: %s" % (error.code, detail)
        ) from error


def load_document(path):
    return json.loads(Path(path).read_text(encoding="utf-8"))


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--base", default="http://127.0.0.1:8765")
    subparsers = parser.add_subparsers(dest="command", required=True)
    subparsers.add_parser("health")
    revision = subparsers.add_parser("put-revision")
    revision.add_argument("manifest")
    publish = subparsers.add_parser("publish-candidate")
    publish.add_argument("channel")
    publish.add_argument("revision_id")
    publish.add_argument("--base-revision")
    publish.add_argument("--expected-candidate-head")
    publish.add_argument("--idempotency-key", required=True)
    assignment = subparsers.add_parser("assign")
    assignment.add_argument("channel")
    assignment.add_argument("document")
    assignment.add_argument("--idempotency-key", required=True)
    report = subparsers.add_parser("report")
    report.add_argument("document")
    report.add_argument("--idempotency-key", required=True)
    lookup = subparsers.add_parser("assignment")
    lookup.add_argument("enrollment_id")
    lookup.add_argument("channel")
    promote = subparsers.add_parser("promote")
    promote.add_argument("channel")
    promote.add_argument("document")
    promote.add_argument("--idempotency-key", required=True)
    args = parser.parse_args()
    base = validate_base_url(args.base)
    if args.command == "health":
        result = request(base, "GET", "/health")
    elif args.command == "put-revision":
        result = request(
            base, "POST", "/v1/revisions", load_document(args.manifest)
        )
    elif args.command == "publish-candidate":
        result = request(
            base,
            "POST",
            "/v1/channels/%s/candidates" % args.channel,
            {
                "revision_id": args.revision_id,
                "base_revision": args.base_revision,
                "expected_candidate_head": args.expected_candidate_head,
            },
            args.idempotency_key,
        )
    elif args.command == "assign":
        result = request(
            base,
            "POST",
            "/v1/channels/%s/assignments" % args.channel,
            load_document(args.document),
            args.idempotency_key,
        )
    elif args.command == "report":
        result = request(
            base,
            "POST",
            "/v1/reports",
            load_document(args.document),
            args.idempotency_key,
        )
    elif args.command == "assignment":
        query = urlencode({"channel": args.channel})
        result = request(
            base,
            "GET",
            "/v1/enrollments/%s/assignment?%s"
            % (args.enrollment_id, query),
        )
    else:
        result = request(
            base,
            "POST",
            "/v1/channels/%s/promote" % args.channel,
            load_document(args.document),
            args.idempotency_key,
        )
    print(json.dumps(result, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
