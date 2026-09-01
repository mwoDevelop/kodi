#!/usr/bin/env python3
"""Create or inspect the non-versioned Favourites head-signing authority."""

from __future__ import annotations

import argparse
import base64
import json
import os
import re
import stat
from pathlib import Path


KEY_ID = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._:-]{0,127}$")


def _encode(value):
    return base64.urlsafe_b64encode(value).rstrip(b"=").decode("ascii")


def validate(path):
    path = Path(path)
    metadata = path.lstat()
    if not stat.S_ISREG(metadata.st_mode) or path.is_symlink():
        raise ValueError("authority must be a regular file")
    if stat.S_IMODE(metadata.st_mode) & 0o077:
        raise ValueError("authority permissions are too broad")
    document = json.loads(path.read_text(encoding="utf-8"))
    if (
        not isinstance(document, dict)
        or set(document) != {"schema", "key_id", "seed"}
        or document.get("schema") != 1
        or not KEY_ID.fullmatch(str(document.get("key_id", "")))
        or not isinstance(document.get("seed"), str)
        or "=" in document["seed"]
    ):
        raise ValueError("invalid authority contract")
    try:
        seed = base64.b64decode(
            document["seed"] + "=" * (-len(document["seed"]) % 4),
            altchars=b"-_",
            validate=True,
        )
    except (ValueError, base64.binascii.Error) as error:
        raise ValueError("invalid authority seed") from error
    if len(seed) != 32 or _encode(seed) != document["seed"]:
        raise ValueError("invalid authority seed")
    return {"schema": 1, "key_id": document["key_id"], "status": "VALID"}


def generate(path, key_id):
    if not KEY_ID.fullmatch(str(key_id)):
        raise ValueError("invalid authority key id")
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
    descriptor = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
    try:
        with os.fdopen(descriptor, "w", encoding="utf-8") as handle:
            json.dump(
                {"schema": 1, "key_id": key_id, "seed": _encode(os.urandom(32))},
                handle,
                sort_keys=True,
                separators=(",", ":"),
            )
            handle.write("\n")
            handle.flush()
            os.fsync(handle.fileno())
    except Exception:
        path.unlink(missing_ok=True)
        raise
    return validate(path)


def main(argv=None):
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "command", choices=("generate", "validate"), nargs="?", default="validate"
    )
    parser.add_argument(
        "--output",
        default=".kodi-private/profile-sync-production/favourites-authority.json",
    )
    parser.add_argument("--key-id", default="favourites-authority-1")
    args = parser.parse_args(argv)
    result = (
        generate(args.output, args.key_id)
        if args.command == "generate"
        else validate(args.output)
    )
    print(json.dumps(result, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
