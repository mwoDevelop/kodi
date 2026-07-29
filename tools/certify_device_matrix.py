#!/usr/bin/env python3
"""Run the redacted release canary matrix against already rolled-out testing."""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import socket
import sqlite3
import subprocess
import sys
import tempfile
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from tools.kodi_devices import load_registry, resolve_device
from tools.kodi_inventory import inventory_device
from tools.snapshot_bundle import canonical_json, verify_bundle


KODI_ROOT = "/sdcard/Android/data/org.xbmc.kodi/files/.kodi"
KODI_ACTIVITY = "org.xbmc.kodi/.Splash"
MAX_CHECK_ATTEMPTS = 2
STABLE_JSONRPC_PINGS = 3
TESTING_ORIGIN = "repository.mwodevelop.testing"


def _run(argv, env=None):
    return subprocess.run(
        argv,
        check=True,
        text=True,
        capture_output=True,
        env=env,
    )


def _evidence(value):
    return hashlib.sha256(canonical_json(value)).hexdigest()


def _adb(adb, server_port, endpoint, *args):
    return _run(
        [adb, "-P", str(server_port), "-s", endpoint, *args]
    ).stdout


def _allowed_origins(testing, stable):
    return {
        addon_id: (
            {TESTING_ORIGIN, "repository.mwodevelop"}
            if stable.get(addon_id, {}).get("zip_sha256") == pin["zip_sha256"]
            else {TESTING_ORIGIN}
        )
        for addon_id, pin in testing.items()
    }


def _latest_addons_database(listing):
    candidates = [
        item.strip()
        for item in listing.splitlines()
        if re.search(r"/Addons\d+\.db$", item.strip())
    ]
    if not candidates:
        raise RuntimeError("Kodi add-on database is missing")
    return max(
        candidates,
        key=lambda item: int(re.search(r"Addons(\d+)\.db$", item).group(1)),
    )


def _forwarded_port(output):
    value = output.strip()
    if not value.isdigit() or not 1 <= int(value) <= 65535:
        raise RuntimeError("ADB did not return a valid dynamic forward port")
    return int(value)


def _wait_for_jsonrpc(host, port, timeout=45.0):
    request = (
        b'{"jsonrpc":"2.0","id":1,"method":"JSONRPC.Ping"}\n'
    )
    deadline = time.monotonic() + timeout
    last_error = None
    consecutive_pings = 0
    while time.monotonic() < deadline:
        try:
            with socket.create_connection((host, port), timeout=2.0) as client:
                client.settimeout(2.0)
                client.sendall(request)
                response = json.loads(client.recv(4096).decode("utf-8"))
                if response.get("result") == "pong":
                    consecutive_pings += 1
                    if consecutive_pings >= STABLE_JSONRPC_PINGS:
                        return
                else:
                    consecutive_pings = 0
                    last_error = RuntimeError(
                        "JSON-RPC returned an unexpected result"
                    )
        except (OSError, UnicodeDecodeError, json.JSONDecodeError) as error:
            consecutive_pings = 0
            last_error = error
        time.sleep(0.5)
    detail = ": %s" % last_error if last_error is not None else ""
    raise RuntimeError(
        "Kodi JSON-RPC did not become ready within %.0f seconds%s"
        % (timeout, detail)
    )


def _recover_kodi(adb, server_port, endpoint, port):
    _adb(
        adb,
        server_port,
        endpoint,
        "shell",
        "am",
        "start",
        "-n",
        KODI_ACTIVITY,
    )
    _wait_for_jsonrpc("127.0.0.1", port)


def _redacted_diagnostic(value):
    value = value or ""
    value = re.sub(
        r"(?i)\b(?:plugin|https?|magnet)://\S+",
        "[REDACTED_URL]",
        value,
    )
    value = re.sub(
        r"(?i)\b(token|key|apikey|access_token|refresh_token|client_secret)"
        r"=([^&\s]+)",
        r"\1=[REDACTED]",
        value,
    )
    return value.strip()[-4000:]


def _run_functional_check(
    name,
    command,
    report,
    env,
    adb,
    server_port,
    endpoint,
    port,
):
    for attempt in range(1, MAX_CHECK_ATTEMPTS + 1):
        report.unlink(missing_ok=True)
        try:
            _run([*command, "--result", str(report)], env=env)
            if not report.is_file():
                raise RuntimeError("%s did not create its result" % name)
            return
        except subprocess.CalledProcessError as error:
            diagnostic = _redacted_diagnostic(
                error.stderr or error.stdout
            )
            print(
                "%s attempt %d/%d failed with exit %d"
                % (name, attempt, MAX_CHECK_ATTEMPTS, error.returncode),
                file=sys.stderr,
            )
            if diagnostic:
                print(diagnostic, file=sys.stderr)
            if attempt == MAX_CHECK_ATTEMPTS:
                raise RuntimeError(
                    "%s failed after %d controlled attempts"
                    % (name, MAX_CHECK_ATTEMPTS)
                ) from None
            _recover_kodi(adb, server_port, endpoint, port)


def _addon_state(
    adb, server_port, endpoint, expected, stable, temporary
):
    versions = {}
    for addon_id, pin in sorted(expected.items()):
        payload = _adb(
            adb,
            server_port,
            endpoint,
            "shell",
            "cat",
            "%s/addons/%s/addon.xml" % (KODI_ROOT, addon_id),
        )
        match = re.search(r'<addon\b[^>]*\bversion="([^"]+)"', payload)
        if not match or match.group(1) != pin["version"]:
            raise RuntimeError(
                "%s has version %r, expected %s"
                % (addon_id, match.group(1) if match else None, pin["version"])
            )
        versions[addon_id] = match.group(1)
    database_remote = _latest_addons_database(
        _adb(
            adb,
            server_port,
            endpoint,
            "shell",
            "ls '%s/userdata/Database'/Addons*.db 2>/dev/null" % KODI_ROOT,
        )
    )
    database = Path(temporary) / "addons.db"
    _run(
        [
            adb,
            "-P",
            str(server_port),
            "-s",
            endpoint,
            "pull",
            database_remote,
            str(database),
        ]
    )
    placeholders = ",".join("?" for _ in expected)
    with sqlite3.connect(database) as connection:
        origins = dict(
            connection.execute(
                "SELECT addonID, origin FROM installed WHERE addonID IN (%s)"
                % placeholders,
                tuple(sorted(expected)),
            )
        )
    allowed = _allowed_origins(expected, stable)
    if set(origins) != set(expected) or any(
        origins[addon_id] not in allowed[addon_id] for addon_id in expected
    ):
        raise RuntimeError(
            "changed add-ons are not owned by testing or an origin is missing"
        )
    return {"versions": versions, "origins": origins}


def _functional_checks(
    adb, server_port, endpoint, logical_id, temporary, observe_seconds
):
    env = {
        **os.environ,
        "ADB_SERVER_SOCKET": "tcp:localhost:%s" % server_port,
        "PYTHONPATH": str(ROOT),
    }
    checks = []
    port = None
    try:
        _adb(
            adb,
            server_port,
            endpoint,
            "shell",
            "am",
            "start",
            "-n",
            KODI_ACTIVITY,
        )
        port = _forwarded_port(
            _adb(
                adb,
                server_port,
                endpoint,
                "forward",
                "tcp:0",
                "tcp:9090",
            )
        )
        _wait_for_jsonrpc("127.0.0.1", port)
        commands = [
            (
                "umbrella-search",
                [
                    sys.executable,
                    str(ROOT / "tests/e2e/umbrella_search_e2e.py"),
                    "--adb",
                    adb,
                    "--serial",
                    endpoint,
                    "--host",
                    "127.0.0.1",
                    "--jsonrpc-port",
                    str(port),
                    "--term",
                    "Sintel",
                    "--media-type",
                    "movie",
                ],
            ),
            (
                "umbrella-resolver-playback",
                [
                    sys.executable,
                    str(ROOT / "tests/e2e/sony_kodi_matrix.py"),
                    "--adb",
                    adb,
                    "--serial",
                    endpoint,
                    "--host",
                    "127.0.0.1",
                    "--jsonrpc-port",
                    str(port),
                    "--event-via-adb",
                    "--direct-play",
                    "--case",
                    "sintel",
                    "--observe-seconds",
                    str(observe_seconds),
                ],
            ),
            (
                "watchnixtoons2-playback",
                [
                    sys.executable,
                    str(ROOT / "tests/e2e/sony_watchnixtoons2.py"),
                    "--adb",
                    adb,
                    "--serial",
                    endpoint,
                    "--host",
                    "127.0.0.1",
                    "--jsonrpc-port",
                    str(port),
                    "--observe-seconds",
                    str(observe_seconds),
                ],
            ),
        ]
        for name, command in commands:
            report = Path(temporary) / ("%s-%s.json" % (logical_id, name))
            _run_functional_check(
                name,
                command,
                report,
                env,
                adb,
                server_port,
                endpoint,
                port,
            )
            checks.append(
                {
                    "name": name,
                    "result": "passed",
                    "evidence_sha256": hashlib.sha256(
                        report.read_bytes()
                    ).hexdigest(),
                }
            )
            report.unlink()
    finally:
        if port is not None:
            subprocess.run(
                [
                    adb,
                    "-P",
                    str(server_port),
                    "-s",
                    endpoint,
                    "forward",
                    "--remove",
                    "tcp:%s" % port,
                ],
                check=False,
                capture_output=True,
            )
    return checks


def certify(
    snapshot,
    devices_file,
    references_file,
    selected,
    adb,
    server_port,
    observe_seconds,
):
    metadata = verify_bundle(snapshot)
    expected = metadata["testing_lock"]["components"]
    stable = json.loads(
        (ROOT / "manifests/locks/stable.json").read_text(encoding="utf-8")
    )["components"]
    registry = load_registry(devices_file)
    results = []
    with tempfile.TemporaryDirectory(prefix="kodi-certification-") as temporary:
        for logical_id in selected:
            device = resolve_device(registry, logical_id)
            if device["platform"] not in {"android", "android-emulator"}:
                raise ValueError(
                    "functional certification currently requires an Android target"
                )
            endpoint = device["endpoints"]["adb"]
            _run([adb, "-P", str(server_port), "connect", endpoint])
            inventory = inventory_device(
                ROOT,
                logical_id,
                devices_file=str(Path(devices_file)),
                references_file=str(Path(references_file)),
                adb=adb,
                adb_server_port=server_port,
            )
            state = _addon_state(
                adb, server_port, endpoint, expected, stable, temporary
            )
            checks = [
                {
                    "name": "device-inventory",
                    "result": "passed",
                    "evidence_sha256": _evidence(inventory),
                },
                {
                    "name": "testing-versions-and-origins",
                    "result": "passed",
                    "evidence_sha256": _evidence(state),
                },
            ]
            checks.extend(
                _functional_checks(
                    adb,
                    server_port,
                    endpoint,
                    logical_id,
                    temporary,
                    observe_seconds,
                )
            )
            results.append(
                {
                    "logical_device_id": logical_id,
                    "device_class": (
                        "android-emulator"
                        if device["platform"] == "android-emulator"
                        else "android-tv"
                    ),
                    "kodi_version": inventory["kodi_version"],
                    "addons": state["versions"],
                    "checks": checks,
                }
            )
    return {"schema": 1, "result": "passed", "devices": results}


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--snapshot", required=True)
    parser.add_argument(
        "--devices", default=str(ROOT / ".kodi-private/devices.json")
    )
    parser.add_argument("--references", default=str(ROOT / ".env"))
    parser.add_argument("--device", action="append")
    parser.add_argument(
        "--adb", default="/home/mwo/android-sdk/platform-tools/adb"
    )
    parser.add_argument("--adb-server-port", type=int, default=5038)
    parser.add_argument("--observe-seconds", type=int, default=15)
    parser.add_argument("--output", required=True)
    args = parser.parse_args()
    report = certify(
        args.snapshot,
        args.devices,
        args.references,
        args.device or ["bluestacks1", "sony-tv"],
        args.adb,
        args.adb_server_port,
        args.observe_seconds,
    )
    Path(args.output).write_text(
        json.dumps(report, indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )
    print(json.dumps(report, indent=2, sort_keys=True))


if __name__ == "__main__":
    main()
