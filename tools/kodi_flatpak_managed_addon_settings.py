#!/usr/bin/env python3
"""Audit or reconcile versioned managed add-on settings on Kodi Flatpak."""

from __future__ import annotations

import argparse
import json
import posixpath
import secrets
import stat
import sys
from pathlib import Path
from types import SimpleNamespace
from xml.etree import ElementTree

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from tools.kodi_lifecycle import lifecycle_for_device
from tools.kodi_managed_addon_settings import applicable_settings, load_policy
from tools.kodi_sync_inventory import load_sync_inventory
from tools.kodi_transports import transport_for_device


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


def _read_regular(sftp, path):
    metadata = sftp.lstat(path)
    if not stat.S_ISREG(metadata.st_mode) or stat.S_ISLNK(metadata.st_mode):
        raise RuntimeError("managed add-on settings path is not a regular file")
    with sftp.open(path, "rb") as handle:
        return handle.read(), metadata


def _addon_version(payload):
    root = ElementTree.fromstring(payload)
    version = root.attrib.get("version")
    if not version:
        raise RuntimeError("managed add-on has no version")
    return version


def _settings_values(payload):
    root = ElementTree.fromstring(payload)
    result = {}
    for node in root.findall(".//setting"):
        setting_id = node.attrib.get("id")
        if setting_id:
            result[setting_id] = node.attrib.get("value", node.text or "")
    return result


def merge_settings_xml(payload, desired):
    root = ElementTree.fromstring(payload)
    nodes = {
        node.attrib.get("id"): node
        for node in root.findall(".//setting")
        if node.attrib.get("id")
    }
    for setting_id, value in sorted(desired.items()):
        node = nodes.get(setting_id)
        if node is None:
            node = ElementTree.SubElement(root, "setting", {"id": setting_id})
        if "value" in node.attrib:
            node.attrib["value"] = value
        else:
            node.text = value
    return ElementTree.tostring(
        root, encoding="utf-8", xml_declaration=True
    )


def _atomic_remote_write(sftp, path, payload, metadata):
    directory = posixpath.dirname(path)
    try:
        directory_metadata = sftp.lstat(directory)
    except FileNotFoundError:
        sftp.mkdir(directory, mode=0o700)
    else:
        if not stat.S_ISDIR(directory_metadata.st_mode) or stat.S_ISLNK(
            directory_metadata.st_mode
        ):
            raise RuntimeError(
                "managed add-on settings directory is not a real directory"
            )
    temporary = f"{path}.mwodevelop-{secrets.token_hex(6)}"
    try:
        with sftp.open(temporary, "wxb") as handle:
            handle.write(payload)
            handle.flush()
        sftp.chmod(temporary, stat.S_IMODE(metadata.st_mode))
        try:
            sftp.posix_rename(temporary, path)
        except (AttributeError, OSError):
            sftp.rename(temporary, path)
    finally:
        try:
            sftp.remove(temporary)
        except OSError:
            pass


def reconcile(repository, logical_device_id, apply=False):
    repository = Path(repository).resolve()
    inventory = load_sync_inventory(repository)
    device = inventory["devices"].get(logical_device_id)
    if device is None:
        raise ValueError("unknown managed-settings device")
    if device["platform"] != "linux-flatpak":
        raise ValueError("Flatpak managed-settings adapter requires Linux Flatpak")
    transport = transport_for_device(device, inventory["references"])
    probe = lifecycle_for_device(device, transport).probe_kodi()
    if not probe["runtime_paths_qualified"]:
        raise RuntimeError("Flatpak Kodi runtime paths are not qualified")
    if apply and probe["running"]:
        raise RuntimeError("Flatpak Kodi must be stopped before settings apply")

    data_root = probe["data_root"]
    policy = load_policy(
        repository / "manifests/kodi-managed-addon-settings.json"
    )
    client, sftp = _connect_sftp(transport)
    try:
        versions = {}
        for addon_id in policy["addons"]:
            manifest_path = posixpath.join(
                data_root, "addons", addon_id, "addon.xml"
            )
            try:
                manifest, _metadata = _read_regular(sftp, manifest_path)
            except OSError:
                continue
            versions[addon_id] = _addon_version(manifest)
        desired = applicable_settings(policy, versions, logical_device_id)
        differences = {}
        sources = {}
        for addon_id, values in desired.items():
            settings_path = posixpath.join(
                data_root,
                "userdata/addon_data",
                addon_id,
                "settings.xml",
            )
            try:
                payload, metadata = _read_regular(sftp, settings_path)
            except FileNotFoundError:
                payload = b'<?xml version="1.0" encoding="UTF-8"?><settings />'
                metadata = SimpleNamespace(st_mode=stat.S_IFREG | 0o600)
            current = _settings_values(payload)
            changed = {
                setting_id: value
                for setting_id, value in values.items()
                if current.get(setting_id) != value
            }
            if changed:
                differences[addon_id] = sorted(changed)
                sources[addon_id] = (
                    settings_path,
                    merge_settings_xml(payload, changed),
                    metadata,
                    values,
                )
        if differences and apply:
            for settings_path, payload, metadata, _values in sources.values():
                _atomic_remote_write(sftp, settings_path, payload, metadata)
            for addon_id, source in sources.items():
                settings_path, _payload, _metadata, values = source
                observed, _ = _read_regular(sftp, settings_path)
                current = _settings_values(observed)
                if any(
                    current.get(setting_id) != value
                    for setting_id, value in values.items()
                ):
                    raise RuntimeError(
                        "Flatpak managed add-on settings verification failed"
                    )
        managed_count = sum(len(values) for values in desired.values())
        return {
            "schema": 1,
            "device": logical_device_id,
            "status": (
                "UPDATED"
                if differences and apply
                else ("DRIFT" if differences else "NO_CHANGE")
            ),
            "addons": len(desired),
            "settings": managed_count,
            "changed_addons": sorted(differences),
            "changed_settings": sum(len(item) for item in differences.values()),
            "changed_setting_ids": differences,
        }
    finally:
        sftp.close()
        client.close()


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("command", choices=("audit", "apply"))
    parser.add_argument("--device", required=True)
    args = parser.parse_args()
    result = reconcile(ROOT, args.device, apply=args.command == "apply")
    print(json.dumps(result, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
