#!/usr/bin/env python3
"""Run the redacted release canary matrix after workflow-controlled testing rollout."""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import socket
import subprocess
import sys
import tempfile
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from tools.kodi_devices import (
    load_registry,
    resolve_device,
    resolve_private_endpoint,
)
from tools.kodi_inventory import inventory_device, load_private_references
from tools.kodi_profile import AdbJsonRpcClient
from tools.kodi_reinstall import installed_addon_origins
from tools.snapshot_bundle import canonical_json, verify_bundle


KODI_ACTIVITY = "org.xbmc.kodi/.Splash"
KODI_PACKAGE = "org.xbmc.kodi"
MAX_CHECK_ATTEMPTS = 2
STABLE_JSONRPC_PINGS = 3
KODI_SERVICE_WARMUP_SECONDS = 20
TESTING_ORIGIN = "repository.mwodevelop.testing"
# The resolver canary must use a durable, openly redistributable title. Sintel
# sources have repeatedly disappeared from otherwise healthy Real-Debrid
# indexes, while the Big Buck Bunny fixture is independently exercised by the
# device E2E matrix and remains resolvable on both release canaries.
UMBRELLA_PLAYBACK_CASE = "big_buck_bunny"
UMBRELLA_DIRECTORY_UNAVAILABLE_EXIT = 75


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
        "force-stop",
        KODI_PACKAGE,
    )
    # BlueStacks can leave the Android package suspended after force-stop.
    # Some Android TV firmware does not implement `cmd package unsuspend` and
    # returns 255 even for an already runnable package. Treat this one command
    # as best-effort: the strict enable, launch and JSON-RPC readiness checks
    # below still fail closed if Kodi is actually suspended or unavailable.
    try:
        _adb(
            adb,
            server_port,
            endpoint,
            "shell",
            "cmd",
            "package",
            "unsuspend",
            KODI_PACKAGE,
        )
    except subprocess.CalledProcessError:
        pass
    # Enabling an already enabled package is idempotent on Android and keeps
    # recovery portable across emulators and physical Android TV devices.
    _adb(
        adb,
        server_port,
        endpoint,
        "shell",
        "pm",
        "enable",
        KODI_PACKAGE,
    )
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
    # JSON-RPC becomes available before EventServer and the video renderer on
    # some Android TV builds. The canaries use both, so process readiness alone
    # is not a sufficient recovery boundary.
    time.sleep(KODI_SERVICE_WARMUP_SECONDS)


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
            if (
                name == "umbrella-search"
                and error.returncode == UMBRELLA_DIRECTORY_UNAVAILABLE_EXIT
            ):
                # The first cold query can initialize Umbrella after reporting
                # its directory unavailable. Restarting Kodi here recreates
                # that same cold state, so retry in a new probe process against
                # the warmed Kodi instance. Every other failure keeps the
                # stronger full-process recovery below.
                time.sleep(KODI_SERVICE_WARMUP_SECONDS)
            else:
                _recover_kodi(adb, server_port, endpoint, port)


def _addon_state(adb, server_port, endpoint, expected, stable):
    versions = {}
    with AdbJsonRpcClient(adb, server_port, endpoint) as jsonrpc:
        _recover_kodi(
            adb,
            server_port,
            endpoint,
            jsonrpc.local_port,
        )
        for addon_id, pin in sorted(expected.items()):
            details = None
            for attempt in range(1, MAX_CHECK_ATTEMPTS + 1):
                try:
                    details = jsonrpc.call(
                        "Addons.GetAddonDetails",
                        {
                            "addonid": addon_id,
                            "properties": ["version"],
                        },
                    )
                    break
                except (OSError, RuntimeError, TimeoutError):
                    if attempt == MAX_CHECK_ATTEMPTS:
                        raise
                    time.sleep(1)
            version = (
                details.get("addon", {}).get("version")
                if isinstance(details, dict)
                else None
            )
            if version != pin["version"]:
                raise RuntimeError(
                    "%s has version %r, expected %s"
                    % (addon_id, version, pin["version"])
                )
            versions[addon_id] = version
    origins = installed_addon_origins(
        adb,
        server_port,
        endpoint,
        sorted(expected),
        origin_script=ROOT / "tools/kodi_profile_origin_device.py",
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
                    UMBRELLA_PLAYBACK_CASE,
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
            # Android TV video initialization can temporarily starve Kodi's
            # JSON-RPC server. Give each functional canary an isolated Kodi
            # process so a previous codec/source cannot poison the next test.
            _recover_kodi(adb, server_port, endpoint, port)
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
    references = load_private_references(references_file)
    results = []
    with tempfile.TemporaryDirectory(prefix="kodi-certification-") as temporary:
        for logical_id in selected:
            device = resolve_private_endpoint(
                resolve_device(registry, logical_id), references
            )
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
                adb, server_port, endpoint, expected, stable
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
