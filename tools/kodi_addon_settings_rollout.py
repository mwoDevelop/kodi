#!/usr/bin/env python3
"""Transactionally copy private add-on settings into one Android Kodi."""

from __future__ import annotations

import argparse
import hashlib
import io
import json
import re
import secrets
import sys
import tarfile
import tempfile
import time
from pathlib import Path
from xml.etree import ElementTree

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from tools.kodi_profile import (
    KODI_PACKAGE,
    RESTORE_ARCHIVE,
    RESTORE_MARKER,
    RESTORE_SCRIPT,
    RESTORE_STARTED,
    VERIFY_MARKER,
    VERIFY_STARTED,
    AdbJsonRpcClient,
    RestoreCommandMayBeQueued,
    _acquire_restore_lock,
    _cleanup_restore_staging,
    _push,
    _quiesce_incomplete_restore,
    _release_restore_lock,
    _run_restore_script,
    _wait_for_kodi_ready,
    adb_command,
    canonical_json,
)


SAFE_ID = re.compile(r"^[A-Za-z0-9._-]+$")


def _digest(payload):
    return hashlib.sha256(payload).hexdigest()


def load_setting_sources(specifications):
    sources = {}
    for specification in specifications:
        addon_id, separator, raw_path = specification.partition("=")
        if (
            separator != "="
            or not SAFE_ID.fullmatch(addon_id)
            or addon_id in sources
            or not raw_path
        ):
            raise ValueError("invalid or duplicate add-on settings source")
        path = Path(raw_path).expanduser().resolve()
        if not path.is_file() or path.is_symlink():
            raise ValueError("add-on settings source is not a regular file")
        payload = path.read_bytes()
        root = ElementTree.fromstring(payload)
        values = {}
        for node in root.findall(".//setting"):
            setting_id = node.attrib.get("id")
            if not setting_id or setting_id in values:
                raise ValueError("add-on settings contain an invalid ID")
            values[setting_id] = node.text or ""
        if not values:
            raise ValueError("add-on settings source is empty")
        sources[addon_id] = {
            "path": path,
            "payload": payload,
            "values": values,
        }
    if not sources:
        raise ValueError("at least one add-on settings source is required")
    return sources


def build_restore_archive(sources, output, operation_id):
    if not re.fullmatch(r"[0-9a-f]{32}", operation_id):
        raise ValueError("invalid restore operation identifier")
    files = {}
    for addon_id, source in sorted(sources.items()):
        relative = "userdata/addon_data/%s/settings.xml" % addon_id
        files[relative] = {
            "sha256": _digest(source["payload"]),
            "size": len(source["payload"]),
            "setting_ids": sorted(source["values"]),
            "settings_sha256": _digest(canonical_json(source["values"])),
        }
    snapshot_id = _digest(canonical_json(files))
    manifest = {
        "schema": 1,
        "snapshot_id": snapshot_id,
        "operation_id": operation_id,
        "files": files,
        "selection_sha256": _digest(canonical_json(files)),
    }
    with tarfile.open(output, "w", format=tarfile.PAX_FORMAT) as archive:
        document = canonical_json(manifest)
        info = tarfile.TarInfo("restore-manifest.json")
        info.size = len(document)
        info.mode = 0o600
        info.mtime = 0
        archive.addfile(info, io.BytesIO(document))
        for addon_id, source in sorted(sources.items()):
            relative = "userdata/addon_data/%s/settings.xml" % addon_id
            info = tarfile.TarInfo("payload/" + relative)
            info.size = len(source["payload"])
            info.mode = 0o600
            info.mtime = 0
            archive.addfile(info, io.BytesIO(source["payload"]))
    return manifest


def _addon_versions(adb, port, serial, addon_ids):
    result = {}
    with AdbJsonRpcClient(adb, port, serial) as rpc:
        for addon_id in sorted(addon_ids):
            details = rpc.call(
                "Addons.GetAddonDetails",
                {
                    "addonid": addon_id,
                    "properties": ["version", "enabled"],
                },
            ).get("addon", {})
            if not details.get("enabled") or not details.get("version"):
                raise RuntimeError(
                    "settings target is absent or disabled: %s" % addon_id
                )
            result[addon_id] = str(details["version"])
    return result


def _start_kodi(adb, port, serial):
    adb_command(
        adb,
        port,
        serial,
        "shell",
        "input keyevent KEYCODE_WAKEUP",
        check=False,
    )
    adb_command(
        adb,
        port,
        serial,
        "shell",
        "monkey -p %s -c android.intent.category.LAUNCHER 1 >/dev/null"
        % KODI_PACKAGE,
    )
    _wait_for_kodi_ready(adb, port, serial)


def rollout(adb, port, serial, sources, device_script):
    operation_id = secrets.token_hex(16)
    locked = False
    safe_to_unlock = True
    try:
        _acquire_restore_lock(adb, port, serial)
        locked = True
        with tempfile.NamedTemporaryFile(suffix=".tar") as archive:
            manifest = build_restore_archive(
                sources, archive.name, operation_id
            )
            _push(adb, port, serial, archive.name, RESTORE_ARCHIVE)
        _push(adb, port, serial, device_script, RESTORE_SCRIPT)
        adb_command(
            adb,
            port,
            serial,
            "shell",
            "rm -f '%s' '%s' '%s' '%s'"
            % (
                RESTORE_MARKER,
                RESTORE_STARTED,
                VERIFY_MARKER,
                VERIFY_STARTED,
            ),
        )
        _start_kodi(adb, port, serial)
        before = _addon_versions(adb, port, serial, sources)
        result = _run_restore_script(adb, port, serial, operation_id)
        if (
            not result.get("ok")
            or result.get("snapshot_id") != manifest["snapshot_id"]
            or result.get("operation_id") != operation_id
            or result.get("restored_files") != len(sources)
            or result.get("selection_sha256")
            != manifest["selection_sha256"]
        ):
            raise RuntimeError(
                "Kodi add-on settings restore failed: %s"
                % result.get("error_type")
            )
        adb_command(
            adb,
            port,
            serial,
            "shell",
            "am force-stop %s" % KODI_PACKAGE,
        )
        time.sleep(2)
        _start_kodi(adb, port, serial)
        time.sleep(5)
        if _addon_versions(adb, port, serial, sources) != before:
            raise RuntimeError("add-on version changed during settings restore")
        adb_command(
            adb,
            port,
            serial,
            "shell",
            "rm -f '%s' '%s'" % (VERIFY_MARKER, VERIFY_STARTED),
        )
        verification = _run_restore_script(
            adb, port, serial, operation_id, mode="verify"
        )
        if (
            not verification.get("ok")
            or verification.get("snapshot_id") != manifest["snapshot_id"]
            or verification.get("operation_id") != operation_id
            or verification.get("verified_files") != len(sources)
            or verification.get("selection_sha256")
            != manifest["selection_sha256"]
        ):
            raise RuntimeError(
                "Kodi add-on settings verification failed: %s"
                % verification.get("error_type")
            )
        return {
            "schema": 1,
            "result": "pass",
            "serial": serial,
            "settings_sources": sorted(sources),
            "versions": before,
            "snapshot_id": manifest["snapshot_id"],
            "restored_files": len(sources),
            "verified_files": len(sources),
        }
    except BaseException as error:
        if locked:
            try:
                _quiesce_incomplete_restore(
                    adb,
                    port,
                    serial,
                    command_may_be_queued=isinstance(
                        error,
                        RestoreCommandMayBeQueued,
                    ),
                )
            except Exception as quiesce_error:
                safe_to_unlock = False
                raise quiesce_error from error
        raise
    finally:
        if locked and safe_to_unlock:
            _cleanup_restore_staging(adb, port, serial)
            _release_restore_lock(adb, port, serial)


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--setting",
        action="append",
        required=True,
        help="ADDON_ID=/private/path/settings.xml; may be repeated",
    )
    parser.add_argument("--serial", required=True)
    parser.add_argument(
        "--adb", default="/home/mwo/android-sdk/platform-tools/adb"
    )
    parser.add_argument("--adb-server-port", type=int, default=5038)
    parser.add_argument(
        "--device-script",
        default=str(ROOT / "tools/kodi_profile_restore_device.py"),
    )
    parser.add_argument("--result")
    args = parser.parse_args()
    result = rollout(
        args.adb,
        args.adb_server_port,
        args.serial,
        load_setting_sources(args.setting),
        Path(args.device_script).resolve(),
    )
    payload = json.dumps(result, indent=2, sort_keys=True) + "\n"
    if args.result:
        Path(args.result).write_text(payload, encoding="utf-8")
    print(payload, end="")


if __name__ == "__main__":
    main()
