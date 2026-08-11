#!/usr/bin/env python3
"""Transactionally enroll and verify Profile Sync in Kodi Flatpak."""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import posixpath
import re
import secrets
import shlex
import shutil
import stat
import struct
import subprocess
import sys
import tempfile
import time
import urllib.request
import zipfile
from pathlib import Path, PurePosixPath
from xml.etree import ElementTree

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from tools.kodi_devices import (
    load_registry,
    resolve_device,
    resolve_private_endpoint,
)
from tools.kodi_inventory import load_private_references
from tools.kodi_lifecycle import lifecycle_for_device
from tools.kodi_transports import transport_for_device
from tools.profile_sync_admin import (
    sign_admin_request,
    sign_bootstrap_assignment,
)
from tools.qnap_profile_sync import (
    PRODUCTION_PORT,
    connect as connect_qnap,
    create_production_pairing,
    production_admin_request,
    production_pair_request,
)


PROFILE_SYNC_ID = "service.mwodevelop.profilesync"
REPOSITORY_ID = "repository.mwodevelop"
DEFAULT_REQUIRED_ADDONS = (
    "script.module.mwoscrapers",
    "script.mwoscrapers",
    "plugin.video.umbrella",
    "plugin.video.watchnixtoons2.mwodevelop",
)
MARKER_NAME = "flatpak-rollout-result.json"
REVISION = re.compile(r"^sha256:[0-9a-f]{64}$")
SHA256 = re.compile(r"^[0-9a-f]{64}$")
ADDON_ID = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._-]{0,127}$")
ADDON_VERSION = re.compile(r"^[A-Za-z0-9][A-Za-z0-9.~+_-]{0,63}$")


class HostEd25519:
    name = "host-cryptography"

    @staticmethod
    def public_from_seed(seed):
        from cryptography.hazmat.primitives import serialization
        from cryptography.hazmat.primitives.asymmetric.ed25519 import (
            Ed25519PrivateKey,
        )

        return Ed25519PrivateKey.from_private_bytes(seed).public_key().public_bytes(
            serialization.Encoding.Raw,
            serialization.PublicFormat.Raw,
        )


class PairingSettings:
    def __init__(self, values):
        self.values = values

    def getSetting(self, key):
        return self.values.get(key, "")


class QnapPairingClient:
    def __init__(self, session):
        self.session = session

    def pair(
        self,
        code,
        logical_device_id,
        channel,
        key_id,
        public_key,
    ):
        return production_pair_request(
            self.session,
            code,
            logical_device_id,
            channel,
            key_id,
            public_key,
        )


def _sha256(path):
    digest = hashlib.sha256()
    with Path(path).open("rb") as handle:
        for block in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def extract_addon(archive_path, expected_id, expected_sha256, output):
    archive_path = Path(archive_path).resolve()
    if (
        not SHA256.fullmatch(expected_sha256)
        or _sha256(archive_path) != expected_sha256
    ):
        raise ValueError("add-on ZIP digest differs")
    output = Path(output)
    with zipfile.ZipFile(archive_path) as archive:
        members = archive.infolist()
        if not members:
            raise ValueError("add-on ZIP is empty")
        for member in members:
            path = PurePosixPath(member.filename)
            mode = member.external_attr >> 16
            if (
                path.is_absolute()
                or ".." in path.parts
                or not path.parts
                or path.parts[0] != expected_id
                or stat.S_ISLNK(mode)
            ):
                raise ValueError("add-on ZIP has an unsafe entry")
            target = output.joinpath(*path.parts)
            if member.is_dir():
                target.mkdir(parents=True, exist_ok=True)
                continue
            target.parent.mkdir(parents=True, exist_ok=True)
            with archive.open(member) as source, target.open("wb") as destination:
                while True:
                    block = source.read(1024 * 1024)
                    if not block:
                        break
                    destination.write(block)
            target.chmod(0o644)
    root = output / expected_id
    addon_xml = root / "addon.xml"
    if not addon_xml.is_file():
        raise ValueError("add-on ZIP has no addon.xml")
    addon = ElementTree.parse(addon_xml).getroot()
    if addon.get("id") != expected_id or not addon.get("version"):
        raise ValueError("add-on ZIP identity differs")
    return root, addon.get("version")


def build_settings(path, server_url, logical_id, channel, policy):
    root = ElementTree.Element("settings", {"version": "2"})
    values = {
        "enabled": "false",
        "server_url": server_url,
        "ca_certificate": (
            "special://profile/addon_data/"
            + PROFILE_SYNC_ID
            + "/profile-sync-ca.pem"
        ),
        "logical_device_id": logical_id,
        "channel": channel,
        "startup_delay_seconds": policy["startup_delay_seconds"],
        "interval_hours": policy["interval_hours"],
        "read_only": policy["read_only"],
    }
    for key, value in values.items():
        node = ElementTree.SubElement(root, "setting", {"id": key})
        node.text = value
    ElementTree.ElementTree(root).write(
        path, encoding="utf-8", xml_declaration=True
    )
    Path(path).chmod(0o600)
    return values


def profile_sync_server_url(qnap_host, override=None):
    if override:
        return override
    return "https://%s:%s" % (qnap_host, PRODUCTION_PORT)


def required_addons(repository, overrides=None):
    if overrides:
        items = []
        for value in overrides:
            addon_id, separator, version = value.partition("=")
            if not separator:
                raise ValueError("required add-on must use ID=VERSION")
            items.append((addon_id, version))
    else:
        stable = json.loads(
            (Path(repository) / "manifests/locks/stable.json").read_text(
                encoding="utf-8"
            )
        )["components"]
        items = [
            (addon_id, stable[addon_id]["version"])
            for addon_id in DEFAULT_REQUIRED_ADDONS
        ]
    if (
        len(items) != len({addon_id for addon_id, _version in items})
        or any(
            not ADDON_ID.fullmatch(addon_id)
            or not ADDON_VERSION.fullmatch(version)
            for addon_id, version in items
        )
    ):
        raise ValueError("invalid required Flatpak add-on set")
    return dict(items)


def required_addon_artifacts(repository, addons):
    """Resolve immutable stable ZIPs used by the in-Kodi Flatpak installer."""

    repository = Path(repository)
    stable = json.loads(
        (repository / "manifests/locks/stable.json").read_text(
            encoding="utf-8"
        )
    )["components"]
    result = {}
    for addon_id, version in addons.items():
        locked = stable.get(addon_id)
        if not locked or locked.get("version") != version:
            raise ValueError(
                "required Flatpak add-on is not pinned by the stable lock"
            )
        candidates = (
            repository
            / ".kodi-private/candidates"
            / ("%s-%s-stable.zip" % (addon_id, version)),
            repository
            / "dist/stable/omega"
            / addon_id
            / ("%s-%s.zip" % (addon_id, version)),
        )
        archive = next((path for path in candidates if path.is_file()), None)
        if archive is None:
            raise ValueError(
                "required Flatpak stable artifact is missing: %s" % addon_id
            )
        digest = hashlib.sha256(archive.read_bytes()).hexdigest()
        if digest != locked.get("zip_sha256"):
            raise ValueError(
                "required Flatpak stable artifact digest differs: %s"
                % addon_id
            )
        result[addon_id] = {
            "filename": addon_id + ".zip",
            "path": archive,
            "sha256": digest,
            "version": version,
        }
    return result


def official_dependency_artifacts(repository):
    """Cache and verify the pure-Python dependency closure from Kodi Omega."""

    repository = Path(repository)
    document = json.loads(
        (repository / "manifests/kodi-official-dependencies.json").read_text(
            encoding="utf-8"
        )
    )
    dependencies = document.get("dependencies")
    if document.get("schema") != 1 or not isinstance(dependencies, dict):
        raise ValueError("invalid Kodi official dependency manifest")
    cache = repository / ".kodi-private/candidates/kodi-official"
    cache.mkdir(parents=True, exist_ok=True, mode=0o700)
    cache.chmod(0o700)
    result = {}
    for addon_id, metadata in sorted(dependencies.items()):
        if (
            not ADDON_ID.fullmatch(addon_id)
            or not isinstance(metadata, dict)
            or set(metadata) != {"sha256", "url", "version"}
            or not ADDON_VERSION.fullmatch(metadata.get("version", ""))
            or not SHA256.fullmatch(metadata.get("sha256", ""))
            or not metadata.get("url", "").startswith(
                "https://mirrors.kodi.tv/addons/omega/"
            )
        ):
            raise ValueError("invalid Kodi official dependency metadata")
        filename = "%s-%s.zip" % (addon_id, metadata["version"])
        archive = cache / filename
        if not archive.is_file():
            temporary = cache / (".%s-%s.tmp" % (filename, secrets.token_hex(8)))
            try:
                with urllib.request.urlopen(metadata["url"], timeout=60) as response:
                    payload = response.read(64 * 1024 * 1024 + 1)
                if len(payload) > 64 * 1024 * 1024:
                    raise ValueError("Kodi official dependency exceeds policy")
                temporary.write_bytes(payload)
                temporary.chmod(0o600)
                if hashlib.sha256(payload).hexdigest() != metadata["sha256"]:
                    raise ValueError("Kodi official dependency digest differs")
                os.replace(temporary, archive)
            finally:
                temporary.unlink(missing_ok=True)
        if hashlib.sha256(archive.read_bytes()).hexdigest() != metadata["sha256"]:
            raise ValueError("cached Kodi official dependency digest differs")
        result[addon_id] = {
            "filename": addon_id + ".zip",
            "path": archive,
            **metadata,
        }
    return result


def _mkdirs(sftp, path, mode=0o700):
    current = "/" if path.startswith("/") else ""
    for part in PurePosixPath(path).parts:
        if part == "/":
            continue
        current = posixpath.join(current, part)
        try:
            metadata = sftp.lstat(current)
        except OSError:
            sftp.mkdir(current, mode=mode)
            continue
        if not stat.S_ISDIR(metadata.st_mode) or stat.S_ISLNK(metadata.st_mode):
            raise RuntimeError("remote path is not a safe directory")


def _upload_tree(sftp, local, remote):
    _mkdirs(sftp, remote)
    for source in sorted(Path(local).rglob("*")):
        relative = source.relative_to(local).as_posix()
        target = posixpath.join(remote, relative)
        if source.is_symlink():
            raise ValueError("local rollout tree contains a symlink")
        if source.is_dir():
            _mkdirs(sftp, target)
        elif source.is_file():
            sftp.put(str(source), target)
            sftp.chmod(target, source.stat().st_mode & 0o777)
        else:
            raise ValueError("local rollout tree contains a special file")


def _exists(sftp, path):
    try:
        sftp.lstat(path)
        return True
    except OSError:
        return False


def _remove_tree(sftp, path):
    if not _exists(sftp, path):
        return
    metadata = sftp.lstat(path)
    if stat.S_ISLNK(metadata.st_mode) or not stat.S_ISDIR(metadata.st_mode):
        sftp.remove(path)
        return
    for child in sftp.listdir_attr(path):
        _remove_tree(sftp, posixpath.join(path, child.filename))
    sftp.rmdir(path)


def _remote_command(transport, command, timeout=30):
    result = subprocess.run(
        [*transport.base_argv(), command],
        capture_output=True,
        text=True,
        check=False,
        timeout=timeout,
        env={**os.environ, "SSH_AUTH_SOCK": ""},
    )
    if result.returncode:
        raise RuntimeError("controlled Flatpak command failed")
    return result.stdout.strip()


def _process_paths(operation):
    return {
        "kpid": "/tmp/mwo-kodi-%s.pid" % operation,
        "xpid": "/tmp/mwo-xvfb-%s.pid" % operation,
        "klog": "/tmp/mwo-kodi-%s.log" % operation,
        "xlog": "/tmp/mwo-xvfb-%s.log" % operation,
    }


def _cleanup_command(operation):
    paths = _process_paths(operation)
    return (
        "test ! -f {kpid} || {{ pid=$(cat {kpid}); "
        "case \"$pid\" in (*[!0-9]*|'') exit 1;; esac; "
        "kill -TERM -- \"-$pid\" 2>/dev/null || kill \"$pid\" 2>/dev/null || true; "
        "sleep 2; kill -KILL -- \"-$pid\" 2>/dev/null || true; }}; "
        "test ! -f {xpid} || {{ pid=$(cat {xpid}); "
        "case \"$pid\" in (*[!0-9]*|'') exit 1;; esac; "
        "kill \"$pid\" 2>/dev/null || true; }}; "
        "rm -f {kpid} {xpid} {klog} {xlog}"
    ).format(**{name: shlex.quote(path) for name, path in paths.items()})


def _event_packets(command, uid):
    if (
        not isinstance(command, str)
        or not command
        or "\0" in command
        or "\n" in command
        or "\r" in command
    ):
        raise ValueError("invalid Kodi builtin command")
    hello = (
        b"mwoDevelop Flatpak Profile Sync\0"
        + bytes((0,))
        + struct.pack("!H", 0)
        + struct.pack("!I", 0)
        + struct.pack("!I", 0)
    )
    action = bytes((0x01,)) + command.encode("utf-8") + b"\0"
    packets = []
    for packet_type, payload in ((0x01, hello), (0x0A, action), (0x02, b"")):
        if len(payload) > 992:
            raise ValueError("Kodi EventServer command exceeds one packet")
        packets.append(
            b"XBMC"
            + bytes((2, 0))
            + struct.pack("!H", packet_type)
            + struct.pack("!I", 1)
            + struct.pack("!I", 1)
            + struct.pack("!H", len(payload))
            + struct.pack("!I", uid)
            + (b"\0" * 10)
            + payload
        )
    return packets


def _stage_event_packets(sftp, stage, command):
    """Stage a bounded EventServer command for loopback delivery on the NUC.

    Sending UDP from WSL to the LAN host is not reliable when the NUC firewall
    permits Kodi EventServer only on loopback.  Keeping packet construction on
    the trusted controller and delivering the resulting bytes over the pinned
    SSH transport avoids opening a network service or uploading executable
    helper code.
    """

    uid = int(time.time()) & 0xFFFFFFFF
    paths = []
    for index, packet in enumerate(_event_packets(command, uid)):
        path = posixpath.join(stage, ".event-%s.bin" % index)
        with sftp.open(path, "wb") as handle:
            handle.write(packet)
        sftp.chmod(path, 0o600)
        paths.append(path)
    return paths


def _send_staged_event_builtin(transport, packet_paths):
    if len(packet_paths) != 3:
        raise ValueError("Kodi EventServer command requires three packets")
    command = "set -eu; command -v nc >/dev/null; " + "; ".join(
        "nc -u -w 1 127.0.0.1 9777 < %s" % shlex.quote(path)
        for path in packet_paths
    )
    _remote_command(transport, command, timeout=10)


def _event_server_ready(sftp, kodi_log, after_mtime=None):
    try:
        metadata = sftp.lstat(kodi_log)
    except OSError:
        return False
    if not stat.S_ISREG(metadata.st_mode) or stat.S_ISLNK(metadata.st_mode):
        raise RuntimeError("Flatpak Kodi log is not a regular file")
    if after_mtime is not None and metadata.st_mtime <= after_mtime:
        return False
    with sftp.open(kodi_log, "rb") as handle:
        if metadata.st_size > 128 * 1024:
            handle.seek(metadata.st_size - 128 * 1024)
        payload = handle.read(128 * 1024)
    return b"UDP: Listening on port 9777" in payload


def _connect_sftp(transport):
    import paramiko

    client = paramiko.SSHClient()
    client.load_host_keys(str(transport.known_hosts_file))
    client.set_missing_host_key_policy(paramiko.RejectPolicy())
    client.connect(
        hostname=transport.host,
        username=transport.user,
        key_filename=str(transport.identity_file),
        timeout=10,
        banner_timeout=10,
        auth_timeout=10,
        allow_agent=False,
        look_for_keys=False,
    )
    return client, client.open_sftp()


def _pair_state(
    repository,
    private_dir,
    pairing,
    settings,
    ca_certificate,
    qnap,
):
    library = repository / "profile-sync-addon/resources/lib"
    sys.path.insert(0, str(library))
    try:
        from mwoprofilesync.pairing import pair_with_code
        from mwoprofilesync.state import StateStore

        state = StateStore(private_dir)
        enrollment = pair_with_code(
            PairingSettings(
                {
                    **settings,
                    "ca_certificate": str(ca_certificate),
                }
            ),
            state,
            pairing["code"],
            client_factory=lambda *_args, **_kwargs: QnapPairingClient(qnap),
            backend_factory=HostEd25519,
        )
    finally:
        sys.path.remove(str(library))
    return state.path, enrollment


def rollout(args):
    repository = Path(__file__).resolve().parents[1]
    references = load_private_references(repository / args.references)
    registry = load_registry(repository / args.devices)
    device = resolve_private_endpoint(
        resolve_device(registry, args.device), references, required=True
    )
    if device["platform"] != "linux-flatpak":
        raise ValueError("Flatpak rollout requires a linux-flatpak device")
    transport = transport_for_device(device, references=references)
    lifecycle = lifecycle_for_device(device, transport)
    probe = lifecycle.probe_kodi()
    if probe["running"] or not probe["runtime_paths_qualified"]:
        raise RuntimeError("Flatpak Kodi must be stopped and path-qualified")
    if not REVISION.fullmatch(args.revision_id):
        raise ValueError("invalid active revision")
    expected_tags = ["home", "linux-flatpak:%s" % probe["abi"][0]]
    private_dir = repository / args.private_root / args.device
    private_dir.mkdir(parents=True, exist_ok=True, mode=0o700)
    private_dir.chmod(0o700)
    ca_certificate = (repository / args.ca_certificate).resolve()
    if not ca_certificate.is_file():
        raise ValueError("Profile Sync CA certificate is missing")
    server_url = profile_sync_server_url(
        references["QNAP_HOST"], args.server_url
    )
    state_path = private_dir / "state.json"
    bootstrap_path = private_dir / "bootstrap.json"
    receipt_path = private_dir / "installed.json"
    enrollment = None
    with tempfile.TemporaryDirectory() as temporary:
        temporary = Path(temporary)
        _profile_root, profile_version = extract_addon(
            repository / args.profile_sync_zip,
            PROFILE_SYNC_ID,
            args.profile_sync_sha256,
            temporary / "profile-sync",
        )
        _repository_root, repository_version = extract_addon(
            repository / args.repository_zip,
            REPOSITORY_ID,
            args.repository_sha256,
            temporary / "repository",
        )
        settings_path = private_dir / "settings.xml"
        settings = build_settings(
            settings_path,
            server_url,
            args.device,
            device["profile_channel"],
            {
                "startup_delay_seconds": references[
                    "KODI_PROFILE_SYNC_STARTUP_DELAY_SECONDS"
                ],
                "interval_hours": references[
                    "KODI_PROFILE_SYNC_INTERVAL_HOURS"
                ],
                "read_only": references["KODI_PROFILE_SYNC_READ_ONLY"],
            },
        )
        if state_path.exists():
            local_state = json.loads(state_path.read_text(encoding="utf-8"))
            enrollment = local_state.get("enrollment")
            if (
                not enrollment
                or enrollment.get("logical_device_id") != args.device
                or enrollment.get("channel") != device["profile_channel"]
                or sorted(enrollment.get("target_tags", [])) != expected_tags
            ):
                raise ValueError("private Flatpak enrollment identity differs")
        else:
            pairing_path = private_dir / (
                ".pairing-%s.json" % secrets.token_hex(8)
            )
            qnap = connect_qnap(repository, args.references)
            try:
                create_production_pairing(
                    qnap,
                    args.device,
                    device["profile_channel"],
                    expected_tags,
                    pairing_path,
                )
                pairing = json.loads(pairing_path.read_text(encoding="utf-8"))
                state_path, enrollment = _pair_state(
                    repository,
                    private_dir,
                    pairing,
                    settings,
                    ca_certificate,
                    qnap,
                )
            finally:
                pairing_path.unlink(missing_ok=True)
                qnap.close()
        assignment = sign_bootstrap_assignment(
            device["profile_channel"],
            enrollment["enrollment_id"],
            args.revision_id,
            expected_tags,
            "promoter-production",
            repository / args.signing_seeds,
            repository / args.key_registry,
        )
        serialized_assignment = (
            json.dumps(assignment, sort_keys=True, separators=(",", ":"))
            + "\n"
        )
        if bootstrap_path.exists():
            if (
                bootstrap_path.read_text(encoding="utf-8")
                != serialized_assignment
            ):
                raise ValueError("private Flatpak bootstrap assignment differs")
        else:
            bootstrap_path.write_text(serialized_assignment, encoding="utf-8")
            bootstrap_path.chmod(0o600)
        idempotency = "bootstrap-%s-%s" % (
            args.device,
            hashlib.sha256(
                (
                    enrollment["enrollment_id"]
                    + "\0"
                    + args.revision_id
                ).encode("utf-8")
            ).hexdigest()[:24],
        )
        admin = sign_admin_request(
            "bootstrap_active",
            assignment,
            "publish",
            idempotency,
            "publisher-production",
            repository / args.signing_seeds,
            repository / args.key_registry,
        )
        qnap = connect_qnap(repository, args.references)
        try:
            production_admin_request(
                qnap,
                "/v1/channels/%s/bootstrap-assignments"
                % device["profile_channel"],
                admin,
                idempotency,
            )
        finally:
            qnap.close()
        required = required_addons(repository, args.required_addons)
        required_artifacts = required_addon_artifacts(repository, required)
        dependency_artifacts = official_dependency_artifacts(repository)
        for addon_id, artifact in required_artifacts.items():
            _root, artifact_version = extract_addon(
                artifact["path"],
                addon_id,
                artifact["sha256"],
                temporary / "required-check" / addon_id,
            )
            if artifact_version != artifact["version"]:
                raise ValueError(
                    "required Flatpak stable artifact version differs"
                )
        for addon_id, artifact in dependency_artifacts.items():
            _root, artifact_version = extract_addon(
                artifact["path"],
                addon_id,
                artifact["sha256"],
                temporary / "dependency-check" / addon_id,
            )
            if artifact_version != artifact["version"]:
                raise ValueError("Kodi official dependency version differs")
        expected = {
            "logical_device_id": args.device,
            "profile_sync_version": profile_version,
            "repository_version": repository_version,
            "required_addons": required,
            "required_artifacts": {
                addon_id: {
                    key: value
                    for key, value in artifact.items()
                    if key != "path"
                }
                for addon_id, artifact in required_artifacts.items()
            },
            "dependency_artifacts": {
                addon_id: {
                    key: value
                    for key, value in artifact.items()
                    if key not in {"path", "url"}
                }
                for addon_id, artifact in dependency_artifacts.items()
            },
        }
        mode = "install"
        if receipt_path.exists():
            receipt = json.loads(receipt_path.read_text(encoding="utf-8"))
            if receipt == expected:
                mode = "sync"
            elif receipt != {
                key: value
                for key, value in expected.items()
                if key != "dependency_artifacts"
            }:
                raise ValueError("private Flatpak installation receipt differs")
        payload = temporary / "payload"
        payload.mkdir()
        required_payload = payload / "required"
        required_payload.mkdir()
        for artifact in required_artifacts.values():
            shutil.copy2(
                artifact["path"],
                required_payload / artifact["filename"],
            )
        dependency_payload = payload / "dependencies"
        dependency_payload.mkdir()
        for artifact in dependency_artifacts.values():
            shutil.copy2(
                artifact["path"],
                dependency_payload / artifact["filename"],
            )
        (payload / "expected.json").write_text(
            json.dumps(expected, sort_keys=True, separators=(",", ":"))
            + "\n",
            encoding="utf-8",
        )
        if mode == "install":
            profile_data = payload / "profile-data"
            profile_data.mkdir()
            shutil.copy2(settings_path, profile_data / "settings.xml")
            shutil.copy2(state_path, profile_data / "state.json")
            shutil.copy2(ca_certificate, profile_data / "profile-sync-ca.pem")
            for path in profile_data.iterdir():
                path.chmod(0o600)
            shutil.copy2(
                repository / args.profile_sync_zip,
                payload / "profile-sync.zip",
            )
            shutil.copy2(
                repository / args.repository_zip,
                payload / "repository.zip",
            )
        shutil.copy2(
            repository / "tools/kodi_flatpak_profile_sync_device.py",
            payload / "bootstrap.py",
        )
        operation = secrets.token_hex(8)
        data_root = probe["data_root"]
        stage = posixpath.join(
            data_root, "temp", ".mwodevelop-flatpak-" + operation
        )
        identity = transport.probe_identity()
        client, sftp = _connect_sftp(transport)
        result = None
        script_invoked = False
        try:
            _upload_tree(sftp, payload, stage)
            marker = posixpath.join(stage, MARKER_NAME)
            display = 90 + identity.uid % 10
            display_name = ":%s" % display
            process_paths = _process_paths(operation)
            kodi_log = posixpath.join(data_root, "temp", "kodi.log")
            try:
                previous_log_mtime = sftp.lstat(kodi_log).st_mtime
            except OSError:
                previous_log_mtime = None
            launch = (
                "set -eu; test ! -e {lock}; "
                "nohup Xvfb {display} -screen 0 1280x720x24 -nolisten tcp "
                "</dev/null >{xlog} 2>&1 & echo $! >{xpid}; sleep 1; "
                "nohup setsid env HOME={home} XDG_RUNTIME_DIR={runtime} DISPLAY={display} "
                "flatpak run {app} --standalone </dev/null >{klog} 2>&1 & "
                "echo $! >{kpid}"
            ).format(
                lock=shlex.quote("/tmp/.X%s-lock" % display),
                display=shlex.quote(display_name),
                xlog=shlex.quote(process_paths["xlog"]),
                xpid=shlex.quote(process_paths["xpid"]),
                home=shlex.quote(identity.home),
                runtime=shlex.quote("/run/user/%s" % identity.uid),
                app=shlex.quote(device["expected"]["flatpak_app_id"]),
                klog=shlex.quote(process_paths["klog"]),
                kpid=shlex.quote(process_paths["kpid"]),
            )
            _remote_command(transport, launch)
            try:
                deadline = time.monotonic() + args.timeout
                while time.monotonic() < deadline:
                    if _event_server_ready(
                        sftp, kodi_log, after_mtime=previous_log_mtime
                    ):
                        command = "RunScript(%s,%s,%s)" % (
                            posixpath.join(stage, "bootstrap.py"),
                            stage,
                            mode,
                        )
                        packet_paths = _stage_event_packets(
                            sftp, stage, command
                        )
                        _send_staged_event_builtin(transport, packet_paths)
                        script_invoked = True
                        break
                    time.sleep(2)
                result = None
                install_request = posixpath.join(
                    stage, "install-request.json"
                )
                last_confirmation = 0.0
                while time.monotonic() < deadline:
                    if _exists(sftp, marker):
                        with sftp.open(marker, "r") as handle:
                            result = json.loads(
                                handle.read().decode("utf-8")
                            )
                        break
                    if (
                        _exists(sftp, install_request)
                        and time.monotonic() - last_confirmation >= 2
                    ):
                        with sftp.open(install_request, "r") as handle:
                            request = json.loads(
                                handle.read().decode("utf-8")
                            )
                        if (
                            request.get("schema") != 1
                            or request.get("addon_id") not in required
                        ):
                            raise RuntimeError(
                                "invalid Flatpak install confirmation request"
                            )
                        confirm_packets = _stage_event_packets(
                            sftp, stage, "Action(Select)"
                        )
                        _send_staged_event_builtin(
                            transport, confirm_packets
                        )
                        last_confirmation = time.monotonic()
                    time.sleep(2)
            finally:
                _remote_command(transport, _cleanup_command(operation))
            if (
                not result
                or not result.get("ok")
                or result.get("profile_sync_version") != profile_version
                or result.get("repository_version") != repository_version
                or result.get("logical_device_id") != args.device
                or result.get("applied_revision") != args.revision_id
                or result.get("pending_report")
                or result.get("required_addons") != required
            ):
                raise RuntimeError(
                    "Flatpak in-Kodi Profile Sync verification failed: %s/%s at %s (%s)"
                    % (
                        (result or {}).get("error_type") or "timeout",
                        (result or {}).get("error_code") or "unclassified",
                        (result or {}).get("error_stage") or "unknown_stage",
                        (result or {}).get("error_origin") or "unknown_origin",
                    )
                )
            remote_profile_data = posixpath.join(
                data_root, "userdata/addon_data", PROFILE_SYNC_ID
            )
            sftp.get(
                posixpath.join(remote_profile_data, "state.json"),
                str(state_path),
            )
            state_path.chmod(0o600)
            stop_deadline = time.monotonic() + 30
            while True:
                post_probe = lifecycle.probe_kodi()
                if (
                    not post_probe["running"]
                    and post_probe["runtime_paths_qualified"]
                ):
                    break
                if time.monotonic() >= stop_deadline:
                    raise RuntimeError("Flatpak Kodi did not stop cleanly")
                time.sleep(2)
            receipt_path.write_text(
                json.dumps(expected, sort_keys=True, separators=(",", ":"))
                + "\n",
                encoding="utf-8",
            )
            receipt_path.chmod(0o600)
            favourites = posixpath.join(data_root, "userdata/favourites.xml")
            favourite_count = 0
            if _exists(sftp, favourites):
                with sftp.open(favourites, "r") as handle:
                    favourite_count = len(
                        ElementTree.fromstring(handle.read()).findall("favourite")
                    )
            _remove_tree(sftp, stage)
            return {
                "schema": 1,
                "result": "pass",
                "device": args.device,
                "platform": "linux-flatpak",
                "kodi_version": probe["kodi_version"],
                "runtime_paths_qualified": True,
                "profile_sync_version": profile_version,
                "repository_version": repository_version,
                "applied_revision": result["applied_revision"],
                "sync_status": result["sync_status"],
                "rollout_mode": mode,
                "favourites": favourite_count,
                "required_addons": result["required_addons"],
                "server_url_sha256": hashlib.sha256(
                    server_url.encode("utf-8")
                ).hexdigest(),
            }
        except BaseException:
            if result is not None or not script_invoked:
                _remove_tree(sftp, stage)
            raise
        finally:
            sftp.close()
            client.close()


def main():
    repository = Path(__file__).resolve().parents[1]
    parser = argparse.ArgumentParser()
    parser.add_argument("--device", required=True)
    parser.add_argument("--revision-id", required=True)
    parser.add_argument("--server-url")
    parser.add_argument("--references", default=".env")
    parser.add_argument("--devices", default=".kodi-private/devices.json")
    parser.add_argument(
        "--private-root", default=".kodi-private/flatpak-profile-sync"
    )
    parser.add_argument(
        "--profile-sync-zip",
        default=(
            ".kodi-private/candidates/"
            "service.mwodevelop.profilesync-1.0.2-stable.zip"
        ),
    )
    parser.add_argument("--profile-sync-sha256", required=True)
    parser.add_argument(
        "--repository-zip",
        default=".kodi-private/candidates/repository.mwodevelop-1.0.0.zip",
    )
    parser.add_argument("--repository-sha256", required=True)
    parser.add_argument(
        "--required-addon",
        dest="required_addons",
        action="append",
        help=(
            "add-on reconciled from the stable mwoDevelop repository before "
            "Profile Sync, as ID=VERSION; repeat to replace the default set"
        ),
    )
    parser.add_argument(
        "--ca-certificate",
        default=".kodi-private/profile-sync-production/tls/ca.crt",
    )
    parser.add_argument(
        "--signing-seeds",
        default=".kodi-private/profile-sync-production/signing-seeds.json",
    )
    parser.add_argument(
        "--key-registry",
        default=".kodi-private/profile-sync-production/key-registry.json",
    )
    parser.add_argument("--timeout", type=int, default=300)
    parser.add_argument("--result")
    args = parser.parse_args()
    result = rollout(args)
    payload = json.dumps(result, indent=2, sort_keys=True) + "\n"
    if args.result:
        destination = (repository / args.result).resolve()
        destination.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
        destination.write_text(payload, encoding="utf-8")
        destination.chmod(0o600)
    print(payload, end="")


if __name__ == "__main__":
    main()
