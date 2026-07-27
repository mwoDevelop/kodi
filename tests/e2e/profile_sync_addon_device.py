#!/usr/bin/env python3
"""Install, pair and check the testing profile-sync add-on on real Kodi.

The flow uses Kodi's add-on manager, a temporary verified loopback server and
ADB reverse. Enrollment secrets are read only to validate their presence and
are never printed. Each enrollment is revoked and removed from Kodi at cleanup.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import socket
import sqlite3
import struct
import subprocess
import sys
import tempfile
import time
import urllib.request
from pathlib import Path

from tools.kodi_devices import load_registry, resolve_device
from tools.kodi_profile import (
    AdbEventClient,
    AdbJsonRpcClient,
    KODI_ROOT,
    adb_command,
    adb_output,
)


ADDON_ID = "service.mwodevelop.profilesync"
ORIGIN = "repository.mwodevelop.testing"
CHANNEL = "home-stable"
STATE_PATH = (
    KODI_ROOT + "/userdata/addon_data/" + ADDON_ID + "/state.json"
)
REMOTE_HELPER = "/sdcard/Download/.mwo-profile-sync-e2e-helper.py"
REMOTE_MARKER = "/sdcard/Download/.mwo-profile-sync-e2e-marker.json"
PUBLISHER_SEED = bytes.fromhex("61" * 32)
PROMOTER_SEED = bytes.fromhex("62" * 32)


def _server_modules(repository, server_repository):
    sys.path.insert(0, str(server_repository / "src"))
    from profile_sync_server.crypto import (
        SignedDocumentVerifier,
        native_ed25519,
        public_key_record,
        sign_document,
    )
    from profile_sync_server.store import ProfileStore, canonical_json

    return {
        "SignedDocumentVerifier": SignedDocumentVerifier,
        "native_ed25519": native_ed25519,
        "public_key_record": public_key_record,
        "sign_document": sign_document,
        "ProfileStore": ProfileStore,
        "canonical_json": canonical_json,
    }


def _execute_builtin(adb, port, serial, command):
    try:
        AdbEventClient(adb, port, serial).execute_builtin(command)
        return
    except (OSError, subprocess.CalledProcessError):
        pass
    host = serial.rsplit(":", 1)[0]
    client = AdbEventClient(adb, port, serial)
    hello = (
        b"mwoDevelop profile sync add-on E2E\0"
        + bytes((0,))
        + struct.pack("!H", 0)
        + struct.pack("!I", 0)
        + struct.pack("!I", 0)
    )
    action = bytes((client.ACTION_EXECBUILTIN,)) + command.encode() + b"\0"
    with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as connection:
        for packet_type, payload in (
            (client.PT_HELO, hello),
            (client.PT_ACTION, action),
            (client.PT_BYE, b""),
        ):
            for packet in client._packets(packet_type, payload):
                connection.sendto(packet, (host, 9777))


def _remote_json(adb, port, serial, path):
    result = adb_command(
        adb,
        port,
        serial,
        "exec-out",
        "cat",
        path,
        check=False,
        text=True,
    )
    if result.returncode or not result.stdout.strip().startswith("{"):
        return None
    return json.loads(result.stdout)


def _wait_json(adb, port, serial, path, predicate, timeout=45):
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        document = _remote_json(adb, port, serial, path)
        if document is not None and predicate(document):
            return document
        time.sleep(1)
    raise TimeoutError("Kodi profile-sync marker timed out")


def _addon_version(adb, port, serial):
    payload = adb_command(
        adb,
        port,
        serial,
        "exec-out",
        "cat",
        KODI_ROOT + "/addons/" + ADDON_ID + "/addon.xml",
        check=False,
        text=True,
    )
    if payload.returncode:
        return None
    import re

    match = re.search(
        r'<addon[^>]+version="([^"]+)"',
        payload.stdout.replace("\n", " "),
    )
    return match.group(1) if match else None


def _install_from_testing(adb, port, serial, expected_version):
    repository = (
        KODI_ROOT + "/addons/" + ORIGIN + "/addon.xml"
    )
    if (
        adb_command(
            adb,
            port,
            serial,
            "shell",
            "test -s '%s'" % repository,
            check=False,
        ).returncode
        != 0
    ):
        raise RuntimeError("testing repository is not installed on device")
    _execute_builtin(adb, port, serial, "UpdateAddonRepos")
    time.sleep(8)
    _execute_builtin(adb, port, serial, "InstallAddon(%s)" % ADDON_ID)
    deadline = time.monotonic() + 90
    while time.monotonic() < deadline:
        if _addon_version(adb, port, serial) == expected_version:
            with AdbJsonRpcClient(adb, port, serial) as jsonrpc:
                jsonrpc.call(
                    "Addons.SetAddonEnabled",
                    {"addonid": ADDON_ID, "enabled": True},
                )
            return
        time.sleep(2)
    raise TimeoutError("testing profile-sync add-on installation timed out")


def _run_helper(adb, port, serial, source):
    with tempfile.NamedTemporaryFile(
        mode="w", suffix=".py", encoding="utf-8"
    ) as helper:
        helper.write(source)
        helper.flush()
        adb_command(
            adb,
            port,
            serial,
            "shell",
            "rm -f '%s' '%s'" % (REMOTE_HELPER, REMOTE_MARKER),
        )
        adb_command(
            adb,
            port,
            serial,
            "push",
            helper.name,
            REMOTE_HELPER,
            text=True,
        )
    _execute_builtin(adb, port, serial, "RunScript(%s)" % REMOTE_HELPER)
    return _wait_json(
        adb,
        port,
        serial,
        REMOTE_MARKER,
        lambda item: item.get("ok") is True,
    )


def _configure(adb, port, serial, server_port, logical_device_id):
    settings = {
        "server_url": "http://127.0.0.1:%d" % server_port,
        "logical_device_id": logical_device_id,
        "channel": CHANNEL,
        "enabled": "true",
        "read_only": "true",
    }
    source = """import json
import xbmcaddon
addon = xbmcaddon.Addon(%s)
for key, value in %s.items():
    addon.setSetting(key, value)
with open(%s, "w", encoding="utf-8") as handle:
    json.dump({"ok": True}, handle)
""" % (
        json.dumps(ADDON_ID),
        repr(settings),
        json.dumps(REMOTE_MARKER),
    )
    _run_helper(adb, port, serial, source)


def _cleanup_client(adb, port, serial):
    source = """import json
import os
import xbmcaddon
addon = xbmcaddon.Addon(%s)
for key in ("server_url", "logical_device_id"):
    addon.setSetting(key, "")
try:
    os.unlink(%s)
except OSError:
    pass
with open(%s, "w", encoding="utf-8") as handle:
    json.dump({"ok": True}, handle)
""" % (
        json.dumps(ADDON_ID),
        json.dumps(STATE_PATH),
        json.dumps(REMOTE_MARKER),
    )
    _run_helper(adb, port, serial, source)


def _installed_origin(adb, port, serial, temporary):
    remote = adb_output(
        adb,
        port,
        serial,
        "shell",
        "ls '%s/userdata/Database'/Addons*.db | sort -V | tail -1"
        % KODI_ROOT,
    ).strip()
    if not remote:
        raise RuntimeError("Kodi add-on database is missing")
    database = Path(temporary) / "addons.db"
    adb_command(adb, port, serial, "pull", remote, str(database), text=True)
    with sqlite3.connect(database) as connection:
        row = connection.execute(
            "SELECT origin FROM installed WHERE addonID=?", (ADDON_ID,)
        ).fetchone()
    return row[0] if row else None


def _wait_server(base, process):
    deadline = time.monotonic() + 15
    while time.monotonic() < deadline:
        if process.poll() is not None:
            raise RuntimeError("profile-sync server exited early")
        try:
            with urllib.request.urlopen(base + "/health", timeout=2) as response:
                if json.load(response).get("status") == "ok":
                    return
        except OSError:
            pass
        time.sleep(0.1)
    raise TimeoutError("profile-sync server did not become ready")


def _free_port():
    with socket.socket() as listener:
        listener.bind(("127.0.0.1", 0))
        return listener.getsockname()[1]


def _prepare_server(repository, server_repository, root):
    modules = _server_modules(repository, server_repository)
    backend = modules["native_ed25519"]()
    records = {
        "publisher-e2e": modules["public_key_record"](
            PUBLISHER_SEED, ["revision"], backend=backend
        ),
        "promoter-e2e": modules["public_key_record"](
            PROMOTER_SEED,
            ["assignment", "promotion"],
            backend=backend,
        ),
    }
    registry = {"schema": 1, "keys": records}
    registry_path = root / "key-registry.json"
    registry_path.write_bytes(modules["canonical_json"](registry))
    registry_path.chmod(0o600)
    verifier = modules["SignedDocumentVerifier"](records, backend=backend)
    database = root / "state.sqlite"
    store = modules["ProfileStore"](
        database,
        verifier,
        bootstrap_keys=verifier.public_bundle(
            {"assignment", "promotion", "revision"}
        ),
    )
    identity = {
        "schema": 2,
        "policy_sha256": "a" * 64,
        "kodi_major": 21,
        "adapters": {},
    }
    revision = {
        **identity,
        "revision_id": "sha256:"
        + hashlib.sha256(modules["canonical_json"](identity)).hexdigest(),
    }
    revision = modules["sign_document"](
        "revision",
        revision,
        "publisher-e2e",
        PUBLISHER_SEED,
        backend=backend,
    )
    store.put_revision(revision)
    store.publish_candidate(
        CHANNEL,
        revision["revision_id"],
        None,
        None,
        "publish-device-e2e",
    )
    return modules, backend, store, revision, database, registry_path


def verify_device(
    repository,
    logical_device_id,
    adb,
    adb_port,
    server_port,
    store,
    modules,
    backend,
    revision,
    expected_version,
    temporary,
):
    registry = load_registry(repository / ".kodi-private/devices.json")
    device = resolve_device(registry, logical_device_id)
    serial = device["endpoints"]["adb"]
    model = adb_output(
        adb, adb_port, serial, "shell", "getprop ro.product.model"
    ).strip()
    if model != device["expected"]["model"]:
        raise RuntimeError("%s resolved to the wrong model" % logical_device_id)
    enrollment_id = None
    try:
        adb_command(
            adb,
            adb_port,
            serial,
            "reverse",
            "tcp:%d" % server_port,
            "tcp:%d" % server_port,
            text=True,
        )
        _install_from_testing(
            adb, adb_port, serial, expected_version
        )
        _configure(
            adb, adb_port, serial, server_port, logical_device_id
        )
        pairing = store.create_pairing_code(
            logical_device_id,
            CHANNEL,
            code=None,
            ttl_seconds=300,
        )
        _execute_builtin(
            adb,
            adb_port,
            serial,
            "RunScript(special://home/addons/%s/default.py,--pair-code,%s)"
            % (ADDON_ID, pairing["code"]),
        )
        state = _wait_json(
            adb,
            adb_port,
            serial,
            STATE_PATH,
            lambda item: item.get("enrollment") is not None,
        )
        enrollment = state["enrollment"]
        enrollment_id = enrollment["enrollment_id"]
        if (
            state.get("status") != "IDLE"
            or not state.get("access_token")
            or not state.get("signing_seed")
        ):
            raise RuntimeError("pairing did not create private local state")
        assignment = modules["sign_document"](
            "assignment",
            {
                "enrollment_id": enrollment_id,
                "channel": CHANNEL,
                "revision_id": revision["revision_id"],
            },
            "promoter-e2e",
            PROMOTER_SEED,
            backend=backend,
        )
        store.assign_candidate(
            assignment, "assign-device-" + logical_device_id
        )
        _execute_builtin(
            adb,
            adb_port,
            serial,
            "RunScript(special://home/addons/%s/default.py,--sync-once)"
            % ADDON_ID,
        )
        checked = _wait_json(
            adb,
            adb_port,
            serial,
            STATE_PATH,
            lambda item: item.get("status") == "ASSIGNMENT_AVAILABLE",
        )
        if (
            checked.get("assigned_revision") != revision["revision_id"]
            or "applied_revision" in checked
        ):
            raise RuntimeError("read-only assignment invariant failed")
        origin = _installed_origin(
            adb,
            adb_port,
            serial,
            Path(temporary) / logical_device_id,
        )
        if origin != ORIGIN:
            raise RuntimeError("profile-sync add-on has unexpected origin")
        return {
            "logical_device_id": logical_device_id,
            "addon_version": expected_version,
            "installed_origin": origin,
            "pairing": "pass",
            "authenticated_heartbeat": "pass",
            "signed_candidate_check": "pass",
            "read_only_no_apply": "pass",
            "result": "pass",
        }
    finally:
        if enrollment_id is not None:
            store.revoke_enrollment(enrollment_id)
        try:
            _cleanup_client(adb, adb_port, serial)
        except Exception:
            pass
        adb_command(
            adb,
            adb_port,
            serial,
            "reverse",
            "--remove",
            "tcp:%d" % server_port,
            check=False,
            text=True,
        )
        adb_command(
            adb,
            adb_port,
            serial,
            "shell",
            "rm -f '%s' '%s'" % (REMOTE_HELPER, REMOTE_MARKER),
            check=False,
        )


def main():
    repository = Path(__file__).resolve().parents[2]
    parser = argparse.ArgumentParser()
    parser.add_argument("--device", action="append")
    parser.add_argument(
        "--adb", default="/home/mwo/android-sdk/platform-tools/adb"
    )
    parser.add_argument("--adb-server-port", type=int, default=5038)
    parser.add_argument(
        "--server-repository",
        type=Path,
        default=repository.parent / "kodi-profile-sync-server",
    )
    args = parser.parse_args()
    lock = json.loads(
        (repository / "manifests/locks/testing.json").read_text()
    )
    expected_version = lock["components"][ADDON_ID]["version"]
    registry = load_registry(repository / ".kodi-private/devices.json")
    selected = args.device or sorted(registry["devices"])
    server_repository = args.server_repository.resolve()
    with tempfile.TemporaryDirectory(
        prefix="mwo-profile-sync-device-e2e-"
    ) as temporary:
        root = Path(temporary)
        modules, backend, store, revision, database, registry_path = (
            _prepare_server(repository, server_repository, root)
        )
        port = _free_port()
        environment = dict(os.environ)
        environment["PYTHONPATH"] = str(server_repository / "src")
        process = subprocess.Popen(
            [
                sys.executable,
                "-m",
                "profile_sync_server.http",
                "--database",
                str(database),
                "--port",
                str(port),
                "--key-registry",
                str(registry_path),
            ],
            cwd=server_repository,
            env=environment,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.PIPE,
            text=True,
        )
        try:
            _wait_server("http://127.0.0.1:%d" % port, process)
            for logical_device_id in selected:
                (root / logical_device_id).mkdir()
            results = [
                verify_device(
                    repository,
                    logical_device_id,
                    args.adb,
                    args.adb_server_port,
                    port,
                    store,
                    modules,
                    backend,
                    revision,
                    expected_version,
                    root,
                )
                for logical_device_id in selected
            ]
        finally:
            process.terminate()
            try:
                process.wait(timeout=5)
            except subprocess.TimeoutExpired:
                process.kill()
                process.wait(timeout=5)
        print(
            json.dumps(
                {"schema": 1, "results": results},
                indent=2,
                sort_keys=True,
            )
        )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
