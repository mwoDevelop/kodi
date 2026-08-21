"""Transactional Profile Sync bootstrap executed inside Kodi Flatpak."""

from __future__ import annotations

import json
import hashlib
import glob
import os
import re
import runpy
import shutil
import sqlite3
import stat
import sys
import time
import zipfile
from pathlib import Path, PurePosixPath
from xml.etree import ElementTree

import xbmc
import xbmcaddon
import xbmcvfs


ADDON_ID = "service.mwodevelop.profilesync"
REPOSITORY_ID = "repository.mwodevelop"
MARKER_NAME = "flatpak-rollout-result.json"
SAFE_STAGE = re.compile(r"^\.mwodevelop-flatpak-[0-9a-f]{16}$")
SAFE_ADDON_ID = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._-]{0,127}$")
MAX_FILES = 4000
MAX_BYTES = 64 * 1024 * 1024
CURRENT_STAGE = "startup"


def _set_stage(name):
    global CURRENT_STAGE
    if not isinstance(name, str) or not re.fullmatch(r"[a-z0-9_]{1,64}", name):
        raise ValueError("invalid Flatpak rollout stage name")
    CURRENT_STAGE = name


def _safe_error_code(error):
    chain = []
    current = error
    while current is not None and current not in chain:
        chain.append(current)
        current = current.__cause__ or current.__context__
    for item in chain:
        code = getattr(item, "code", None)
        if isinstance(code, (str, int)) and code is not None:
            return code
    message = " ".join(str(item).lower() for item in chain)
    classifications = (
        (
            "native official add-on version is unqualified",
            "official_version_unqualified",
        ),
        (
            "could not install native official add-on",
            "official_install_failed",
        ),
        ("native official add-on origin differs", "official_origin_differs"),
        ("native official dependency differs", "official_dependency_differs"),
        ("unknown addon id", "unknown_addon_id"),
        ("timed out", "timeout"),
        ("connection refused", "connection_refused"),
        ("certificate", "certificate_error"),
        ("signature", "signature_error"),
        ("favourites json-rpc failed", "favourites_rpc_failed"),
        ("returned invalid favourites", "invalid_favourites_response"),
        ("favourites changed during apply", "favourites_changed_during_apply"),
        ("favourites health check", "favourites_health_check"),
        ("artwork health check", "artwork_health_check"),
        ("failure report is pending", "failure_report_pending"),
        ("success report", "success_report_pending"),
    )
    for needle, classification in classifications:
        if needle in message:
            return classification
    return None


def _safe_error_origin(error):
    current = error
    seen = []
    while current is not None and current not in seen:
        seen.append(current)
        current = current.__cause__ or current.__context__
    leaf = seen[-1]
    traceback = leaf.__traceback__
    if traceback is None:
        return None
    while traceback.tb_next is not None:
        traceback = traceback.tb_next
    filename = Path(traceback.tb_frame.f_code.co_filename).name
    function = traceback.tb_frame.f_code.co_name
    if not re.fullmatch(r"[A-Za-z0-9_.-]{1,128}", filename) or not re.fullmatch(
        r"[A-Za-z0-9_<>.-]{1,128}", function
    ):
        return None
    return "%s:%s" % (filename, function)


def _write_atomic(path, document):
    payload = (json.dumps(document, sort_keys=True) + "\n").encode("utf-8")
    temporary = str(path) + ".tmp"
    with open(temporary, "wb") as handle:
        handle.write(payload)
        handle.flush()
        os.fsync(handle.fileno())
    os.chmod(temporary, 0o600)
    os.replace(temporary, path)


def _safe_members(archive, addon_id):
    members = []
    total = 0
    for member in archive.infolist():
        path = PurePosixPath(member.filename)
        mode = member.external_attr >> 16
        if (
            path.is_absolute()
            or not path.parts
            or path.parts[0] != addon_id
            or ".." in path.parts
            or stat.S_ISLNK(mode)
            or member.file_size < 0
        ):
            raise ValueError("unsafe candidate archive")
        members.append(member)
        total += member.file_size
    if not members or len(members) > MAX_FILES or total > MAX_BYTES:
        raise ValueError("candidate archive exceeds policy")
    return members


def _extract_candidate(archive_path, addon_id, output):
    with zipfile.ZipFile(archive_path) as archive:
        members = _safe_members(archive, addon_id)
        archive.extractall(output, members=members)
    root = output / addon_id
    addon = ElementTree.parse(root / "addon.xml").getroot()
    if addon.get("id") != addon_id or not addon.get("version"):
        raise ValueError("candidate identity mismatch")
    return root, addon.get("version")


def _extract_artifact_candidates(stage, addons, artifacts, directory, output):
    if (
        not isinstance(addons, dict)
        or not addons
        or not isinstance(artifacts, dict)
        or set(artifacts) != set(addons)
    ):
        raise ValueError("invalid required Flatpak artifact set")
    required_root = stage / directory
    if not required_root.is_dir() or required_root.is_symlink():
        raise ValueError("required Flatpak artifact directory is missing")
    candidates = {}
    for addon_id, version in addons.items():
        artifact = artifacts[addon_id]
        expected_filename = addon_id + ".zip"
        if (
            not SAFE_ADDON_ID.fullmatch(addon_id)
            or not isinstance(version, str)
            or not version
            or not isinstance(artifact, dict)
            or set(artifact) != {"filename", "sha256", "version"}
            or artifact.get("filename") != expected_filename
            or artifact.get("version") != version
            or not re.fullmatch(r"[0-9a-f]{64}", artifact.get("sha256", ""))
        ):
            raise ValueError("invalid required Flatpak artifact metadata")
        archive = required_root / expected_filename
        if (
            not archive.is_file()
            or archive.is_symlink()
            or hashlib.sha256(archive.read_bytes()).hexdigest()
            != artifact["sha256"]
        ):
            raise ValueError("required Flatpak artifact digest differs")
        root, candidate_version = _extract_candidate(
            archive, addon_id, output / addon_id
        )
        if candidate_version != version:
            raise ValueError("required Flatpak artifact version differs")
        candidates[addon_id] = root
    if {path.name for path in required_root.iterdir()} != {
        artifact["filename"] for artifact in artifacts.values()
    }:
        raise ValueError("unexpected required Flatpak artifact")
    return candidates


def _extract_required_candidates(stage, expected, output):
    return _extract_artifact_candidates(
        stage,
        expected.get("required_addons"),
        expected.get("required_artifacts"),
        "required",
        output,
    )


def _extract_dependency_candidates(stage, expected, output):
    artifacts = expected.get("dependency_artifacts")
    addons = (
        {
            addon_id: metadata.get("version")
            for addon_id, metadata in artifacts.items()
        }
        if isinstance(artifacts, dict)
        and all(isinstance(metadata, dict) for metadata in artifacts.values())
        else None
    )
    return _extract_artifact_candidates(
        stage, addons, artifacts, "dependencies", output
    )


def _extract_official_candidates(stage, expected, output):
    official = expected.get("official_addons")
    artifacts = expected.get("official_artifacts")
    addons = (
        {
            addon_id: metadata.get("version")
            for addon_id, metadata in official.items()
        }
        if isinstance(official, dict)
        and all(isinstance(metadata, dict) for metadata in official.values())
        else None
    )
    return _extract_artifact_candidates(
        stage, addons, artifacts, "official", output
    )


def _rpc(method, params):
    response = json.loads(
        xbmc.executeJSONRPC(
            json.dumps(
                {
                    "jsonrpc": "2.0",
                    "id": method,
                    "method": method,
                    "params": params,
                },
                separators=(",", ":"),
            )
        )
    )
    if "error" in response:
        raise RuntimeError("Kodi JSON-RPC rejected %s" % method)
    return response.get("result")


class KodiRpcUnavailable(RuntimeError):
    def __init__(self, code=None):
        super().__init__("Kodi JSON-RPC is not ready")
        self.code = code if isinstance(code, int) else None


def _wait_favourites_api(timeout=60):
    deadline = time.monotonic() + timeout
    last_code = None
    while time.monotonic() < deadline:
        try:
            response = json.loads(
                xbmc.executeJSONRPC(
                    json.dumps(
                        {
                            "jsonrpc": "2.0",
                            "id": "mwo-flatpak-readiness",
                            "method": "Favourites.GetFavourites",
                            "params": {
                                "properties": [
                                    "path",
                                    "window",
                                    "windowparameter",
                                    "thumbnail",
                                ]
                            },
                        },
                        separators=(",", ":"),
                    )
                )
            )
        except (TypeError, ValueError):
            response = None
        if isinstance(response, dict) and "error" not in response:
            return
        error = response.get("error") if isinstance(response, dict) else None
        last_code = error.get("code") if isinstance(error, dict) else None
        xbmc.sleep(2000)
    raise KodiRpcUnavailable(last_code)


def _enable(addon_id, timeout=30):
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        try:
            if _rpc(
                "Addons.SetAddonEnabled",
                {"addonid": addon_id, "enabled": True},
            ) == "OK":
                return
        except RuntimeError:
            pass
        xbmc.sleep(1000)
    raise RuntimeError("Kodi refused to enable %s" % addon_id)


def _enabled_addon(addon_id, timeout=30):
    """Enable a freshly discovered add-on before opening its settings."""

    _enable(addon_id, timeout=timeout)
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        try:
            return xbmcaddon.Addon(addon_id)
        except RuntimeError:
            xbmc.sleep(1000)
    raise RuntimeError("Kodi did not register enabled add-on %s" % addon_id)


def _addon_details(addon_id):
    try:
        return _rpc(
            "Addons.GetAddonDetails",
            {
                "addonid": addon_id,
                "properties": ["version", "enabled"],
            },
        )["addon"]
    except (KeyError, RuntimeError):
        return None


def _addon_openable(addon_id):
    try:
        xbmcaddon.Addon(addon_id)
        return True
    except RuntimeError:
        return False


def _version_tuple(value):
    if not isinstance(value, str) or not value or len(value) > 128:
        raise ValueError("invalid Kodi add-on version")
    match = re.match(r"^(\d+(?:\.\d+)*)", value)
    if not match:
        raise ValueError("unsupported Kodi add-on version")
    return tuple(int(part) for part in match.group(1).split("."))


def _version_at_least(actual, minimum):
    actual_parts = _version_tuple(actual)
    minimum_parts = _version_tuple(minimum)
    width = max(len(actual_parts), len(minimum_parts))
    return actual_parts + (0,) * (width - len(actual_parts)) >= (
        minimum_parts + (0,) * (width - len(minimum_parts))
    )


def _addon_database():
    databases = []
    database_root = xbmcvfs.translatePath("special://database")
    for path in glob.glob(os.path.join(database_root, "Addons*.db")):
        match = re.search(r"Addons(\d+)[.]db$", path)
        if match:
            databases.append((int(match.group(1)), path))
    if not databases:
        raise RuntimeError("Kodi add-on database is unavailable")
    return max(databases)[1]


def _installed_origin(addon_id):
    connection = sqlite3.connect(_addon_database())
    try:
        row = connection.execute(
            "SELECT origin FROM installed WHERE addonID=?", (addon_id,)
        ).fetchone()
    finally:
        connection.close()
    return row[0] if row else None


def _forget_native_official(addon_id):
    """Forget one qualified official add-on before an exact reinstall."""
    if not SAFE_ADDON_ID.fullmatch(addon_id):
        raise ValueError("invalid native official add-on identity")
    connection = sqlite3.connect(_addon_database())
    try:
        with connection:
            connection.execute(
                "DELETE FROM installed WHERE addonID=?", (addon_id,)
            )
            connection.execute(
                "DELETE FROM update_rules WHERE addonID=?", (addon_id,)
            )
            connection.execute(
                "DELETE FROM package WHERE addonID=?", (addon_id,)
            )
    finally:
        connection.close()


def _set_installed_origin(addon_id, origin):
    if (
        not SAFE_ADDON_ID.fullmatch(addon_id)
        or not isinstance(origin, str)
        or (origin and not SAFE_ADDON_ID.fullmatch(origin))
    ):
        raise ValueError("invalid native official origin assignment")
    connection = sqlite3.connect(_addon_database())
    try:
        with connection:
            cursor = connection.execute(
                "UPDATE installed SET origin=? WHERE addonID=?",
                (origin, addon_id),
            )
            if cursor.rowcount != 1:
                raise RuntimeError("native official add-on is not registered")
    finally:
        connection.close()


def _reconcile_required_addons(addons, timeout=120, stage=None):
    if (
        not isinstance(addons, dict)
        or not addons
        or any(
            not isinstance(addon_id, str)
            or not SAFE_ADDON_ID.fullmatch(addon_id)
            or not isinstance(version, str)
            or not version
            for addon_id, version in addons.items()
        )
    ):
        raise ValueError("invalid required add-on set")
    _enable(REPOSITORY_ID)
    xbmc.executebuiltin("UpdateAddonRepos")
    xbmc.sleep(5000)
    installed = {}
    for addon_id, expected_version in addons.items():
        request = stage / "install-request.json" if stage else None
        try:
            deadline = time.monotonic() + timeout
            next_install = 0
            while time.monotonic() < deadline:
                details = _addon_details(addon_id)
                if details:
                    if not details.get("enabled"):
                        _enable(addon_id)
                        details = _addon_details(addon_id)
                    if (
                        details
                        and details.get("enabled")
                        and str(details.get("version")) == expected_version
                        and _addon_openable(addon_id)
                    ):
                        installed[addon_id] = expected_version
                        break
                if time.monotonic() >= next_install:
                    if request:
                        _write_atomic(
                            request,
                            {"addon_id": addon_id, "schema": 1},
                        )
                    xbmc.executebuiltin("InstallAddon(%s)" % addon_id)
                    next_install = time.monotonic() + 10
                xbmc.sleep(2000)
            else:
                raise RuntimeError("Kodi could not install required add-on")
        finally:
            if request:
                request.unlink(missing_ok=True)
    return installed


def _reconcile_native_official(addons, timeout=180, stage=None):
    if not isinstance(addons, dict) or not addons:
        raise ValueError("invalid native official add-on set")
    for addon_id, metadata in addons.items():
        if (
            not isinstance(addon_id, str)
            or not SAFE_ADDON_ID.fullmatch(addon_id)
            or not isinstance(metadata, dict)
            or set(metadata)
            != {
                "dependency_requirements",
                "origin",
                "sha256",
                "version",
            }
            or metadata.get("origin") != "repository.xbmc.org"
            or not isinstance(metadata.get("version"), str)
            or not metadata["version"]
            or not re.fullmatch(r"[0-9a-f]{64}", metadata.get("sha256", ""))
        ):
            raise ValueError("invalid native official add-on policy")
        requirements = metadata.get("dependency_requirements")
        if not isinstance(requirements, dict) or any(
            not isinstance(dependency_id, str)
            or not SAFE_ADDON_ID.fullmatch(dependency_id)
            or not isinstance(requirement, dict)
            or not {"minimum_version", "type"}.issubset(requirement)
            or not set(requirement).issubset(
                {"minimum_version", "type", "supported_android_abis"}
            )
            or requirement.get("type") not in {"platform", "python"}
            or not isinstance(requirement.get("minimum_version"), str)
            or not requirement["minimum_version"]
            or (
                "supported_android_abis" in requirement
                and (
                    requirement.get("type") != "platform"
                    or not isinstance(requirement["supported_android_abis"], list)
                    or not requirement["supported_android_abis"]
                    or len(requirement["supported_android_abis"])
                    != len(set(requirement["supported_android_abis"]))
                    or any(
                        not isinstance(abi, str)
                        or not SAFE_ADDON_ID.fullmatch(abi)
                        for abi in requirement["supported_android_abis"]
                    )
                )
            )
            for dependency_id, requirement in requirements.items()
        ):
            raise ValueError("invalid native official dependency policy")

    _enable("repository.xbmc.org")
    xbmc.executebuiltin("UpdateAddonRepos")
    xbmc.sleep(5000)
    installed = {}
    for addon_id, metadata in addons.items():
        request = stage / "install-request.json" if stage else None
        try:
            deadline = time.monotonic() + timeout
            next_install = 0
            while time.monotonic() < deadline:
                details = _addon_details(addon_id)
                if details:
                    observed = str(details.get("version"))
                    expected = metadata["version"]
                    if _version_at_least(observed, expected) and observed != expected:
                        raise RuntimeError(
                            "native official add-on version is unqualified"
                        )
                    if not details.get("enabled"):
                        _enable(addon_id)
                        details = _addon_details(addon_id)
                    if (
                        details
                        and details.get("enabled")
                        and str(details.get("version")) == expected
                        and _addon_openable(addon_id)
                    ):
                        break
                if time.monotonic() >= next_install:
                    if request:
                        _write_atomic(
                            request, {"addon_id": addon_id, "schema": 1}
                        )
                    xbmc.executebuiltin("InstallAddon(%s)" % addon_id)
                    next_install = time.monotonic() + 10
                xbmc.sleep(2000)
            else:
                raise RuntimeError("Kodi could not install native official add-on")
        finally:
            if request:
                request.unlink(missing_ok=True)

        if _installed_origin(addon_id) != "repository.xbmc.org":
            raise RuntimeError("native official add-on origin differs")
        for dependency_id, requirement in metadata[
            "dependency_requirements"
        ].items():
            dependency = _addon_details(dependency_id)
            if (
                not dependency
                or not dependency.get("enabled")
                or not _version_at_least(
                    str(dependency.get("version")),
                    requirement["minimum_version"],
                )
            ):
                raise RuntimeError("native official dependency differs")
        installed[addon_id] = metadata["version"]
    return installed


def _configure_youtube(stage):
    script = stage / "youtube-configure.py"
    config = stage / "youtube-config.json"
    report_path = stage / "youtube-report.json"
    if not script.is_file() or script.is_symlink():
        raise ValueError("YouTube Flatpak adapter is missing")
    if not config.exists():
        return {
            "ok": True,
            "status": "API_CONFIG_REQUIRED",
            "authorization": "AUTHORIZATION_REQUIRED",
        }
    if not config.is_file() or config.is_symlink():
        raise ValueError("YouTube Flatpak private configuration is unsafe")
    previous_argv = sys.argv
    try:
        sys.argv = [str(script), str(config), str(report_path)]
        runpy.run_path(str(script), run_name="__main__")
    finally:
        sys.argv = previous_argv
    if not report_path.is_file() or report_path.is_symlink():
        raise RuntimeError("YouTube Flatpak adapter returned no report")
    report = json.loads(report_path.read_text(encoding="utf-8"))
    allowed = {
        "addon_id",
        "addon_version",
        "account_verified",
        "api_status",
        "authorization",
        "changed",
        "error_type",
        "http_loopback_only",
        "ok",
        "personal_api_configured",
        "rolled_back",
        "schema",
        "session_configured",
        "session_rolled_back",
        "setup_wizard_disabled",
        "stage",
    }
    if (
        not isinstance(report, dict)
        or not set(report).issubset(allowed)
        or report.get("schema") != 1
        or not report.get("ok")
    ):
        raise RuntimeError(
            "YouTube Flatpak adapter failed: %s at %s"
            % (
                report.get("error_type", "unknown")
                if isinstance(report, dict)
                else "invalid_report",
                report.get("stage", "unknown")
                if isinstance(report, dict)
                else "unknown",
            )
        )
    return report


def _verify_required_addons(addons, timeout=30):
    if (
        not isinstance(addons, dict)
        or not addons
        or any(
            not isinstance(addon_id, str)
            or not SAFE_ADDON_ID.fullmatch(addon_id)
            or not isinstance(version, str)
            or not version
            for addon_id, version in addons.items()
        )
    ):
        raise ValueError("invalid required add-on set")
    verified = {}
    for addon_id, expected_version in addons.items():
        _enable(addon_id, timeout=timeout)
        details = _addon_details(addon_id)
        if (
            not details
            or not details.get("enabled")
            or str(details.get("version")) != expected_version
        ):
            raise RuntimeError("Kodi did not register required stable add-on")
        verified[addon_id] = expected_version
    return verified


def _candidate_dependencies(candidates):
    managed = set(candidates)
    dependencies = set()
    for root in candidates.values():
        addon = ElementTree.parse(root / "addon.xml").getroot()
        for node in addon.findall("./requires/import"):
            addon_id = node.get("addon", "")
            if (
                node.get("optional", "false").lower() == "true"
                or addon_id == "xbmc.python"
                or addon_id in managed
            ):
                continue
            if not SAFE_ADDON_ID.fullmatch(addon_id):
                raise ValueError("invalid required dependency identity")
            dependencies.add(addon_id)
    return sorted(dependencies)


def _remove(path):
    if path.is_symlink() or path.is_file():
        path.unlink(missing_ok=True)
    elif path.is_dir():
        shutil.rmtree(path)


def _recover(journal, targets, backup):
    if not journal.is_file():
        return
    document = json.loads(journal.read_text(encoding="utf-8"))
    existing = document.get("existing")
    if document.get("schema") != 1 or not isinstance(existing, list):
        raise ValueError("invalid Flatpak rollout journal")
    for name, target in reversed(list(targets.items())):
        saved = backup / name
        if saved.exists():
            _remove(target)
            os.replace(saved, target)
        elif name not in existing:
            _remove(target)
    journal.unlink(missing_ok=True)
    _remove(backup)


def _identity(addon_xml, expected_id):
    addon = ElementTree.parse(addon_xml).getroot()
    if addon.get("id") != expected_id or not addon.get("version"):
        raise ValueError("installed add-on identity mismatch")
    return addon.get("version")


def _sync(profile_root, addon_root, profile_version, repository_version):
    profile_data = profile_root / "addon_data" / ADDON_ID
    _set_stage("wait_favourites_api")
    _wait_favourites_api()
    _set_stage("initialize_profile_sync")
    _enable(REPOSITORY_ID)
    addon_root_text = str(addon_root / ADDON_ID)
    if addon_root_text not in sys.path:
        sys.path.insert(0, addon_root_text)
    from resources.lib.mwoprofilesync.apply import (
        KodiAddonSettings,
        TransactionalApplier,
    )
    from resources.lib.mwoprofilesync.portable import (
        KodiFavourites,
        PortableFavouritesAdapter,
    )
    from resources.lib.mwoprofilesync.state import StateStore
    from resources.lib.mwoprofilesync.sync import ReadOnlySync

    addon = _enabled_addon(ADDON_ID)
    state = StateStore(profile_data)
    applier = TransactionalApplier(
        profile_data,
        state,
        KodiAddonSettings(xbmcaddon.Addon),
        portable=PortableFavouritesAdapter(
            str(profile_root), KodiFavourites(xbmc.executeJSONRPC)
        ),
    )
    applier.recover()
    _set_stage("apply_profile_sync")
    sync = ReadOnlySync(addon, state, applier=applier)()
    addon.setSetting("enabled", "true")
    local = state.read()
    enrollment = local.get("enrollment") or {}
    return {
        "ok": True,
        "profile_sync_version": profile_version,
        "repository_version": repository_version,
        "logical_device_id": enrollment.get("logical_device_id"),
        "status": local.get("status"),
        "sync_status": sync.get("status"),
        "assigned_revision": local.get("assigned_revision"),
        "applied_revision": local.get("applied_revision"),
        "pending_report": bool(local.get("pending_report")),
    }


def _paths(stage):
    addon_root = Path(xbmcvfs.translatePath("special://home/addons")).resolve()
    profile_root = Path(xbmcvfs.translatePath("special://profile")).resolve()
    temp_root = Path(xbmcvfs.translatePath("special://temp")).resolve()
    stage = stage.resolve()
    if stage.parent != temp_root or not SAFE_STAGE.fullmatch(stage.name):
        raise ValueError("unsafe Flatpak rollout stage")
    return stage, addon_root, profile_root


def _sync_existing(stage):
    _set_stage("validate_sync_receipt")
    stage, addon_root, profile_root = _paths(stage)
    expected = json.loads((stage / "expected.json").read_text(encoding="utf-8"))
    if set(expected) != {
        "logical_device_id",
        "profile_sync_version",
        "repository_version",
        "required_addons",
        "required_artifacts",
        "dependency_artifacts",
        "official_addons",
        "official_artifacts",
    }:
        raise ValueError("invalid Flatpak sync receipt")
    profile_version = _identity(
        addon_root / ADDON_ID / "addon.xml", ADDON_ID
    )
    repository_version = _identity(
        addon_root / REPOSITORY_ID / "addon.xml", REPOSITORY_ID
    )
    if (
        profile_version != expected["profile_sync_version"]
        or repository_version != expected["repository_version"]
    ):
        raise ValueError("installed Flatpak add-on version differs")
    _set_stage("reconcile_required_addons")
    required_addons = _reconcile_required_addons(
        expected["required_addons"]
    )
    _set_stage("reconcile_native_official")
    official_addons = _reconcile_native_official(
        expected["official_addons"]
    )
    _set_stage("configure_youtube")
    youtube = _configure_youtube(stage)
    _set_stage("apply_profile_sync")
    result = _sync(
        profile_root,
        addon_root,
        profile_version,
        repository_version,
    )
    if result["logical_device_id"] != expected["logical_device_id"]:
        raise ValueError("installed Flatpak enrollment identity differs")
    result["required_addons"] = required_addons
    result["official_addons"] = official_addons
    result["youtube"] = youtube
    return result


def _transaction(stage):
    _set_stage("validate_install_payload")
    stage, addon_root, profile_root = _paths(stage)
    supplied = stage / "profile-data"
    required = {
        "settings.xml",
        "state.json",
        "profile-sync-ca.pem",
    }
    if (
        not supplied.is_dir()
        or {item.name for item in supplied.iterdir()} != required
        or any(not item.is_file() or item.is_symlink() for item in supplied.iterdir())
    ):
        raise ValueError("invalid Profile Sync configuration payload")
    work = stage / "work"
    backup = stage / "backup"
    journal = stage / "journal.json"
    targets = {
        "profile-addon": addon_root / ADDON_ID,
        "repository-addon": addon_root / REPOSITORY_ID,
        "profile-data": profile_root / "addon_data" / ADDON_ID,
    }
    expected = json.loads(
        (stage / "expected.json").read_text(encoding="utf-8")
    )
    if set(expected) != {
        "dependency_artifacts",
        "logical_device_id",
        "profile_sync_version",
        "repository_version",
        "required_addons",
        "required_artifacts",
        "official_addons",
        "official_artifacts",
    }:
        raise ValueError("invalid Flatpak installation receipt")
    expected_required = expected.get("required_addons")
    expected_dependencies = expected.get("dependency_artifacts")
    expected_official = expected.get("official_addons")
    if (
        not isinstance(expected_required, dict)
        or not expected_required
        or any(
            not isinstance(addon_id, str)
            or not SAFE_ADDON_ID.fullmatch(addon_id)
            for addon_id in expected_required
        )
    ):
        raise ValueError("invalid required Flatpak add-on set")
    if (
        not isinstance(expected_dependencies, dict)
        or not expected_dependencies
        or any(
            not isinstance(addon_id, str)
            or not SAFE_ADDON_ID.fullmatch(addon_id)
            for addon_id in expected_dependencies
        )
    ):
        raise ValueError("invalid Flatpak dependency artifact set")
    if set(expected_required) & set(expected_dependencies):
        raise ValueError("Flatpak dependency artifacts overlap managed add-ons")
    if (
        not isinstance(expected_official, dict)
        or not expected_official
        or set(expected_official)
        & (set(expected_required) | set(expected_dependencies))
    ):
        raise ValueError("invalid native official Flatpak add-on set")
    targets.update(
        {
            "required-" + addon_id: addon_root / addon_id
            for addon_id in expected_required
        }
    )
    targets.update(
        {
            "dependency-" + addon_id: addon_root / addon_id
            for addon_id in expected_dependencies
        }
    )
    targets.update(
        {
            "official-" + addon_id: addon_root / addon_id
            for addon_id in expected_official
        }
    )
    for target in targets.values():
        if target.parent not in {addon_root, profile_root / "addon_data"}:
            raise ValueError("unsafe Flatpak rollout target")
    _set_stage("recover_previous_transaction")
    _recover(journal, targets, backup)
    _remove(work)
    work.mkdir(mode=0o700)
    _set_stage("extract_verified_artifacts")
    profile_candidate, profile_version = _extract_candidate(
        stage / "profile-sync.zip", ADDON_ID, work / "profile"
    )
    repository_candidate, repository_version = _extract_candidate(
        stage / "repository.zip", REPOSITORY_ID, work / "repository"
    )
    required_candidates = _extract_required_candidates(
        stage, expected, work / "required"
    )
    dependency_candidates = _extract_dependency_candidates(
        stage, expected, work / "dependencies"
    )
    official_candidates = _extract_official_candidates(
        stage, expected, work / "official"
    )
    all_candidates = {
        **required_candidates,
        **dependency_candidates,
        **official_candidates,
    }
    platform_dependencies = {
        dependency_id
        for metadata in expected_official.values()
        for dependency_id, requirement in metadata[
            "dependency_requirements"
        ].items()
        if requirement.get("type") == "platform"
    }
    if set(_candidate_dependencies(all_candidates)) - platform_dependencies:
        raise ValueError("Flatpak dependency artifact closure is incomplete")
    official_previous_origins = {
        addon_id: _installed_origin(addon_id)
        for addon_id in expected_official
        if _addon_details(addon_id) is not None
    }
    official_reinstalls = {
        addon_id
        for addon_id, metadata in expected_official.items()
        if (
            (details := _addon_details(addon_id)) is not None
            and (
                str(details.get("version")) != metadata["version"]
                or official_previous_origins.get(addon_id)
                != "repository.xbmc.org"
            )
        )
    }
    existing = [name for name, target in targets.items() if target.exists()]
    backup.mkdir(mode=0o700)
    _write_atomic(journal, {"schema": 1, "existing": existing})
    try:
        _set_stage("install_verified_artifacts")
        for name, target in targets.items():
            if name in existing:
                os.replace(target, backup / name)
            target.parent.mkdir(parents=True, exist_ok=True)
        os.replace(profile_candidate, targets["profile-addon"])
        os.replace(repository_candidate, targets["repository-addon"])
        os.replace(supplied, targets["profile-data"])
        for addon_id, candidate in required_candidates.items():
            os.replace(candidate, targets["required-" + addon_id])
        for addon_id, candidate in dependency_candidates.items():
            os.replace(candidate, targets["dependency-" + addon_id])
        for addon_id, candidate in official_candidates.items():
            os.replace(candidate, targets["official-" + addon_id])
        for addon_id in official_reinstalls:
            _forget_native_official(addon_id)
        xbmc.executebuiltin("UpdateLocalAddons")
        xbmc.sleep(3000)
        for addon_id in expected_official:
            _set_installed_origin(addon_id, "repository.xbmc.org")
        _set_stage("reconcile_required_addons")
        _reconcile_required_addons(
            expected["required_addons"], stage=stage
        )
        _set_stage("verify_required_addons")
        required_addons = _verify_required_addons(
            expected["required_addons"]
        )
        _set_stage("reconcile_native_official")
        official_addons = _reconcile_native_official(
            expected["official_addons"], stage=stage
        )
        _set_stage("configure_youtube")
        youtube = _configure_youtube(stage)
        _set_stage("apply_profile_sync")
        result = _sync(
            profile_root,
            addon_root,
            profile_version,
            repository_version,
        )
        journal.unlink(missing_ok=True)
        _remove(backup)
        _remove(work)
    except BaseException:
        _recover(journal, targets, backup)
        xbmc.executebuiltin("UpdateLocalAddons")
        xbmc.sleep(3000)
        for addon_id, origin in official_previous_origins.items():
            try:
                _set_installed_origin(addon_id, origin or "")
            except BaseException:
                pass
        raise
    result["required_addons"] = required_addons
    result["official_addons"] = official_addons
    result["youtube"] = youtube
    return result


def main():
    stage = Path(sys.argv[1]) if len(sys.argv) == 3 else Path("/")
    mode = sys.argv[2] if len(sys.argv) == 3 else "invalid"
    marker = stage / MARKER_NAME
    try:
        if mode == "install":
            result = _transaction(stage)
        elif mode == "sync":
            result = _sync_existing(stage)
        else:
            raise ValueError("invalid Flatpak rollout mode")
    except BaseException as error:
        result = {
            "ok": False,
            "error_type": type(error).__name__,
            "error_code": _safe_error_code(error),
            "error_origin": _safe_error_origin(error),
            "error_stage": CURRENT_STAGE,
        }
    try:
        _write_atomic(marker, result)
    except BaseException as error:
        _write_atomic(
            marker,
            {
                "ok": False,
                "error_type": type(error).__name__,
                "error_code": _safe_error_code(error),
                "error_origin": _safe_error_origin(error),
                "error_stage": CURRENT_STAGE,
            },
        )
    finally:
        xbmc.sleep(1000)
        xbmc.executebuiltin("Quit")


if __name__ == "__main__":
    main()
