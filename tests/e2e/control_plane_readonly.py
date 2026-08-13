#!/usr/bin/env python3
"""Cross-repository E2E for Profile Sync -> Control Plane -> operator mTLS."""

from __future__ import annotations

import json
import os
import socket
import ssl
import subprocess
import sys
import tempfile
import time
import urllib.error
import urllib.request
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
PROFILE_SERVER = ROOT.parent / "kodi-profile-sync-server"
CONTROL_PLANE = ROOT.parent / "kodi-control-plane"


def free_port():
    with socket.socket() as listener:
        listener.bind(("127.0.0.1", 0))
        return listener.getsockname()[1]


def run(*args, cwd):
    subprocess.run(args, cwd=cwd, check=True, capture_output=True, text=True)


def create_ca(root, name):
    run(
        "openssl", "req", "-x509", "-newkey", "rsa:2048", "-nodes",
        "-days", "1", "-sha256", "-subj", f"/CN={name}",
        "-addext", "basicConstraints=critical,CA:TRUE,pathlen:0",
        "-addext", "keyUsage=critical,keyCertSign,cRLSign",
        "-keyout", "ca.key", "-out", "ca.crt", cwd=root,
    )


def issue(root, name, common_name, usage, *, server=False):
    run(
        "openssl", "req", "-newkey", "rsa:2048", "-nodes",
        "-subj", f"/CN={common_name}", "-keyout", f"{name}.key",
        "-out", f"{name}.csr", cwd=root,
    )
    lines = [f"extendedKeyUsage={usage}", "keyUsage=digitalSignature"]
    if server:
        lines.insert(0, "subjectAltName=IP:127.0.0.1")
        lines[-1] += ",keyEncipherment"
    (root / f"{name}.ext").write_text(
        "\n".join(lines) + "\n", encoding="utf-8"
    )
    run(
        "openssl", "x509", "-req", "-in", f"{name}.csr", "-CA",
        "ca.crt", "-CAkey", "ca.key", "-CAcreateserial", "-days", "1",
        "-sha256", "-extfile", f"{name}.ext", "-out", f"{name}.crt",
        cwd=root,
    )
    (root / f"{name}.key").chmod(0o600)


def request(url, context, method="GET"):
    data = b"{}" if method != "GET" else None
    query = urllib.request.Request(url, data=data, method=method)
    with urllib.request.urlopen(query, context=context, timeout=2) as response:
        return response.status, json.load(response)


def wait_for(url, context, process):
    last_error = None
    for _attempt in range(100):
        if process.poll() is not None:
            stdout, stderr = process.communicate()
            raise RuntimeError(
                f"control plane exited early: {stdout[-500:]} {stderr[-1000:]}"
            )
        try:
            result = request(url, context)
            if result[1].get("profile_sync", {}).get("status") == "ok":
                return result
            time.sleep(0.2)
        except (OSError, urllib.error.URLError, ssl.SSLError) as error:
            last_error = error
            time.sleep(0.05)
    raise RuntimeError("control plane API did not become ready") from last_error


def terminate(process):
    process.terminate()
    try:
        process.wait(timeout=5)
    except subprocess.TimeoutExpired:
        process.kill()
        process.wait(timeout=5)


def main():
    for repository in (PROFILE_SERVER, CONTROL_PLANE):
        if not (repository / "src").is_dir():
            raise SystemExit(f"missing sibling repository: {repository}")
    processes = []
    with tempfile.TemporaryDirectory(prefix="kodi-control-plane-e2e-") as raw:
        temporary = Path(raw)
        profile_tls = temporary / "profile-tls"
        operator_tls = temporary / "operator-tls"
        profile_tls.mkdir()
        operator_tls.mkdir()
        create_ca(profile_tls, "Profile Sync E2E CA")
        issue(profile_tls, "server", "127.0.0.1", "serverAuth", server=True)
        issue(profile_tls, "client", "kodi-control-plane", "clientAuth")
        create_ca(operator_tls, "Control Plane E2E CA")
        issue(operator_tls, "server", "127.0.0.1", "serverAuth", server=True)
        issue(operator_tls, "client", "operator-e2e", "clientAuth")
        checkpoint = temporary / "audit-checkpoint.key"
        checkpoint.write_bytes(os.urandom(32))
        checkpoint.chmod(0o600)
        consumer_port, admin_port, integration_port = (
            free_port(), free_port(), free_port()
        )
        api_port, health_port = free_port(), free_port()
        profile = subprocess.Popen(
            (
                sys.executable, "-m", "profile_sync_server.http", "--listen",
                "127.0.0.1", "--port", str(consumer_port), "--admin-port",
                str(admin_port), "--database", str(temporary / "profile.sqlite"),
                "--unsafe-accept-signatures", "--tls-cert",
                str(profile_tls / "server.crt"), "--tls-key",
                str(profile_tls / "server.key"), "--integration-listen",
                "127.0.0.1", "--integration-port", str(integration_port),
                "--integration-client-ca", str(profile_tls / "ca.crt"),
            ),
            cwd=PROFILE_SERVER,
            env={**os.environ, "PYTHONPATH": str(PROFILE_SERVER / "src")},
            stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True,
        )
        processes.append(profile)
        control = subprocess.Popen(
            (
                sys.executable, "-m", "kodi_control_plane.http", "--listen",
                "127.0.0.1", "--port", str(api_port), "--health-port",
                str(health_port), "--database", str(temporary / "control.sqlite"),
                "--tls-cert", str(operator_tls / "server.crt"), "--tls-key",
                str(operator_tls / "server.key"), "--client-ca",
                str(operator_tls / "ca.crt"), "--checkpoint-key", str(checkpoint),
                "--profile-sync-host", "127.0.0.1", "--profile-sync-port",
                str(integration_port), "--profile-sync-server-name", "127.0.0.1",
                "--profile-sync-ca", str(profile_tls / "ca.crt"),
                "--profile-sync-client-cert", str(profile_tls / "client.crt"),
                "--profile-sync-client-key", str(profile_tls / "client.key"),
                "--refresh-seconds", "15",
            ),
            cwd=CONTROL_PLANE,
            env={**os.environ, "PYTHONPATH": str(CONTROL_PLANE / "src")},
            stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True,
        )
        processes.append(control)
        context = ssl.create_default_context(cafile=operator_tls / "ca.crt")
        context.load_cert_chain(
            operator_tls / "client.crt", operator_tls / "client.key"
        )
        endpoint = f"https://127.0.0.1:{api_port}"
        try:
            status, fleet = wait_for(endpoint + "/v1/fleet", context, control)
            if status != 200 or fleet["profile_sync"]["status"] != "ok":
                raise RuntimeError("Profile Sync fleet did not cross mTLS")
            if fleet["profile_sync"]["data"]["database_schema"] != 4:
                raise RuntimeError("unexpected Profile Sync database schema")
            no_client = ssl.create_default_context(cafile=operator_tls / "ca.crt")
            try:
                request(endpoint + "/v1/fleet", no_client)
            except (urllib.error.URLError, ssl.SSLError):
                pass
            else:
                raise RuntimeError("operator API accepted no client certificate")
            try:
                request(endpoint + "/v1/fleet", context, method="POST")
            except urllib.error.HTTPError as error:
                if error.code != 405 or json.load(error)["error"] != "read_only":
                    raise
            else:
                raise RuntimeError("operator API accepted a mutation")
            _status, services = request(endpoint + "/v1/services", context)
            print(json.dumps({
                "schema": 1,
                "status": "PASS",
                "fleet_devices": len(fleet["profile_sync"]["data"]["devices"]),
                "profile_sync_database_schema": 4,
                "mtls_without_client": "REJECTED",
                "mutation": "REJECTED",
                "services": [item["source"] for item in services["services"]],
            }, indent=2, sort_keys=True))
        finally:
            for process in reversed(processes):
                terminate(process)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
