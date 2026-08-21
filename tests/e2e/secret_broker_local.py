#!/usr/bin/env python3
"""Reproducible local container E2E for Secret Broker lifecycle and HPKE."""

from __future__ import annotations

import argparse
import http.client
import json
import os
import socket
import ssl
import subprocess
import sys
import tempfile
import uuid
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "secret-broker/src"))
sys.path.insert(
    0,
    str(
        ROOT.parent
        / "service.mwodevelop.profilesync/resources/lib"
    ),
)

from kodi_secret_broker.model import b64url_encode
from mwoprofilesync.hpke import decrypt_envelope
from pyhpke import AEADId, CipherSuite, KDFId, KEMId


class Connection(http.client.HTTPSConnection):
    def __init__(self, port, context):
        super().__init__("127.0.0.1", port=port, context=context, timeout=10)

    def connect(self):
        raw = socket.create_connection((self.host, self.port), self.timeout)
        self.sock = self._context.wrap_socket(raw, server_hostname="secret-broker")


def run(*args, input_text=None):
    return subprocess.run(
        args,
        input=input_text,
        text=True,
        check=True,
        capture_output=True,
    ).stdout.strip()


def request(port, tls_root, identity):
    context = ssl.create_default_context(cafile=str(tls_root / "clients-ca.crt"))
    context.load_cert_chain(tls_root / "health.crt", tls_root / "health.key")
    connection = Connection(port, context)
    payload = json.dumps(identity, sort_keys=True, separators=(",", ":")).encode()
    try:
        connection.request(
            "POST",
            "/v1/envelopes",
            body=payload,
            headers={"Content-Type": "application/json"},
        )
        response = connection.getresponse()
        document = json.loads(response.read())
        return response.status, document
    finally:
        connection.close()


def transition(container, expected, target):
    output = run(
        "docker",
        "exec",
        container,
        "kodi-secret-broker",
        "--database",
        "/data/secrets.db",
        "--master-key",
        "/run/secrets/broker-master-key",
        "transition",
        "youtube-home",
        "1",
        "--from",
        expected,
        "--to",
        target,
    )
    return json.loads(output)


def require_envelope(status, document, lifecycle):
    if status != 200:
        raise RuntimeError(
            "Secret Broker returned HTTP %d: %s"
            % (status, document.get("error", "unknown_error"))
        )
    if document.get("secret_lifecycle") != lifecycle:
        raise RuntimeError("Secret Broker returned an unexpected lifecycle")
    return document


def main(argv=None):
    parser = argparse.ArgumentParser()
    parser.add_argument("--image", default="kodi-secret-broker:e2e")
    parser.add_argument(
        "--secret-set",
        default=str(
            ROOT / ".kodi-private/secret-broker/youtube-generation-1.json"
        ),
    )
    parser.add_argument(
        "--private", default=str(ROOT / ".kodi-private/secret-broker")
    )
    args = parser.parse_args(argv)
    private = Path(args.private).resolve()
    secret_set = Path(args.secret_set).resolve()
    expected = json.loads(secret_set.read_text(encoding="utf-8"))["secret"]
    container = "kodi-secret-broker-e2e-" + uuid.uuid4().hex[:12]
    with tempfile.TemporaryDirectory(prefix="secret-broker-e2e-") as temporary:
        data = Path(temporary) / "data"
        data.mkdir(mode=0o700)
        try:
            run(
                "docker",
                "run",
                "-d",
                "--name",
                container,
                "--user",
                "%d:%d" % (os.getuid(), os.getgid()),
                "-p",
                "127.0.0.1::9444",
                "-v",
                str(data) + ":/data",
                "-v",
                str(private / "broker-master-key")
                + ":/run/secrets/broker-master-key:ro",
                "-v",
                str(private / "tls/server.crt") + ":/run/tls/server.crt:ro",
                "-v",
                str(private / "tls/server.key") + ":/run/tls/server.key:ro",
                "-v",
                str(private / "tls/clients-ca.crt")
                + ":/run/tls/client-ca.crt:ro",
                args.image,
            )
            port = int(
                run(
                    "docker",
                    "inspect",
                    "--format",
                    "{{(index (index .NetworkSettings.Ports \"9444/tcp\") 0).HostPort}}",
                    container,
                )
            )
            imported = json.loads(
                run(
                    "docker",
                    "exec",
                    "-i",
                    container,
                    "kodi-secret-broker",
                    "--database",
                    "/data/secrets.db",
                    "--master-key",
                    "/run/secrets/broker-master-key",
                    "import",
                    "--input",
                    "-",
                    input_text=secret_set.read_text(encoding="utf-8"),
                )
            )
            suite = CipherSuite.new(
                KEMId.DHKEM_X25519_HKDF_SHA256,
                KDFId.HKDF_SHA256,
                AEADId.CHACHA20_POLY1305,
            )
            pair = suite.kem.derive_key_pair(b"e2e-recipient" * 3)
            public = b64url_encode(pair.public_key.to_public_bytes())
            private_key = b64url_encode(pair.private_key.to_private_bytes())
            identity = {
                "logical_device_id": "e2e-device",
                "enrollment_id": "enr:e2e-device-00001",
                "enrollment_generation": 1,
                "encryption_key_id": "e2e-encryption-key",
                "encryption_public_key": public,
                "delivery_mode": "shadow",
            }
            status, shadow = request(port, private / "tls", identity)
            require_envelope(status, shadow, "PREPARED")
            assert decrypt_envelope(shadow, private_key) == expected
            identity["delivery_mode"] = "active"
            inactive_status, inactive = request(port, private / "tls", identity)
            if inactive_status != 404:
                raise RuntimeError(
                    "inactive delivery returned HTTP %d: %s"
                    % (inactive_status, inactive.get("error", "unknown_error"))
                )
            transition(container, "PREPARED", "CANARY_VERIFIED")
            identity["delivery_mode"] = "canary"
            status, canary = request(port, private / "tls", identity)
            require_envelope(status, canary, "CANARY_VERIFIED")
            assert decrypt_envelope(canary, private_key) == expected
            transition(container, "CANARY_VERIFIED", "ACTIVE")
            identity["delivery_mode"] = "active"
            status, active = request(port, private / "tls", identity)
            require_envelope(status, active, "ACTIVE")
            assert decrypt_envelope(active, private_key) == expected
            print(
                json.dumps(
                    {
                        "container": "pass",
                        "hpke_backend": "pass",
                        "import_generation": imported["generation"],
                        "lifecycle": ["PREPARED", "CANARY_VERIFIED", "ACTIVE"],
                        "secret_values_reported": False,
                    },
                    sort_keys=True,
                )
            )
        finally:
            subprocess.run(
                ("docker", "rm", "-f", container),
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
            )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
