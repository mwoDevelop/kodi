#!/usr/bin/env python3
"""Generate local-only mTLS material for the Watchdog observer endpoint."""

from __future__ import annotations

import argparse
import json
import shutil
import tempfile
from pathlib import Path

try:
    from control_plane_credentials import CredentialError, issue, private_file
except ModuleNotFoundError:
    from tools.control_plane_credentials import CredentialError, issue, private_file


def generate(control_plane_tls, output, server_name="upstream-watchdog"):
    control_plane_tls = Path(control_plane_tls).expanduser().resolve()
    ca_certificate = control_plane_tls / "ca.crt"
    ca_key = private_file(control_plane_tls / "ca.key", "Control Plane CA key")
    if not ca_certificate.is_file() or ca_certificate.is_symlink():
        raise CredentialError("Control Plane CA certificate is invalid")
    if not server_name or any(char not in "abcdefghijklmnopqrstuvwxyz0123456789-." for char in server_name):
        raise CredentialError("watchdog server name is invalid")
    output = Path(output).expanduser().resolve()
    if output.exists():
        raise CredentialError("Watchdog observer credential directory already exists")
    output.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
    temporary = Path(tempfile.mkdtemp(prefix=f".{output.name}.", dir=output.parent))
    temporary.chmod(0o700)
    try:
        server_certificate, server_key = issue(
            temporary,
            ca_certificate,
            ca_key,
            "watchdog-server",
            server_name,
            "subjectAltName=DNS:%s\nextendedKeyUsage=serverAuth\nkeyUsage=digitalSignature,keyEncipherment\n"
            % server_name,
        )
        client_certificate, client_key = issue(
            temporary,
            ca_certificate,
            ca_key,
            "watchdog-client",
            "kodi-control-plane-watchdog-observer",
            "extendedKeyUsage=clientAuth\nkeyUsage=digitalSignature\n",
        )
        for source, destination in (
            (server_certificate, temporary / "server.crt"),
            (server_key, temporary / "server.key"),
            (client_certificate, temporary / "client.crt"),
            (client_key, temporary / "client.key"),
            (ca_certificate, temporary / "ca.crt"),
            (ca_certificate, temporary / "clients-ca.crt"),
        ):
            if source != destination:
                shutil.copyfile(source, destination)
        for path in (temporary / "server.key", temporary / "client.key"):
            path.chmod(0o600)
        for path in (
            temporary / "server.crt",
            temporary / "client.crt",
            temporary / "ca.crt",
            temporary / "clients-ca.crt",
        ):
            path.chmod(0o644)
        for generated in temporary.glob("watchdog-*.*"):
            generated.unlink()
        temporary.replace(output)
        output.chmod(0o700)
    finally:
        if temporary.exists():
            shutil.rmtree(temporary)
    return {
        "schema": 1,
        "directory": str(output),
        "server_name": server_name,
        "files": sorted(path.name for path in output.iterdir() if path.is_file()),
    }


def main(argv=None):
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--control-plane-tls", default=".kodi-private/control-plane/tls"
    )
    parser.add_argument(
        "--output", default=".kodi-private/control-plane/watchdog"
    )
    parser.add_argument("--server-name", default="upstream-watchdog")
    args = parser.parse_args(argv)
    try:
        result = generate(args.control_plane_tls, args.output, args.server_name)
    except (OSError, CredentialError) as error:
        parser.error(str(error))
    print(json.dumps(result, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
