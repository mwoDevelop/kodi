#!/usr/bin/env python3
"""Materialize a private OpenVPN Connect profile from a public Nord template."""

from __future__ import annotations

import argparse
import hashlib
import ipaddress
import json
import os
import re
import stat
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from tools.kodi_inventory import load_private_references


REMOTE = re.compile(r"^remote [A-Za-z0-9.-]+ [0-9]{1,5}$", re.MULTILINE)


def materialize(source, output, username, password, bypass_cidrs):
    source = Path(source).resolve()
    output = Path(output).resolve()
    if source.is_symlink() or not source.is_file():
        raise ValueError("NordVPN source profile is unavailable")
    if any(
        not isinstance(value, str)
        or not value
        or len(value) > 512
        or "\n" in value
        or "\r" in value
        for value in (username, password)
    ):
        raise ValueError("NordVPN service credentials are invalid")
    document = source.read_text(encoding="utf-8")
    if document.count("auth-user-pass") != 1 or "<auth-user-pass>" in document:
        raise ValueError("NordVPN source has an unsupported credential directive")
    if not REMOTE.search(document):
        raise ValueError("NordVPN source has no supported remote endpoint")
    routes = []
    for value in bypass_cidrs:
        network = ipaddress.ip_network(value, strict=True)
        if network.version != 4:
            raise ValueError("OpenVPN Connect bypass must use IPv4")
        routes.append(
            "route %s %s net_gateway" % (network.network_address, network.netmask)
        )
    auth = "<auth-user-pass>\n%s\n%s\n</auth-user-pass>" % (
        username,
        password,
    )
    payload = document.replace(
        "auth-user-pass", "\n".join([*routes, auth]), 1
    ).encode("utf-8")
    output.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
    output.parent.chmod(0o700)
    descriptor, name = tempfile.mkstemp(prefix=".ovpn-", dir=output.parent)
    temporary = Path(name)
    try:
        with os.fdopen(descriptor, "wb") as handle:
            handle.write(payload)
            handle.flush()
            os.fsync(handle.fileno())
        os.chmod(temporary, 0o600)
        os.replace(temporary, output)
    finally:
        temporary.unlink(missing_ok=True)
    metadata = output.lstat()
    if not stat.S_ISREG(metadata.st_mode) or stat.S_IMODE(metadata.st_mode) != 0o600:
        raise RuntimeError("private OpenVPN profile permissions differ")
    return {
        "schema": 1,
        "output": str(output),
        "sha256": hashlib.sha256(payload).hexdigest(),
        "bypass_cidrs": list(bypass_cidrs),
    }


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("source")
    parser.add_argument("output")
    parser.add_argument("--references", default=".env")
    parser.add_argument("--bypass-cidr", action="append", default=[])
    args = parser.parse_args()
    references_path = Path(args.references)
    if not references_path.is_absolute():
        references_path = ROOT / references_path
    references = load_private_references(references_path)
    result = materialize(
        args.source,
        args.output,
        references.get("NORDVPN_SERVICE_USERNAME"),
        references.get("NORDVPN_SERVICE_PASSWORD"),
        args.bypass_cidr,
    )
    print(json.dumps(result, indent=2, sort_keys=True))


if __name__ == "__main__":
    main()
