#!/usr/bin/env python3
"""Cleanly reinstall Kodi targets and restore private profile snapshots."""

from __future__ import annotations

import argparse
import hashlib
import json
import re
import sqlite3
import subprocess
import sys
import tempfile
import time
import zipfile
from pathlib import Path

try:
    from kodi_addon_candidate_rollout import android_runtime_facts
    from kodi_addon_runtime_compatibility import (
        assert_compatible,
        inspect_directory,
        load_policy as load_runtime_policy,
    )
    from kodi_devices import load_registry, resolve_device, resolve_private_endpoint
    from kodi_inventory import load_private_references
    from kodi_profile import (
        KODI_ROOT,
        KODI_PACKAGE,
        AdbEventClient,
        AdbJsonRpcClient,
        _prepare_kodi_permissions,
        _wait_for_kodi_ready,
        adb_command,
        adb_output,
        device_info,
        ensure_private_output,
        kodi_versions_compatible,
        restore_snapshot,
        verify_snapshot,
    )
except ModuleNotFoundError:
    from tools.kodi_addon_candidate_rollout import android_runtime_facts
    from tools.kodi_addon_runtime_compatibility import (
        assert_compatible,
        inspect_directory,
        load_policy as load_runtime_policy,
    )
    from tools.kodi_devices import (
        load_registry,
        resolve_device,
        resolve_private_endpoint,
    )
    from tools.kodi_inventory import load_private_references
    from tools.kodi_profile import (
        KODI_ROOT,
        KODI_PACKAGE,
        AdbEventClient,
        AdbJsonRpcClient,
        _prepare_kodi_permissions,
        _wait_for_kodi_ready,
        adb_command,
        adb_output,
        device_info,
        ensure_private_output,
        kodi_versions_compatible,
        restore_snapshot,
        verify_snapshot,
    )


KODI_STORAGE_PATHS = (
    "/sdcard/Android/data/org.xbmc.kodi",
    "/sdcard/Android/obb/org.xbmc.kodi",
    "/sdcard/.kodi",
)
KODI_DATABASE_ROOT = KODI_ROOT + "/userdata/Database"
SAFE_ADDON_ID = re.compile(r"^[A-Za-z0-9._-]+$")
ORIGIN_SCRIPT = "/sdcard/Download/mwo-kodi-profile-origin-device.py"
ORIGIN_MAPPING = "/sdcard/Download/mwo-kodi-profile-origin-mapping.json"
ORIGIN_MARKER = "/sdcard/Download/mwo-kodi-profile-origin-result.json"


class RepositoryIndexNotReady(RuntimeError):
    pass


def execute_kodi_builtin(adb, port, serial, command):
    try:
        with AdbJsonRpcClient(adb, port, serial) as jsonrpc:
            jsonrpc.call(
                "XBMC.ExecuteBuiltin",
                {"command": command, "wait": False},
            )
        return "jsonrpc"
    except (OSError, RuntimeError, TimeoutError):
        AdbEventClient(adb, port, serial).execute_builtin(command)
        return "eventserver"


def _start_kodi(adb, port, serial):
    # BlueStacks may leave Kodi suspended or disabled after force-stop.
    # Unsuspending is best-effort for older Android builds; enabling an already
    # enabled package is idempotent and portable across emulators and TVs.
    adb_command(
        adb,
        port,
        serial,
        "shell",
        "cmd package unsuspend %s" % KODI_PACKAGE,
        check=False,
    )
    # Android TV may destroy Kodi's display surface while the device is asleep.
    # Wake it before launching so a maintenance restart cannot race the display
    # lifecycle and crash Kodi during early GUI initialization.
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
        "pm enable %s" % KODI_PACKAGE,
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


def file_digest(path):
    hasher = hashlib.sha256()
    with Path(path).open("rb") as handle:
        for block in iter(lambda: handle.read(1024 * 1024), b""):
            hasher.update(block)
    return hasher.hexdigest()


def apk_abis(path):
    result = set()
    with zipfile.ZipFile(path) as archive:
        for name in archive.namelist():
            parts = name.split("/", 2)
            if len(parts) == 3 and parts[0] == "lib":
                result.add(parts[1])
    return sorted(result)


def resolve_private_path(repository, value):
    path = Path(value)
    if not path.is_absolute():
        path = repository / path
    return ensure_private_output(path, repository)


def resolve_ignored_reference_path(repository, value):
    path = Path(value)
    if not path.is_absolute():
        path = repository / path
    path = path.resolve()
    try:
        path.relative_to(repository.resolve())
    except ValueError as error:
        raise ValueError("private reference file escapes repository") from error
    if not path.is_file():
        raise FileNotFoundError(path)
    ignored = subprocess.run(
        ["git", "-C", str(repository), "check-ignore", "-q", str(path)],
        check=False,
    )
    if ignored.returncode:
        raise ValueError("private reference file must be ignored by git")
    return path


def load_config(path, repository):
    path = resolve_private_path(repository, path)
    document = json.loads(path.read_text(encoding="utf-8"))
    schema = document.get("schema")
    if schema != 2:
        raise ValueError("unsupported Kodi reinstall config")
    targets = document.get("targets")
    if not isinstance(targets, list) or not targets:
        raise ValueError("Kodi reinstall config has no targets")
    devices_value = document.get(
        "devices_file", ".kodi-private/devices.json"
    )
    devices_path = resolve_private_path(repository, devices_value)
    registry = load_registry(devices_path)
    default_addons_manifest = document.get("default_addons_manifest")
    if default_addons_manifest is not None and (
        not isinstance(default_addons_manifest, str)
        or not default_addons_manifest
    ):
        raise ValueError("invalid default add-ons manifest path")
    private_profiles = document.get("default_addon_private_profiles", [])
    references_file = document.get("private_references_file", ".env")
    if not isinstance(private_profiles, list):
        raise ValueError("invalid default add-on private profiles")
    if not isinstance(references_file, str) or not references_file:
        raise ValueError("invalid private references path")
    references_path = Path(references_file)
    if not references_path.is_absolute():
        references_path = repository / references_path
    references = (
        load_private_references(references_path)
        if references_path.is_file()
        else {}
    )
    try:
        from kodi_private_addons import validate_profiles
    except ModuleNotFoundError:
        from tools.kodi_private_addons import validate_profiles

    private_profiles = validate_profiles(private_profiles)
    if private_profiles and default_addons_manifest is None:
        raise ValueError(
            "private add-on profiles require a default add-ons manifest"
        )
    resolved = []
    forbidden = {"name", "serial", "expected_model"}
    for target in targets:
        if not isinstance(target, dict):
            raise ValueError("Kodi reinstall target must be an object")
        duplicate = sorted(forbidden.intersection(target))
        if duplicate:
            raise ValueError(
                "schema 2 target duplicates device inventory fields: %s"
                % ", ".join(duplicate)
            )
        logical_id = target.get("logical_device_id")
        if not isinstance(logical_id, str):
            raise ValueError("schema 2 target lacks logical_device_id")
        device = resolve_private_endpoint(
            resolve_device(registry, logical_id), references
        )
        if device["platform"] not in {"android", "android-emulator"}:
            raise ValueError(
                "%s uses unsupported reinstall platform %s"
                % (logical_id, device["platform"])
            )
        expected_major = device["expected"]["kodi_major"]
        expected_version = target.get("expected_kodi_version", "")
        match = re.match(r"^(\d+)", str(expected_version))
        if not match or int(match.group(1)) != expected_major:
            raise ValueError(
                "%s Kodi major differs from device inventory" % logical_id
            )
        resolved.append(
            {
                **target,
                **(
                    {"default_addons_manifest": default_addons_manifest}
                    if default_addons_manifest is not None
                    else {}
                ),
                "default_addon_private_profiles": private_profiles,
                "private_references_file": references_file,
                "name": logical_id,
                "serial": device["endpoints"]["adb"],
                "expected_model": device["expected"]["model"],
                "runtime_platform": device["platform"],
            }
        )
    return path, resolved


def preflight_target(target, repository, adb, port):
    required = {
        "name",
        "serial",
        "expected_model",
        "expected_kodi_version",
        "snapshot",
        "apk",
        "apk_sha256",
    }
    missing = sorted(required.difference(target))
    if missing:
        raise ValueError(
            "%s target lacks: %s"
            % (target.get("name", "<unnamed>"), ", ".join(missing))
        )
    serial = target["serial"]
    state = adb_output(adb, port, serial, "get-state").strip()
    if state != "device":
        raise RuntimeError("%s is not an authorized ADB device" % serial)
    model = adb_output(
        adb, port, serial, "shell", "getprop ro.product.model"
    ).strip()
    if model != target["expected_model"]:
        raise RuntimeError(
            "%s resolved to unexpected model %r" % (serial, model)
        )
    device_abis = [
        item
        for item in adb_output(
            adb,
            port,
            serial,
            "shell",
            "getprop ro.product.cpu.abilist",
        ).strip().split(",")
        if item
    ]
    required_addons = target.get("required_addons", [])
    addon_origins = target.get("addon_origins", {})
    default_addons_manifest = None
    private_profiles = target.get("default_addon_private_profiles", [])
    references_path = None
    default_manifest_value = target.get("default_addons_manifest")
    if default_manifest_value is not None:
        candidate = (repository / default_manifest_value).resolve()
        try:
            candidate.relative_to(repository.resolve())
        except ValueError as error:
            raise ValueError(
                "%s default add-ons manifest escapes repository"
                % target["name"]
            ) from error
        try:
            from kodi_default_addons import load_manifest
        except ModuleNotFoundError:
            from tools.kodi_default_addons import load_manifest

        default_addons_manifest = load_manifest(candidate)
        default_ids = [
            addon["id"] for addon in default_addons_manifest["addons"]
        ]
        default_origins = {
            addon["id"]: addon["origin"]
            for addon in default_addons_manifest["addons"]
            if "origin" in addon
        }
        origin_ids = list(default_origins.values())
        required_addons = list(
            dict.fromkeys([*required_addons, *default_ids, *origin_ids])
        )
        conflicts = {
            addon_id
            for addon_id, origin in default_origins.items()
            if addon_id in addon_origins and addon_origins[addon_id] != origin
        }
        if conflicts:
            raise ValueError(
                "%s default add-on origins conflict: %s"
                % (target["name"], ", ".join(sorted(conflicts)))
            )
        addon_origins = {**addon_origins, **default_origins}
    if private_profiles:
        references_path = resolve_ignored_reference_path(
            repository, target["private_references_file"]
        )
        try:
            from kodi_inventory import load_private_references
            from kodi_private_addons import validate_references
        except ModuleNotFoundError:
            from tools.kodi_inventory import load_private_references
            from tools.kodi_private_addons import validate_references

        references = load_private_references(references_path)
        validate_references(private_profiles, references)
    restore_mode = target.get("restore_mode", "kodi-process")
    if not isinstance(required_addons, list) or any(
        not isinstance(item, str) or not SAFE_ADDON_ID.fullmatch(item)
        for item in required_addons
    ):
        raise ValueError("%s has invalid required add-ons" % target["name"])
    if not isinstance(addon_origins, dict):
        raise ValueError("%s has invalid add-on origins" % target["name"])
    if restore_mode not in ("adb-push", "kodi-process"):
        raise ValueError("%s has invalid restore mode" % target["name"])
    if any(
        addon_id not in required_addons or origin not in required_addons
        for addon_id, origin in addon_origins.items()
    ):
        raise ValueError(
            "%s origin mappings must reference required add-ons"
            % target["name"]
        )
    snapshot_path = resolve_private_path(repository, target["snapshot"])
    manifest = verify_snapshot(snapshot_path)
    addon_root = snapshot_path / "payload/addons"
    snapshot_addons = []
    if addon_root.exists():
        if addon_root.is_symlink() or not addon_root.is_dir():
            raise ValueError("%s snapshot add-on root is unsafe" % target["name"])
        for addon_path in sorted(addon_root.iterdir()):
            if addon_path.is_dir():
                snapshot_addons.append(inspect_directory(addon_path))
            else:
                raise ValueError(
                    "%s snapshot add-on root contains a non-directory"
                    % target["name"]
                )
    snapshot_ids = {item["id"] for item in snapshot_addons}
    manifest_ids = {item["id"] for item in manifest["addons"]}
    if snapshot_ids != manifest_ids:
        raise ValueError("%s snapshot add-on inventory differs" % target["name"])
    allow_upgrade = bool(target.get("allow_kodi_upgrade"))
    if not kodi_versions_compatible(
        manifest["device"]["kodi_version"],
        target["expected_kodi_version"],
        allow_upgrade=allow_upgrade,
    ):
        raise ValueError(
            "%s snapshot Kodi version is incompatible" % target["name"]
        )
    if not set(device_abis).intersection(manifest["device"]["abi_list"]):
        raise ValueError(
            "%s snapshot ABI is incompatible with device" % target["name"]
        )
    apk_path = resolve_private_path(repository, target["apk"])
    if not apk_path.is_file():
        raise FileNotFoundError(apk_path)
    actual_sha256 = file_digest(apk_path)
    if actual_sha256 != target["apk_sha256"]:
        raise ValueError("%s APK digest differs from config" % target["name"])
    packaged_abis = apk_abis(apk_path)
    if packaged_abis and not set(packaged_abis).intersection(device_abis):
        raise ValueError(
            "%s APK ABI %s is incompatible with device ABI %s"
            % (target["name"], packaged_abis, device_abis)
        )
    package = adb_output(
        adb,
        port,
        serial,
        "shell",
        "dumpsys package %s" % KODI_PACKAGE,
    )
    version = re.search(r"versionName=([^\s]+)", package)
    compatibility = {
        "status": "PENDING_POST_INSTALL",
        "addons": len(snapshot_addons),
    }
    if version:
        process = adb_command(
            adb,
            port,
            serial,
            "shell",
            "pidof %s" % KODI_PACKAGE,
            check=False,
            text=True,
        )
        running_before = bool((process.stdout or "").strip())
        _start_kodi(adb, port, serial)
        try:
            facts = android_runtime_facts(
                adb,
                port,
                serial,
                platform=target.get("runtime_platform", "android"),
            )
            facts["kodi_version"] = target["expected_kodi_version"]
            if packaged_abis:
                facts["abis"] = packaged_abis
            report = assert_compatible(
                snapshot_addons,
                facts,
                load_runtime_policy(
                    repository
                    / "manifests/kodi-addon-runtime-compatibility.json"
                ),
            )
            compatibility = {
                "status": report["status"],
                "addons": len(snapshot_addons),
                "policy_sha256": report["policy_sha256"],
                "graph_sha256": report["graph_sha256"],
            }
        finally:
            if not running_before:
                adb_command(
                    adb,
                    port,
                    serial,
                    "shell",
                    "am force-stop %s" % KODI_PACKAGE,
                    check=False,
                )
    return {
        "name": target["name"],
        "serial": serial,
        "model": model,
        "device_abis": device_abis,
        "apk_abis": packaged_abis,
        "apk": apk_path,
        "snapshot": snapshot_path,
        "snapshot_manifest": manifest,
        "installed_version": version.group(1) if version else None,
        "expected_version": target["expected_kodi_version"],
        "required_addons": required_addons,
        "addon_origins": addon_origins,
        "allow_kodi_upgrade": allow_upgrade,
        "restore_mode": restore_mode,
        "default_addons_manifest": default_addons_manifest,
        "default_addons_cache": (
            repository / ".kodi-private/cache/default-addons"
        ),
        "default_addon_private_profiles": private_profiles,
        "private_references_file": references_path,
        "runtime_platform": target.get("runtime_platform", "android"),
        "snapshot_addons": snapshot_addons,
        "compatibility": compatibility,
    }


def verify_target_runtime_compatibility(adb, port, target, repository):
    _start_kodi(adb, port, target["serial"])
    try:
        facts = android_runtime_facts(
            adb,
            port,
            target["serial"],
            platform=target["runtime_platform"],
        )
        report = assert_compatible(
            target["snapshot_addons"],
            facts,
            load_runtime_policy(
                repository / "manifests/kodi-addon-runtime-compatibility.json"
            ),
        )
    finally:
        adb_command(
            adb,
            port,
            target["serial"],
            "shell",
            "am force-stop %s" % KODI_PACKAGE,
            check=False,
        )
    return {
        "status": report["status"],
        "addons": len(target["snapshot_addons"]),
        "policy_sha256": report["policy_sha256"],
        "graph_sha256": report["graph_sha256"],
    }


def reconcile_default_addons(adb, port, target):
    manifest = target.get("default_addons_manifest")
    if not manifest:
        return None
    try:
        from kodi_default_addons import (
            load_official_dependencies,
            reconcile_android,
        )
    except ModuleNotFoundError:
        from tools.kodi_default_addons import (
            load_official_dependencies,
            reconcile_android,
        )

    return reconcile_android(
        adb,
        port,
        target["serial"],
        manifest,
        target["default_addons_cache"],
        assign_origins=False,
        official_dependencies=load_official_dependencies(
            Path(__file__).resolve().parents[1]
            / "manifests/kodi-official-dependencies.json"
        ),
    )


def reconcile_private_addons(adb, port, target):
    profiles = target.get("default_addon_private_profiles", [])
    if not profiles:
        return []
    try:
        from kodi_inventory import load_private_references
        from kodi_private_addons import reconcile
    except ModuleNotFoundError:
        from tools.kodi_inventory import load_private_references
        from tools.kodi_private_addons import reconcile

    references = load_private_references(target["private_references_file"])
    return reconcile(
        adb,
        port,
        target["serial"],
        profiles,
        references,
        Path(__file__).resolve().parents[1],
    )


def uninstall_and_clean(adb, port, serial):
    package = adb_command(
        adb,
        port,
        serial,
        "shell",
        "pm path %s" % KODI_PACKAGE,
        check=False,
        text=True,
    )
    if package.stdout.strip().startswith("package:"):
        result = adb_command(
            adb,
            port,
            serial,
            "uninstall",
            KODI_PACKAGE,
            check=False,
            text=True,
        )
        if "Success" not in result.stdout:
            raise RuntimeError("Kodi uninstall did not report success")
    quoted = " ".join("'%s'" % path for path in KODI_STORAGE_PATHS)
    adb_command(
        adb,
        port,
        serial,
        "shell",
        "rm -rf %s" % quoted,
        check=False,
    )
    remaining = adb_output(
        adb,
        port,
        serial,
        "shell",
        "for path in %s; do test ! -e \"$path\" || echo \"$path\"; done"
        % quoted,
    ).strip()
    if remaining:
        raise RuntimeError("Kodi storage cleanup left data behind")


def install_apk(adb, port, serial, apk, expected_version):
    result = adb_command(
        adb,
        port,
        serial,
        "install",
        "-r",
        "-g",
        str(apk),
        text=True,
        timeout=300,
    )
    if "Success" not in result.stdout:
        raise RuntimeError("Kodi APK installation did not report success")
    _prepare_kodi_permissions(adb, port, serial)
    installed = device_info(adb, port, serial)
    if installed["kodi_version"] != expected_version:
        raise RuntimeError(
            "installed Kodi version %s differs from expected %s"
            % (installed["kodi_version"], expected_version)
        )


def addon_database_path(adb, port, serial):
    output = adb_output(
        adb,
        port,
        serial,
        "shell",
        "ls '%s'/Addons*.db 2>/dev/null | tail -n 1"
        % KODI_DATABASE_ROOT,
    ).strip()
    expected = re.compile(
        "^%s/Addons[0-9]+[.]db$" % re.escape(KODI_DATABASE_ROOT)
    )
    if not expected.fullmatch(output):
        raise RuntimeError("Kodi add-on database was not found")
    return output

def apply_addon_origins(
    database,
    origins,
    previous_origins=None,
    repository_checksums=None,
    version_transitions=None,
):
    previous_origins = previous_origins or {}
    repository_checksums = repository_checksums or {}
    version_transitions = version_transitions or {}
    for addon_id, origin in origins.items():
        if not SAFE_ADDON_ID.fullmatch(addon_id):
            raise ValueError("unsafe add-on identifier in origin mapping")
        if not SAFE_ADDON_ID.fullmatch(origin):
            raise ValueError("unsafe repository identifier in origin mapping")
    for addon_id, origin in previous_origins.items():
        if addon_id not in origins:
            raise ValueError("previous origin has no target origin")
        if not SAFE_ADDON_ID.fullmatch(origin):
            raise ValueError("unsafe previous repository identifier")
    for origin, checksum in repository_checksums.items():
        if not SAFE_ADDON_ID.fullmatch(origin):
            raise ValueError("unsafe checksum repository identifier")
        if not re.fullmatch(r"[0-9a-f]{64}", checksum):
            raise ValueError("invalid repository checksum")
    for addon_id, transition in version_transitions.items():
        if addon_id not in previous_origins:
            raise ValueError("version transition has no previous origin")
        if (
            not isinstance(transition, dict)
            or set(transition) != {"from", "to"}
            or not all(
                isinstance(value, str)
                and value
                and len(value) <= 128
                for value in transition.values()
            )
        ):
            raise ValueError("invalid version transition")
    connection = sqlite3.connect(database)
    try:
        with connection:
            for addon_id, origin in origins.items():
                repository = connection.execute(
                    "SELECT checksum FROM repo WHERE addonID=?",
                    (origin,),
                ).fetchone()
                if not repository or not repository[0]:
                    raise RepositoryIndexNotReady(
                        "%s repository index is not ready" % origin
                    )
                expected_checksum = repository_checksums.get(origin)
                if (
                    expected_checksum is not None
                    and repository[0] != expected_checksum
                ):
                    raise RepositoryIndexNotReady(
                        "%s repository index checksum differs" % origin
                    )
                candidate = connection.execute(
                    """
                    SELECT addons.version
                    FROM addons
                    JOIN addonlinkrepo ON addonlinkrepo.idAddon=addons.id
                    JOIN repo ON repo.id=addonlinkrepo.idRepo
                    WHERE addons.addonID=? AND repo.addonID=?
                    """,
                    (addon_id, origin),
                ).fetchone()
                if not candidate:
                    raise RepositoryIndexNotReady(
                        "%s is not indexed by %s" % (addon_id, origin)
                    )
                installed = connection.execute(
                    "SELECT origin FROM installed WHERE addonID=?",
                    (addon_id,),
                ).fetchone()
                if not installed:
                    raise RuntimeError("%s is not installed" % addon_id)
                current = installed[0]
                if current not in ("", origin):
                    previous = previous_origins.get(addon_id)
                    if current != previous:
                        raise RuntimeError(
                            "%s already belongs to a different origin"
                            % addon_id
                        )
                    previous_repository = connection.execute(
                        "SELECT checksum FROM repo WHERE addonID=?",
                        (previous,),
                    ).fetchone()
                    if not previous_repository or not previous_repository[0]:
                        raise RepositoryIndexNotReady(
                            "%s repository index is not ready" % previous
                        )
                    expected_previous_checksum = repository_checksums.get(
                        previous
                    )
                    if (
                        expected_previous_checksum is not None
                        and previous_repository[0]
                        != expected_previous_checksum
                    ):
                        raise RepositoryIndexNotReady(
                            "%s repository index checksum differs" % previous
                        )
                    previous_candidate = connection.execute(
                        """
                        SELECT addons.version
                        FROM addons
                        JOIN addonlinkrepo
                          ON addonlinkrepo.idAddon=addons.id
                        JOIN repo ON repo.id=addonlinkrepo.idRepo
                        WHERE addons.addonID=? AND repo.addonID=?
                        """,
                        (addon_id, previous),
                    ).fetchone()
                    if not previous_candidate:
                        raise RepositoryIndexNotReady(
                            "%s is not indexed by %s"
                            % (addon_id, previous)
                        )
                    if previous_candidate[0] != candidate[0]:
                        expected = version_transitions.get(addon_id)
                        actual = {
                            "from": previous_candidate[0],
                            "to": candidate[0],
                        }
                        if expected != actual:
                            raise RepositoryIndexNotReady(
                                "%s repository candidates differ" % addon_id
                            )
                connection.execute(
                    "UPDATE installed SET origin=? WHERE addonID=?",
                    (origin, addon_id),
                )
    finally:
        connection.close()


def assign_addon_origins_via_adb(adb, port, target, timeout=90):
    origins = target["addon_origins"]
    if not origins:
        return
    started = time.monotonic()
    last_error = None
    while time.monotonic() - started < timeout:
        adb_command(
            adb,
            port,
            target["serial"],
            "shell",
            "am force-stop %s" % KODI_PACKAGE,
        )
        database = addon_database_path(
            adb,
            port,
            target["serial"],
        )
        with tempfile.TemporaryDirectory() as temporary:
            local = Path(temporary) / Path(database).name
            adb_command(
                adb,
                port,
                target["serial"],
                "pull",
                database,
                str(local),
                timeout=120,
            )
            try:
                apply_addon_origins(
                    local,
                    origins,
                    target.get("addon_previous_origins"),
                    target.get("addon_repository_checksums"),
                    target.get("addon_version_transitions"),
                )
            except RepositoryIndexNotReady as error:
                last_error = error
            else:
                adb_command(
                    adb,
                    port,
                    target["serial"],
                    "push",
                    str(local),
                    database,
                    timeout=120,
                )
                last_error = None
        _start_kodi(adb, port, target["serial"])
        if last_error is None:
            return
        time.sleep(5)
    raise RuntimeError("Kodi repository index stayed unavailable") from last_error


def assign_addon_origins_in_kodi(
    adb,
    port,
    target,
    origin_script,
    timeout=90,
):
    origins = target["addon_origins"]
    if not origins:
        return
    for addon_id, origin in origins.items():
        if not SAFE_ADDON_ID.fullmatch(addon_id):
            raise ValueError("unsafe add-on identifier in origin mapping")
        if not SAFE_ADDON_ID.fullmatch(origin):
            raise ValueError("unsafe repository identifier in origin mapping")
    previous_origins = target.get("addon_previous_origins", {})
    repository_checksums = target.get("addon_repository_checksums", {})
    version_transitions = target.get("addon_version_transitions", {})
    document = origins
    if previous_origins or repository_checksums or version_transitions:
        document = {
            "schema": 3 if version_transitions else 2,
            "origins": origins,
            "previous_origins": previous_origins,
            "repository_checksums": repository_checksums,
            "version_transitions": version_transitions,
        }
    with tempfile.NamedTemporaryFile("w", encoding="utf-8") as mapping:
        json.dump(document, mapping, sort_keys=True)
        mapping.flush()
        adb_command(
            adb,
            port,
            target["serial"],
            "push",
            str(origin_script),
            ORIGIN_SCRIPT,
        )
        adb_command(
            adb,
            port,
            target["serial"],
            "push",
            mapping.name,
            ORIGIN_MAPPING,
        )
    try:
        _start_kodi(adb, port, target["serial"])
        started = time.monotonic()
        result = None
        while time.monotonic() - started < timeout:
            adb_command(
                adb,
                port,
                target["serial"],
                "shell",
                "rm -f '%s'" % ORIGIN_MARKER,
                check=False,
            )
            execute_kodi_builtin(
                adb,
                port,
                target["serial"],
                "RunScript(%s,%s,%s)"
                % (ORIGIN_SCRIPT, ORIGIN_MAPPING, ORIGIN_MARKER)
            )
            attempt = time.monotonic()
            while time.monotonic() - attempt < 30:
                marker = adb_command(
                    adb,
                    port,
                    target["serial"],
                    "shell",
                    "cat '%s'" % ORIGIN_MARKER,
                    check=False,
                    text=True,
                )
                if marker.returncode == 0 and marker.stdout.strip():
                    result = json.loads(marker.stdout)
                    break
                time.sleep(1)
            if result and result.get("ok"):
                break
            if result and result.get("error_type") != "RepositoryIndexNotReady":
                break
            result = None
            execute_kodi_builtin(
                adb, port, target["serial"], "UpdateAddonRepos"
            )
            time.sleep(10)
        if result is None:
            raise TimeoutError("Kodi origin assignment did not finish")
        if not result.get("ok"):
            raise RuntimeError(
                "Kodi origin assignment failed: %s"
                % result.get("error_type", "unknown")
            )
        if result.get("updated") != len(origins):
            raise RuntimeError("Kodi origin assignment count differs")
        adb_command(
            adb,
            port,
            target["serial"],
            "shell",
            "am force-stop %s" % KODI_PACKAGE,
        )
        _start_kodi(adb, port, target["serial"])
    finally:
        adb_command(
            adb,
            port,
            target["serial"],
            "shell",
            "rm -f '%s' '%s' '%s'"
            % (ORIGIN_SCRIPT, ORIGIN_MAPPING, ORIGIN_MARKER),
            check=False,
        )


def assign_addon_origins(adb, port, target, origin_script):
    if target["restore_mode"] == "adb-push":
        assign_addon_origins_via_adb(adb, port, target)
    else:
        assign_addon_origins_in_kodi(
            adb,
            port,
            target,
            origin_script,
        )


def installed_addon_origins_in_kodi(
    adb,
    port,
    serial,
    addon_ids,
    origin_script,
    timeout=45,
):
    with tempfile.NamedTemporaryFile("w", encoding="utf-8") as mapping:
        json.dump(sorted(addon_ids), mapping)
        mapping.flush()
        adb_command(
            adb,
            port,
            serial,
            "push",
            str(origin_script),
            ORIGIN_SCRIPT,
        )
        adb_command(adb, port, serial, "push", mapping.name, ORIGIN_MAPPING)
    try:
        started = time.monotonic()
        while time.monotonic() - started < timeout:
            adb_command(
                adb,
                port,
                serial,
                "shell",
                "rm -f '%s'" % ORIGIN_MARKER,
                check=False,
            )
            execute_kodi_builtin(
                adb,
                port,
                serial,
                "RunScript(%s,%s,%s,read)"
                % (ORIGIN_SCRIPT, ORIGIN_MAPPING, ORIGIN_MARKER)
            )
            attempt = time.monotonic()
            while (
                time.monotonic() - attempt < 10
                and time.monotonic() - started < timeout
            ):
                marker = adb_command(
                    adb,
                    port,
                    serial,
                    "shell",
                    "cat '%s'" % ORIGIN_MARKER,
                    check=False,
                    text=True,
                )
                if marker.returncode == 0 and marker.stdout.strip():
                    result = json.loads(marker.stdout)
                    if not result.get("ok"):
                        raise RuntimeError(
                            "Kodi origin read failed: %s"
                            % result.get("error_type", "unknown")
                        )
                    origins = result.get("origins")
                    if not isinstance(origins, dict):
                        raise RuntimeError(
                            "Kodi origin read returned no mapping"
                        )
                    return origins
                time.sleep(1)
        raise TimeoutError("Kodi origin read did not finish")
    finally:
        adb_command(
            adb,
            port,
            serial,
            "shell",
            "rm -f '%s' '%s' '%s'"
            % (ORIGIN_SCRIPT, ORIGIN_MAPPING, ORIGIN_MARKER),
            check=False,
        )


def installed_addon_origins(
    adb,
    port,
    serial,
    addon_ids,
    origin_script=None,
):
    try:
        database = addon_database_path(adb, port, serial)
    except RuntimeError:
        if origin_script is None:
            raise
        return installed_addon_origins_in_kodi(
            adb,
            port,
            serial,
            addon_ids,
            origin_script,
        )
    with tempfile.TemporaryDirectory() as temporary:
        local = Path(temporary) / Path(database).name
        adb_command(
            adb,
            port,
            serial,
            "pull",
            database,
            str(local),
            timeout=120,
        )
        connection = sqlite3.connect(local)
        try:
            return {
                addon_id: (
                    connection.execute(
                        "SELECT origin FROM installed WHERE addonID=?",
                        (addon_id,),
                    ).fetchone()
                    or (None,)
                )[0]
                for addon_id in addon_ids
            }
        finally:
            connection.close()


def validate_restored_target(
    adb,
    port,
    target,
    restore_result,
    origin_script=None,
):
    addons = {}
    with AdbJsonRpcClient(adb, port, target["serial"]) as jsonrpc:
        if jsonrpc.call("JSONRPC.Ping") != "pong":
            raise RuntimeError("Kodi JSON-RPC did not return pong")
        for addon_id in target["required_addons"]:
            addon = jsonrpc.call(
                "Addons.GetAddonDetails",
                {
                    "addonid": addon_id,
                    "properties": ["enabled", "version"],
                },
            )["addon"]
            if not addon["enabled"]:
                raise RuntimeError("%s is disabled" % addon_id)
            addons[addon_id] = addon["version"]
        skin = jsonrpc.call(
            "Settings.GetSettingValue",
            {"setting": "lookandfeel.skin"},
        )["value"]
    expected_skin = target["snapshot_manifest"]["selected_skin"]
    if skin != expected_skin:
        raise RuntimeError(
            "active skin %s differs from snapshot %s" % (skin, expected_skin)
        )
    origins = installed_addon_origins(
        adb,
        port,
        target["serial"],
        target["addon_origins"],
        origin_script=origin_script,
    )
    for addon_id, expected in target["addon_origins"].items():
        if origins.get(addon_id) != expected:
            raise RuntimeError("%s has an unexpected origin" % addon_id)
    return {
        "name": target["name"],
        "serial": target["serial"],
        "model": target["model"],
        "kodi_version": target["expected_version"],
        "snapshot_id": restore_result["snapshot_id"],
        "restored_files": restore_result["restored_files"],
        "skin": skin,
        "addons": addons,
        "result": "pass",
    }


def restore_snapshot_via_adb(adb, port, target):
    manifest = target["snapshot_manifest"]
    adb_command(
        adb,
        port,
        target["serial"],
        "shell",
        "am force-stop %s" % KODI_PACKAGE,
    )
    adb_command(
        adb,
        port,
        target["serial"],
        "shell",
        "rm -rf "
        "'%s/addons/script.mwodevelop.profile.restore' "
        "'%s/addons/plugin.video.mwodevelop.profile.restore'; "
        "rm -f '%s/temp/mwo-write-test'"
        % (KODI_ROOT, KODI_ROOT, KODI_ROOT),
        check=False,
    )
    payload = target["snapshot"] / "payload"
    adb_command(
        adb,
        port,
        target["serial"],
        "push",
        str(payload) + "/.",
        KODI_ROOT + "/",
        timeout=900,
    )
    _start_kodi(adb, port, target["serial"])
    enabled = [
        item["id"]
        for item in manifest["addons"]
        if item["enabled"] and item["id"] != manifest["selected_skin"]
    ]
    with AdbJsonRpcClient(
        adb,
        port,
        target["serial"],
    ) as jsonrpc:
        for addon_id in enabled:
            started = time.monotonic()
            while True:
                try:
                    jsonrpc.call(
                        "Addons.SetAddonEnabled",
                        {"addonid": addon_id, "enabled": True},
                    )
                    break
                except RuntimeError:
                    if time.monotonic() - started >= 60:
                        raise
                    time.sleep(2)
        jsonrpc.call(
            "Addons.SetAddonEnabled",
            {
                "addonid": manifest["selected_skin"],
                "enabled": True,
            },
        )
    time.sleep(2)
    skin = manifest["selected_skin"]
    if not re.fullmatch(r"[A-Za-z0-9._-]+", skin):
        raise ValueError("snapshot contains an unsafe skin identifier")
    adb_command(
        adb,
        port,
        target["serial"],
        "shell",
        "am force-stop %s" % KODI_PACKAGE,
    )
    settings = KODI_ROOT + "/userdata/guisettings.xml"
    result = adb_command(
        adb,
        port,
        target["serial"],
        "shell",
        "sed -i -E "
        "'s#(<setting id=\"lookandfeel.skin\"[^>]*>)[^<]*"
        "(</setting>)#\\1%s\\2#' '%s'" % (skin, settings),
        check=False,
        text=True,
    )
    if result.returncode != 0:
        raise RuntimeError("failed to persist the restored skin setting")
    _start_kodi(adb, port, target["serial"])
    with AdbJsonRpcClient(
        adb,
        port,
        target["serial"],
    ) as jsonrpc:
        selected = jsonrpc.call(
            "Settings.GetSettingValue",
            {"setting": "lookandfeel.skin"},
        )["value"]
    if selected != skin:
        raise RuntimeError("Kodi did not load the restored skin after restart")
    return {
        "snapshot_id": manifest["snapshot_id"],
        "restored_files": len(manifest["files"]),
        "selected_skin": manifest["selected_skin"],
        "enabled_addons_requested": len(enabled) + 1,
    }


def deploy_target(
    adb,
    port,
    target,
    device_script,
    origin_script,
    restore_only=False,
):
    if not restore_only:
        uninstall_and_clean(adb, port, target["serial"])
        install_apk(
            adb,
            port,
            target["serial"],
            target["apk"],
            target["expected_version"],
        )
    compatibility = verify_target_runtime_compatibility(
        adb,
        port,
        target,
        Path(__file__).resolve().parents[1],
    )
    if target["restore_mode"] == "adb-push":
        restore_result = restore_snapshot_via_adb(
            adb,
            port,
            target,
        )
    elif target["restore_mode"] == "kodi-process":
        restore_result = restore_snapshot(
            adb,
            port,
            target["serial"],
            target["snapshot"],
            device_script,
            allow_kodi_upgrade=target["allow_kodi_upgrade"],
        )
    else:
        raise ValueError(
            "unsupported restore mode: %s" % target["restore_mode"]
        )
    reconcile_default_addons(adb, port, target)
    private_addons = reconcile_private_addons(adb, port, target)
    assign_addon_origins(adb, port, target, origin_script)
    result = validate_restored_target(
        adb,
        port,
        target,
        restore_result,
        origin_script,
    )
    if private_addons:
        result["private_addons"] = private_addons
    result["compatibility"] = compatibility
    return result


def main():
    repository = Path(__file__).resolve().parents[1]
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--config",
        default=".kodi-private/kodi-reinstall.json",
    )
    parser.add_argument(
        "--adb",
        default="/home/mwo/android-sdk/platform-tools/adb",
    )
    parser.add_argument("--adb-server-port", type=int, default=5038)
    parser.add_argument(
        "--target",
        action="append",
        help="target name from config; omit or use 'all' for every target",
    )
    parser.add_argument(
        "--yes",
        action="store_true",
        help="authorize uninstall, storage cleanup, reinstall and restore",
    )
    parser.add_argument(
        "--restore-only",
        action="store_true",
        help="skip uninstall and APK installation, then restore and validate",
    )
    args = parser.parse_args()
    _config_path, configured = load_config(args.config, repository)
    selected_names = set(args.target or ["all"])
    if "all" in selected_names:
        selected = configured
    else:
        selected = [
            item for item in configured if item.get("name") in selected_names
        ]
        found = {item["name"] for item in selected}
        missing = sorted(selected_names.difference(found))
        if missing:
            raise ValueError("unknown targets: %s" % ", ".join(missing))
    preflight = [
        preflight_target(
            item,
            repository,
            args.adb,
            args.adb_server_port,
        )
        for item in selected
    ]
    plan = {
        "targets": [
            {
                "name": item["name"],
                "serial": item["serial"],
                "model": item["model"],
                "installed_version": item["installed_version"],
                "new_version": item["expected_version"],
                "snapshot_id": item["snapshot_manifest"]["snapshot_id"],
                "apk_abis": item["apk_abis"],
                "compatibility": item["compatibility"],
            }
            for item in preflight
        ]
    }
    if not args.yes:
        print(json.dumps(plan, indent=2, sort_keys=True))
        print("Re-run with --yes to perform the destructive reinstall.")
        return 0
    results = []
    device_script = repository / "tools/kodi_profile_restore_device.py"
    origin_script = repository / "tools/kodi_profile_origin_device.py"
    for target in preflight:
        action = "Restoring" if args.restore_only else "Reinstalling"
        print("%s %s..." % (action, target["name"]), flush=True)
        results.append(
            deploy_target(
                args.adb,
                args.adb_server_port,
                target,
                device_script,
                origin_script,
                restore_only=args.restore_only,
            )
        )
    print(
        json.dumps(
            {"schema": 1, "results": results},
            indent=2,
            sort_keys=True,
        )
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
