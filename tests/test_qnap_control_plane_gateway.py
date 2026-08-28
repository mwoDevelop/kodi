import base64
import hashlib
import hmac
import json
import os
import struct
import subprocess
import threading
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

import pytest

from tools.qnap_control_plane_gateway import (
    BACKEND_PORT,
    CGI_ROOT,
    DISPLAY_NAME,
    NAME,
    PUBLIC_BASE,
    QDK_SHA256,
    VERSION,
    WEBUI,
    load_operator,
    validate_source,
)


@pytest.fixture
def repository_root():
    return Path(__file__).resolve().parents[1]


def test_gateway_source_is_minimal_and_fail_closed(repository_root):
    assert validate_source(repository_root) == {
        "name": NAME,
        "version": VERSION,
        "backend_port": BACKEND_PORT,
        "public_base": PUBLIC_BASE,
    }
    assert len(QDK_SHA256) == 64
    int(QDK_SHA256, 16)


def test_gateway_webui_uses_system_https_cgi_path(repository_root):
    config = (
        repository_root / "deploy/qnap-control-plane-gateway/qpkg.cfg"
    ).read_text(encoding="utf-8")
    assert f'QPKG_WEBUI="{WEBUI}"' in config
    assert f'QPKG_DISPLAY_NAME="{DISPLAY_NAME}"' in config
    assert 'QPKG_WEB_PORT="-2"' in config
    assert 'QPKG_WEB_SSL_PORT="-1"' in config
    assert 'QPKG_USE_PROXY="0"' in config
    assert "QPKG_PROXY_PATH" not in config
    assert "QPKG_SERVICE_PROGRAM" not in config


def test_gateway_contains_no_credentials_or_generated_package(repository_root):
    root = repository_root / "deploy/qnap-control-plane-gateway"
    assert not list(root.rglob("*.qpkg"))
    text = "\n".join(
        path.read_text(encoding="utf-8") for path in root.rglob("*") if path.is_file()
    ).lower()
    assert "github_token" not in text
    assert "password=" not in text
    assert not (root / "shared/private").exists()


def test_operator_credentials_are_loaded_only_from_private_file(tmp_path):
    secret = base64.b32encode(b"0123456789abcdefghij").decode("ascii").rstrip("=")
    operator = tmp_path / "operator.json"
    operator.write_text(
        json.dumps(
            {
                "schema": 1,
                "username": "mwo",
                "password": "local-only-credential_123",
                "totp_uri": f"otpauth://totp/mwo?secret={secret}&issuer=test",
            }
        ),
        encoding="utf-8",
    )
    operator.chmod(0o600)
    assert load_operator(operator) == {
        "username": "mwo",
        "credential": "local-only-credential_123",
        "totp_secret": secret,
    }
    operator.chmod(0o640)
    with pytest.raises(RuntimeError, match="permissions"):
        load_operator(operator)


def test_gateway_uses_only_fixed_system_curl_locations(repository_root):
    script = (
        repository_root / "deploy/qnap-control-plane-gateway/shared/www/gateway.cgi"
    ).read_text(encoding="utf-8")
    assert "command -v" not in script
    assert "for candidate in /sbin/curl /usr/bin/curl /usr/local/bin/curl" in script


def test_gateway_http_request_redirects_to_system_https(repository_root):
    script = repository_root / "deploy/qnap-control-plane-gateway/shared/www/gateway.cgi"
    result = subprocess.run(
        (str(script),),
        env={
            **os.environ,
            "REQUEST_METHOD": "GET",
            "REQUEST_URI": PUBLIC_BASE + "/login",
            "HTTP_HOST": "192.168.1.39:8080",
            "SERVER_PORT": "8080",
        },
        capture_output=True,
        check=True,
        text=True,
    )
    assert "Status: 308 Permanent Redirect\n" in result.stdout
    assert f"Location: https://192.168.1.39{PUBLIC_BASE}/login\n" in result.stdout


def test_gateway_proxies_only_the_public_cgi_route(repository_root):
    received = {}

    class Handler(BaseHTTPRequestHandler):
        def do_GET(self):
            received["path"] = self.path
            received["host"] = self.headers.get("Host")
            payload = b"<title>Kodi Control Plane</title>"
            self.send_response(200)
            self.send_header("Content-Type", "text/html; charset=utf-8")
            self.send_header("Set-Cookie", "mwo_cp_csrf=value; Secure")
            self.send_header("Content-Length", str(len(payload)))
            self.end_headers()
            self.wfile.write(payload)

        def log_message(self, _format, *_args):
            return

    server = ThreadingHTTPServer(("127.0.0.1", BACKEND_PORT), Handler)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    script = repository_root / "deploy/qnap-control-plane-gateway/shared/www/gateway.cgi"
    try:
        result = subprocess.run(
            (str(script),),
            env={
                **os.environ,
                "REQUEST_METHOD": "GET",
                "REQUEST_URI": PUBLIC_BASE + "/login",
                "HTTP_HOST": "192.168.1.39",
                "HTTPS": "on",
                "SERVER_PORT": "443",
            },
            capture_output=True,
            check=True,
            text=True,
        )
    finally:
        server.shutdown()
        server.server_close()
        thread.join(timeout=2)
    assert "Status: 200\n" in result.stdout
    assert "Set-Cookie: mwo_cp_csrf=value; Secure\n" in result.stdout
    assert result.stdout.endswith("<title>Kodi Control Plane</title>")
    assert received == {"path": PUBLIC_BASE + "/login", "host": "192.168.1.39"}

    rejected = subprocess.run(
        (str(script),),
        env={
            **os.environ,
            "REQUEST_METHOD": "GET",
            "REQUEST_URI": CGI_ROOT + "/other.cgi",
            "HTTP_HOST": "192.168.1.39",
            "HTTPS": "on",
            "SERVER_PORT": "443",
        },
        capture_output=True,
        check=True,
        text=True,
    )
    assert "Status: 404 Not Found\n" in rejected.stdout


@pytest.mark.parametrize(
    ("control_plane_cookie", "validates_existing_session"),
    (("", False), ("; mwo_cp_session=stale_session_token_value_123456", True)),
)
def test_qts_admin_session_performs_server_side_totp_login(
    repository_root, tmp_path, control_plane_cookie, validates_existing_session
):
    received = {}
    secret_bytes = b"12345678901234567890"
    secret = base64.b32encode(secret_bytes).decode("ascii").rstrip("=")

    def current_code():
        counter = int(time.time()) // 30
        digest = hmac.new(secret_bytes, struct.pack(">Q", counter), hashlib.sha1).digest()
        offset = digest[-1] & 0x0F
        value = struct.unpack(">I", digest[offset : offset + 4])[0] & 0x7FFFFFFF
        return f"{value % 1_000_000:06d}"

    class Handler(BaseHTTPRequestHandler):
        def do_GET(self):
            if self.path == PUBLIC_BASE + "/":
                received["validated_cookie"] = self.headers.get("Cookie")
                self.send_response(303)
                self.send_header("Location", PUBLIC_BASE + "/login")
                self.send_header("Content-Length", "0")
                self.end_headers()
                return
            if self.path == PUBLIC_BASE + "/auth/status":
                payload = b'{"csrf":"csrf-value"}'
                self.send_response(200)
                self.send_header(
                    "Set-Cookie",
                    f"mwo_cp_csrf=csrf-value; Path={PUBLIC_BASE}/; Secure; SameSite=Strict",
                )
                self.send_header("Content-Length", str(len(payload)))
                self.end_headers()
                self.wfile.write(payload)
                return
            self.send_error(404)

        def do_POST(self):
            payload = self.rfile.read(int(self.headers.get("Content-Length", "0")))
            if self.path == "/cgi-bin/authLogin.cgi":
                assert payload == b"sid=QTSSESSION123"
                response = b"<QDocRoot><authPassed>1</authPassed><isAdmin>1</isAdmin></QDocRoot>"
                self.send_response(200)
                self.send_header("Content-Length", str(len(response)))
                self.end_headers()
                self.wfile.write(response)
                return
            if self.path == PUBLIC_BASE + "/auth/login":
                received["login"] = json.loads(payload)
                received["expected_code"] = current_code()
                received["origin"] = self.headers.get("Origin")
                received["csrf"] = self.headers.get("X-CSRF-Token")
                received["cookie"] = self.headers.get("Cookie")
                response = b'{"username":"mwo"}'
                self.send_response(200)
                self.send_header(
                    "Set-Cookie",
                    f"mwo_cp_session=session-value; Path={PUBLIC_BASE}/; Secure; SameSite=Strict; HttpOnly",
                )
                self.send_header("Content-Length", str(len(response)))
                self.end_headers()
                self.wfile.write(response)
                return
            self.send_error(404)

        def log_message(self, _format, *_args):
            return

    server = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    shared = tmp_path / "shared"
    www = shared / "www"
    private = shared / "private"
    www.mkdir(parents=True)
    private.mkdir()
    source = (
        repository_root / "deploy/qnap-control-plane-gateway/shared/www/gateway.cgi"
    ).read_text(encoding="utf-8")
    source = source.replace(
        'backend="http://127.0.0.1:19445"',
        f'backend="http://127.0.0.1:{server.server_port}"',
    ).replace(
        'qts_auth="https://127.0.0.1/cgi-bin/authLogin.cgi"',
        f'qts_auth="http://127.0.0.1:{server.server_port}/cgi-bin/authLogin.cgi"',
    )
    script = www / "gateway.cgi"
    script.write_text(source, encoding="utf-8")
    script.chmod(0o755)
    for name, value in (
        ("operator-username", "mwo"),
        ("operator-credential", "local-only-credential_123"),
        ("totp-secret", secret),
    ):
        path = private / name
        path.write_text(value + "\n", encoding="utf-8")
        path.chmod(0o600)
    try:
        result = subprocess.run(
            (str(script),),
            env={
                **os.environ,
                "REQUEST_METHOD": "GET",
                "REQUEST_URI": PUBLIC_BASE + "/",
                "HTTP_HOST": "192.168.1.39",
                "HTTP_COOKIE": "NAS_SID=QTSSESSION123" + control_plane_cookie,
                "HTTPS": "on",
                "SERVER_PORT": "443",
            },
            capture_output=True,
            check=True,
            text=True,
        )
    finally:
        server.shutdown()
        server.server_close()
        thread.join(timeout=2)
    assert "Status: 303 See Other\n" in result.stdout
    assert "Set-Cookie: mwo_cp_csrf=csrf-value" in result.stdout
    assert "Set-Cookie: mwo_cp_session=session-value" in result.stdout
    assert result.stdout.count("SameSite=Lax") == 2
    assert "SameSite=Strict" not in result.stdout
    assert f"Location: {PUBLIC_BASE}/\n" in result.stdout
    assert received["login"] == {
        "username": "mwo",
        "password": "local-only-credential_123",
        "code": received.pop("expected_code"),
    }
    assert received == {
        "login": received["login"],
        "origin": "https://192.168.1.39",
        "csrf": "csrf-value",
        "cookie": "mwo_cp_csrf=csrf-value",
        **(
            {"validated_cookie": "mwo_cp_session=stale_session_token_value_123456"}
            if validates_existing_session
            else {}
        ),
    }


def test_valid_control_plane_session_skips_qts_reauthentication(
    repository_root, tmp_path
):
    received = {"qts_auth": 0, "cookies": []}

    class Handler(BaseHTTPRequestHandler):
        def do_GET(self):
            if self.path == PUBLIC_BASE + "/":
                received["cookies"].append(self.headers.get("Cookie"))
                payload = b"<title>Kodi Control Plane</title>"
                self.send_response(200)
                self.send_header("Content-Type", "text/html; charset=utf-8")
                self.send_header("Content-Length", str(len(payload)))
                self.end_headers()
                self.wfile.write(payload)
                return
            self.send_error(404)

        def do_POST(self):
            if self.path == "/cgi-bin/authLogin.cgi":
                received["qts_auth"] += 1
            self.send_error(500)

        def log_message(self, _format, *_args):
            return

    server = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    shared = tmp_path / "shared"
    www = shared / "www"
    www.mkdir(parents=True)
    source = (
        repository_root / "deploy/qnap-control-plane-gateway/shared/www/gateway.cgi"
    ).read_text(encoding="utf-8")
    source = source.replace(
        'backend="http://127.0.0.1:19445"',
        f'backend="http://127.0.0.1:{server.server_port}"',
    ).replace(
        'qts_auth="https://127.0.0.1/cgi-bin/authLogin.cgi"',
        f'qts_auth="http://127.0.0.1:{server.server_port}/cgi-bin/authLogin.cgi"',
    )
    script = www / "gateway.cgi"
    script.write_text(source, encoding="utf-8")
    script.chmod(0o755)
    session = "valid_session_token_value_1234567890"
    try:
        result = subprocess.run(
            (str(script),),
            env={
                **os.environ,
                "REQUEST_METHOD": "GET",
                "REQUEST_URI": PUBLIC_BASE + "/",
                "HTTP_HOST": "192.168.1.39",
                "HTTP_COOKIE": f"NAS_SID=QTSSESSION123; mwo_cp_session={session}",
                "HTTPS": "on",
                "SERVER_PORT": "443",
            },
            capture_output=True,
            check=True,
            text=True,
        )
    finally:
        server.shutdown()
        server.server_close()
        thread.join(timeout=2)
    assert "Status: 200\n" in result.stdout
    assert result.stdout.endswith("<title>Kodi Control Plane</title>")
    assert received == {
        "qts_auth": 0,
        "cookies": [
            f"mwo_cp_session={session}",
            f"NAS_SID=QTSSESSION123; mwo_cp_session={session}",
        ],
    }
