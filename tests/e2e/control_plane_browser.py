#!/usr/bin/env python3
"""E2E for browser TLS -> Web BFF -> mTLS authz/core."""

from __future__ import annotations

import base64
import http.cookiejar
import json
import os
import socket
import ssl
import subprocess
import sys
import tempfile
import threading
import time
import urllib.error
import urllib.request
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import parse_qs, urlparse


ROOT = Path(__file__).resolve().parents[2]
CONTROL_PLANE = ROOT.parent / "kodi-control-plane"


def free_port():
    with socket.socket() as listener:
        listener.bind(("127.0.0.1", 0))
        return listener.getsockname()[1]


def run(*args, cwd):
    subprocess.run(args, cwd=cwd, check=True, capture_output=True, text=True)


def credentials(root):
    run(
        "openssl", "req", "-x509", "-newkey", "rsa:2048", "-nodes",
        "-days", "1", "-sha256", "-subj", "/CN=Browser E2E CA",
        "-addext", "basicConstraints=critical,CA:TRUE,pathlen:0",
        "-addext", "keyUsage=critical,keyCertSign,cRLSign",
        "-keyout", "ca.key", "-out", "ca.crt", cwd=root,
    )
    for name, common_name, extension in (
        (
            "server",
            "127.0.0.1",
            "subjectAltName=IP:127.0.0.1\nextendedKeyUsage=serverAuth\n"
            "keyUsage=digitalSignature,keyEncipherment\n",
        ),
        (
            "web-client",
            "control-plane-web-readonly",
            "extendedKeyUsage=clientAuth\nkeyUsage=digitalSignature\n",
        ),
    ):
        run(
            "openssl", "req", "-newkey", "rsa:2048", "-nodes",
            "-subj", f"/CN={common_name}", "-keyout", f"{name}.key",
            "-out", f"{name}.csr", cwd=root,
        )
        (root / f"{name}.ext").write_text(extension, encoding="utf-8")
        run(
            "openssl", "x509", "-req", "-in", f"{name}.csr", "-CA",
            "ca.crt", "-CAkey", "ca.key", "-CAcreateserial", "-days", "1",
            "-sha256", "-extfile", f"{name}.ext", "-out", f"{name}.crt",
            cwd=root,
        )
    for path in root.glob("*.key"):
        path.chmod(0o600)


class CoreHandler(BaseHTTPRequestHandler):
    def do_GET(self):
        if urlparse(self.path).path != "/api/v1/dashboard":
            self.send_error(403)
            return
        payload = json.dumps(
            {
                "schema": 1,
                "overall_state": "OK",
                "fleet": {"total": 2, "online": 2, "stale_or_offline": 0},
                "alerts": {"alerts": []},
                "services": {"services": []},
                "schedules": {"jobs": []},
                "generated_at": int(time.time()),
            }
        ).encode("utf-8")
        self.send_response(200)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(payload)))
        self.end_headers()
        self.wfile.write(payload)

    def log_message(self, _format, *_args):
        return


def start_process(module, arguments):
    return subprocess.Popen(
        (sys.executable, "-m", module, *arguments),
        cwd=CONTROL_PLANE,
        env={**os.environ, "PYTHONPATH": str(CONTROL_PLANE / "src")},
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
    )


def stop(process):
    process.terminate()
    try:
        process.wait(timeout=5)
    except subprocess.TimeoutExpired:
        process.kill()
        process.wait(timeout=5)


def totp_from_uri(uri):
    sys.path.insert(0, str(CONTROL_PLANE / "src"))
    try:
        from kodi_control_plane.authz import totp_step
    finally:
        sys.path.pop(0)
    encoded = parse_qs(urlparse(uri).query)["secret"][0]
    encoded += "=" * ((8 - len(encoded) % 8) % 8)
    return totp_step(base64.b32decode(encoded), int(time.time()))[0]


def main():
    if not (CONTROL_PLANE / "src").is_dir():
        raise SystemExit(f"missing sibling repository: {CONTROL_PLANE}")
    processes = []
    with tempfile.TemporaryDirectory(prefix="kodi-control-plane-browser-e2e-") as raw:
        temporary = Path(raw)
        credentials(temporary)
        auth_key = temporary / "auth.key"
        auth_key.write_text(os.urandom(32).hex(), encoding="ascii")
        auth_key.chmod(0o600)
        database = temporary / "authz.sqlite"
        core_port, authz_port, web_port = free_port(), free_port(), free_port()
        core = ThreadingHTTPServer(("127.0.0.1", core_port), CoreHandler)
        core_tls = ssl.SSLContext(ssl.PROTOCOL_TLS_SERVER)
        core_tls.load_cert_chain(temporary / "server.crt", temporary / "server.key")
        core_tls.load_verify_locations(temporary / "ca.crt")
        core_tls.verify_mode = ssl.CERT_REQUIRED
        core.socket = core_tls.wrap_socket(core.socket, server_side=True)
        core_thread = threading.Thread(target=core.serve_forever, daemon=True)
        core_thread.start()

        def start_authz():
            process = start_process(
                "kodi_control_plane.authz_http",
                (
                    "--listen", "127.0.0.1", "--port", str(authz_port),
                    "--health-port", str(free_port()), "--database", str(database),
                    "--auth-key", str(auth_key), "--tls-cert",
                    str(temporary / "server.crt"), "--tls-key",
                    str(temporary / "server.key"), "--client-ca",
                    str(temporary / "ca.crt"),
                ),
            )
            processes.append(process)
            return process

        def start_web():
            process = start_process(
                "kodi_control_plane.web",
                (
                    "--listen", "127.0.0.1", "--port", str(web_port),
                    "--health-port", str(free_port()), "--tls-cert",
                    str(temporary / "server.crt"), "--tls-key",
                    str(temporary / "server.key"), "--expected-host",
                    f"127.0.0.1:{web_port}", "--expected-origin",
                    f"https://127.0.0.1:{web_port}", "--allowed-network",
                    "127.0.0.0/8", "--core-host", "127.0.0.1",
                    "--core-port", str(core_port), "--core-server-name",
                    "127.0.0.1", "--core-ca", str(temporary / "ca.crt"),
                    "--core-client-cert", str(temporary / "web-client.crt"),
                    "--core-client-key", str(temporary / "web-client.key"),
                    "--authz-host", "127.0.0.1", "--authz-port", str(authz_port),
                    "--authz-server-name", "127.0.0.1", "--authz-ca",
                    str(temporary / "ca.crt"), "--authz-client-cert",
                    str(temporary / "web-client.crt"), "--authz-client-key",
                    str(temporary / "web-client.key"),
                ),
            )
            processes.append(process)
            return process

        authz = start_authz()
        web = start_web()
        context = ssl.create_default_context(cafile=temporary / "ca.crt")
        jar = http.cookiejar.CookieJar()
        opener = urllib.request.build_opener(
            urllib.request.HTTPSHandler(context=context),
            urllib.request.HTTPCookieProcessor(jar),
        )
        base = f"https://127.0.0.1:{web_port}/control-plane/"

        def open_json(path, document):
            csrf = next(
                (cookie.value for cookie in jar if cookie.name == "mwo_cp_csrf"),
                "",
            )
            request = urllib.request.Request(
                base + path,
                data=json.dumps(document).encode("utf-8"),
                method="POST",
                headers={
                    "Content-Type": "application/json",
                    "Origin": f"https://127.0.0.1:{web_port}",
                    "X-CSRF-Token": csrf,
                },
            )
            with opener.open(request, timeout=5) as response:
                return json.load(response)

        try:
            for _attempt in range(100):
                if authz.poll() is not None or web.poll() is not None:
                    failed = authz if authz.poll() is not None else web
                    stdout, stderr = failed.communicate()
                    raise RuntimeError(f"browser service exited: {stdout[-500:]} {stderr[-1000:]}")
                try:
                    with opener.open(base + "login", timeout=2) as response:
                        if b"Kodi Control Plane" in response.read():
                            break
                except (OSError, urllib.error.URLError, ssl.SSLError):
                    time.sleep(0.05)
            else:
                raise RuntimeError("browser listener did not become ready")

            bootstrap = subprocess.run(
                (
                    sys.executable, "-m", "kodi_control_plane.admin", "--database",
                    str(database), "auth-bootstrap", "--auth-key", str(auth_key),
                ),
                cwd=CONTROL_PLANE,
                env={**os.environ, "PYTHONPATH": str(CONTROL_PLANE / "src")},
                check=True,
                capture_output=True,
                text=True,
            )
            bootstrap_code = json.loads(bootstrap.stdout)["code"]
            pending = open_json(
                "auth/bootstrap/start",
                {
                    "code": bootstrap_code,
                    "username": "operator",
                    "password": "correct horse battery staple",
                },
            )
            configured = open_json(
                "auth/bootstrap/confirm",
                {
                    "pending_token": pending["pending_token"],
                    "code": totp_from_uri(pending["totp_uri"]),
                },
            )
            recovery_code = configured["recovery_codes"][0]
            with opener.open(base, timeout=5) as response:
                if b"Kodi Control Plane" not in response.read():
                    raise RuntimeError("authenticated dashboard is unavailable")
            with opener.open(base + "api/v1/dashboard", timeout=5) as response:
                if json.load(response)["overall_state"] != "OK":
                    raise RuntimeError("dashboard BFF result differs")

            recovery = open_json(
                "auth/recovery/start",
                {
                    "username": "operator",
                    "password": "correct horse battery staple",
                    "recovery_code": recovery_code,
                },
            )
            recovered = open_json(
                "auth/recovery/confirm",
                {
                    "pending_token": recovery["pending_token"],
                    "code": totp_from_uri(recovery["totp_uri"]),
                },
            )
            if len(recovered["recovery_codes"]) != 10:
                raise RuntimeError("recovery did not rotate recovery codes")
            mutation = urllib.request.Request(base + "api/v1/dashboard", data=b"{}", method="PUT")
            try:
                opener.open(mutation, timeout=5)
            except urllib.error.HTTPError as error:
                if error.code != 405 or json.load(error)["error"] != "read_only":
                    raise
            else:
                raise RuntimeError("browser facade accepted mutation")

            stop(web)
            stop(authz)
            processes.clear()
            authz = start_authz()
            web = start_web()
            for _attempt in range(100):
                try:
                    with opener.open(base + "api/v1/dashboard", timeout=2) as response:
                        if json.load(response)["overall_state"] == "OK":
                            break
                except (OSError, urllib.error.URLError, ssl.SSLError):
                    time.sleep(0.05)
            else:
                raise RuntimeError("session did not survive authz/web restart")

            print(
                json.dumps(
                    {
                        "schema": 1,
                        "status": "PASS",
                        "browser_client_certificate": "NOT_REQUIRED",
                        "bootstrap": "ONE_TIME",
                        "authentication": "PASSWORD_TOTP",
                        "recovery_codes": "ROTATED",
                        "session_restart": "PRESERVED",
                        "mutation": "REJECTED",
                        "core_channel": "MTLS_READ_ONLY",
                    },
                    indent=2,
                    sort_keys=True,
                )
            )
        finally:
            for process in reversed(processes):
                if process.poll() is None:
                    stop(process)
            core.shutdown()
            core.server_close()
            core_thread.join(timeout=2)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
