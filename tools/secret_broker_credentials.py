#!/usr/bin/env python3
"""Create the local private PKI and KEK inputs for QNAP Secret Broker."""

from __future__ import annotations

import argparse
import datetime as dt
import json
import os
from pathlib import Path

from cryptography import x509
from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.asymmetric import ec
from cryptography.x509.oid import ExtendedKeyUsageOID, NameOID


def _write(path, payload, mode):
    path.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
    descriptor = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL, mode)
    with os.fdopen(descriptor, "wb") as handle:
        handle.write(payload)


def _replace(path, payload, mode):
    temporary = path.with_name(path.name + ".tmp")
    _write(temporary, payload, mode)
    os.replace(temporary, path)


def _private_bytes(key):
    return key.private_bytes(
        serialization.Encoding.PEM,
        serialization.PrivateFormat.PKCS8,
        serialization.NoEncryption(),
    )


def _certificate(subject, issuer, public_key, issuer_key, *, server=False):
    now = dt.datetime.now(dt.timezone.utc)
    builder = (
        x509.CertificateBuilder()
        .subject_name(x509.Name([x509.NameAttribute(NameOID.COMMON_NAME, subject)]))
        .issuer_name(issuer)
        .public_key(public_key)
        .serial_number(x509.random_serial_number())
        .not_valid_before(now - dt.timedelta(minutes=5))
        .not_valid_after(now + dt.timedelta(days=397))
        .add_extension(x509.BasicConstraints(ca=False, path_length=None), critical=True)
        .add_extension(
            x509.ExtendedKeyUsage(
                [
                    ExtendedKeyUsageOID.SERVER_AUTH
                    if server
                    else ExtendedKeyUsageOID.CLIENT_AUTH
                ]
            ),
            critical=False,
        )
    )
    if server:
        builder = builder.add_extension(
            x509.SubjectAlternativeName([x509.DNSName("secret-broker")]),
            critical=False,
        )
    return builder.sign(issuer_key, hashes.SHA256())


def add_client(root, name):
    if name not in {"profile-sync", "control-plane"}:
        raise ValueError("unsupported Secret Broker client")
    root = Path(root)
    ca_key = serialization.load_pem_private_key(
        (root / "tls/ca.key").read_bytes(), password=None
    )
    ca = x509.load_pem_x509_certificate(
        (root / "tls/clients-ca.crt").read_bytes()
    )
    destination = root / name
    if destination.exists() and any(destination.iterdir()):
        raise RuntimeError("Secret Broker client credential already exists")
    key = ec.generate_private_key(ec.SECP256R1())
    certificate = _certificate(name, ca.subject, key.public_key(), ca_key)
    _write(destination / "ca.crt", ca.public_bytes(serialization.Encoding.PEM), 0o600)
    _write(destination / "client.key", _private_bytes(key), 0o600)
    _write(
        destination / "client.crt",
        certificate.public_bytes(serialization.Encoding.PEM),
        0o600,
    )
    metadata_path = root / "metadata.json"
    if metadata_path.is_file():
        metadata = json.loads(metadata_path.read_text(encoding="utf-8"))
        clients = set(metadata.get("clients", []))
        clients.add(name)
        metadata["clients"] = sorted(clients)
        _replace(
            metadata_path,
            (json.dumps(metadata, indent=2, sort_keys=True) + "\n").encode(),
            0o600,
        )
    return {"client": name, "status": "created"}


def initialize(root):
    root = Path(root)
    if root.exists() and any(root.iterdir()):
        raise RuntimeError("Secret Broker credential directory already exists")
    root.mkdir(parents=True, exist_ok=True, mode=0o700)
    ca_key = ec.generate_private_key(ec.SECP256R1())
    now = dt.datetime.now(dt.timezone.utc)
    ca_name = x509.Name(
        [x509.NameAttribute(NameOID.COMMON_NAME, "mwoDevelop Secret Broker CA")]
    )
    ca = (
        x509.CertificateBuilder()
        .subject_name(ca_name)
        .issuer_name(ca_name)
        .public_key(ca_key.public_key())
        .serial_number(x509.random_serial_number())
        .not_valid_before(now - dt.timedelta(minutes=5))
        .not_valid_after(now + dt.timedelta(days=1825))
        .add_extension(x509.BasicConstraints(ca=True, path_length=0), critical=True)
        .add_extension(
            x509.KeyUsage(
                digital_signature=True,
                content_commitment=False,
                key_encipherment=False,
                data_encipherment=False,
                key_agreement=False,
                key_cert_sign=True,
                crl_sign=True,
                encipher_only=False,
                decipher_only=False,
            ),
            critical=True,
        )
        .sign(ca_key, hashes.SHA256())
    )
    ca_pem = ca.public_bytes(serialization.Encoding.PEM)
    _write(root / "broker-master-key", (os.urandom(32).hex() + "\n").encode(), 0o600)
    _write(root / "tls/ca.key", _private_bytes(ca_key), 0o600)
    _write(root / "tls/clients-ca.crt", ca_pem, 0o600)
    for name, common_name, server in (
        ("server", "secret-broker", True),
        ("health", "secret-broker-health", False),
    ):
        key = ec.generate_private_key(ec.SECP256R1())
        certificate = _certificate(
            common_name, ca.subject, key.public_key(), ca_key, server=server
        )
        _write(root / ("tls/%s.key" % name), _private_bytes(key), 0o600)
        _write(
            root / ("tls/%s.crt" % name),
            certificate.public_bytes(serialization.Encoding.PEM),
            0o600,
        )
    for client_name in ("profile-sync", "control-plane"):
        add_client(root, client_name)
    report = {
        "schema": 1,
        "status": "created",
        "server_name": "secret-broker",
        "clients": ["control-plane", "health", "profile-sync"],
    }
    _write(
        root / "metadata.json",
        (json.dumps(report, indent=2, sort_keys=True) + "\n").encode(),
        0o600,
    )
    return report


def main(argv=None):
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--output", default=".kodi-private/secret-broker"
    )
    parser.add_argument(
        "--add-client", choices=("profile-sync", "control-plane")
    )
    args = parser.parse_args(argv)
    result = (
        add_client(args.output, args.add_client)
        if args.add_client
        else initialize(args.output)
    )
    print(json.dumps(result, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
