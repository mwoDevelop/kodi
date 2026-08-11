#!/usr/bin/env python3
"""Install, pair and check the profile-sync add-on on real Kodi.

The flow uses Kodi's add-on manager, a temporary verified loopback server and
ADB reverse. A single probe running as Kodi reports only sanitized state; it
never copies enrollment secrets outside Kodi. Each enrollment is revoked and
removed from Kodi at cleanup.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import socket
import sqlite3
import struct
import subprocess
import sys
import tempfile
import time
import urllib.request
import zipfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))

from tools.kodi_devices import (
    load_registry,
    resolve_device,
    resolve_private_endpoint,
)
from tools.kodi_inventory import load_private_references
from tools.kodi_profile import (
    AdbEventClient,
    AdbJsonRpcClient,
    KODI_PACKAGE,
    KODI_ROOT,
    adb_command,
    adb_output,
)
from tools.kodi_reinstall import (
    assign_addon_origins_in_kodi,
    installed_addon_origins,
)


ADDON_ID = "service.mwodevelop.profilesync"
ADDON_LABEL = "mwoDevelop Profile Sync"
ORIGIN_VERSION = "1.0.0"
REPOSITORY_CHANNELS = {
    "stable": {
        "origin": "repository.mwodevelop",
        "sha256": "0bde0bf4b61a178cacc07d8ffc2b5006b8374b1ec2c1a12d610ea02c2e6dc287",
    },
    "testing": {
        "origin": "repository.mwodevelop.testing",
        "sha256": "d5529a150e7b9f9491fcb19a9884e30b8d95632c258b16dc8578e8435fdcf430",
    },
}
ORIGIN = REPOSITORY_CHANNELS["testing"]["origin"]
ORIGIN_ARCHIVE = "%s-%s.zip" % (ORIGIN, ORIGIN_VERSION)
ORIGIN_URL = "https://mwodevelop.github.io/kodi/" + ORIGIN_ARCHIVE
ORIGIN_SHA256 = REPOSITORY_CHANNELS["testing"]["sha256"]
CHANNEL = "home-stable"
STATE_PATH = (
    KODI_ROOT + "/userdata/addon_data/" + ADDON_ID + "/state.json"
)
REMOTE_HELPER = "/sdcard/Download/.mwo-profile-sync-e2e-helper.py"
REMOTE_MARKER = "/sdcard/Download/.mwo-profile-sync-e2e-marker.json"
REMOTE_COMMAND = "/sdcard/Download/.mwo-profile-sync-e2e-command.json"
REMOTE_CLEANUP = "/sdcard/Download/.mwo-profile-sync-e2e-cleanup.json"
REMOTE_ORIGIN_ARCHIVE = "/sdcard/Download/" + ORIGIN_ARCHIVE
PUBLISHER_SEED = bytes.fromhex("61" * 32)
PROMOTER_SEED = bytes.fromhex("62" * 32)


def _configure_repository_channel(channel):
    global ORIGIN
    global ORIGIN_ARCHIVE
    global ORIGIN_URL
    global ORIGIN_SHA256
    global REMOTE_ORIGIN_ARCHIVE

    configuration = REPOSITORY_CHANNELS[channel]
    ORIGIN = configuration["origin"]
    ORIGIN_ARCHIVE = "%s-%s.zip" % (ORIGIN, ORIGIN_VERSION)
    ORIGIN_URL = "https://mwodevelop.github.io/kodi/" + ORIGIN_ARCHIVE
    ORIGIN_SHA256 = configuration["sha256"]
    REMOTE_ORIGIN_ARCHIVE = "/sdcard/Download/" + ORIGIN_ARCHIVE


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
        with AdbJsonRpcClient(adb, port, serial) as jsonrpc:
            jsonrpc.call(
                "XBMC.ExecuteBuiltin",
                {"command": command, "wait": False},
            )
        return
    except (OSError, RuntimeError, TimeoutError):
        pass
    _execute_event_builtin(adb, port, serial, command)


def _execute_event_builtin(adb, port, serial, command):
    try:
        AdbEventClient(adb, port, serial).execute_builtin(command)
        return
    except (
        OSError,
        subprocess.CalledProcessError,
        subprocess.TimeoutExpired,
    ):
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


def _wait_probe_phase(adb, port, serial, phase, timeout=120):
    order = {"configured": 1, "paired": 2, "checked": 3}
    expected = order[phase]
    marker = _wait_json(
        adb,
        port,
        serial,
        REMOTE_MARKER,
        lambda item: item.get("phase") == "error"
        or order.get(item.get("phase"), 0) >= expected,
        timeout=timeout,
    )
    if marker.get("phase") == "error":
        raise RuntimeError(
            "Kodi profile-sync probe failed: %s"
            % marker.get("error_type", "unknown")
        )
    return marker


def _wait_probe_cleanup(adb, port, serial, timeout=120):
    marker = _wait_json(
        adb,
        port,
        serial,
        REMOTE_CLEANUP,
        lambda item: isinstance(item.get("ok"), bool),
        timeout=timeout,
    )
    if not marker["ok"]:
        raise RuntimeError(
            "Kodi profile-sync state restoration failed: %s"
            % marker.get("error_type", "unknown")
        )
    return marker


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
    if not payload.returncode:
        match = re.search(
            r'<addon[^>]+version="([^"]+)"',
            payload.stdout.replace("\n", " "),
        )
        if match:
            return match.group(1)
    try:
        with AdbJsonRpcClient(adb, port, serial) as jsonrpc:
            details = jsonrpc.call(
                "Addons.GetAddonDetails",
                {
                    "addonid": ADDON_ID,
                    "properties": ["version"],
                },
            )
        return details.get("addon", {}).get("version")
    except (OSError, RuntimeError, TimeoutError):
        return None


def _addon_database_contains(adb, port, serial, table, addon_id):
    if table not in {"installed", "repo"}:
        raise ValueError("unsupported Kodi add-on database table")
    listing = adb_output(
        adb,
        port,
        serial,
        "shell",
        "ls '%s/userdata/Database'/Addons*.db 2>/dev/null" % KODI_ROOT,
    )
    remote = _latest_addons_database(listing)
    with tempfile.TemporaryDirectory(
        prefix="mwo-testing-repository-index-"
    ) as temporary:
        database = Path(temporary) / "addons.db"
        adb_command(
            adb,
            port,
            serial,
            "pull",
            remote,
            str(database),
            text=True,
        )
        with sqlite3.connect(database) as connection:
            row = connection.execute(
                "SELECT 1 FROM %s WHERE addonID=?" % table,
                (addon_id,),
            ).fetchone()
    return row is not None


def _repository_installed(adb, port, serial):
    manifest = KODI_ROOT + "/addons/" + ORIGIN + "/addon.xml"
    files_present = (
        adb_command(
            adb,
            port,
            serial,
            "shell",
            "test -s '%s'" % manifest,
            check=False,
        ).returncode
        == 0
    )
    if files_present:
        try:
            if _addon_database_contains(
                adb, port, serial, "installed", ORIGIN
            ):
                return True
        except (RuntimeError, subprocess.CalledProcessError):
            # Kodi may expose the add-on directory while keeping the database
            # behind Android scoped storage. Fall through to the supported
            # in-process API instead of treating this as "not installed".
            pass
    try:
        with AdbJsonRpcClient(adb, port, serial) as jsonrpc:
            details = jsonrpc.call(
                "Addons.GetAddonDetails",
                {
                    "addonid": ORIGIN,
                    "properties": ["enabled", "version"],
                },
            )
        addon = details.get("addon", {})
        return (
            addon.get("enabled") is True
            and addon.get("version") == ORIGIN_VERSION
        )
    except (OSError, RuntimeError, TimeoutError):
        return False


def _repository_indexed(adb, port, serial):
    return _addon_database_contains(adb, port, serial, "repo", ORIGIN)


def _current_control(jsonrpc):
    return jsonrpc.call(
        "GUI.GetProperties",
        {"properties": ["currentwindow", "currentcontrol"]},
    )


def _control_label(value):
    label = str(value).strip()
    if label.startswith("[") and label.endswith("]"):
        label = label[1:-1].strip()
    return label.casefold()


def _select_control(jsonrpc, labels, maximum_steps=64):
    expected = {_control_label(label) for label in labels}
    observed = []
    for _ in range(maximum_steps):
        gui = _current_control(jsonrpc)
        control = gui.get("currentcontrol", {})
        label = str(control.get("label", "")).strip()
        if label and label not in observed:
            observed.append(label)
        if _control_label(label) in expected:
            jsonrpc.call("Input.Select")
            return
        jsonrpc.call("Input.Down")
        time.sleep(0.1)
    raise RuntimeError(
        "Kodi file browser did not expose %s; visible controls: %s"
        % (sorted(labels), observed)
    )


def _ensure_kodi_foreground(adb, port, serial):
    adb_command(
        adb,
        port,
        serial,
        "shell",
        "input",
        "keyevent",
        "KEYCODE_WAKEUP",
        check=False,
        text=True,
        timeout=10,
    )
    adb_command(
        adb,
        port,
        serial,
        "shell",
        "am",
        "start",
        "-n",
        KODI_PACKAGE + "/.Splash",
        text=True,
        timeout=15,
    )
    deadline = time.monotonic() + 15
    while time.monotonic() < deadline:
        windows = adb_output(
            adb,
            port,
            serial,
            "shell",
            "dumpsys",
            "window",
        )
        if (
            "mCurrentFocus=" in windows
            and KODI_PACKAGE + "/" in windows.split("mCurrentFocus=", 1)[1]
        ):
            return
        adb_command(
            adb,
            port,
            serial,
            "shell",
            "input",
            "keyevent",
            "KEYCODE_WAKEUP",
            check=False,
            timeout=10,
        )
        time.sleep(0.5)
    raise RuntimeError("Kodi did not become the foreground Android app")


def _download_repository_archive(destination):
    with urllib.request.urlopen(ORIGIN_URL, timeout=30) as response:
        payload = response.read()
    if hashlib.sha256(payload).hexdigest() != ORIGIN_SHA256:
        raise RuntimeError("testing repository archive digest mismatch")
    destination.write_bytes(payload)
    with zipfile.ZipFile(destination) as archive:
        manifest = archive.read(ORIGIN + "/addon.xml").decode("utf-8")
    if (
        'id="%s"' % ORIGIN not in manifest
        or 'version="%s"' % ORIGIN_VERSION not in manifest
    ):
        raise RuntimeError("testing repository archive manifest mismatch")


def _accept_addon_install_prompt(adb, port, serial, timeout=15):
    deadline = time.monotonic() + timeout
    with AdbJsonRpcClient(adb, port, serial) as jsonrpc:
        while time.monotonic() < deadline:
            gui = _current_control(jsonrpc)
            window = gui.get("currentwindow", {})
            control = gui.get("currentcontrol", {})
            if window.get("id") == 10100:
                if str(control.get("label", "")).casefold() not in {
                    "yes",
                    "tak",
                }:
                    jsonrpc.call("Input.Left")
                jsonrpc.call("Input.Select")
                return True
            time.sleep(0.25)
    return False


def _bootstrap_testing_repository(adb, port, serial):
    with tempfile.TemporaryDirectory(
        prefix="mwo-profile-sync-repository-"
    ) as temporary:
        archive = Path(temporary) / ORIGIN_ARCHIVE
        _download_repository_archive(archive)
        adb_command(
            adb,
            port,
            serial,
            "push",
            str(archive),
            REMOTE_ORIGIN_ARCHIVE,
            text=True,
        )
    try:
        # Kodi 21 acknowledges InstallFromZip through JSON-RPC without opening
        # the file browser. EventServer executes this GUI-only builtin.
        _execute_event_builtin(adb, port, serial, "InstallFromZip")
        time.sleep(1)
        with AdbJsonRpcClient(adb, port, serial) as jsonrpc:
            _select_control(
                jsonrpc,
                {"External storage", "Pamięć zewnętrzna"},
            )
            time.sleep(0.5)
            _select_control(jsonrpc, {"Download", "Pobrane"})
            time.sleep(0.5)
            _select_control(jsonrpc, {ORIGIN_ARCHIVE})
        deadline = time.monotonic() + 45
        while time.monotonic() < deadline:
            if _repository_installed(adb, port, serial):
                return
            time.sleep(1)
        raise TimeoutError("testing repository installation timed out")
    finally:
        adb_command(
            adb,
            port,
            serial,
            "shell",
            "rm -f '%s'" % REMOTE_ORIGIN_ARCHIVE,
            check=False,
        )


def _install_from_testing(adb, port, serial, expected_version):
    current_version = _addon_version(adb, port, serial)
    current_origin = None
    if current_version is not None:
        with tempfile.TemporaryDirectory(
            prefix="mwo-profile-sync-origin-"
        ) as temporary:
            current_origin = _installed_origin(
                adb, port, serial, Path(temporary)
            )
    if current_version == expected_version and current_origin == ORIGIN:
        _set_addon_enabled(adb, port, serial, False)
        _set_addon_enabled(adb, port, serial, True)
        return
    if not _repository_installed(adb, port, serial):
        _bootstrap_testing_repository(adb, port, serial)
    _execute_builtin(adb, port, serial, "UpdateAddonRepos")
    deadline = time.monotonic() + 45
    while time.monotonic() < deadline:
        try:
            indexed = _repository_indexed(adb, port, serial)
        except (RuntimeError, subprocess.CalledProcessError):
            # Scoped storage can make Kodi's database opaque to the ADB shell.
            # The subsequent InstallAddon + exact-version check remains the
            # authoritative in-process repository test.
            indexed = None
        if indexed is not False:
            break
        time.sleep(1)
    else:
        raise TimeoutError("testing repository indexing timed out")
    if current_version == expected_version:
        _switch_matching_version_origin(
            adb, port, serial, current_origin
        )
        _set_addon_enabled(adb, port, serial, False)
        _set_addon_enabled(adb, port, serial, True)
        return
    if current_version is None:
        _execute_builtin(adb, port, serial, "InstallAddon(%s)" % ADDON_ID)
        _accept_addon_install_prompt(adb, port, serial)
    else:
        # Kodi intentionally does not switch an installed add-on between two
        # private repositories through InstallAddon or automatic updates. The
        # supported path is the add-on information dialog's Versions picker.
        # It records both the selected version and its repository origin.
        _select_repository_version(
            adb,
            port,
            serial,
            expected_version,
            current_origin,
        )
    deadline = time.monotonic() + 90
    while time.monotonic() < deadline:
        if _addon_version(adb, port, serial) == expected_version:
            _set_addon_enabled(adb, port, serial, False)
            _set_addon_enabled(adb, port, serial, True)
            return
        time.sleep(2)
    raise TimeoutError("testing profile-sync add-on installation timed out")


def _switch_matching_version_origin(adb, port, serial, current_origin):
    if not current_origin:
        raise RuntimeError("installed profile-sync origin is unavailable")
    assign_addon_origins_in_kodi(
        adb,
        port,
        {
            "serial": serial,
            "addon_origins": {ADDON_ID: ORIGIN},
            "addon_previous_origins": {ADDON_ID: current_origin},
            "addon_repository_checksums": {},
            "addon_version_transitions": {},
        },
        ROOT / "tools/kodi_profile_origin_device.py",
    )


def _select_repository_version(
    adb, port, serial, expected_version, current_origin
):
    _ensure_kodi_foreground(adb, port, serial)
    with AdbJsonRpcClient(adb, port, serial) as jsonrpc:
        # A previous interrupted GUI operation must not mask ActivateWindow.
        for _ in range(8):
            window_id = (
                _current_control(jsonrpc)
                .get("currentwindow", {})
                .get("id")
            )
            if window_id not in {10100, 10103, 10146, 12000}:
                break
            jsonrpc.call("Input.Back")
            time.sleep(0.25)
    _execute_event_builtin(
        adb,
        port,
        serial,
        "ActivateWindow(AddonBrowser,addons://user/xbmc.service,return)",
    )
    time.sleep(1)
    with AdbJsonRpcClient(adb, port, serial) as jsonrpc:
        _select_control(jsonrpc, {ADDON_LABEL})
        time.sleep(0.5)
        if current_origin == ORIGIN:
            _select_control(jsonrpc, {"Update", "Aktualizuj"})
            return
        _select_control(jsonrpc, {"Versions", "Wersje"})
        time.sleep(0.5)
        _select_control(
            jsonrpc,
            {
                "Version %s" % expected_version,
                "Wersja %s" % expected_version,
            },
        )


def _set_addon_enabled(adb, port, serial, enabled):
    deadline = time.monotonic() + 20
    requested = False
    while time.monotonic() < deadline:
        try:
            with AdbJsonRpcClient(adb, port, serial) as jsonrpc:
                if not requested:
                    try:
                        jsonrpc.call(
                            "Addons.SetAddonEnabled",
                            {"addonid": ADDON_ID, "enabled": enabled},
                        )
                    except (TimeoutError, RuntimeError):
                        pass
                    requested = True
                details = jsonrpc.call(
                    "Addons.GetAddonDetails",
                    {"addonid": ADDON_ID, "properties": ["enabled"]},
                )
            if details.get("addon", {}).get("enabled") is enabled:
                return
            requested = False
        except (OSError, TimeoutError, RuntimeError):
            pass
        time.sleep(0.5)
    raise TimeoutError("Kodi add-on enabled state did not converge")


def _start_probe(
    adb,
    port,
    serial,
    server_port,
    logical_device_id,
    expected_revision,
    pairing_code,
):
    settings = {
        "server_url": "http://127.0.0.1:%d" % server_port,
        "logical_device_id": logical_device_id,
        "channel": CHANNEL,
        "enabled": "true",
        "read_only": "true",
    }
    source = """import json
import os
import time
import xbmc
import xbmcaddon

ADDON_ID = %s
SETTINGS = %s
SETTING_KEYS = %s
STATE_PATH = %s
MARKER_PATH = %s
COMMAND_PATH = %s
CLEANUP_PATH = %s
EXPECTED_REVISION = %s
PAIRING_CODE = %s
COMMAND_ENTRYPOINT = (
    "special://home/addons/" + ADDON_ID + "/default.py"
)


def write_marker(document):
    temporary = MARKER_PATH + ".tmp"
    with open(temporary, "w", encoding="utf-8") as handle:
        json.dump(document, handle, sort_keys=True)
    os.replace(temporary, MARKER_PATH)


def write_cleanup(document):
    temporary = CLEANUP_PATH + ".tmp"
    with open(temporary, "w", encoding="utf-8") as handle:
        json.dump(document, handle, sort_keys=True)
    os.replace(temporary, CLEANUP_PATH)


def read_state():
    try:
        with open(STATE_PATH, "r", encoding="utf-8") as handle:
            return json.load(handle)
    except (OSError, ValueError):
        return {}


def wait_for(predicate, timeout=120):
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        document = read_state()
        if predicate(document):
            return document
        time.sleep(0.25)
    raise TimeoutError("profile sync state transition timed out")


addon = xbmcaddon.Addon(ADDON_ID)
original_settings = {
    key: addon.getSetting(key) for key in SETTING_KEYS
}
try:
    with open(STATE_PATH, "r", encoding="utf-8") as handle:
        original_state = handle.read()
except OSError:
    original_state = None
try:
    for key, value in SETTINGS.items():
        addon.setSetting(key, value)
    actual = {key: addon.getSetting(key) for key in SETTING_KEYS}
    if actual != SETTINGS:
        raise RuntimeError("profile sync settings did not persist")
    try:
        os.unlink(STATE_PATH)
    except OSError:
        pass
    write_marker({"ok": True, "phase": "configured"})
    deadline = time.monotonic() + 120
    direct_pair_at = time.monotonic() + 10
    next_pair_notification = 0
    pair_transport = "service_notification"
    direct_pair_sent = False
    paired = None
    while time.monotonic() < deadline:
        candidate = read_state()
        if (
            (candidate.get("enrollment") or {}).get("enrollment_id")
            and candidate.get("access_token")
            and candidate.get("signing_seed")
        ):
            paired = candidate
            break
        if (
            not direct_pair_sent
            and time.monotonic() >= direct_pair_at
        ):
            xbmc.executebuiltin(
                "RunScript(%%s,--pair-code,%%s)"
                %% (COMMAND_ENTRYPOINT, PAIRING_CODE)
            )
            direct_pair_sent = True
            pair_transport = "direct_command"
        if time.monotonic() >= next_pair_notification:
            xbmc.executebuiltin(
                "NotifyAll(%s,pair-code,{\\"code\\":\\"%%s\\"})"
                %% PAIRING_CODE
            )
            next_pair_notification = time.monotonic() + 5
        time.sleep(0.25)
    if paired is None:
        raise TimeoutError("profile sync pairing timed out")
    enrollment = paired["enrollment"]
    write_marker(
        {
            "ok": True,
            "phase": "paired",
            "status": paired.get("status"),
            "enrollment_id": enrollment["enrollment_id"],
            "has_access_token": bool(paired.get("access_token")),
            "has_signing_seed": bool(paired.get("signing_seed")),
            "pair_transport": pair_transport,
        }
    )

    deadline = time.monotonic() + 120
    while time.monotonic() < deadline:
        try:
            with open(COMMAND_PATH, "r", encoding="utf-8") as handle:
                command = json.load(handle)
        except (OSError, ValueError):
            command = {}
        if command.get("sync") is True:
            break
        time.sleep(0.25)
    else:
        raise TimeoutError("profile sync command timed out")
    xbmc.executebuiltin(
        "NotifyAll(%s,sync-now,{\\"source\\":\\"device-e2e\\"})"
    )

    sync_transport = "service_notification"
    checked = None
    direct_sync_at = time.monotonic() + 10
    while time.monotonic() < direct_sync_at:
        candidate = read_state()
        if (
            candidate.get("status") == "ASSIGNMENT_AVAILABLE"
            and candidate.get("assigned_revision") == EXPECTED_REVISION
        ):
            checked = candidate
            break
        time.sleep(0.25)
    if checked is None:
        xbmc.executebuiltin(
            "RunScript(%%s,--sync-once)" %% COMMAND_ENTRYPOINT
        )
        sync_transport = "direct_command"
        checked = wait_for(
            lambda item: item.get("status") == "ASSIGNMENT_AVAILABLE"
            and item.get("assigned_revision") == EXPECTED_REVISION
        )
    write_marker(
        {
            "ok": True,
            "phase": "checked",
            "status": checked.get("status"),
            "enrollment_id": enrollment["enrollment_id"],
            "assigned_revision": checked.get("assigned_revision"),
            "has_applied_revision": "applied_revision" in checked,
            "pair_transport": pair_transport,
            "sync_transport": sync_transport,
        }
    )
except Exception as error:
    write_marker(
        {
            "ok": False,
            "phase": "error",
            "error_type": type(error).__name__,
        }
    )
finally:
    try:
        for key, value in original_settings.items():
            addon.setSetting(key, value)
        if original_state is None:
            try:
                os.unlink(STATE_PATH)
            except OSError:
                pass
        else:
            temporary = STATE_PATH + ".restore"
            with open(temporary, "w", encoding="utf-8") as handle:
                handle.write(original_state)
            os.replace(temporary, STATE_PATH)
    except Exception as error:
        write_cleanup(
            {"ok": False, "error_type": type(error).__name__}
        )
    else:
        write_cleanup({"ok": True})
""" % (
        json.dumps(ADDON_ID),
        repr(settings),
        repr(sorted(settings)),
        json.dumps(STATE_PATH),
        json.dumps(REMOTE_MARKER),
        json.dumps(REMOTE_COMMAND),
        json.dumps(REMOTE_CLEANUP),
        json.dumps(expected_revision),
        json.dumps(pairing_code),
        ADDON_ID,
        ADDON_ID,
    )
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
            "rm -f '%s' '%s' '%s' '%s'"
            % (REMOTE_HELPER, REMOTE_MARKER, REMOTE_COMMAND, REMOTE_CLEANUP),
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
    return _wait_probe_phase(adb, port, serial, "configured")


def _signal_probe_sync(adb, port, serial):
    with tempfile.NamedTemporaryFile(
        mode="w", suffix=".json", encoding="utf-8"
    ) as command:
        json.dump({"sync": True}, command)
        command.flush()
        adb_command(
            adb,
            port,
            serial,
            "push",
            command.name,
            REMOTE_COMMAND,
            text=True,
        )


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


def _installed_origin(adb, port, serial, temporary):
    try:
        listing = adb_output(
            adb,
            port,
            serial,
            "shell",
            "ls '%s/userdata/Database'/Addons*.db 2>/dev/null" % KODI_ROOT,
        )
        remote = _latest_addons_database(listing)
        database = Path(temporary) / "addons.db"
        adb_command(
            adb, port, serial, "pull", remote, str(database), text=True
        )
        with sqlite3.connect(database) as connection:
            row = connection.execute(
                "SELECT origin FROM installed WHERE addonID=?", (ADDON_ID,)
            ).fetchone()
        return row[0] if row else None
    except (RuntimeError, subprocess.CalledProcessError):
        origins = installed_addon_origins(
            adb,
            port,
            serial,
            [ADDON_ID],
            origin_script=(
                Path(__file__).resolve().parents[2]
                / "tools/kodi_profile_origin_device.py"
            ),
        )
        return origins.get(ADDON_ID)


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
    registry,
    references,
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
    device = resolve_private_endpoint(
        resolve_device(registry, logical_device_id),
        references,
        required=True,
    )
    serial = device["endpoints"]["adb"]
    model = adb_output(
        adb, adb_port, serial, "shell", "getprop ro.product.model"
    ).strip()
    if model != device["expected"]["model"]:
        raise RuntimeError("%s resolved to the wrong model" % logical_device_id)
    enrollment_id = None
    probe_started = False
    cleanup_complete = False
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
        _ensure_kodi_foreground(adb, adb_port, serial)
        _install_from_testing(
            adb, adb_port, serial, expected_version
        )
        pairing = store.create_pairing_code(
            logical_device_id,
            CHANNEL,
            code=None,
            ttl_seconds=300,
        )
        _start_probe(
            adb,
            adb_port,
            serial,
            server_port,
            logical_device_id,
            revision["revision_id"],
            pairing["code"],
        )
        probe_started = True
        state = _wait_probe_phase(
            adb, adb_port, serial, "paired"
        )
        candidate_enrollment_id = state["enrollment_id"]
        if (
            state.get("status") != "IDLE"
            or not state.get("has_access_token")
            or not state.get("has_signing_seed")
        ):
            raise RuntimeError("pairing did not create private local state")
        enrollment_id = candidate_enrollment_id
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
        _signal_probe_sync(adb, adb_port, serial)
        checked = _wait_probe_phase(adb, adb_port, serial, "checked")
        if (
            checked.get("assigned_revision") != revision["revision_id"]
            or checked.get("has_applied_revision")
        ):
            raise RuntimeError("read-only assignment invariant failed")
        _wait_probe_cleanup(adb, adb_port, serial)
        cleanup_complete = True
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
            "pair_transport": checked.get("pair_transport"),
            "authenticated_heartbeat": "pass",
            "signed_candidate_check": "pass",
            "sync_transport": checked.get("sync_transport"),
            "read_only_no_apply": "pass",
            "result": "pass",
        }
    finally:
        if probe_started and not cleanup_complete:
            _wait_probe_cleanup(adb, adb_port, serial)
        if enrollment_id is not None:
            store.revoke_enrollment(enrollment_id)
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
            "rm -f '%s' '%s' '%s' '%s'"
            % (REMOTE_HELPER, REMOTE_MARKER, REMOTE_COMMAND, REMOTE_CLEANUP),
            check=False,
        )


def main():
    repository = ROOT
    parser = argparse.ArgumentParser()
    parser.add_argument("--device", action="append")
    parser.add_argument(
        "--devices",
        type=Path,
        default=repository / ".kodi-private/devices.json",
    )
    parser.add_argument(
        "--references",
        type=Path,
        default=repository / ".env",
        help="ignored private endpoint reference file",
    )
    parser.add_argument(
        "--adb", default="/home/mwo/android-sdk/platform-tools/adb"
    )
    parser.add_argument("--adb-server-port", type=int, default=5038)
    parser.add_argument(
        "--server-repository",
        type=Path,
        default=repository.parent / "kodi-profile-sync-server",
    )
    parser.add_argument(
        "--result",
        type=Path,
        help="write the sanitized JSON result to this path",
    )
    parser.add_argument(
        "--repository-channel",
        choices=sorted(REPOSITORY_CHANNELS),
        default="testing",
        help="repository channel used to install and verify the add-on",
    )
    args = parser.parse_args()
    _configure_repository_channel(args.repository_channel)
    lock = json.loads(
        (
            repository
            / "manifests/locks"
            / ("%s.json" % args.repository_channel)
        ).read_text()
    )
    expected_version = lock["components"][ADDON_ID]["version"]
    registry = load_registry(args.devices.resolve())
    references = load_private_references(args.references.resolve())
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
                    registry,
                    references,
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
        result = json.dumps(
            {"schema": 1, "results": results},
            indent=2,
            sort_keys=True,
        )
        if args.result is not None:
            destination = args.result.resolve()
            destination.parent.mkdir(parents=True, exist_ok=True)
            destination.write_text(result + "\n", encoding="utf-8")
        print(result)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
