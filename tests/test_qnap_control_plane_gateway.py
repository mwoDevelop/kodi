import os
import subprocess
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

import pytest

from tools.qnap_control_plane_gateway import (
    BACKEND_PORT,
    CGI_ROOT,
    NAME,
    PUBLIC_BASE,
    QDK_SHA256,
    VERSION,
    WEBUI,
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
