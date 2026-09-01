#!/usr/bin/env python3
"""Backup, reset and restore one identity-pinned Kodi Flatpak profile."""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import posixpath
import re
import shlex
import shutil
import stat
import sys
import tempfile
from datetime import datetime, timezone
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
from tools import build_repo
from tools.kodi_addon_runtime_compatibility import (
    assert_compatible,
    inspect_directory,
    load_policy as load_runtime_policy,
)
from tools.kodi_flatpak_profile_sync_rollout import (
    _connect_sftp,
    _exists,
    _mkdirs,
    _remove_tree,
    _remote_command,
    _upload_tree,
)
from tools.kodi_inventory import load_private_references
from tools.kodi_lifecycle import lifecycle_for_device
from tools.kodi_profile import (
    canonical_json,
    digest,
    ensure_private_output,
    included_by_policy,
    load_policy,
    secure_private_tree,
    verify_snapshot,
)
from tools.kodi_transports import ReadOnlyCommand, transport_for_device
from tools.kodi_transports import TransportError


MAX_FILES = 50_000
MAX_FILE_BYTES = 256 * 1024 * 1024
MAX_SNAPSHOT_BYTES = 2 * 1024 * 1024 * 1024
APP_ID = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._-]{0,127}$")


def _flatpak_lines(transport, scope):
    result = transport.execute_read_only(
        ReadOnlyCommand(
            (
                "flatpak",
                "list",
                "--%s" % scope,
                "--app",
                "--columns=application,arch,version",
            )
        )
    )
    return [line.split("\t") for line in result.stdout.splitlines() if line.strip()]


def _flatpak_info(transport, scope, app_id, option):
    result = transport.execute_read_only(
        ReadOnlyCommand(
            ("flatpak", "info", "--%s" % scope, option, app_id),
            allowed_returncodes=(0, 1),
        )
    )
    if result.returncode:
        return None
    value = result.stdout.strip()
    if not value or "\n" in value or "\r" in value:
        raise RuntimeError("Flatpak returned an invalid installer identity")
    return value


def _installer_probe(transport, app_id, fallback=None):
    observed = {}
    for scope in ("user", "system"):
        matches = [
            row for row in _flatpak_lines(transport, scope)
            if len(row) == 3 and row[0].strip() == app_id
        ]
        if len(matches) > 1:
            raise RuntimeError("Flatpak Kodi inventory is ambiguous")
        if matches:
            _application, architecture, version = (
                value.strip() for value in matches[0]
            )
            observed[scope] = {
                "app_id": app_id,
                "architecture": architecture,
                "origin": _flatpak_info(
                    transport, scope, app_id, "--show-origin"
                ),
                "ref": _flatpak_info(transport, scope, app_id, "--show-ref"),
                "scope": scope,
                "version": version,
            }
    if len(observed) == 1:
        installer = next(iter(observed.values()))
        ref_parts = str(installer.get("ref", "")).split("/")
        if (
            any(not value for value in installer.values())
            or not APP_ID.fullmatch(installer["origin"])
            or not re.fullmatch(
                r"[A-Za-z0-9._-]+", installer["architecture"]
            )
            or len(ref_parts) != 4
            or ref_parts[:2] != ["app", app_id]
            or ref_parts[2] != installer["architecture"]
            or not re.fullmatch(r"[A-Za-z0-9._-]+", ref_parts[3])
        ):
            raise RuntimeError("Flatpak Kodi installer identity is incomplete")
        return installer
    if observed:
        raise RuntimeError("Kodi is installed in both Flatpak scopes")
    if fallback:
        return dict(fallback)
    raise RuntimeError("Flatpak Kodi is not installed")


def _expected_data_root(identity, device):
    root = PurePosixPath(identity.home) / device["expected"]["kodi_data_root"]
    if root == PurePosixPath(identity.home) or ".." in root.parts:
        raise RuntimeError("Flatpak Kodi data root is unsafe")
    return root.as_posix()


def preflight_target(
    device_id,
    repository,
    *,
    snapshot_manifest=None,
    references_file=".env",
    devices_file=".kodi-private/devices.json",
):
    repository = Path(repository).resolve()
    references = load_private_references(repository / references_file)
    registry = load_registry(repository / devices_file)
    device = resolve_private_endpoint(
        resolve_device(registry, device_id), references, required=True
    )
    if device["platform"] != "linux-flatpak":
        raise ValueError("Flatpak restore requires a linux-flatpak device")
    transport = transport_for_device(device, references=references)
    identity = transport.probe_identity()
    expected = device["expected"]
    if identity.model != expected["model"]:
        raise RuntimeError("Linux model differs from restore inventory")
    if identity.architecture not in expected.get("abi", [identity.architecture]):
        raise RuntimeError("Linux architecture differs from restore inventory")
    fallback = None
    if snapshot_manifest:
        snapshot_device = snapshot_manifest.get("device", {})
        fallback = snapshot_manifest.get("installer", {}).get("flatpak")
        if (
            snapshot_device.get("logical_device_id") != device_id
            or snapshot_device.get("principal_uid") != identity.uid
            or snapshot_device.get("host_fingerprint") != identity.fingerprint
            or not isinstance(fallback, dict)
        ):
            raise RuntimeError("Flatpak snapshot target binding differs")
    installer = _installer_probe(
        transport, expected["flatpak_app_id"], fallback=fallback
    )
    if installer["architecture"] not in expected.get(
        "abi", [installer["architecture"]]
    ):
        raise RuntimeError("Flatpak installer architecture differs")
    data_root = _expected_data_root(identity, device)
    data_exists = False
    runtime_paths_qualified = False
    try:
        client, sftp = _connect_sftp(transport)
        try:
            if _exists(sftp, data_root):
                metadata = sftp.lstat(data_root)
                if stat.S_ISLNK(metadata.st_mode) or not stat.S_ISDIR(
                    metadata.st_mode
                ):
                    raise RuntimeError("Flatpak data root is not a safe directory")
                if metadata.st_uid != identity.uid:
                    raise RuntimeError("Flatpak data root owner differs")
                data_exists = True
        finally:
            sftp.close()
            client.close()
    except OSError as error:
        raise RuntimeError("Flatpak data root probe failed") from error
    running = transport.execute_read_only(
        ReadOnlyCommand(
            (
                "pgrep",
                "-u",
                str(identity.uid),
                "-f",
                "tv.kodi.Kodi|/kodi( |$)",
            ),
            allowed_returncodes=(0, 1),
        )
    ).returncode == 0
    if data_exists and installer:
        try:
            probe = lifecycle_for_device(device, transport).probe_kodi()
        except TransportError:
            if not snapshot_manifest:
                raise
        else:
            runtime_paths_qualified = bool(probe["runtime_paths_qualified"])
            data_root = probe["data_root"]
            running = probe["running"]
    elif not snapshot_manifest:
        raise RuntimeError("Flatpak Kodi data root does not exist")
    if running:
        raise RuntimeError("Flatpak Kodi must be stopped before restore")
    if data_exists and not runtime_paths_qualified and not snapshot_manifest:
        raise RuntimeError("Flatpak Kodi runtime paths are not qualified")
    return {
        "device": device,
        "device_id": device_id,
        "transport": transport,
        "identity": identity,
        "model": identity.model,
        "host_fingerprint": identity.fingerprint,
        "principal_uid": identity.uid,
        "data_root": data_root,
        "data_exists": data_exists,
        "runtime_paths_qualified": runtime_paths_qualified,
        "installed_version": installer["version"],
        "expected_version": installer["version"],
        "installer": installer,
    }


def _remote_files(sftp, root):
    result = []

    def visit(directory, relative=""):
        for item in sftp.listdir_attr(directory):
            if (
                item.filename in {".", ".."}
                or "/" in item.filename
                or "\x00" in item.filename
            ):
                raise RuntimeError("Flatpak profile contains an unsafe path")
            child_relative = posixpath.join(relative, item.filename)
            child = posixpath.join(directory, item.filename)
            if stat.S_ISLNK(item.st_mode):
                raise RuntimeError("Flatpak profile contains a symbolic link")
            if stat.S_ISDIR(item.st_mode):
                visit(child, child_relative)
            elif stat.S_ISREG(item.st_mode):
                result.append((child_relative, child, item.st_size))
            else:
                raise RuntimeError("Flatpak profile contains a special file")
            if len(result) > MAX_FILES:
                raise RuntimeError("Flatpak profile exceeds file-count limit")

    visit(root)
    return result


def _copy_remote_profile(sftp, data_root, payload, policy):
    inventory = {}
    total = 0
    selected = [
        item for item in _remote_files(sftp, data_root)
        if included_by_policy(item[0], policy)
    ]
    if not selected:
        raise RuntimeError("Flatpak profile policy selected no files")
    for relative, remote, size in selected:
        if size < 0 or size > MAX_FILE_BYTES or total + size > MAX_SNAPSHOT_BYTES:
            raise RuntimeError("Flatpak profile exceeds snapshot size policy")
        destination = payload.joinpath(*PurePosixPath(relative).parts)
        destination.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
        sftp.get(remote, str(destination))
        destination.chmod(0o600)
        content = destination.read_bytes()
        if len(content) != size:
            raise RuntimeError("Flatpak profile changed during backup")
        inventory[relative] = {
            "sha256": hashlib.sha256(content).hexdigest(),
            "size": len(content),
        }
        total += len(content)
    return inventory


def _selected_skin(payload):
    path = payload / "userdata/guisettings.xml"
    if not path.is_file():
        return "skin.estuary"
    root = ElementTree.fromstring(path.read_bytes())
    for setting in root.findall(".//setting"):
        if setting.attrib.get("id") == "lookandfeel.skin":
            return setting.text or "skin.estuary"
    return "skin.estuary"


def _addon_inventory(payload):
    result = []
    for manifest in sorted((payload / "addons").glob("*/addon.xml")):
        root = ElementTree.fromstring(manifest.read_bytes())
        addon_id = root.attrib.get("id")
        if addon_id:
            result.append(
                {
                    "id": addon_id,
                    "version": root.attrib.get("version", ""),
                    "enabled": True,
                    "origin": "snapshot-flatpak",
                }
            )
    return result


def create_snapshot(target, output, policy_path, repository):
    repository = Path(repository).resolve()
    output = ensure_private_output(output, repository)
    if output.exists() or output.is_symlink():
        raise ValueError("snapshot output already exists")
    output.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
    output.parent.chmod(0o700)
    temporary = Path(
        tempfile.mkdtemp(prefix=".flatpak-snapshot-", dir=str(output.parent))
    )
    try:
        policy = load_policy(policy_path)
        payload = temporary / "payload"
        payload.mkdir(mode=0o700)
        client, sftp = _connect_sftp(target["transport"])
        try:
            files = _copy_remote_profile(
                sftp, target["data_root"], payload, policy
            )
        finally:
            sftp.close()
            client.close()
        identity = {
            "schema": 1,
            "policy_sha256": digest(canonical_json(policy)),
            "device": {
                "logical_device_id": target["device_id"],
                "platform": "linux-flatpak",
                "model": target["model"],
                "host_fingerprint": target["host_fingerprint"],
                "principal_uid": target["principal_uid"],
                "kodi_version": target["installed_version"],
            },
            "selected_skin": _selected_skin(payload),
            "addons": _addon_inventory(payload),
            "files": files,
            "installer": {"flatpak": target["installer"]},
        }
        manifest = {
            **identity,
            "created_utc": datetime.now(timezone.utc).isoformat(),
            "snapshot_id": digest(canonical_json(identity)),
        }
        (temporary / "manifest.json").write_bytes(
            canonical_json(manifest) + b"\n"
        )
        secure_private_tree(temporary)
        verify_snapshot(temporary)
        temporary.rename(output)
        return manifest
    except BaseException:
        shutil.rmtree(temporary, ignore_errors=True)
        raise


def reset_profile(target, snapshot_manifest, private_root):
    refreshed = preflight_target(
        target["device_id"],
        Path(__file__).resolve().parents[1],
        snapshot_manifest=snapshot_manifest,
    )
    for key in ("host_fingerprint", "principal_uid", "data_root"):
        if refreshed[key] != target[key]:
            raise RuntimeError("Flatpak restore target identity changed")
    installer = snapshot_manifest["installer"]["flatpak"]
    transport = refreshed["transport"]
    if installer["scope"] == "user":
        _remote_command(
            transport,
            "flatpak uninstall --user --delete-data --noninteractive -y -- %s"
            % shlex.quote(installer["app_id"]),
            timeout=300,
        )
        binary_action = "UNINSTALLED_USER_FLATPAK"
    else:
        client, sftp = _connect_sftp(transport)
        try:
            _remove_tree(sftp, refreshed["data_root"])
        finally:
            sftp.close()
            client.close()
        binary_action = "PRESERVED_SHARED_SYSTEM_FLATPAK"
    receipt = Path(private_root) / target["device_id"] / "installed.json"
    if receipt.exists():
        if receipt.is_symlink() or not receipt.is_file():
            raise RuntimeError("Flatpak private receipt is unsafe")
        receipt.unlink()
    return {"binary_action": binary_action}


def install_binary(target, snapshot_manifest):
    installer = snapshot_manifest["installer"]["flatpak"]
    transport = target["transport"]
    if installer["scope"] == "user":
        branch = installer["ref"].rsplit("/", 1)[-1]
        if not branch or not APP_ID.fullmatch(installer["app_id"]):
            raise RuntimeError("Flatpak restore ref is invalid")
        _remote_command(
            transport,
            "flatpak install --user --noninteractive -y -- %s %s"
            % (
                shlex.quote(installer["origin"]),
                shlex.quote(installer["app_id"] + "//" + branch),
            ),
            timeout=600,
        )
        action = "INSTALLED_USER_FLATPAK"
    else:
        action = "VERIFIED_SHARED_SYSTEM_FLATPAK"
    client, sftp = _connect_sftp(transport)
    try:
        _mkdirs(sftp, target["data_root"], mode=0o700)
    finally:
        sftp.close()
        client.close()
    compatibility = audit_snapshot_runtime(
        target,
        snapshot_manifest,
        Path(__file__).resolve().parents[1],
    )
    return {"binary_action": action, "compatibility": compatibility}


def audit_snapshot_runtime(target, manifest, repository):
    repository = Path(repository).resolve()
    snapshot = target.get("operation_backup")
    if snapshot is None:
        raise RuntimeError("Flatpak compatibility audit requires snapshot path")
    snapshot = Path(snapshot)
    addon_root = snapshot / "payload/addons"
    descriptors = []
    if addon_root.exists():
        if addon_root.is_symlink() or not addon_root.is_dir():
            raise RuntimeError("Flatpak snapshot add-on root is unsafe")
        for addon in sorted(addon_root.iterdir()):
            if not addon.is_dir():
                raise RuntimeError(
                    "Flatpak snapshot add-on root contains a non-directory"
                )
            descriptors.append(inspect_directory(addon))
    if {item["id"] for item in descriptors} != {
        item["id"] for item in manifest["addons"]
    }:
        raise RuntimeError("Flatpak snapshot add-on inventory differs")
    installer = _installer_probe(
        target["transport"], manifest["installer"]["flatpak"]["app_id"]
    )
    planned = {
        **build_repo.load_build_targets()["external_addons"],
        **{item["id"]: item["version"] for item in descriptors},
    }
    report = assert_compatible(
        descriptors,
        {
            "platform": "linux-flatpak",
            "kodi_version": installer["version"],
            "abis": [installer["architecture"]],
            "installed_addons": {},
        },
        load_runtime_policy(
            repository / "manifests/kodi-addon-runtime-compatibility.json"
        ),
        planned_versions=planned,
    )
    return {
        "status": report["status"],
        "addons": len(descriptors),
        "policy_sha256": report["policy_sha256"],
        "graph_sha256": report["graph_sha256"],
    }


def restore_snapshot(target, snapshot):
    manifest = verify_snapshot(snapshot)
    expected = manifest["device"]
    if (
        expected.get("logical_device_id") != target["device_id"]
        or expected.get("host_fingerprint") != target["host_fingerprint"]
        or expected.get("principal_uid") != target["principal_uid"]
    ):
        raise RuntimeError("Flatpak restore snapshot target differs")
    target["operation_backup"] = Path(snapshot)
    compatibility = audit_snapshot_runtime(
        target, manifest, Path(__file__).resolve().parents[1]
    )
    client, sftp = _connect_sftp(target["transport"])
    try:
        _mkdirs(sftp, target["data_root"], mode=0o700)
        _upload_tree(sftp, Path(snapshot) / "payload", target["data_root"])
    finally:
        sftp.close()
        client.close()
    return {
        "snapshot_id": manifest["snapshot_id"],
        "restored_files": len(manifest["files"]),
        "compatibility": compatibility,
    }


def verify_remote_snapshot(target, snapshot):
    manifest = verify_snapshot(snapshot)
    observed = {}
    client, sftp = _connect_sftp(target["transport"])
    try:
        for relative, expected in manifest["files"].items():
            remote = posixpath.join(target["data_root"], relative)
            metadata = sftp.lstat(remote)
            if stat.S_ISLNK(metadata.st_mode) or not stat.S_ISREG(
                metadata.st_mode
            ):
                raise RuntimeError("restored Flatpak path is not a regular file")
            with sftp.open(remote, "rb") as handle:
                checksum = hashlib.sha256()
                size = 0
                while True:
                    block = handle.read(1024 * 1024)
                    if not block:
                        break
                    checksum.update(block)
                    size += len(block)
            observed[relative] = {
                "sha256": checksum.hexdigest(),
                "size": size,
            }
    finally:
        sftp.close()
        client.close()
    if observed != manifest["files"]:
        raise RuntimeError("restored Flatpak profile inventory differs")
    return {
        "snapshot_id": manifest["snapshot_id"],
        "restored_files": len(observed),
    }


def main():
    repository = Path(__file__).resolve().parents[1]
    parser = argparse.ArgumentParser()
    parser.add_argument("--device", required=True)
    parser.add_argument("--snapshot")
    args = parser.parse_args()
    manifest = verify_snapshot(args.snapshot) if args.snapshot else None
    target = preflight_target(
        args.device, repository, snapshot_manifest=manifest
    )
    print(
        json.dumps(
            {
                "device": target["device_id"],
                "model": target["model"],
                "principal_uid": target["principal_uid"],
                "runtime_paths_qualified": target["runtime_paths_qualified"],
                "data_exists": target["data_exists"],
                "flatpak_scope": target["installer"]["scope"],
                "kodi_version": target["installed_version"],
            },
            indent=2,
            sort_keys=True,
        )
    )


if __name__ == "__main__":
    main()
