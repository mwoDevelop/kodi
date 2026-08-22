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
            "-set_serial",
            hex(secrets.randbits(159) | 1),
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
            "subjectAltName=IP:%s,DNS:control-plane\nextendedKeyUsage=serverAuth\nkeyUsage=digitalSignature,keyEncipherment\n"
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
        web_client_certificate, web_client_key = issue(
            temporary,
            operator_ca_certificate,
            operator_ca_key,
            "web-client",
            "control-plane-web-readonly",
            "extendedKeyUsage=clientAuth\nkeyUsage=digitalSignature\n",
        )
        authz_server_certificate, authz_server_key = issue(
            temporary,
            operator_ca_certificate,
            operator_ca_key,
            "authz-server",
            "control-plane-authz",
            "subjectAltName=DNS:control-plane-authz\nextendedKeyUsage=serverAuth\nkeyUsage=digitalSignature,keyEncipherment\n",
        )
        authz_client_certificate, authz_client_key = issue(
            temporary,
            operator_ca_certificate,
            operator_ca_key,
            "authz-client",
            "control-plane-web-authz-client",
            "extendedKeyUsage=clientAuth\nkeyUsage=digitalSignature\n",
        )
        web = temporary / "web"
        authz = temporary / "authz"
        web.mkdir(mode=0o700)
        authz.mkdir(mode=0o700)
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
            (web_client_certificate, web / "core-client.crt"),
            (web_client_key, web / "core-client.key"),
            (operator_ca_certificate, web / "core-ca.crt"),
            (authz_client_certificate, web / "authz-client.crt"),
            (authz_client_key, web / "authz-client.key"),
            (operator_ca_certificate, web / "authz-ca.crt"),
            (authz_server_certificate, authz / "server.crt"),
            (authz_server_key, authz / "server.key"),
            (operator_ca_certificate, authz / "clients-ca.crt"),
        ):
            shutil.copyfile(source, destination)
        auth_key = authz / "aead.key"
        auth_key.write_text(secrets.token_hex(32), encoding="ascii")
        checkpoint = temporary / "audit-checkpoint.key"
        checkpoint.write_text(secrets.token_hex(32) + "\n", encoding="ascii")
        for path in (tls / "ca.key", tls / "server.key", tls / "operator-client.key", profile / "client.key", watchdog / "server.key", watchdog / "client.key", web / "core-client.key", web / "authz-client.key", authz / "server.key", auth_key, checkpoint):
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
        for generated in temporary.glob("web-client.*"):
            generated.unlink()
        for generated in temporary.glob("authz-*.*"):
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


def extend_existing(output, host_ip):
    output = Path(output).expanduser().resolve()
    if not output.is_dir() or output.is_symlink():
        raise CredentialError("existing Control Plane credential directory is invalid")
    ca_certificate = output / "tls/ca.crt"
    ca_key = private_file(output / "tls/ca.key", "Control Plane CA key")
    try:
        address = ipaddress.ip_address(host_ip)
    except ValueError as error:
        raise CredentialError("host IP is invalid") from error
    if not address.is_private or address.is_loopback or address.is_unspecified:
        raise CredentialError("host IP must be a private LAN address")
    temporary = Path(tempfile.mkdtemp(prefix=".control-plane-extend-", dir=output.parent))
    temporary.chmod(0o700)
    try:
        issued = {}
        issued["server"] = issue(
            temporary,
            ca_certificate,
            ca_key,
            "control-plane-server",
            str(address),
            "subjectAltName=IP:%s,DNS:control-plane\nextendedKeyUsage=serverAuth\nkeyUsage=digitalSignature,keyEncipherment\n" % address,
        )
        issued["web"] = issue(
            temporary,
            ca_certificate,
            ca_key,
            "web-client",
            "control-plane-web-readonly",
            "extendedKeyUsage=clientAuth\nkeyUsage=digitalSignature\n",
        )
        issued["authz_server"] = issue(
            temporary,
            ca_certificate,
            ca_key,
            "authz-server",
            "control-plane-authz",
            "subjectAltName=DNS:control-plane-authz\nextendedKeyUsage=serverAuth\nkeyUsage=digitalSignature,keyEncipherment\n",
        )
        issued["authz_client"] = issue(
            temporary,
            ca_certificate,
            ca_key,
            "authz-client",
            "control-plane-web-authz-client",
            "extendedKeyUsage=clientAuth\nkeyUsage=digitalSignature\n",
        )
        destinations = {
            output / "tls/server.crt": issued["server"][0],
            output / "tls/server.key": issued["server"][1],
            output / "web/core-client.crt": issued["web"][0],
            output / "web/core-client.key": issued["web"][1],
            output / "web/core-ca.crt": ca_certificate,
            output / "web/authz-client.crt": issued["authz_client"][0],
            output / "web/authz-client.key": issued["authz_client"][1],
            output / "web/authz-ca.crt": ca_certificate,
            output / "authz/server.crt": issued["authz_server"][0],
            output / "authz/server.key": issued["authz_server"][1],
            output / "authz/clients-ca.crt": ca_certificate,
        }
        for destination, source in destinations.items():
            destination.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
            staged = destination.with_name("." + destination.name + ".new")
            shutil.copyfile(source, staged)
            staged.chmod(0o600 if destination.suffix == ".key" else 0o644)
            staged.replace(destination)
        auth_key = output / "authz/aead.key"
        if not auth_key.exists():
            auth_key.write_text(secrets.token_hex(32), encoding="ascii")
            auth_key.chmod(0o600)
    finally:
        shutil.rmtree(temporary, ignore_errors=True)
    return {
        "schema": 1,
        "directory": str(output),
        "host_ip": str(address),
        "extended": True,
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
    parser.add_argument("--extend-existing", action="store_true")
    args = parser.parse_args(argv)
    try:
        result = (
            extend_existing(args.output, args.host_ip)
            if args.extend_existing
            else generate(args.profile_sync_tls, args.output, args.host_ip)
        )
    except (OSError, CredentialError) as error:
        parser.error(str(error))
    print(json.dumps(result, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
