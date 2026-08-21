#!/usr/bin/env python3
"""Build an ignored Secret Broker import document from the portable session."""

from __future__ import annotations

import argparse
import datetime as dt
import json
import os
from pathlib import Path


SESSION_FIELDS = {
    "account_hint",
    "api_key",
    "client_id",
    "client_secret",
    "expected_channel_id",
    "personal_refresh_token",
    "tv_refresh_token",
    "vr_refresh_token",
}


def build(session, secret_set_id, generation):
    if (
        not isinstance(session, dict)
        or session.get("schema") != 1
        or session.get("addon_id") != "plugin.video.youtube"
        or not isinstance(session.get("addon_version"), str)
    ):
        raise ValueError("invalid private YouTube session")
    secret = {name: session.get(name) for name in SESSION_FIELDS}
    if any(not isinstance(value, str) or not value for value in secret.values()):
        raise ValueError("private YouTube session is incomplete")
    now = (
        dt.datetime.now(dt.timezone.utc)
        .replace(microsecond=0)
        .isoformat()
        .replace("+00:00", "Z")
    )
    return {
        "schema": 1,
        "secret_type": "youtube-session-v1",
        "secret_set_id": secret_set_id,
        "generation": generation,
        "lifecycle": "PREPARED",
        "addon_id": session["addon_id"],
        "addon_version": session["addon_version"],
        "adapter": "youtube-oauth-v1",
        "created_utc": now,
        "verified_utc": now,
        "secret": secret,
    }


def write_exclusive(path, document):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
    descriptor = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
    with os.fdopen(descriptor, "w", encoding="utf-8") as destination:
        json.dump(document, destination, sort_keys=True, separators=(",", ":"))
        destination.write("\n")
        destination.flush()
        os.fsync(destination.fileno())


def main(argv=None):
    parser = argparse.ArgumentParser()
    parser.add_argument("--session", default=".kodi-private/youtube/session.json")
    parser.add_argument(
        "--output", default=".kodi-private/secret-broker/youtube-generation-1.json"
    )
    parser.add_argument("--secret-set-id", default="youtube-home")
    parser.add_argument("--generation", type=int, default=1)
    args = parser.parse_args(argv)
    if args.generation < 1:
        raise ValueError("generation must be positive")
    document = build(
        json.loads(Path(args.session).read_text(encoding="utf-8")),
        args.secret_set_id,
        args.generation,
    )
    write_exclusive(args.output, document)
    print(
        json.dumps(
            {
                "generation": args.generation,
                "lifecycle": "PREPARED",
                "output": args.output,
                "secret_set_id": args.secret_set_id,
            },
            sort_keys=True,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
