"""Private mTLS envelope service."""

from __future__ import annotations

import json
import secrets
import ssl
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

from .crypto import seal
from .model import ENVELOPE_TYPE, SECRET_TYPE, validate_envelope_request


MAX_REQUEST = 16 * 1024


class BrokerHandler(BaseHTTPRequestHandler):
    server_version = "kodi-secret-broker"

    def log_message(self, *_args):
        return

    def _send(self, status, document):
        payload = json.dumps(document, sort_keys=True, separators=(",", ":")).encode()
        self.send_response(status)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(payload)))
        self.end_headers()
        self.wfile.write(payload)

    def do_GET(self):
        if self.path != "/ready":
            self._send(404, {"error": "not_found"})
            return
        try:
            self._send(200, self.server.store.readiness())
        except Exception:
            self._send(503, {"status": "unavailable"})

    def do_POST(self):
        if self.path != "/v1/envelopes":
            self._send(404, {"error": "not_found"})
            return
        length = int(self.headers.get("Content-Length", "0"))
        if length < 2 or length > MAX_REQUEST:
            self._send(400, {"error": "invalid_request"})
            return
        try:
            request = validate_envelope_request(json.loads(self.rfile.read(length)))
        except (json.JSONDecodeError, TypeError, ValueError):
            self._send(400, {"error": "invalid_request"})
            return
        try:
            secret_set = self.server.store.deliver(request["delivery_mode"])
        except KeyError:
            self._send(404, {"error": "secret_not_available"})
            return
        except Exception:
            self._send(503, {"error": "broker_unavailable"})
            return
        try:
            now = int(time.time())
            metadata = {
                "schema": 1,
                "envelope_type": ENVELOPE_TYPE,
                "secret_type": SECRET_TYPE,
                "secret_set_id": secret_set["secret_set_id"],
                "secret_set_generation": secret_set["generation"],
                "secret_lifecycle": secret_set["lifecycle"],
                "logical_device_id": request["logical_device_id"],
                "enrollment_id": request["enrollment_id"],
                "enrollment_generation": request["enrollment_generation"],
                "encryption_key_id": request["encryption_key_id"],
                "adapter": secret_set["adapter"],
                "addon_id": secret_set["addon_id"],
                "addon_version": secret_set["addon_version"],
                "nonce": "env-" + secrets.token_hex(16),
                "issued_at": now,
                "expires_at": now + 900,
            }
            envelope = seal(
                metadata,
                request["encryption_public_key"],
                secret_set["secret"],
            )
        except (TypeError, ValueError):
            self._send(400, {"error": "invalid_request"})
            return
        except Exception:
            self._send(503, {"error": "broker_unavailable"})
            return
        self._send(200, envelope)


class BrokerServer(ThreadingHTTPServer):
    def __init__(self, address, store):
        super().__init__(address, BrokerHandler)
        self.store = store


def serve(store, host, port, certificate, private_key, client_ca):
    server = BrokerServer((host, port), store)
    context = ssl.SSLContext(ssl.PROTOCOL_TLS_SERVER)
    context.minimum_version = ssl.TLSVersion.TLSv1_2
    context.load_cert_chain(certificate, private_key)
    context.load_verify_locations(client_ca)
    context.verify_mode = ssl.CERT_REQUIRED
    server.socket = context.wrap_socket(server.socket, server_side=True)
    server.serve_forever()
