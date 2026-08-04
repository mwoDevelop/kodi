#!/usr/bin/env python3
"""Reconcile pinned, externally published default Kodi add-ons on Android."""

from __future__ import annotations

import argparse
import hashlib
import json
import re
import stat
import tempfile
import time
import urllib.request
from pathlib import Path, PurePosixPath
from xml.etree import ElementTree
from zipfile import ZipFile

try:
    from kodi_addon_candidate_rollout import rollout
    from kodi_profile import AdbEventClient, AdbJsonRpcClient
    from kodi_reinstall import assign_addon_origins_in_kodi
except ModuleNotFoundError:
    from tools.kodi_addon_candidate_rollout import rollout
    from tools.kodi_profile import AdbEventClient, AdbJsonRpcClient
    from tools.kodi_reinstall import assign_addon_origins_in_kodi


SAFE_ID = re.compile(r"^[A-Za-z0-9._-]+$")
SHA256 = re.compile(r"^[0-9a-f]{64}$")
KINDS = {"repository", "module", "plugin"}
LICENSES = {"GPL-2.0-only", "GPL-3.0-only", "not-declared"}


def _digest(path):
    hasher = hashlib.sha256()
    with Path(path).open("rb") as handle:
        for block in iter(lambda: handle.read(1024 * 1024), b""):
            hasher.update(block)
    return hasher.hexdigest()


def load_manifest(path):
    document = json.loads(Path(path).read_text(encoding="utf-8"))
    if set(document) != {"schema", "policy", "addons"}:
        raise ValueError("default add-on manifest has unsupported fields")
    if document["schema"] != 1 or document["policy"] != "official-external":
        raise ValueError("unsupported default add-on policy")
    addons = document["addons"]
    if not isinstance(addons, list) or not addons:
        raise ValueError("default add-on manifest is empty")
    seen = set()
    repositories = {"repository.xbmc.org"}
    for index, addon in enumerate(addons):
        required = {"id", "version", "kind", "url", "sha256", "source", "license"}
        optional = {"origin", "dependencies"}
        if not isinstance(addon, dict) or not required.issubset(addon) or not set(addon).issubset(required | optional):
            raise ValueError("invalid default add-on entry at index %s" % index)
        addon_id = addon["id"]
        if not isinstance(addon_id, str) or not SAFE_ID.fullmatch(addon_id) or addon_id in seen:
            raise ValueError("invalid or duplicate default add-on id")
        seen.add(addon_id)
        if addon["kind"] not in KINDS:
            raise ValueError("invalid default add-on kind")
        if not isinstance(addon["version"], str) or not addon["version"]:
            raise ValueError("invalid default add-on version")
        if not isinstance(addon["url"], str) or not addon["url"].startswith("https://"):
            raise ValueError("default add-on URL must use HTTPS")
        if not isinstance(addon["source"], str) or not addon["source"].startswith("https://"):
            raise ValueError("default add-on source must use HTTPS")
        if not isinstance(addon["sha256"], str) or not SHA256.fullmatch(addon["sha256"]):
            raise ValueError("invalid default add-on digest")
        if addon["license"] not in LICENSES:
            raise ValueError("unsupported default add-on license")
        dependencies = addon.get("dependencies", [])
        if not isinstance(dependencies, list) or len(dependencies) != len(set(dependencies)) or any(not isinstance(item, str) or not SAFE_ID.fullmatch(item) for item in dependencies):
            raise ValueError("invalid default add-on dependencies")
        if addon["kind"] == "repository":
            if "origin" in addon or dependencies:
                raise ValueError("repository entry cannot have origin or dependencies")
            repositories.add(addon_id)
        else:
            origin = addon.get("origin")
            if not isinstance(origin, str) or origin not in repositories:
                raise ValueError("add-on origin must be an available repository")
    return document


def validate_archive(path, addon):
    total = 0
    with ZipFile(path) as archive:
        members = archive.infolist()
        if not members or len(members) > 2000:
            raise ValueError("default add-on archive exceeds file policy")
        for member in members:
            candidate = PurePosixPath(member.filename)
            if candidate.is_absolute() or not candidate.parts or candidate.parts[0] != addon["id"] or ".." in candidate.parts:
                raise ValueError("unsafe default add-on archive path")
            if stat.S_ISLNK(member.external_attr >> 16):
                raise ValueError("default add-on archive contains a symlink")
            total += member.file_size
        if total > 32 * 1024 * 1024:
            raise ValueError("default add-on archive exceeds size policy")
        try:
            addon_xml = archive.read(addon["id"] + "/addon.xml")
        except KeyError as error:
            raise ValueError("default add-on archive lacks addon.xml") from error
    root = ElementTree.fromstring(addon_xml.decode("utf-8-sig"))
    if root.attrib.get("id") != addon["id"] or root.attrib.get("version") != addon["version"]:
        raise ValueError("default add-on archive identity differs")


def fetch_artifact(addon, cache_dir, opener=urllib.request.urlopen):
    cache_dir = Path(cache_dir)
    cache_dir.mkdir(parents=True, exist_ok=True)
    destination = cache_dir / ("%s-%s.zip" % (addon["id"], addon["version"]))
    if not destination.is_file() or _digest(destination) != addon["sha256"]:
        with opener(addon["url"], timeout=30) as response:
            final_url = (
                response.geturl()
                if hasattr(response, "geturl")
                else addon["url"]
            )
            if not str(final_url).startswith("https://"):
                raise ValueError("default add-on redirect must use HTTPS")
            payload = response.read(33 * 1024 * 1024)
        if len(payload) > 32 * 1024 * 1024:
            raise ValueError("default add-on download exceeds size policy")
        with tempfile.NamedTemporaryFile(dir=cache_dir, delete=False) as temporary:
            temporary.write(payload)
            temporary_path = Path(temporary.name)
        try:
            if _digest(temporary_path) != addon["sha256"]:
                raise ValueError("default add-on digest differs")
            temporary_path.replace(destination)
        finally:
            if temporary_path.exists():
                temporary_path.unlink()
    validate_archive(destination, addon)
    return destination


def addon_details(adb, port, serial, addon_id):
    try:
        with AdbJsonRpcClient(adb, port, serial) as rpc:
            return rpc.call(
                "Addons.GetAddonDetails",
                {"addonid": addon_id, "properties": ["version", "enabled"]},
            )["addon"]
    except RuntimeError as error:
        if "code -32602" in str(error):
            return None
        raise


def _wait_addon(adb, port, serial, addon_id, timeout=60):
    started = time.monotonic()
    while time.monotonic() - started < timeout:
        details = addon_details(adb, port, serial, addon_id)
        if details and details.get("enabled"):
            return details
        time.sleep(2)
    raise TimeoutError("Kodi dependency stayed unavailable: %s" % addon_id)


def reconcile_android(
    adb,
    port,
    serial,
    manifest,
    cache_dir,
    timeout=180,
    assign_origins=True,
):
    prepared = [(addon, fetch_artifact(addon, cache_dir)) for addon in manifest["addons"]]
    results = []
    events = AdbEventClient(adb, port, serial)
    for addon, artifact in prepared:
        for dependency in addon.get("dependencies", []):
            if addon_details(adb, port, serial, dependency) is None:
                events.execute_builtin("InstallAddon(%s)" % dependency)
                _wait_addon(adb, port, serial, dependency)
        current = addon_details(adb, port, serial, addon["id"])
        if current and str(current.get("version")) == addon["version"] and current.get("enabled"):
            results.append({"addon": addon["id"], "action": "unchanged", "version": addon["version"]})
            continue
        try:
            applied = rollout(adb, port, serial, artifact, addon["id"], addon["version"], timeout)
        except RuntimeError as error:
            if current is not None or "PermissionError at backup-installed-addon" not in str(error):
                raise
            applied = rollout(
                adb,
                port,
                serial,
                artifact,
                addon["id"],
                addon["version"],
                timeout,
                repair_orphan=True,
            )
        results.append({"addon": addon["id"], "action": "installed", "version": addon["version"], "repaired_orphan": bool(applied.get("repaired_orphan"))})
        if addon["kind"] == "repository":
            events.execute_builtin("UpdateAddonRepos")
            time.sleep(3)
    origins = {addon["id"]: addon["origin"] for addon in manifest["addons"] if "origin" in addon}
    if origins and assign_origins:
        assign_addon_origins_in_kodi(
            adb,
            port,
            {"serial": serial, "addon_origins": origins},
            Path(__file__).with_name("kodi_profile_origin_device.py"),
            timeout=timeout,
        )
    verified = {}
    for addon in manifest["addons"]:
        details = addon_details(adb, port, serial, addon["id"])
        if not details or not details.get("enabled") or str(details.get("version")) != addon["version"]:
            raise RuntimeError("default add-on verification failed: %s" % addon["id"])
        verified[addon["id"]] = addon["version"]
    return {"schema": 1, "serial": serial, "result": "pass", "addons": verified, "actions": results}


def main():
    root = Path(__file__).resolve().parents[1]
    parser = argparse.ArgumentParser()
    parser.add_argument("--manifest", default="manifests/kodi-default-addons.json")
    parser.add_argument("--cache-dir", default=".kodi-private/cache/default-addons")
    parser.add_argument("--serial", required=True)
    parser.add_argument("--adb", default="/home/mwo/android-sdk/platform-tools/adb")
    parser.add_argument("--adb-server-port", type=int, default=5038)
    parser.add_argument("--timeout", type=float, default=180)
    args = parser.parse_args()
    manifest_path = Path(args.manifest)
    if not manifest_path.is_absolute():
        manifest_path = root / manifest_path
    cache_dir = Path(args.cache_dir)
    if not cache_dir.is_absolute():
        cache_dir = root / cache_dir
    result = reconcile_android(
        args.adb,
        args.adb_server_port,
        args.serial,
        load_manifest(manifest_path),
        cache_dir,
        timeout=args.timeout,
    )
    print(json.dumps(result, indent=2, sort_keys=True))


if __name__ == "__main__":
    main()
