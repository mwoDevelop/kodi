"""Crash-safe exact add-on transaction executed inside Kodi.

The host invokes this file with ``RunScript``. Transaction state and backup live
under ``special://home`` so a host disconnect or Kodi restart can be recovered
by a later rollout without knowing an earlier random operation identifier.
"""

import base64
import json
import os
import re
import shutil
import stat
import sys
import uuid
from pathlib import Path, PurePosixPath
from xml.etree import ElementTree
from zipfile import ZipFile

import xbmcvfs

SAFE_ID = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._-]{0,127}$")
MAX_FILES = 10_000
MAX_BYTES = 64 * 1024 * 1024


def _fsync_directory(path):
    descriptor = os.open(str(path), os.O_RDONLY)
    try:
        os.fsync(descriptor)
    finally:
        os.close(descriptor)


def _atomic_json(path, value, sync_directory=True):
    temporary = path.with_name(".%s-%s.tmp" % (path.name, uuid.uuid4().hex))
    payload = json.dumps(value, sort_keys=True, separators=(",", ":")) + "\n"
    with temporary.open("w", encoding="utf-8") as handle:
        handle.write(payload)
        handle.flush()
        os.fsync(handle.fileno())
    os.replace(temporary, path)
    if sync_directory:
        _fsync_directory(path.parent)


def _identity(addon_xml):
    payload = addon_xml.read_bytes()
    lowered = payload.lower()
    if b"<!doctype" in lowered or b"<!entity" in lowered:
        raise ValueError("addon.xml contains forbidden XML declarations")
    root = ElementTree.fromstring(payload.decode("utf-8-sig"))
    return root.attrib.get("id"), root.attrib.get("version")


def _safe_members(archive, addon_id):
    members = []
    names = set()
    folded = set()
    total = 0
    for member in archive.infolist():
        name = member.filename
        path = PurePosixPath(name)
        if (
            "\\" in name
            or "\x00" in name
            or path.is_absolute()
            or not path.parts
            or path.parts[0] != addon_id
            or ".." in path.parts
        ):
            raise ValueError("unsafe candidate archive path")
        normalized = path.as_posix().rstrip("/")
        folded_name = normalized.casefold()
        if normalized in names or folded_name in folded:
            raise ValueError("candidate archive contains duplicate paths")
        names.add(normalized)
        folded.add(folded_name)
        mode = member.external_attr >> 16
        file_type = stat.S_IFMT(mode)
        if (
            member.flag_bits & 0x1
            or stat.S_ISLNK(mode)
            or file_type not in {0, stat.S_IFREG, stat.S_IFDIR}
        ):
            raise ValueError("candidate archive contains an unsafe entry")
        total += member.file_size
        members.append(member)
    if not members or len(members) > MAX_FILES or total > MAX_BYTES:
        raise ValueError("candidate archive exceeds policy")
    return members


def _paths(addon_id):
    if not SAFE_ID.fullmatch(addon_id):
        raise ValueError("unsafe add-on id")
    addon_root = Path(xbmcvfs.translatePath("special://home/addons")).resolve()
    transaction_root = Path(
        xbmcvfs.translatePath("special://home/.mwodevelop-transactions")
    ).resolve()
    transaction_root.mkdir(parents=True, exist_ok=True)
    addon_root.mkdir(parents=True, exist_ok=True)
    if addon_root.stat().st_dev != transaction_root.stat().st_dev:
        raise RuntimeError("transaction and add-on roots differ by filesystem")
    transaction = transaction_root / addon_id
    target = addon_root / addon_id
    if transaction.parent != transaction_root or target.parent != addon_root:
        raise ValueError("unsafe transaction target")
    return {
        "addon_root": addon_root,
        "transaction_root": transaction_root,
        "transaction": transaction,
        "journal": transaction / "journal.json",
        "staging": transaction / "staging",
        "backup": transaction / "backup",
        "target": target,
    }


def _load(paths):
    if not paths["journal"].is_file():
        return None
    value = json.loads(paths["journal"].read_text(encoding="utf-8"))
    if (
        not isinstance(value, dict)
        or value.get("schema") != 1
        or value.get("addon_id") != paths["transaction"].name
    ):
        raise RuntimeError("transaction journal is invalid")
    return value


def _decode_context(value):
    if not value:
        return {"enabled": None, "origin": None}
    padding = "=" * (-len(value) % 4)
    decoded = base64.urlsafe_b64decode((value + padding).encode("ascii"))
    context = json.loads(decoded.decode("utf-8"))
    if not isinstance(context, dict) or set(context) != {"enabled", "origin"}:
        raise ValueError("transaction context is invalid")
    if context["enabled"] not in {True, False, None} or (
        context["origin"] is not None
        and not isinstance(context["origin"], str)
    ):
        raise ValueError("transaction context values are invalid")
    return context


def _prepare(zip_path, addon_id, expected_version, context_value, repair_orphan=False):
    stage = "validate"
    try:
        paths = _paths(addon_id)
        if _load(paths) is not None or paths["transaction"].exists() and any(
            paths["transaction"].iterdir()
        ):
            raise RuntimeError("RECOVERY_REQUIRED: active transaction exists")
        context = _decode_context(context_value)
        paths["transaction"].mkdir(parents=False, exist_ok=True)
        _fsync_directory(paths["transaction_root"])
        paths["staging"].mkdir()
        stage = "extract-candidate"
        with ZipFile(zip_path) as archive:
            members = _safe_members(archive, addon_id)
            archive.extractall(paths["staging"], members=members)
        candidate = paths["staging"] / addon_id
        stage = "verify-candidate"
        found_id, found_version = _identity(candidate / "addon.xml")
        if found_id != addon_id or found_version != expected_version:
            raise ValueError("candidate identity mismatch")
        previous = {
            "exists": paths["target"].exists(),
            "enabled": context["enabled"],
            "origin": context["origin"],
            "version": None,
        }
        if previous["exists"]:
            previous_id, previous["version"] = _identity(
                paths["target"] / "addon.xml"
            )
            if previous_id != addon_id:
                raise ValueError("installed add-on identity mismatch")
        journal = {
            "schema": 1,
            "transaction_id": uuid.uuid4().hex,
            "addon_id": addon_id,
            "candidate_version": expected_version,
            "previous": previous,
            "state": "PREPARED",
        }
        _atomic_json(paths["journal"], journal)
        stage = "backup-installed-addon"
        repaired_orphan = False
        if previous["exists"]:
            try:
                os.replace(paths["target"], paths["backup"])
            except PermissionError:
                if not repair_orphan or paths["target"].is_symlink():
                    raise
                existing_id, _existing_version = _identity(
                    paths["target"] / "addon.xml"
                )
                if existing_id != addon_id:
                    raise ValueError("orphan add-on identity mismatch")
                shutil.rmtree(paths["target"])
                previous["exists"] = False
                journal["previous"] = previous
                repaired_orphan = True
                _atomic_json(paths["journal"], journal)
        stage = "activate-candidate"
        os.replace(candidate, paths["target"])
        _fsync_directory(paths["addon_root"])
        installed_id, installed_version = _identity(
            paths["target"] / "addon.xml"
        )
        if installed_id != addon_id or installed_version != expected_version:
            raise ValueError("installed candidate identity mismatch")
        journal["state"] = "ACTIVATED"
        journal["repaired_orphan"] = repaired_orphan
        _atomic_json(paths["journal"], journal)
        return {
            "status": "ACTIVATED",
            "transaction_id": journal["transaction_id"],
            "files": len(members),
            "version": expected_version,
            "repaired_orphan": repaired_orphan,
        }
    except Exception as error:
        error.apply_stage = stage
        raise


def _status(addon_id):
    paths = _paths(addon_id)
    journal = _load(paths)
    if journal is None:
        if paths["transaction"].exists() and any(
            paths["transaction"].iterdir()
        ):
            return {
                "status": "RECOVERY_REQUIRED",
                "addon_id": addon_id,
                "reason": "transaction journal is absent",
            }
        return {"status": "NO_CHANGE", "addon_id": addon_id}
    return {
        "status": journal["state"],
        "addon_id": addon_id,
        "transaction_id": journal["transaction_id"],
        "candidate_version": journal["candidate_version"],
        "previous": journal["previous"],
    }


def _verify(addon_id, expected_version, context_value):
    paths = _paths(addon_id)
    journal = _load(paths)
    if journal is None or journal.get("state") != "ACTIVATED":
        raise RuntimeError("transaction is not activated")
    if journal["candidate_version"] != expected_version:
        raise RuntimeError("transaction candidate version differs")
    installed_id, installed_version = _identity(paths["target"] / "addon.xml")
    if installed_id != addon_id or installed_version != expected_version:
        raise RuntimeError("activated candidate identity differs")
    journal["observed"] = _decode_context(context_value)
    journal["state"] = "VERIFIED"
    _atomic_json(paths["journal"], journal)
    return {
        "status": "VERIFIED",
        "addon_id": addon_id,
        "transaction_id": journal["transaction_id"],
        "version": expected_version,
    }


def _commit(addon_id):
    paths = _paths(addon_id)
    journal = _load(paths)
    if journal is None:
        return {"status": "NO_CHANGE", "addon_id": addon_id}
    if journal.get("state") != "VERIFIED":
        raise RuntimeError("transaction is not verified")
    transaction_id = journal["transaction_id"]
    shutil.rmtree(paths["backup"], ignore_errors=True)
    shutil.rmtree(paths["staging"], ignore_errors=True)
    paths["journal"].unlink()
    _fsync_directory(paths["transaction"])
    paths["transaction"].rmdir()
    _fsync_directory(paths["transaction_root"])
    return {
        "status": "COMMITTED",
        "addon_id": addon_id,
        "transaction_id": transaction_id,
    }


def _rollback(addon_id):
    paths = _paths(addon_id)
    journal = _load(paths)
    if journal is None:
        if paths["transaction"].exists():
            shutil.rmtree(paths["transaction"])
            _fsync_directory(paths["transaction_root"])
            return {
                "status": "ROLLED_BACK",
                "addon_id": addon_id,
                "previous": None,
            }
        return {"status": "NO_CHANGE", "addon_id": addon_id}
    transaction_id = journal["transaction_id"]
    previous = journal["previous"]
    if previous["exists"]:
        if paths["backup"].is_dir():
            if paths["target"].exists():
                shutil.rmtree(paths["target"])
            os.replace(paths["backup"], paths["target"])
        else:
            if not paths["target"].is_dir():
                raise RuntimeError(
                    "RECOVERY_REQUIRED: transaction backup is missing"
                )
            target_id, target_version = _identity(
                paths["target"] / "addon.xml"
            )
            if (
                target_id != addon_id
                or target_version != previous["version"]
            ):
                raise RuntimeError(
                    "RECOVERY_REQUIRED: transaction backup is missing"
                )
    elif paths["target"].exists():
        shutil.rmtree(paths["target"])
    _fsync_directory(paths["addon_root"])
    shutil.rmtree(paths["transaction"])
    _fsync_directory(paths["transaction_root"])
    return {
        "status": "ROLLED_BACK",
        "addon_id": addon_id,
        "transaction_id": transaction_id,
        "previous": previous,
    }


def _run(arguments):
    action = arguments[0] if arguments else ""
    if action == "prepare" and len(arguments) in {6, 7}:
        return _prepare(
            arguments[1],
            arguments[2],
            arguments[3],
            arguments[4],
            repair_orphan=len(arguments) == 7 and arguments[5] == "repair-orphan",
        ), arguments[-1]
    if action == "status" and len(arguments) == 3:
        return _status(arguments[1]), arguments[2]
    if action == "verify" and len(arguments) == 5:
        return _verify(arguments[1], arguments[2], arguments[3]), arguments[4]
    if action == "commit" and len(arguments) == 3:
        return _commit(arguments[1]), arguments[2]
    if action == "rollback" and len(arguments) == 3:
        return _rollback(arguments[1]), arguments[2]
    raise ValueError("invalid transaction action arguments")


def main():
    marker = ""
    result = {"ok": False, "schema": 1}
    try:
        result_value, marker = _run(sys.argv[1:])
        result.update(result_value)
        result["ok"] = True
    except Exception as error:  # noqa: BLE001 - Kodi process boundary
        result["error_type"] = type(error).__name__
        result["error_stage"] = getattr(error, "apply_stage", "unknown")
        result["error"] = str(error)
        if len(sys.argv) > 1:
            candidates = [item for item in sys.argv[1:] if item.endswith(".json")]
            marker = candidates[-1] if candidates else ""
    if marker:
        marker_path = Path(marker)
        marker_path.parent.mkdir(parents=True, exist_ok=True)
        _atomic_json(marker_path, result, sync_directory=False)


if __name__ == "__main__":
    main()
