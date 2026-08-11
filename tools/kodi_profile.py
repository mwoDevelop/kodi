#!/usr/bin/env python3
"""Export, verify and restore a private Kodi profile snapshot over ADB."""

from __future__ import annotations

import argparse
import base64
import hashlib
import io
import json
import re
import secrets
import shutil
import socket
import sqlite3
import struct
import subprocess
import tarfile
import tempfile
import time
import xml.etree.ElementTree as ET
from datetime import datetime, timezone
from pathlib import Path, PurePosixPath

try:
    from tools.favourite_artwork import (
        materialize as materialize_favourite_artwork,
    )
except ModuleNotFoundError:
    from favourite_artwork import materialize as materialize_favourite_artwork


SCHEMA = 1
LEGACY_WATCH_ID = "plugin.video.watchnixtoons2"
KODI_PACKAGE = "org.xbmc.kodi"
KODI_ROOT = "/sdcard/Android/data/org.xbmc.kodi/files/.kodi"
PRIVATE_ROOT_NAME = ".kodi-private"
RESTORE_ARCHIVE = "/sdcard/Download/mwo-kodi-profile-restore.tar"
RESTORE_SCRIPT = "/sdcard/Download/mwo-kodi-profile-restore-device.py"
RESTORE_MARKER = "/sdcard/Download/mwo-kodi-profile-restore-result.json"
RESTORE_STARTED = "/sdcard/Download/mwo-kodi-profile-restore-started.json"
VERIFY_MARKER = "/sdcard/Download/mwo-kodi-profile-verify-result.json"
VERIFY_STARTED = "/sdcard/Download/mwo-kodi-profile-verify-started.json"
RESTORE_LOCK = "/sdcard/Download/mwo-kodi-profile-restore.lock"
EXPORT_FILE_LIST = "/sdcard/Download/mwo-kodi-profile-filelist.txt"


class RestoreCommandMayBeQueued(TimeoutError):
    """A Kodi EventServer command was sent but never acknowledged."""


def canonical_json(value):
    return json.dumps(
        value, sort_keys=True, separators=(",", ":"), ensure_ascii=False
    ).encode("utf-8")


def digest(payload):
    return hashlib.sha256(payload).hexdigest()


def glob_regex(pattern):
    result = ""
    index = 0
    while index < len(pattern):
        character = pattern[index]
        if character == "*":
            if index + 1 < len(pattern) and pattern[index + 1] == "*":
                result += ".*"
                index += 2
                continue
            result += "[^/]*"
        elif character == "?":
            result += "[^/]"
        else:
            result += re.escape(character)
        index += 1
    return re.compile("^" + result + "$")


def load_policy(path):
    document = json.loads(Path(path).read_text(encoding="utf-8"))
    if document.get("schema") != 2:
        raise ValueError("unsupported Kodi profile policy")
    scopes = document.get("scopes")
    if not isinstance(scopes, dict) or not isinstance(
        scopes.get("disaster_recovery"), dict
    ):
        raise ValueError("Kodi profile policy lacks disaster recovery scope")
    return document


def disaster_recovery_policy(policy):
    if policy.get("schema") == 2:
        return policy["scopes"]["disaster_recovery"]
    raise ValueError("unsupported Kodi profile policy")


def included_by_policy(relative, policy):
    policy = disaster_recovery_policy(policy)
    relative = PurePosixPath(relative).as_posix()
    included = any(
        glob_regex(item).fullmatch(relative) for item in policy["include"]
    )
    excluded = any(
        glob_regex(item).fullmatch(relative) for item in policy["exclude"]
    )
    return included and not excluded


PROFILE_SYNC_IDENTITY_PREFIX = (
    "userdata",
    "addon_data",
    "service.mwodevelop.profilesync",
)


def contains_profile_sync_identity(paths):
    return any(
        PurePosixPath(relative).parts[:3] == PROFILE_SYNC_IDENTITY_PREFIX
        for relative in paths
    )


def classify_snapshot_identity(snapshot):
    snapshot = Path(snapshot).resolve()
    manifest = json.loads(
        (snapshot / "manifest.json").read_text(encoding="utf-8")
    )
    files = manifest.get("files")
    if not isinstance(files, dict):
        raise ValueError("snapshot has no file inventory")
    return {
        "snapshot": str(snapshot),
        "identity_status": (
            "IDENTITY_CONTAMINATED"
            if contains_profile_sync_identity(files)
            else "IDENTITY_CLEAN"
        ),
    }


def sanitize_snapshot_identity(snapshot, output):
    """Create a verified copy without device-local Profile Sync identity."""
    snapshot = Path(snapshot).resolve()
    output = Path(output).resolve()
    if output.exists():
        raise ValueError("sanitized snapshot output already exists")
    if classify_snapshot_identity(snapshot)["identity_status"] != (
        "IDENTITY_CONTAMINATED"
    ):
        raise ValueError("snapshot does not contain Profile Sync identity")
    output.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
    temporary = Path(
        tempfile.mkdtemp(prefix=".sanitize-", dir=str(output.parent))
    ).resolve()
    try:
        shutil.copytree(snapshot, temporary, dirs_exist_ok=True, symlinks=True)
        identity_root = temporary / "payload" / Path(
            *PROFILE_SYNC_IDENTITY_PREFIX
        )
        if identity_root.is_symlink():
            raise ValueError("snapshot identity path cannot be a link")
        shutil.rmtree(identity_root)
        manifest_path = temporary / "manifest.json"
        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
        manifest["files"] = {
            relative: metadata
            for relative, metadata in manifest["files"].items()
            if not contains_profile_sync_identity([relative])
        }
        identity = {
            key: manifest[key]
            for key in (
                "schema",
                "policy_sha256",
                "device",
                "selected_skin",
                "addons",
                "files",
                "installer",
            )
        }
        manifest["sanitized_from"] = manifest["snapshot_id"]
        manifest["snapshot_id"] = digest(canonical_json(identity))
        manifest_path.write_bytes(canonical_json(manifest) + b"\n")
        secure_private_tree(temporary)
        verify_snapshot(temporary)
        temporary.rename(output)
        return manifest
    except BaseException:
        shutil.rmtree(temporary, ignore_errors=True)
        raise


def requires_direct_copy(relative):
    return any(
        part.startswith("...")
        for part in PurePosixPath(relative).parts
    )


def kodi_versions_compatible(source, target, allow_upgrade=False):
    if source == target:
        return True
    source_numbers = tuple(int(item) for item in re.findall(r"\d+", source))
    target_numbers = tuple(int(item) for item in re.findall(r"\d+", target))
    if not source_numbers or not target_numbers:
        return False
    return (
        allow_upgrade
        and source_numbers[0] == target_numbers[0]
        and target_numbers >= source_numbers
    )


def adb_command(
    adb,
    adb_server_port,
    serial,
    *args,
    check=True,
    text=False,
    timeout=120,
):
    command = [adb]
    if adb_server_port:
        command.extend(["-P", str(adb_server_port)])
    command.extend(["-s", serial, *args])
    return subprocess.run(
        command,
        check=check,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        text=text,
        timeout=timeout,
    )


def adb_output(
    adb, adb_server_port, serial, *args, text=True, timeout=120
):
    return adb_command(
        adb,
        adb_server_port,
        serial,
        *args,
        text=text,
        timeout=timeout,
    ).stdout


def ensure_private_output(path, repository_root):
    path = Path(path).resolve()
    private_root = (Path(repository_root).resolve() / PRIVATE_ROOT_NAME).resolve()
    if path == private_root or private_root not in path.parents:
        raise ValueError("snapshot must be stored below %s" % private_root)
    check = subprocess.run(
        ["git", "-C", str(repository_root), "check-ignore", "-q", str(path)],
        check=False,
    )
    if check.returncode != 0:
        raise ValueError("private snapshot path is not ignored by git")
    return path


def secure_private_tree(root):
    root = Path(root)
    for path in root.rglob("*"):
        if path.is_dir():
            path.chmod(0o700)
        elif path.is_file():
            path.chmod(0o600)
    root.chmod(0o700)


def device_info(adb, port, serial):
    package = adb_output(
        adb, port, serial, "shell", "dumpsys package %s" % KODI_PACKAGE
    )
    version = re.search(r"versionName=([^\s]+)", package)
    if not version:
        raise RuntimeError("Kodi is not installed on the source device")
    return {
        "serial": serial,
        "manufacturer": adb_output(
            adb, port, serial, "shell", "getprop ro.product.manufacturer"
        ).strip(),
        "model": adb_output(
            adb, port, serial, "shell", "getprop ro.product.model"
        ).strip(),
        "android": adb_output(
            adb, port, serial, "shell", "getprop ro.build.version.release"
        ).strip(),
        "abi_list": [
            item
            for item in adb_output(
                adb, port, serial, "shell", "getprop ro.product.cpu.abilist"
            ).strip().split(",")
            if item
        ],
        "kodi_package": KODI_PACKAGE,
        "kodi_version": version.group(1),
    }


def _read_remote(adb, port, serial, path):
    return adb_output(adb, port, serial, "exec-out", "cat", path, text=False)


def selected_skin(adb, port, serial):
    payload = _read_remote(
        adb, port, serial, KODI_ROOT + "/userdata/guisettings.xml"
    )
    root = ET.fromstring(payload)
    for setting in root.findall(".//setting"):
        if setting.attrib.get("id") == "lookandfeel.skin":
            return setting.text or "skin.estuary"
    return "skin.estuary"


def installed_state(adb, port, serial):
    payload = _read_remote(
        adb,
        port,
        serial,
        KODI_ROOT + "/userdata/Database/Addons33.db",
    )
    with tempfile.NamedTemporaryFile(suffix=".db") as handle:
        handle.write(payload)
        handle.flush()
        with sqlite3.connect(handle.name) as database:
            rows = database.execute(
                "select addonID, enabled, origin from installed order by addonID"
            ).fetchall()
    return {
        addon_id: {"enabled": bool(enabled), "origin": origin}
        for addon_id, enabled, origin in rows
    }


def _extract_profile(adb, port, serial, destination, policy):
    listing = adb_output(
        adb,
        port,
        serial,
        "shell",
        "cd '%s' && find addons userdata -type f -print" % KODI_ROOT,
    )
    selected = sorted(
        {
            PurePosixPath(line.strip()).as_posix()
            for line in listing.splitlines()
            if line.strip() and included_by_policy(line.strip(), policy)
        }
    )
    if not selected:
        raise RuntimeError("Kodi profile policy selected no files")
    direct_files = [
        relative
        for relative in selected
        if requires_direct_copy(relative)
    ]
    archive_files = [
        relative for relative in selected if relative not in direct_files
    ]
    with tempfile.NamedTemporaryFile(mode="w", encoding="utf-8") as file_list:
        file_list.write("\n".join(archive_files) + "\n")
        file_list.flush()
        adb_command(
            adb,
            port,
            serial,
            "push",
            file_list.name,
            EXPORT_FILE_LIST,
        )
    command = [adb]
    if port:
        command.extend(["-P", str(port)])
    command.extend(
        [
            "-s",
            serial,
            "exec-out",
            "tar",
            "-C",
            KODI_ROOT,
            "-cf",
            "-",
            "--no-recursion",
            "-T",
            EXPORT_FILE_LIST,
        ]
    )
    inventory = {}
    try:
        with tempfile.TemporaryFile() as error_log:
            process = subprocess.Popen(
                command, stdout=subprocess.PIPE, stderr=error_log
            )
            try:
                with tarfile.open(fileobj=process.stdout, mode="r|") as archive:
                    for member in archive:
                        if not member.isfile():
                            if member.issym() or member.islnk():
                                raise ValueError(
                                    "profile payload cannot contain links"
                                )
                            continue
                        relative = PurePosixPath(member.name).as_posix()
                        if relative.startswith("./"):
                            relative = relative[2:]
                        if not included_by_policy(relative, policy):
                            continue
                        if (
                            relative.startswith("/")
                            or ".." in PurePosixPath(relative).parts
                        ):
                            raise ValueError("unsafe profile member")
                        source = archive.extractfile(member)
                        payload = source.read() if source else b""
                        target = destination / relative
                        target.parent.mkdir(
                            parents=True, exist_ok=True, mode=0o700
                        )
                        target.write_bytes(payload)
                        target.chmod(0o600)
                        inventory[relative] = {
                            "sha256": digest(payload),
                            "size": len(payload),
                        }
            finally:
                if process.stdout:
                    process.stdout.close()
            return_code = process.wait()
            error_log.seek(0)
            stderr = error_log.read().decode("utf-8", "replace")
    finally:
        adb_command(
            adb,
            port,
            serial,
            "shell",
            "rm -f '%s'" % EXPORT_FILE_LIST,
            check=False,
        )
    if return_code:
        raise RuntimeError("ADB profile archive failed: %s" % stderr.strip()[:400])
    for relative in direct_files:
        payload = _read_remote(
            adb, port, serial, KODI_ROOT + "/" + relative
        )
        target = destination / relative
        target.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
        target.write_bytes(payload)
        target.chmod(0o600)
        inventory[relative] = {
            "sha256": digest(payload),
            "size": len(payload),
        }
    if set(inventory) != set(selected):
        raise RuntimeError("ADB profile archive inventory was incomplete")
    return inventory


def _copy_apks(adb, port, serial, destination):
    output = adb_output(
        adb, port, serial, "shell", "pm path %s" % KODI_PACKAGE
    )
    remote_paths = [
        line.split(":", 1)[1].strip()
        for line in output.splitlines()
        if line.startswith("package:")
    ]
    if not remote_paths:
        raise RuntimeError("Kodi APK path was not found")
    result = []
    destination.mkdir(parents=True, exist_ok=True, mode=0o700)
    for index, remote in enumerate(remote_paths):
        name = "base.apk" if index == 0 else "split-%02d.apk" % index
        payload = _read_remote(adb, port, serial, remote)
        target = destination / name
        target.write_bytes(payload)
        target.chmod(0o600)
        result.append(
            {"name": name, "sha256": digest(payload), "size": len(payload)}
        )
    return result


def _addon_inventory(payload_root, state):
    result = []
    addons = payload_root / "addons"
    if not addons.exists():
        return result
    for manifest in sorted(addons.glob("*/addon.xml")):
        try:
            root = ET.fromstring(manifest.read_bytes())
        except ET.ParseError:
            # Preserve the exact file in the disaster-recovery payload, but
            # never treat a corrupt manifest as an add-on that can be safely
            # enabled after restore.
            continue
        addon_id = root.attrib["id"]
        item = state.get(addon_id, {"enabled": False, "origin": ""})
        result.append(
            {
                "id": addon_id,
                "version": root.attrib.get("version", ""),
                "enabled": item["enabled"],
                "origin": item["origin"],
            }
        )
    return result


def _payload_inventory(payload_root):
    result = {}
    for path in sorted(Path(payload_root).rglob("*")):
        if path.is_symlink():
            raise ValueError("profile payload cannot contain links")
        if path.is_file():
            payload = path.read_bytes()
            result[path.relative_to(payload_root).as_posix()] = {
                "sha256": digest(payload),
                "size": len(payload),
            }
    return result


def create_snapshot(adb, port, serial, output, policy_path, repository_root):
    output = ensure_private_output(output, repository_root)
    if output.exists():
        raise ValueError("snapshot output already exists")
    output.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
    output.parent.chmod(0o700)
    temporary = Path(
        tempfile.mkdtemp(prefix=".snapshot-", dir=str(output.parent))
    ).resolve()
    temporary.chmod(0o700)
    source_was_stopped = False
    try:
        info = device_info(adb, port, serial)
        skin = selected_skin(adb, port, serial)
        adb_command(
            adb,
            port,
            serial,
            "shell",
            "am force-stop %s" % KODI_PACKAGE,
        )
        source_was_stopped = True
        time.sleep(2)
        state = installed_state(adb, port, serial)
        policy = load_policy(policy_path)
        payload_root = temporary / "payload"
        payload_root.mkdir(mode=0o700)
        _extract_profile(adb, port, serial, payload_root, policy)
        materialize_favourite_artwork(
            payload_root / "userdata/favourites.xml",
            payload_root / "userdata/favourite-artwork",
        )
        files = _payload_inventory(payload_root)
        apks = _copy_apks(adb, port, serial, temporary / "installer")
        identity = {
            "schema": SCHEMA,
            "policy_sha256": digest(canonical_json(policy)),
            "device": info,
            "selected_skin": skin,
            "addons": _addon_inventory(payload_root, state),
            "files": files,
            "installer": {"apks": apks},
        }
        manifest = {
            **identity,
            "created_utc": datetime.now(timezone.utc).isoformat(),
            "snapshot_id": digest(canonical_json(identity)),
        }
        manifest_path = temporary / "manifest.json"
        manifest_path.write_bytes(canonical_json(manifest) + b"\n")
        manifest_path.chmod(0o600)
        secure_private_tree(temporary)
        verify_snapshot(temporary)
        temporary.rename(output)
        return manifest
    except BaseException:
        shutil.rmtree(temporary, ignore_errors=True)
        raise
    finally:
        if source_was_stopped:
            adb_command(
                adb,
                port,
                serial,
                "shell",
                "monkey -p %s -c android.intent.category.LAUNCHER 1 >/dev/null"
                % KODI_PACKAGE,
                check=False,
            )


def verify_snapshot(snapshot):
    snapshot = Path(snapshot).resolve()
    manifest = json.loads(
        (snapshot / "manifest.json").read_text(encoding="utf-8")
    )
    if manifest.get("schema") != SCHEMA:
        raise ValueError("unsupported snapshot schema")
    if contains_profile_sync_identity(manifest.get("files", {})):
        raise ValueError(
            "IDENTITY_CONTAMINATED: snapshot contains Profile Sync identity"
        )
    payload = snapshot / "payload"
    actual = {}
    for path in sorted(payload.rglob("*")):
        if path.is_symlink():
            raise ValueError("snapshot payload contains a link")
        if path.is_file():
            relative = path.relative_to(payload).as_posix()
            data = path.read_bytes()
            actual[relative] = {
                "sha256": digest(data),
                "size": len(data),
            }
    if actual != manifest["files"]:
        raise ValueError("snapshot payload inventory mismatch")
    for item in manifest["installer"]["apks"]:
        path = snapshot / "installer" / item["name"]
        data = path.read_bytes()
        if digest(data) != item["sha256"] or len(data) != item["size"]:
            raise ValueError("snapshot APK inventory mismatch")
    identity = {
        key: manifest[key]
        for key in (
            "schema",
            "policy_sha256",
            "device",
            "selected_skin",
            "addons",
            "files",
            "installer",
        )
    }
    if digest(canonical_json(identity)) != manifest["snapshot_id"]:
        raise ValueError("snapshot ID mismatch")
    return manifest


def snapshot_restore_status(snapshot, manifest=None):
    """Classify restore eligibility without changing the immutable snapshot."""
    snapshot = Path(snapshot).resolve()
    manifest = manifest or verify_snapshot(snapshot)
    files = manifest.get("files", {})
    if any(
        relative == "addons/%s" % LEGACY_WATCH_ID
        or relative.startswith("addons/%s/" % LEGACY_WATCH_ID)
        or relative == "userdata/addon_data/%s" % LEGACY_WATCH_ID
        or relative.startswith("userdata/addon_data/%s/" % LEGACY_WATCH_ID)
        for relative in files
    ) or any(
        isinstance(item, dict) and item.get("id") == LEGACY_WATCH_ID
        for item in manifest.get("addons", [])
    ):
        return "LEGACY_QUARANTINED"
    favourites = snapshot / "payload/userdata/favourites.xml"
    if favourites.is_file() and (
        "plugin://%s/" % LEGACY_WATCH_ID
        in favourites.read_text(encoding="utf-8", errors="replace")
    ):
        return "LEGACY_QUARANTINED"
    return "CURRENT"


def _selected_restore_files(manifest, relative_paths=None):
    if relative_paths is None:
        return manifest["files"]
    selected = {}
    for relative in relative_paths:
        if not isinstance(relative, str) or not relative:
            raise ValueError("restore path must be a non-empty string")
        parsed = PurePosixPath(relative)
        if (
            parsed.is_absolute()
            or ".." in parsed.parts
            or parsed.as_posix() != relative
        ):
            raise ValueError("restore path is unsafe: %s" % relative)
        if relative not in manifest["files"]:
            raise ValueError(
                "restore path is absent from verified snapshot: %s"
                % relative
            )
        selected[relative] = manifest["files"][relative]
    if not selected:
        raise ValueError("at least one restore path is required")
    return selected


def _selective_addon_requirements(manifest, selected_files):
    addon_versions = {
        item["id"]: item["version"]
        for item in manifest["addons"]
        if item.get("id") and item.get("version")
    }
    requirements = {}
    for relative in selected_files:
        parts = PurePosixPath(relative).parts
        if not parts or parts[0] != "userdata":
            raise ValueError(
                "selective restore is limited to userdata paths: %s"
                % relative
            )
        if parts[:2] == ("userdata", "addon_data"):
            if len(parts) < 4:
                raise ValueError("add-on data restore path is incomplete")
            addon_id = parts[2]
            version = addon_versions.get(addon_id)
            if version is None:
                raise ValueError(
                    "add-on data has no versioned snapshot add-on: %s"
                    % addon_id
                )
            requirements[addon_id] = version
    return requirements


def _selection_sha256(selected_files):
    return digest(canonical_json(selected_files))


def _addon_settings_metadata(source):
    root = ET.fromstring(source.read_bytes())
    values = {}
    for setting in root.findall(".//setting"):
        setting_id = setting.attrib.get("id")
        if not setting_id:
            raise ValueError("add-on settings contain an entry without an ID")
        if setting_id in values:
            raise ValueError("add-on settings contain a duplicate ID")
        values[setting_id] = setting.text or ""
    return {
        "setting_ids": sorted(values),
        "settings_sha256": digest(canonical_json(values)),
    }


def _build_restore_archive(
    snapshot,
    output,
    relative_paths=None,
    operation_id=None,
    semantic_addon_settings=False,
):
    manifest = verify_snapshot(snapshot)
    if snapshot_restore_status(snapshot, manifest) != "CURRENT":
        raise ValueError(
            "LEGACY_QUARANTINED: modernize the snapshot with the offline "
            "WatchNixtoons2 migrator before restore"
        )
    selected_files = _selected_restore_files(manifest, relative_paths)
    if operation_id is not None and not re.fullmatch(
        r"[0-9a-f]{32}", operation_id
    ):
        raise ValueError("invalid restore operation identifier")
    payload_root = Path(snapshot) / "payload"
    restore_files = {
        relative: dict(metadata)
        for relative, metadata in selected_files.items()
    }
    if semantic_addon_settings:
        for relative, metadata in restore_files.items():
            parts = PurePosixPath(relative).parts
            if (
                len(parts) == 4
                and parts[:2] == ("userdata", "addon_data")
                and parts[3] == "settings.xml"
            ):
                metadata.update(
                    _addon_settings_metadata(payload_root / relative)
                )
    restore_manifest = {
        "schema": SCHEMA,
        "snapshot_id": manifest["snapshot_id"],
        "files": restore_files,
        "selection_sha256": _selection_sha256(restore_files),
    }
    if operation_id is not None:
        restore_manifest["operation_id"] = operation_id
    with tarfile.open(output, "w", format=tarfile.PAX_FORMAT) as archive:
        payload = canonical_json(restore_manifest)
        info = tarfile.TarInfo("restore-manifest.json")
        info.size = len(payload)
        info.mode = 0o600
        info.mtime = 0
        archive.addfile(info, fileobj=io.BytesIO(payload))
        for relative in sorted(restore_files):
            source = payload_root / relative
            info = tarfile.TarInfo("payload/" + relative)
            info.size = source.stat().st_size
            info.mode = 0o600
            info.mtime = 0
            with source.open("rb") as handle:
                archive.addfile(info, handle)
    return restore_manifest
    return manifest


class AdbEventClient:
    HEADER_SIZE = 32
    PT_HELO = 0x01
    PT_BYE = 0x02
    PT_BLOB = 0x08
    PT_ACTION = 0x0A
    ACTION_EXECBUILTIN = 0x01
    MAX_PAYLOAD_SIZE = 1024 - HEADER_SIZE

    def __init__(self, adb, port, serial, source_port=None):
        self.adb = adb
        self.port = port
        self.serial = serial
        self.uid = int(time.time()) & 0xFFFFFFFF
        self.source_port = source_port or 40000 + self.uid % 20000

    def _header(self, packet_type, sequence, packet_count, payload_size):
        return (
            b"XBMC"
            + bytes((2, 0))
            + struct.pack("!H", packet_type)
            + struct.pack("!I", sequence)
            + struct.pack("!I", packet_count)
            + struct.pack("!H", payload_size)
            + struct.pack("!I", self.uid)
            + (b"\0" * 10)
        )

    def _packets(self, packet_type, payload=b""):
        chunks = [
            payload[offset : offset + self.MAX_PAYLOAD_SIZE]
            for offset in range(0, len(payload), self.MAX_PAYLOAD_SIZE)
        ] or [b""]
        for index, chunk in enumerate(chunks, start=1):
            current_type = packet_type if index == 1 else self.PT_BLOB
            yield self._header(
                current_type, index, len(chunks), len(chunk)
            ) + chunk

    def _network_host(self):
        if self.serial.startswith("[") and "]:" in self.serial:
            return self.serial[1 : self.serial.index("]:")]
        if self.serial.count(":") == 1:
            host, port = self.serial.rsplit(":", 1)
            if port.isdigit():
                return host
        return None

    def _send_from_host(self, packets):
        host = self._network_host()
        if host in (None, "127.0.0.1", "::1", "localhost"):
            raise RuntimeError(
                "ADB target has no netcat and is not a direct LAN endpoint"
            )
        family = socket.AF_INET6 if ":" in host else socket.AF_INET
        with socket.socket(family, socket.SOCK_DGRAM) as event_socket:
            for packet in packets:
                event_socket.sendto(packet, (host, 9777))

    def _builtin_packets(self, command):
        hello = (
            b"mwoDevelop Kodi profile restore\0"
            + bytes((0,))
            + struct.pack("!H", 0)
            + struct.pack("!I", 0)
            + struct.pack("!I", 0)
        )
        action = bytes((self.ACTION_EXECBUILTIN,)) + command.encode() + b"\0"
        packets = [
            packet
            for packet_type, payload in (
                (self.PT_HELO, hello),
                (self.PT_ACTION, action),
                (self.PT_BYE, b""),
            )
            for packet in self._packets(packet_type, payload)
        ]
        return packets

    def execute_builtin_from_host(self, command):
        self._send_from_host(self._builtin_packets(command))

    def execute_builtin(self, command):
        listeners = adb_output(
            self.adb,
            self.port,
            self.serial,
            "shell",
            "netstat -anu 2>/dev/null | grep ':9777'",
            timeout=10,
        )
        has_ipv4 = any(
            line.lstrip().startswith("udp ")
            for line in listeners.splitlines()
        )
        has_ipv6 = any(
            line.lstrip().startswith("udp6 ")
            for line in listeners.splitlines()
        )
        nc_family = ""
        destination = "127.0.0.1"
        if has_ipv6 and not has_ipv4:
            # Kodi's Android EventServer is exposed by netstat as an IPv6
            # wildcard socket, but it is dual-stack. Some Android toybox
            # netcat builds successfully send to ::1 yet Kodi never receives
            # those datagrams. Use the socket's IPv4-mapped loopback path,
            # which works without exposing EventServer beyond the device.
            nc_family = "-4 "
        packets = self._builtin_packets(command)
        nc_probe = adb_command(
            self.adb,
            self.port,
            self.serial,
            "shell",
            "command -v nc 2>/dev/null",
            check=False,
            text=True,
        )
        nc_path = (nc_probe.stdout or "").strip()
        if not nc_path:
            self._send_from_host(packets)
            return
        for packet in packets:
            encoded = base64.b64encode(packet).decode("ascii")
            remote = (
                "echo %s | base64 -d | "
                "nc %s-u -w 1 -p %d -q 1 %s 9777"
                % (
                    encoded,
                    nc_family,
                    self.source_port,
                    destination,
                )
            )
            adb_command(
                self.adb,
                self.port,
                self.serial,
                "shell",
                remote,
                timeout=10,
            )


class AdbJsonRpcClient:
    def __init__(self, adb, port, serial):
        self.adb = adb
        self.port = port
        self.serial = serial
        self.local_port = None
        self.request_id = 0

    def __enter__(self):
        result = adb_command(
            self.adb,
            self.port,
            self.serial,
            "forward",
            "tcp:0",
            "tcp:9090",
            text=True,
        )
        self.local_port = int(result.stdout.strip())
        return self

    def __exit__(self, _exc_type, _exc_value, _traceback):
        if self.local_port is not None:
            adb_command(
                self.adb,
                self.port,
                self.serial,
                "forward",
                "--remove",
                "tcp:%d" % self.local_port,
                check=False,
            )

    def call(self, method, params=None):
        self.request_id += 1
        request = {
            "jsonrpc": "2.0",
            "id": self.request_id,
            "method": method,
        }
        if params is not None:
            request["params"] = params
        payload = json.dumps(request, separators=(",", ":")).encode() + b"\n"
        with socket.create_connection(
            ("127.0.0.1", self.local_port), timeout=5
        ) as connection:
            connection.settimeout(10)
            connection.sendall(payload)
            response = b""
            document = None
            while document is None:
                block = connection.recv(65536)
                if not block:
                    break
                response += block
                try:
                    document = json.loads(response)
                except json.JSONDecodeError:
                    pass
        if document is None:
            raise RuntimeError("Kodi JSON-RPC returned an incomplete response")
        if "error" in document:
            raise RuntimeError(
                "Kodi JSON-RPC %s failed with code %s"
                % (method, document["error"].get("code"))
            )
        return document.get("result")


def _validate_selective_addon_versions(
    jsonrpc,
    requirements,
    allow_addon_upgrade=False,
):
    verified = {}
    for addon_id, snapshot_version in requirements.items():
        details = jsonrpc.call(
            "Addons.GetAddonDetails",
            {
                "addonid": addon_id,
                "properties": ["version", "enabled"],
            },
        )
        addon = details.get("addon", {}) if isinstance(details, dict) else {}
        installed_version = str(addon.get("version") or "")
        if not installed_version:
            raise RuntimeError(
                "selective restore target add-on is not installed: %s"
                % addon_id
            )
        if installed_version != snapshot_version:
            if not allow_addon_upgrade:
                raise ValueError(
                    "target add-on version differs from snapshot: %s"
                    % addon_id
                )
            if not _compatible_forward_addon_version(
                snapshot_version,
                installed_version,
            ):
                raise ValueError(
                    "target add-on version is not a compatible forward upgrade: %s"
                    % addon_id
                )
        verified[addon_id] = installed_version
    return verified


def _parse_addon_version(value):
    match = re.fullmatch(
        r"([0-9]+(?:\.[0-9]+)*)(?:([~+])(.+))?",
        str(value),
    )
    if match is None:
        raise ValueError("unsupported add-on version: %r" % value)
    base, separator, suffix = match.groups()
    numeric = tuple(int(part) for part in base.split("."))
    suffix_tokens = tuple(
        (0, int(token)) if token.isdigit() else (1, token.lower())
        for token in re.findall(r"[A-Za-z]+|[0-9]+", suffix or "")
    )
    return numeric, separator, suffix_tokens


def _compatible_forward_addon_version(snapshot_version, installed_version):
    source_numeric, source_separator, source_suffix = _parse_addon_version(
        snapshot_version
    )
    target_numeric, target_separator, target_suffix = _parse_addon_version(
        installed_version
    )
    if source_numeric[0] != target_numeric[0]:
        return False
    width = max(len(source_numeric), len(target_numeric))
    source_numeric += (0,) * (width - len(source_numeric))
    target_numeric += (0,) * (width - len(target_numeric))
    if target_numeric != source_numeric:
        return target_numeric > source_numeric
    if source_separator is None:
        return target_separator is None
    if target_separator is None:
        return True
    if source_separator != target_separator:
        return False
    return target_suffix >= source_suffix


def _push(adb, port, serial, source, destination):
    adb_command(adb, port, serial, "push", str(source), destination)


def _acquire_restore_lock(adb, port, serial):
    result = adb_command(
        adb,
        port,
        serial,
        "shell",
        "mkdir '%s'" % RESTORE_LOCK,
        check=False,
        text=True,
    )
    if result.returncode != 0:
        raise RuntimeError(
            "another Kodi profile restore is active or its lock is stale; "
            "use recover-lock only when aborting that operation is safe"
        )


def _release_restore_lock(adb, port, serial):
    result = adb_command(
        adb,
        port,
        serial,
        "shell",
        "rmdir '%s'" % RESTORE_LOCK,
        check=False,
        text=True,
    )
    if result.returncode != 0:
        raise RuntimeError("Kodi restore lock could not be removed")


def _cleanup_restore_staging(adb, port, serial):
    result = adb_command(
        adb,
        port,
        serial,
        "shell",
        "rm -f '%s' '%s' '%s' '%s' '%s' '%s'"
        % (
            RESTORE_ARCHIVE,
            RESTORE_SCRIPT,
            RESTORE_MARKER,
            RESTORE_STARTED,
            VERIFY_MARKER,
            VERIFY_STARTED,
        ),
        check=False,
        text=True,
    )
    if result.returncode != 0:
        raise RuntimeError(
            "Kodi restore staging cleanup failed; the device lock was retained"
        )


def recover_restore_lock(adb, port, serial):
    existing = adb_command(
        adb,
        port,
        serial,
        "shell",
        "test -d '%s'" % RESTORE_LOCK,
        check=False,
        text=True,
    )
    if existing.returncode != 0:
        return {"restore_lock_recovered": False}
    stopped = adb_command(
        adb,
        port,
        serial,
        "shell",
        "am force-stop %s" % KODI_PACKAGE,
        check=False,
        text=True,
    )
    if stopped.returncode != 0:
        raise RuntimeError(
            "Kodi could not be stopped; the restore lock was retained"
        )
    _cleanup_restore_staging(adb, port, serial)
    removed = adb_command(
        adb,
        port,
        serial,
        "shell",
        "rmdir '%s'" % RESTORE_LOCK,
        check=False,
        text=True,
    )
    if removed.returncode != 0:
        raise RuntimeError("Kodi restore lock recovery failed")
    return {"restore_lock_recovered": True}


def _quiesce_incomplete_restore(
    adb,
    port,
    serial,
    command_may_be_queued=False,
):
    incomplete = command_may_be_queued
    for started_marker, result_marker in (
        (RESTORE_STARTED, RESTORE_MARKER),
        (VERIFY_STARTED, VERIFY_MARKER),
    ):
        started = _read_marker(adb, port, serial, started_marker)
        result = _read_marker(adb, port, serial, result_marker)
        if (
            isinstance(started, dict)
            and started.get("started") is True
            and result is None
        ):
            incomplete = True
    if not incomplete:
        return
    stopped = adb_command(
        adb,
        port,
        serial,
        "shell",
        "am force-stop %s" % KODI_PACKAGE,
        check=False,
        text=True,
    )
    if stopped.returncode != 0:
        raise RuntimeError(
            "Kodi restore writer may still be active; the device lock was "
            "retained for safe manual recovery"
        )


def _read_marker(adb, port, serial, path):
    result = adb_command(
        adb,
        port,
        serial,
        "shell",
        "cat '%s'" % path,
        check=False,
        text=True,
    )
    if result.returncode == 0 and result.stdout.strip().startswith("{"):
        try:
            return json.loads(result.stdout)
        except json.JSONDecodeError:
            # The exclusive started marker is visible as soon as it is
            # created, before its small JSON payload is necessarily complete.
            return None
    return None


def _wait_for_marker(
    adb,
    port,
    serial,
    timeout=360,
    marker=RESTORE_MARKER,
):
    started = time.monotonic()
    while time.monotonic() - started < timeout:
        document = _read_marker(adb, port, serial, marker)
        if document is not None:
            return document
        time.sleep(2)
    raise TimeoutError("Kodi profile restore marker timed out")


def _wait_for_restore_delivery(
    adb,
    port,
    serial,
    operation_id,
    result_marker,
    started_marker,
    timeout,
):
    started = time.monotonic()
    while time.monotonic() - started < timeout:
        result = _read_marker(adb, port, serial, result_marker)
        if (
            result is not None
            and result.get("operation_id") == operation_id
        ):
            return "complete", result
        acknowledgement = _read_marker(
            adb,
            port,
            serial,
            started_marker,
        )
        if acknowledgement == {
            "operation_id": operation_id,
            "started": True,
        }:
            return "started", None
        time.sleep(2)
    return "missing", None


def _run_restore_script(
    adb,
    port,
    serial,
    operation_id,
    attempts=4,
    delivery_timeout=20,
    completion_timeout=360,
    mode="restore",
):
    if not re.fullmatch(r"[0-9a-f]{32}", operation_id):
        raise ValueError("invalid restore operation identifier")
    if mode not in {"restore", "verify"}:
        raise ValueError("invalid restore device-script mode")
    result_marker, started_marker = (
        (RESTORE_MARKER, RESTORE_STARTED)
        if mode == "restore"
        else (VERIFY_MARKER, VERIFY_STARTED)
    )
    command = "RunScript(%s,%s,%s,%s,%s,%s)" % (
        RESTORE_SCRIPT,
        RESTORE_ARCHIVE,
        result_marker,
        started_marker,
        operation_id,
        mode,
    )
    for attempt in range(attempts):
        try:
            AdbEventClient(adb, port, serial).execute_builtin(command)
            state, result = _wait_for_restore_delivery(
                adb,
                port,
                serial,
                operation_id,
                result_marker,
                started_marker,
                timeout=delivery_timeout,
            )
        except BaseException as exc:
            raise RestoreCommandMayBeQueued(
                "Kodi profile restore dispatch outcome is unknown"
            ) from exc
        if state == "complete":
            return result
        if state == "started":
            return _wait_for_marker(
                adb,
                port,
                serial,
                timeout=completion_timeout,
                marker=result_marker,
            )
        if attempt + 1 < attempts:
            time.sleep(2)
    raise RestoreCommandMayBeQueued(
        "Kodi profile restore command was sent but not acknowledged"
    )


def install_kodi(adb, port, serial, snapshot):
    manifest = verify_snapshot(snapshot)
    apks = [
        str(Path(snapshot) / "installer" / item["name"])
        for item in manifest["installer"]["apks"]
    ]
    command = ["install", "-r", "-g"]
    if len(apks) > 1:
        command = ["install-multiple", "-r", "-g"]
    result = adb_command(
        adb,
        port,
        serial,
        *command,
        *apks,
        text=True,
    )
    if "Success" not in result.stdout:
        raise RuntimeError("Kodi APK installation did not report success")
    _prepare_kodi_permissions(adb, port, serial)
    return manifest


def _prepare_kodi_permissions(adb, port, serial):
    commands = (
        "pm grant %s android.permission.RECORD_AUDIO" % KODI_PACKAGE,
        "appops set %s MANAGE_EXTERNAL_STORAGE allow" % KODI_PACKAGE,
    )
    for command in commands:
        adb_command(
            adb,
            port,
            serial,
            "shell",
            command,
            check=False,
            text=True,
        )


def _wait_for_kodi_ready(adb, port, serial, timeout=90):
    guisettings = KODI_ROOT + "/userdata/guisettings.xml"
    started = time.monotonic()
    while time.monotonic() - started < timeout:
        userdata = adb_command(
            adb,
            port,
            serial,
            "shell",
            "test -s '%s'" % guisettings,
            check=False,
        )
        event_server = adb_command(
            adb,
            port,
            serial,
            "shell",
            "netstat -anu 2>/dev/null | grep -q ':9777'",
            check=False,
        )
        if event_server.returncode == 0:
            if userdata.returncode == 0:
                return
            # Android scoped storage can deny the shell user access to
            # Android/data even though Kodi has completed initialization.
            # A successful in-process JSON-RPC ping proves that Kodi's
            # userdata and services are ready without weakening the check.
            try:
                with AdbJsonRpcClient(adb, port, serial) as jsonrpc:
                    if jsonrpc.call("JSONRPC.Ping") == "pong":
                        return
            except (OSError, RuntimeError, ValueError):
                pass
        time.sleep(2)
    raise TimeoutError(
        "Kodi services did not finish first-run initialization; "
        "check the device for a permission dialog"
    )


def _skin_rpc(jsonrpc, method, params=None, attempts=3):
    for attempt in range(attempts):
        try:
            return jsonrpc.call(method, params)
        except (OSError, TimeoutError):
            if attempt + 1 == attempts:
                raise
            time.sleep(1)


def _activate_skin(jsonrpc, skin_id, timeout=15):
    if skin_id != "skin.estuary":
        _skin_rpc(
            jsonrpc,
            "Settings.SetSettingValue",
            {"setting": "lookandfeel.skin", "value": "skin.estuary"},
        )
        time.sleep(1)
    _skin_rpc(
        jsonrpc,
        "Settings.SetSettingValue",
        {"setting": "lookandfeel.skin", "value": skin_id},
    )
    started = time.monotonic()
    while time.monotonic() - started < timeout:
        gui = _skin_rpc(
            jsonrpc,
            "GUI.GetProperties",
            {"properties": ["currentwindow", "currentcontrol"]},
        )
        window = gui.get("currentwindow", {})
        control = gui.get("currentcontrol", {})
        if window.get("id") == 10100:
            if control.get("label") == "No":
                _skin_rpc(jsonrpc, "Input.Left")
            _skin_rpc(jsonrpc, "Input.Select")
            break
        time.sleep(0.25)
    time.sleep(2)
    selected = _skin_rpc(
        jsonrpc,
        "Settings.GetSettingValue",
        {"setting": "lookandfeel.skin"},
    )
    if selected.get("value") != skin_id:
        raise RuntimeError("Kodi did not retain the restored skin")


def _restore_snapshot_inner(
    adb,
    port,
    serial,
    snapshot,
    device_script,
    allow_kodi_upgrade=False,
):
    manifest = verify_snapshot(snapshot)
    operation_id = secrets.token_hex(16)
    target = device_info(adb, port, serial)
    source = manifest["device"]
    if not kodi_versions_compatible(
        source["kodi_version"],
        target["kodi_version"],
        allow_upgrade=allow_kodi_upgrade,
    ):
        raise ValueError(
            "Kodi version is incompatible with snapshot: %s -> %s"
            % (source["kodi_version"], target["kodi_version"])
        )
    if not set(target["abi_list"]).intersection(source["abi_list"]):
        raise ValueError("target ABI is incompatible with snapshot")
    with tempfile.NamedTemporaryFile(suffix=".tar") as archive:
        restore_manifest = _build_restore_archive(
            snapshot,
            archive.name,
            operation_id=operation_id,
        )
        selection_sha256 = restore_manifest["selection_sha256"]
        _push(adb, port, serial, archive.name, RESTORE_ARCHIVE)
    _push(adb, port, serial, device_script, RESTORE_SCRIPT)
    _prepare_kodi_permissions(adb, port, serial)
    adb_command(
        adb,
        port,
        serial,
        "shell",
        "rm -f '%s' '%s' '%s' '%s' && "
        "monkey -p %s -c android.intent.category.LAUNCHER 1 >/dev/null"
        % (
            RESTORE_MARKER,
            RESTORE_STARTED,
            VERIFY_MARKER,
            VERIFY_STARTED,
            KODI_PACKAGE,
        ),
    )
    _wait_for_kodi_ready(adb, port, serial)
    events = AdbEventClient(adb, port, serial)
    result = _run_restore_script(adb, port, serial, operation_id)
    if (
        not result.get("ok")
        or result.get("snapshot_id") != manifest["snapshot_id"]
        or result.get("operation_id") != operation_id
        or result.get("selection_sha256") != selection_sha256
    ):
        raise RuntimeError(
            "Kodi profile restore failed: %s" % result.get("error_type")
        )
    adb_command(
        adb, port, serial, "shell", "am force-stop %s" % KODI_PACKAGE
    )
    time.sleep(2)
    adb_command(
        adb,
        port,
        serial,
        "shell",
        "monkey -p %s -c android.intent.category.LAUNCHER 1 >/dev/null"
        % KODI_PACKAGE,
    )
    _wait_for_kodi_ready(adb, port, serial)
    events.execute_builtin("UpdateLocalAddons")
    time.sleep(12)
    enabled = [
        item["id"]
        for item in manifest["addons"]
        if item["enabled"] and item["id"] != manifest["selected_skin"]
    ]
    with AdbJsonRpcClient(adb, port, serial) as jsonrpc:
        for addon_id in enabled:
            jsonrpc.call(
                "Addons.SetAddonEnabled",
                {"addonid": addon_id, "enabled": True},
            )
        jsonrpc.call(
            "Addons.SetAddonEnabled",
            {"addonid": manifest["selected_skin"], "enabled": True},
        )
        _activate_skin(jsonrpc, manifest["selected_skin"])
    events.execute_builtin("UpdateAddonRepos")
    time.sleep(15)
    return {
        "snapshot_id": manifest["snapshot_id"],
        "restored_files": result["restored_files"],
        "selected_skin": manifest["selected_skin"],
        "enabled_addons_requested": len(enabled) + 1,
    }


def restore_snapshot(
    adb,
    port,
    serial,
    snapshot,
    device_script,
    allow_kodi_upgrade=False,
):
    locked = False
    safe_to_unlock = True
    try:
        _acquire_restore_lock(adb, port, serial)
        locked = True
        return _restore_snapshot_inner(
            adb,
            port,
            serial,
            snapshot,
            device_script,
            allow_kodi_upgrade,
        )
    except BaseException as exc:
        if locked:
            try:
                _quiesce_incomplete_restore(
                    adb,
                    port,
                    serial,
                    command_may_be_queued=isinstance(
                        exc,
                        RestoreCommandMayBeQueued,
                    ),
                )
            except Exception as quiesce_error:
                safe_to_unlock = False
                raise quiesce_error from exc
        raise
    finally:
        if locked and safe_to_unlock:
            _cleanup_restore_staging(adb, port, serial)
            _release_restore_lock(adb, port, serial)


def _restore_snapshot_paths_inner(
    adb,
    port,
    serial,
    snapshot,
    device_script,
    relative_paths,
    allow_kodi_upgrade=False,
    allow_addon_upgrade=False,
):
    manifest = verify_snapshot(snapshot)
    selected_files = _selected_restore_files(manifest, relative_paths)
    addon_requirements = _selective_addon_requirements(
        manifest,
        selected_files,
    )
    operation_id = secrets.token_hex(16)
    target = device_info(adb, port, serial)
    source = manifest["device"]
    if not kodi_versions_compatible(
        source["kodi_version"],
        target["kodi_version"],
        allow_upgrade=allow_kodi_upgrade,
    ):
        raise ValueError(
            "Kodi version is incompatible with snapshot: %s -> %s"
            % (source["kodi_version"], target["kodi_version"])
        )
    if not set(target["abi_list"]).intersection(source["abi_list"]):
        raise ValueError("target ABI is incompatible with snapshot")
    with tempfile.NamedTemporaryFile(suffix=".tar") as archive:
        restore_manifest = _build_restore_archive(
            snapshot,
            archive.name,
            relative_paths=selected_files,
            operation_id=operation_id,
            semantic_addon_settings=True,
        )
        selection_sha256 = restore_manifest["selection_sha256"]
        _push(adb, port, serial, archive.name, RESTORE_ARCHIVE)
    _push(adb, port, serial, device_script, RESTORE_SCRIPT)
    _prepare_kodi_permissions(adb, port, serial)
    adb_command(
        adb,
        port,
        serial,
        "shell",
        "rm -f '%s' '%s' '%s' '%s' && "
        "monkey -p %s -c android.intent.category.LAUNCHER 1 >/dev/null"
        % (
            RESTORE_MARKER,
            RESTORE_STARTED,
            VERIFY_MARKER,
            VERIFY_STARTED,
            KODI_PACKAGE,
        ),
    )
    _wait_for_kodi_ready(adb, port, serial)
    with AdbJsonRpcClient(adb, port, serial) as jsonrpc:
        verified_addons = _validate_selective_addon_versions(
            jsonrpc,
            addon_requirements,
            allow_addon_upgrade=allow_addon_upgrade,
        )
    result = _run_restore_script(adb, port, serial, operation_id)
    if (
        not result.get("ok")
        or result.get("snapshot_id") != manifest["snapshot_id"]
        or result.get("restored_files") != len(selected_files)
        or result.get("operation_id") != operation_id
        or result.get("selection_sha256") != selection_sha256
    ):
        raise RuntimeError(
            "Kodi selective profile restore failed: %s"
            % result.get("error_type")
        )
    # Terminating the process prevents an already-running add-on service from
    # writing its stale in-memory settings over the restored file.
    adb_command(
        adb, port, serial, "shell", "am force-stop %s" % KODI_PACKAGE
    )
    time.sleep(2)
    adb_command(
        adb,
        port,
        serial,
        "shell",
        "monkey -p %s -c android.intent.category.LAUNCHER 1 >/dev/null"
        % KODI_PACKAGE,
    )
    _wait_for_kodi_ready(adb, port, serial)
    # Wait until add-on services have loaded the restored settings, then prove
    # that no stale in-memory writer reverted any selected file.
    time.sleep(5)
    with AdbJsonRpcClient(adb, port, serial) as jsonrpc:
        post_restart_addons = _validate_selective_addon_versions(
            jsonrpc,
            addon_requirements,
            allow_addon_upgrade=allow_addon_upgrade,
        )
    if post_restart_addons != verified_addons:
        raise RuntimeError(
            "target add-on version changed during selective restore"
        )
    adb_command(
        adb,
        port,
        serial,
        "shell",
        "rm -f '%s' '%s'" % (VERIFY_MARKER, VERIFY_STARTED),
    )
    verification = _run_restore_script(
        adb,
        port,
        serial,
        operation_id,
        mode="verify",
    )
    if (
        not verification.get("ok")
        or verification.get("snapshot_id") != manifest["snapshot_id"]
        or verification.get("verified_files") != len(selected_files)
        or verification.get("operation_id") != operation_id
        or verification.get("selection_sha256") != selection_sha256
    ):
        raise RuntimeError(
            "Kodi selective profile post-restart verification failed: %s"
            % verification.get("error_type")
        )
    return {
        "snapshot_id": manifest["snapshot_id"],
        "restored_files": result["restored_files"],
        "verified_files": verification["verified_files"],
        "verified_addons": len(verified_addons),
    }


def restore_snapshot_paths(
    adb,
    port,
    serial,
    snapshot,
    device_script,
    relative_paths,
    allow_kodi_upgrade=False,
    allow_addon_upgrade=False,
):
    locked = False
    safe_to_unlock = True
    try:
        _acquire_restore_lock(adb, port, serial)
        locked = True
        return _restore_snapshot_paths_inner(
            adb,
            port,
            serial,
            snapshot,
            device_script,
            relative_paths,
            allow_kodi_upgrade,
            allow_addon_upgrade,
        )
    except BaseException as exc:
        if locked:
            try:
                _quiesce_incomplete_restore(
                    adb,
                    port,
                    serial,
                    command_may_be_queued=isinstance(
                        exc,
                        RestoreCommandMayBeQueued,
                    ),
                )
            except Exception as quiesce_error:
                safe_to_unlock = False
                raise quiesce_error from exc
        raise
    finally:
        if locked and safe_to_unlock:
            _cleanup_restore_staging(adb, port, serial)
            _release_restore_lock(adb, port, serial)


def main():
    repository_root = Path(__file__).resolve().parents[1]
    default_policy = (
        repository_root / "manifests/kodi-profile-policy.json"
    )
    default_device_script = (
        repository_root / "tools/kodi_profile_restore_device.py"
    )
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--adb", default="/home/mwo/android-sdk/platform-tools/adb"
    )
    parser.add_argument("--adb-server-port", type=int, default=5038)
    parser.add_argument("--serial", default="127.0.0.1:5555")
    commands = parser.add_subparsers(dest="command", required=True)
    export = commands.add_parser("export")
    export.add_argument("--output", required=True)
    export.add_argument("--policy", default=str(default_policy))
    verify = commands.add_parser("verify")
    verify.add_argument("snapshot")
    classify = commands.add_parser("classify-identity")
    classify.add_argument("snapshot", nargs="+")
    sanitize = commands.add_parser("sanitize-identity")
    sanitize.add_argument("snapshot")
    sanitize.add_argument("--output", required=True)
    install = commands.add_parser("install-kodi")
    install.add_argument("snapshot")
    restore = commands.add_parser("restore")
    restore.add_argument("snapshot")
    restore.add_argument(
        "--allow-kodi-upgrade",
        action="store_true",
        help="allow restore to a newer Kodi release in the same major line",
    )
    restore.add_argument(
        "--device-script", default=str(default_device_script)
    )
    restore_paths = commands.add_parser("restore-path")
    restore_paths.add_argument("snapshot")
    restore_paths.add_argument(
        "--path",
        action="append",
        required=True,
        dest="paths",
        help="exact verified snapshot path to restore; may be repeated",
    )
    restore_paths.add_argument(
        "--allow-kodi-upgrade",
        action="store_true",
        help="allow restore to a newer Kodi release in the same major line",
    )
    restore_paths.add_argument(
        "--allow-addon-upgrade",
        action="store_true",
        help=(
            "allow addon_data restore to a newer installed add-on version "
            "within the same major line"
        ),
    )
    restore_paths.add_argument(
        "--device-script", default=str(default_device_script)
    )
    commands.add_parser(
        "recover-lock",
        help=(
            "abort an unfinished restore, clean its staging files, and "
            "remove its device lock"
        ),
    )
    args = parser.parse_args()
    if args.command == "export":
        result = create_snapshot(
            args.adb,
            args.adb_server_port,
            args.serial,
            args.output,
            args.policy,
            repository_root,
        )
    elif args.command == "verify":
        result = verify_snapshot(args.snapshot)
    elif args.command == "classify-identity":
        result = {
            "snapshots": [
                classify_snapshot_identity(snapshot)
                for snapshot in args.snapshot
            ]
        }
    elif args.command == "sanitize-identity":
        result = sanitize_snapshot_identity(args.snapshot, args.output)
    elif args.command == "install-kodi":
        result = install_kodi(
            args.adb,
            args.adb_server_port,
            args.serial,
            args.snapshot,
        )
    elif args.command == "restore":
        result = restore_snapshot(
            args.adb,
            args.adb_server_port,
            args.serial,
            args.snapshot,
            args.device_script,
            args.allow_kodi_upgrade,
        )
    elif args.command == "recover-lock":
        result = recover_restore_lock(
            args.adb,
            args.adb_server_port,
            args.serial,
        )
    else:
        result = restore_snapshot_paths(
            args.adb,
            args.adb_server_port,
            args.serial,
            args.snapshot,
            args.device_script,
            args.paths,
            args.allow_kodi_upgrade,
            args.allow_addon_upgrade,
        )
    if args.command == "classify-identity":
        print(json.dumps(result, indent=2, sort_keys=True))
        return
    summary = {
        key: result[key]
        for key in (
            "snapshot_id",
            "created_utc",
            "selected_skin",
            "restored_files",
            "verified_files",
            "verified_addons",
            "restore_lock_recovered",
            "enabled_addons_requested",
        )
        if key in result
    }
    if "files" in result:
        summary["files"] = len(result["files"])
        summary["bytes"] = sum(
            item["size"] for item in result["files"].values()
        )
        summary["addons"] = len(result["addons"])
    print(json.dumps(summary, indent=2, sort_keys=True))


if __name__ == "__main__":
    main()
