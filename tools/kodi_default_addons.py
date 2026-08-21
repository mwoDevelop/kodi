#!/usr/bin/env python3
"""Reconcile externally published default Kodi add-ons on Android."""

from __future__ import annotations

import argparse
import hashlib
import json
import re
import stat
import subprocess
import tempfile
import time
import urllib.request
from pathlib import Path, PurePosixPath
from xml.etree import ElementTree
from zipfile import ZipFile

try:
    from kodi_addon_candidate_rollout import rollout
    from kodi_addon_remove import remove_addon
    from kodi_profile import AdbEventClient, AdbJsonRpcClient, adb_command
    from kodi_reinstall import (
        assign_addon_origins_in_kodi,
        installed_addon_origins_in_kodi,
    )
except ModuleNotFoundError:
    from tools.kodi_addon_candidate_rollout import rollout
    from tools.kodi_addon_remove import remove_addon
    from tools.kodi_profile import AdbEventClient, AdbJsonRpcClient, adb_command
    from tools.kodi_reinstall import (
        assign_addon_origins_in_kodi,
        installed_addon_origins_in_kodi,
    )


SAFE_ID = re.compile(r"^[A-Za-z0-9._-]+$")
SAFE_ABI = re.compile(r"^[A-Za-z0-9._-]+$")
SHA256 = re.compile(r"^[0-9a-f]{64}$")
KINDS = {"repository", "module", "plugin", "subtitle"}
LICENSES = {"GPL-2.0-only", "GPL-3.0-only", "not-declared"}
INSTALL_MODES = {"managed-pinned-zip", "kodi-native-official"}
DEPENDENCY_TYPES = {"python", "platform"}
OFFICIAL_PREFIX = "https://mirrors.kodi.tv/addons/omega/"
REMOTE_ADDONS = "/sdcard/Android/data/org.xbmc.kodi/files/.kodi/addons"
YES_NO_DIALOG_ID = 10100


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
        optional = {
            "origin",
            "dependencies",
            "dependency_requirements",
            "install_mode",
        }
        if (
            not isinstance(addon, dict)
            or not required.issubset(addon)
            or not set(addon).issubset(required | optional)
        ):
            raise ValueError("invalid default add-on entry at index %s" % index)
        addon_id = addon["id"]
        if (
            not isinstance(addon_id, str)
            or not SAFE_ID.fullmatch(addon_id)
            or addon_id in seen
        ):
            raise ValueError("invalid or duplicate default add-on id")
        seen.add(addon_id)
        if addon["kind"] not in KINDS:
            raise ValueError("invalid default add-on kind")
        if not isinstance(addon["version"], str) or not addon["version"]:
            raise ValueError("invalid default add-on version")
        if not isinstance(addon["url"], str) or not addon["url"].startswith("https://"):
            raise ValueError("default add-on URL must use HTTPS")
        if not isinstance(addon["source"], str) or not addon["source"].startswith(
            "https://"
        ):
            raise ValueError("default add-on source must use HTTPS")
        if not isinstance(addon["sha256"], str) or not SHA256.fullmatch(
            addon["sha256"]
        ):
            raise ValueError("invalid default add-on digest")
        if addon["license"] not in LICENSES:
            raise ValueError("unsupported default add-on license")
        dependencies = addon.get("dependencies", [])
        if (
            not isinstance(dependencies, list)
            or len(dependencies) != len(set(dependencies))
            or any(
                not isinstance(item, str) or not SAFE_ID.fullmatch(item)
                for item in dependencies
            )
        ):
            raise ValueError("invalid default add-on dependencies")
        install_mode = addon.get("install_mode", "managed-pinned-zip")
        if install_mode not in INSTALL_MODES:
            raise ValueError("invalid default add-on install mode")
        requirements = addon.get("dependency_requirements", {})
        if not isinstance(requirements, dict) or set(requirements) != set(dependencies):
            if requirements:
                raise ValueError("dependency requirements differ from dependencies")
        for dependency_id, requirement in requirements.items():
            if (
                not SAFE_ID.fullmatch(dependency_id)
                or not isinstance(requirement, dict)
                or not {"minimum_version", "type"}.issubset(requirement)
                or not set(requirement).issubset(
                    {"minimum_version", "type", "supported_android_abis"}
                )
                or not isinstance(requirement["minimum_version"], str)
                or not requirement["minimum_version"]
                or len(requirement["minimum_version"]) > 64
                or requirement["type"] not in DEPENDENCY_TYPES
            ):
                raise ValueError("invalid default add-on dependency requirement")
            supported_abis = requirement.get("supported_android_abis")
            if supported_abis is not None and (
                requirement["type"] != "platform"
                or not isinstance(supported_abis, list)
                or not supported_abis
                or len(supported_abis) != len(set(supported_abis))
                or any(
                    not isinstance(abi, str) or not SAFE_ABI.fullmatch(abi)
                    for abi in supported_abis
                )
            ):
                raise ValueError("invalid supported Android ABI policy")
        if addon["kind"] == "repository":
            if (
                "origin" in addon
                or dependencies
                or requirements
                or install_mode != "managed-pinned-zip"
            ):
                raise ValueError("repository entry cannot have origin or dependencies")
            repositories.add(addon_id)
        else:
            origin = addon.get("origin")
            if not isinstance(origin, str) or origin not in repositories:
                raise ValueError("add-on origin must be an available repository")
            if (
                install_mode == "kodi-native-official"
                and origin != "repository.xbmc.org"
            ):
                raise ValueError("native official add-on must use Kodi origin")
    return document


def _version_tuple(value):
    """Return the numeric release prefix used by Kodi dependency constraints."""

    if not isinstance(value, str) or not value or len(value) > 128:
        raise ValueError("invalid Kodi add-on version")
    match = re.match(r"^(\d+(?:\.\d+)*)", value)
    if not match:
        raise ValueError("unsupported Kodi add-on version")
    return tuple(int(part) for part in match.group(1).split("."))


def version_at_least(actual, minimum):
    actual_parts = _version_tuple(actual)
    minimum_parts = _version_tuple(minimum)
    width = max(len(actual_parts), len(minimum_parts))
    return actual_parts + (0,) * (width - len(actual_parts)) >= (
        minimum_parts + (0,) * (width - len(minimum_parts))
    )


def load_official_dependencies(path):
    document = json.loads(Path(path).read_text(encoding="utf-8"))
    dependencies = document.get("dependencies")
    if document.get("schema") != 1 or not isinstance(dependencies, dict):
        raise ValueError("invalid Kodi official dependency manifest")
    result = []
    for addon_id, metadata in sorted(dependencies.items()):
        if (
            not SAFE_ID.fullmatch(str(addon_id))
            or not isinstance(metadata, dict)
            or set(metadata) != {"sha256", "url", "version"}
            or not isinstance(metadata["version"], str)
            or not metadata["version"]
            or not isinstance(metadata["sha256"], str)
            or not SHA256.fullmatch(metadata["sha256"])
            or not isinstance(metadata["url"], str)
            or not metadata["url"].startswith(OFFICIAL_PREFIX)
        ):
            raise ValueError("invalid Kodi official dependency metadata")
        result.append({"id": addon_id, **metadata})
    if not result:
        raise ValueError("Kodi official dependency manifest is empty")
    return result


def validate_archive(path, addon):
    total = 0
    with ZipFile(path) as archive:
        members = archive.infolist()
        if not members or len(members) > 2000:
            raise ValueError("default add-on archive exceeds file policy")
        for member in members:
            candidate = PurePosixPath(member.filename)
            if (
                candidate.is_absolute()
                or not candidate.parts
                or candidate.parts[0] != addon["id"]
                or ".." in candidate.parts
            ):
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
    if (
        root.attrib.get("id") != addon["id"]
        or root.attrib.get("version") != addon["version"]
    ):
        raise ValueError("default add-on archive identity differs")


def fetch_artifact(addon, cache_dir, opener=urllib.request.urlopen):
    cache_dir = Path(cache_dir)
    cache_dir.mkdir(parents=True, exist_ok=True)
    destination = cache_dir / ("%s-%s.zip" % (addon["id"], addon["version"]))
    if not destination.is_file() or _digest(destination) != addon["sha256"]:
        with opener(addon["url"], timeout=30) as response:
            final_url = (
                response.geturl() if hasattr(response, "geturl") else addon["url"]
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


def installed_archive_matches(adb, port, serial, archive, addon_id):
    """Verify every immutable ZIP member without trusting Kodi's version DB."""

    with tempfile.TemporaryDirectory(prefix="kodi-addon-audit-") as temporary:
        destination = Path(temporary) / addon_id
        result = adb_command(
            adb,
            port,
            serial,
            "pull",
            REMOTE_ADDONS + "/" + addon_id,
            str(destination),
            check=False,
            text=True,
            timeout=90,
        )
        if result.returncode or not destination.is_dir():
            return False
        with ZipFile(archive) as zipped:
            for member in zipped.infolist():
                if member.is_dir():
                    continue
                relative = PurePosixPath(member.filename)
                if not relative.parts or relative.parts[0] != addon_id:
                    return False
                installed = destination.joinpath(*relative.parts[1:])
                if (
                    installed.is_symlink()
                    or not installed.is_file()
                    or installed.stat().st_size != member.file_size
                    or _digest(installed)
                    != hashlib.sha256(zipped.read(member)).hexdigest()
                ):
                    return False
    return True


def reconcile_official_dependencies(
    adb,
    port,
    serial,
    dependencies,
    cache_dir,
    timeout,
):
    actions = []
    for dependency in dependencies:
        artifact = fetch_artifact(dependency, cache_dir)
        current = addon_details(adb, port, serial, dependency["id"])
        intact = bool(
            current
            and current.get("enabled")
            and str(current.get("version")) == dependency["version"]
            and installed_archive_matches(
                adb,
                port,
                serial,
                artifact,
                dependency["id"],
            )
        )
        if intact:
            actions.append(
                {
                    "addon": dependency["id"],
                    "action": "unchanged",
                    "version": dependency["version"],
                }
            )
            continue
        rollout(
            adb,
            port,
            serial,
            artifact,
            dependency["id"],
            dependency["version"],
            timeout,
        )
        actions.append(
            {
                "addon": dependency["id"],
                "action": "repaired" if current else "installed",
                "version": dependency["version"],
            }
        )
    return actions


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


def android_package_abi(adb, port, serial):
    result = adb_command(
        adb,
        port,
        serial,
        "shell",
        "dumpsys package org.xbmc.kodi",
        text=True,
        timeout=30,
    )
    for line in (result.stdout or "").splitlines():
        key, separator, value = line.strip().partition("=")
        if key == "primaryCpuAbi" and separator and SAFE_ABI.fullmatch(value):
            return value
    raise RuntimeError("Kodi Android package ABI could not be determined")


def _wait_addon(adb, port, serial, addon_id, timeout=60):
    started = time.monotonic()
    while time.monotonic() - started < timeout:
        details = addon_details(adb, port, serial, addon_id)
        if details and details.get("enabled"):
            return details
        time.sleep(2)
    raise TimeoutError("Kodi dependency stayed unavailable: %s" % addon_id)


def _wait_addon_version(adb, port, serial, addon_id, minimum_version, timeout=60):
    started = time.monotonic()
    last = None
    while time.monotonic() - started < timeout:
        last = addon_details(adb, port, serial, addon_id)
        if (
            last
            and last.get("enabled")
            and version_at_least(str(last.get("version")), minimum_version)
        ):
            return last
        time.sleep(2)
    raise TimeoutError(
        "Kodi add-on stayed below required version: %s (observed %s)"
        % (addon_id, (last or {}).get("version", "absent"))
    )


def install_official_addon(
    adb, port, serial, addon_id, minimum_version=None, timeout=180
):
    if not SAFE_ID.fullmatch(addon_id):
        raise ValueError("unsafe official add-on identifier")
    properties = {"properties": ["currentwindow", "currentcontrol"]}
    with AdbJsonRpcClient(adb, port, serial) as rpc:
        before = rpc.call("GUI.GetProperties", properties)
    if before.get("currentwindow", {}).get("id") == YES_NO_DIALOG_ID:
        raise RuntimeError(
            "Kodi already has a confirmation dialog before add-on install"
        )

    existing = addon_details(adb, port, serial, addon_id)
    if existing and not existing.get("enabled"):
        with AdbJsonRpcClient(adb, port, serial) as rpc:
            rpc.call(
                "Addons.SetAddonEnabled",
                {"addonid": addon_id, "enabled": True},
            )
    events = AdbEventClient(adb, port, serial)
    events.execute_builtin("UpdateAddonRepos")
    time.sleep(3)
    events.execute_builtin("InstallAddon(%s)" % addon_id)
    started = time.monotonic()
    while time.monotonic() - started < timeout:
        try:
            details = addon_details(adb, port, serial, addon_id)
        except (OSError, RuntimeError, TimeoutError, subprocess.SubprocessError):
            time.sleep(1)
            continue
        if details and details.get("enabled") and (
            minimum_version is None
            or version_at_least(str(details.get("version")), minimum_version)
        ):
            return "completed"
        try:
            with AdbJsonRpcClient(adb, port, serial) as rpc:
                current = rpc.call("GUI.GetProperties", properties)
                if current.get("currentwindow", {}).get("id") == YES_NO_DIALOG_ID:
                    # Kodi's safe default is the right-hand No button. Moving left
                    # is idempotent when Yes is already focused, then Select
                    # confirms the install requested immediately above.
                    rpc.call("Input.Left")
                    rpc.call("Input.Select")
                    return "accepted"
        except (OSError, RuntimeError, TimeoutError, subprocess.SubprocessError):
            pass
        time.sleep(1)
    raise TimeoutError("Kodi official add-on confirmation did not appear")


def reconcile_android(
    adb,
    port,
    serial,
    manifest,
    cache_dir,
    timeout=180,
    assign_origins=True,
    official_dependencies=None,
):
    dependency_actions = (
        reconcile_official_dependencies(
            adb,
            port,
            serial,
            official_dependencies,
            cache_dir,
            timeout,
        )
        if official_dependencies
        else []
    )
    prepared = [
        (addon, fetch_artifact(addon, cache_dir)) for addon in manifest["addons"]
    ]
    results = []
    events = AdbEventClient(adb, port, serial)
    for addon, artifact in prepared:
        requirements = addon.get("dependency_requirements", {})
        for dependency in addon.get("dependencies", []):
            details = addon_details(adb, port, serial, dependency)
            requirement = requirements.get(dependency, {})
            minimum = requirement.get("minimum_version")
            if details is None or (
                minimum and not version_at_least(str(details.get("version")), minimum)
            ):
                if details is not None:
                    origin = installed_addon_origins_in_kodi(
                        adb,
                        port,
                        serial,
                        [dependency],
                        Path(__file__).with_name("kodi_profile_origin_device.py"),
                        timeout=timeout,
                    ).get(dependency)
                    if origin != "repository.xbmc.org":
                        raise RuntimeError(
                            "official dependency origin differs: %s" % dependency
                        )
                supported_abis = requirement.get("supported_android_abis")
                if supported_abis:
                    package_abi = android_package_abi(adb, port, serial)
                    if package_abi not in supported_abis:
                        raise RuntimeError(
                            "Kodi package ABI %s cannot load %s; supported ABIs: %s"
                            % (
                                package_abi,
                                dependency,
                                ",".join(supported_abis),
                            )
                        )
                install_official_addon(
                    adb,
                    port,
                    serial,
                    dependency,
                    minimum_version=minimum,
                    timeout=timeout,
                )
                if minimum:
                    _wait_addon_version(adb, port, serial, dependency, minimum, timeout)
                else:
                    _wait_addon(adb, port, serial, dependency, timeout)
        current = addon_details(adb, port, serial, addon["id"])
        install_mode = addon.get("install_mode", "managed-pinned-zip")
        current_is_candidate = (
            current
            and str(current.get("version")) == addon["version"]
            and current.get("enabled")
        )
        if current_is_candidate and install_mode == "kodi-native-official":
            origin = installed_addon_origins_in_kodi(
                adb,
                port,
                serial,
                [addon["id"]],
                Path(__file__).with_name("kodi_profile_origin_device.py"),
                timeout=timeout,
            ).get(addon["id"])
            if origin != "repository.xbmc.org":
                current_is_candidate = False
            elif not installed_archive_matches(
                adb, port, serial, artifact, addon["id"]
            ):
                rollout(
                    adb,
                    port,
                    serial,
                    artifact,
                    addon["id"],
                    addon["version"],
                    timeout,
                )
                results.append(
                    {
                        "addon": addon["id"],
                        "action": "repaired",
                        "install_mode": install_mode,
                        "version": addon["version"],
                    }
                )
                continue
        if current_is_candidate:
            results.append(
                {
                    "addon": addon["id"],
                    "action": "unchanged",
                    "version": addon["version"],
                }
            )
            continue
        if install_mode == "kodi-native-official":
            reinstalled = current is not None
            if reinstalled:
                # A native Kodi install cannot downgrade an already installed
                # beta/newer build. Remove the known add-on identity first, then
                # let the official repository install the pinned qualification.
                # The removal helper updates scoped storage and Addons*.db
                # transactionally and verifies absence after Kodi restarts.
                remove_addon(
                    adb, port, serial, addon["id"], timeout=timeout
                )
            install_official_addon(
                adb,
                port,
                serial,
                addon["id"],
                minimum_version=addon["version"],
                timeout=timeout,
            )
            installed = _wait_addon_version(
                adb, port, serial, addon["id"], addon["version"], timeout
            )
            if str(installed.get("version")) != addon["version"]:
                raise RuntimeError(
                    "Kodi installed an unqualified official add-on version"
                )
            results.append(
                {
                    "addon": addon["id"],
                    "action": "reinstalled" if reinstalled else "installed",
                    "install_mode": install_mode,
                    "version": addon["version"],
                }
            )
            continue
        try:
            applied = rollout(
                adb, port, serial, artifact, addon["id"], addon["version"], timeout
            )
        except RuntimeError as error:
            if (
                current is not None
                or "PermissionError at backup-installed-addon" not in str(error)
            ):
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
        results.append(
            {
                "addon": addon["id"],
                "action": "installed",
                "version": addon["version"],
                "repaired_orphan": bool(applied.get("repaired_orphan")),
            }
        )
        if addon["kind"] == "repository":
            events.execute_builtin("UpdateAddonRepos")
            time.sleep(3)
    origins = {
        **{
            dependency["id"]: "repository.xbmc.org"
            for dependency in (official_dependencies or [])
        },
        **{
            addon["id"]: addon["origin"]
            for addon in manifest["addons"]
            if "origin" in addon
            and addon.get("install_mode", "managed-pinned-zip") == "managed-pinned-zip"
        },
    }
    if origins and assign_origins:
        assign_addon_origins_in_kodi(
            adb,
            port,
            {"serial": serial, "addon_origins": origins},
            Path(__file__).with_name("kodi_profile_origin_device.py"),
            timeout=timeout,
        )
    native = [
        addon["id"]
        for addon in manifest["addons"]
        if addon.get("install_mode") == "kodi-native-official"
    ]
    if native:
        observed = installed_addon_origins_in_kodi(
            adb,
            port,
            serial,
            native,
            Path(__file__).with_name("kodi_profile_origin_device.py"),
            timeout=timeout,
        )
        invalid = {
            addon_id: observed.get(addon_id)
            for addon_id in native
            if observed.get(addon_id) != "repository.xbmc.org"
        }
        if invalid:
            raise RuntimeError(
                "native official add-on origin differs: %s" % ",".join(sorted(invalid))
            )
    verified = {}
    for addon in manifest["addons"]:
        details = addon_details(adb, port, serial, addon["id"])
        if (
            not details
            or not details.get("enabled")
            or str(details.get("version")) != addon["version"]
        ):
            raise RuntimeError("default add-on verification failed: %s" % addon["id"])
        verified[addon["id"]] = addon["version"]
    return {
        "schema": 1,
        "serial": serial,
        "result": "pass",
        "addons": verified,
        "actions": [*dependency_actions, *results],
    }


def main():
    root = Path(__file__).resolve().parents[1]
    parser = argparse.ArgumentParser()
    parser.add_argument("--manifest", default="manifests/kodi-default-addons.json")
    parser.add_argument("--cache-dir", default=".kodi-private/cache/default-addons")
    parser.add_argument(
        "--dependencies-manifest",
        default="manifests/kodi-official-dependencies.json",
    )
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
    dependencies_path = Path(args.dependencies_manifest)
    if not dependencies_path.is_absolute():
        dependencies_path = root / dependencies_path
    result = reconcile_android(
        args.adb,
        args.adb_server_port,
        args.serial,
        load_manifest(manifest_path),
        cache_dir,
        timeout=args.timeout,
        official_dependencies=load_official_dependencies(dependencies_path),
    )
    print(json.dumps(result, indent=2, sort_keys=True))


if __name__ == "__main__":
    main()
