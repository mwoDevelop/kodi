#!/usr/bin/env python3
"""Generate local-only mTLS material for the read-only Control Plane."""

from __future__ import annotations

import argparse
import ipaddress
import json
import secrets
import shutil
import stat
import subprocess
import tempfile
from pathlib import Path


class CredentialError(RuntimeError):
    pass


def private_file(path, description):
    path = Path(path).expanduser()
    metadata = path.lstat()
    if (
        not stat.S_ISREG(metadata.st_mode)
        or path.is_symlink()
        or stat.S_IMODE(metadata.st_mode) & 0o077
    ):
        raise CredentialError(f"{description} must be a private regular file")
    return path.resolve()


def run(argv, cwd):
    try:
        subprocess.run(
            [str(item) for item in argv],
            cwd=cwd,
            check=True,
            capture_output=True,
            text=True,
        )
    except subprocess.CalledProcessError as error:
        raise CredentialError("OpenSSL credential operation failed") from error


def create_ca(root, name, common_name):
    key = root / f"{name}.key"
    certificate = root / f"{name}.crt"
    run(
        (
            "openssl",
            "req",
            "-x509",
            "-newkey",
            "rsa:3072",
            "-nodes",
            "-days",
            "3650",
            "-sha256",
            "-subj",
            f"/CN={common_name}",
            "-addext",
            "basicConstraints=critical,CA:TRUE,pathlen:0",
            "-addext",
            "keyUsage=critical,keyCertSign,cRLSign",
            "-keyout",
            key,
            "-out",
            certificate,
        ),
        root,
    )
    key.chmod(0o600)
    certificate.chmod(0o644)
    return certificate, key


def issue(root, ca_certificate, ca_key, name, common_name, extension):
    key = root / f"{name}.key"
    request = root / f"{name}.csr"
    certificate = root / f"{name}.crt"
    extfile = root / f"{name}.ext"
    extfile.write_text(extension, encoding="utf-8")
    run(
        (
            "openssl",
            "genpkey",
            "-algorithm",
            "RSA",
            "-pkeyopt",
            "rsa_keygen_bits:3072",
            "-out",
            key,
        ),
        root,
    )
    run(
        (
            "openssl",
            "req",
            "-new",
            "-key",
            key,
            "-subj",
            f"/CN={common_name}",
            "-out",
            request,
        ),
        root,
    )
    run(
        (
            "openssl",
            "x509",
            "-req",
            "-in",
            request,
            "-CA",
            ca_certificate,
            "-CAkey",
            ca_key,
            "-CAcreateserial",
            "-days",
            "825",
            "-sha256",
            "-extfile",
            extfile,
            "-out",
            certificate,
        ),
        root,
    )
    run(("openssl", "verify", "-CAfile", ca_certificate, certificate), root)
    key.chmod(0o600)
    certificate.chmod(0o644)
    request.unlink()
    extfile.unlink()
    return certificate, key


def generate(profile_sync_tls, output, host_ip):
    try:
        address = ipaddress.ip_address(host_ip)
    except ValueError as error:
        raise CredentialError("host IP is invalid") from error
    if not address.is_private or address.is_loopback or address.is_unspecified:
        raise CredentialError("host IP must be a private LAN address")
    profile_sync_tls = Path(profile_sync_tls).expanduser().resolve()
    ca_certificate = profile_sync_tls / "ca.crt"
    ca_key = private_file(profile_sync_tls / "ca.key", "Profile Sync CA key")
    if not ca_certificate.is_file() or ca_certificate.is_symlink():
        raise CredentialError("Profile Sync CA certificate is invalid")
    output = Path(output).expanduser().resolve()
    if output.exists():
        raise CredentialError("Control Plane credential directory already exists")
    output.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
    temporary = Path(tempfile.mkdtemp(prefix=f".{output.name}.", dir=output.parent))
    temporary.chmod(0o700)
    try:
        tls = temporary / "tls"
        profile = temporary / "profile-sync"
        watchdog = temporary / "watchdog"
        tls.mkdir(mode=0o700)
        profile.mkdir(mode=0o700)
        watchdog.mkdir(mode=0o700)
        operator_ca_certificate, operator_ca_key = create_ca(
            temporary,
            "control-plane-ca",
            "mwoDevelop Kodi Control Plane CA",
        )
        server_certificate, server_key = issue(
            temporary,
            operator_ca_certificate,
            operator_ca_key,
            "control-plane-server",
            str(address),
            "subjectAltName=IP:%s\nextendedKeyUsage=serverAuth\nkeyUsage=digitalSignature,keyEncipherment\n"
            % address,
        )
        operator_certificate, operator_key = issue(
            temporary,
            operator_ca_certificate,
            operator_ca_key,
            "operator-client",
            "mwoDevelop Kodi Control Plane operator",
            "extendedKeyUsage=clientAuth\nkeyUsage=digitalSignature\n",
        )
        profile_certificate, profile_key = issue(
            temporary,
            ca_certificate,
            ca_key,
            "profile-sync-client",
            "kodi-control-plane",
            "extendedKeyUsage=clientAuth\nkeyUsage=digitalSignature\n",
        )
        watchdog_server_certificate, watchdog_server_key = issue(
            temporary,
            operator_ca_certificate,
            operator_ca_key,
            "watchdog-server",
            "upstream-watchdog",
            "subjectAltName=DNS:upstream-watchdog\nextendedKeyUsage=serverAuth\nkeyUsage=digitalSignature,keyEncipherment\n",
        )
        watchdog_client_certificate, watchdog_client_key = issue(
            temporary,
            operator_ca_certificate,
            operator_ca_key,
            "watchdog-client",
            "kodi-control-plane-watchdog-observer",
            "extendedKeyUsage=clientAuth\nkeyUsage=digitalSignature\n",
        )
        for source, destination in (
            (server_certificate, tls / "server.crt"),
            (server_key, tls / "server.key"),
            (operator_certificate, tls / "operator-client.crt"),
            (operator_key, tls / "operator-client.key"),
            (operator_ca_certificate, tls / "clients-ca.crt"),
            (operator_ca_certificate, tls / "ca.crt"),
            (operator_ca_key, tls / "ca.key"),
            (profile_certificate, profile / "client.crt"),
            (profile_key, profile / "client.key"),
            (ca_certificate, profile / "ca.crt"),
            (watchdog_server_certificate, watchdog / "server.crt"),
            (watchdog_server_key, watchdog / "server.key"),
            (watchdog_client_certificate, watchdog / "client.crt"),
            (watchdog_client_key, watchdog / "client.key"),
            (operator_ca_certificate, watchdog / "ca.crt"),
            (operator_ca_certificate, watchdog / "clients-ca.crt"),
        ):
            shutil.copyfile(source, destination)
        checkpoint = temporary / "audit-checkpoint.key"
        checkpoint.write_text(secrets.token_hex(32) + "\n", encoding="ascii")
        for path in (tls / "ca.key", tls / "server.key", tls / "operator-client.key", profile / "client.key", watchdog / "server.key", watchdog / "client.key", checkpoint):
            path.chmod(0o600)
        for path in (tls / "ca.crt", tls / "server.crt", tls / "operator-client.crt", tls / "clients-ca.crt", profile / "client.crt", profile / "ca.crt", watchdog / "server.crt", watchdog / "client.crt", watchdog / "ca.crt", watchdog / "clients-ca.crt"):
            path.chmod(0o644)
        for generated in temporary.glob("control-plane-*.*"):
            generated.unlink()
        for generated in temporary.glob("operator-client.*"):
            generated.unlink()
        for generated in temporary.glob("profile-sync-client.*"):
            generated.unlink()
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
        "host_ip": str(address),
        "files": sorted(str(path.relative_to(output)) for path in output.rglob("*") if path.is_file()),
    }


def main(argv=None):
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--profile-sync-tls",
        default=".kodi-private/profile-sync-production/tls",
    )
    parser.add_argument("--output", default=".kodi-private/control-plane")
    parser.add_argument("--host-ip", required=True)
    args = parser.parse_args(argv)
    try:
        result = generate(args.profile_sync_tls, args.output, args.host_ip)
    except (OSError, CredentialError) as error:
        parser.error(str(error))
    print(json.dumps(result, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
