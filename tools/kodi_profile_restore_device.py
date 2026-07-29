"""Restore a verified Kodi profile archive from inside the Kodi process."""

import hashlib
import json
import os
import sys
import tarfile
import xml.etree.ElementTree as ET


def _digest(payload):
    return hashlib.sha256(payload).hexdigest()


def _write_marker(path, value):
    temporary = path + ".tmp"
    with open(temporary, "w", encoding="utf-8") as handle:
        json.dump(value, handle, sort_keys=True)
        handle.flush()
        os.fsync(handle.fileno())
    os.replace(temporary, path)


def _claim_marker(path, operation_id=None):
    document = {"started": True}
    if operation_id is not None:
        document["operation_id"] = operation_id
    payload = json.dumps(document, sort_keys=True).encode("utf-8")
    try:
        descriptor = os.open(
            path,
            os.O_CREAT | os.O_EXCL | os.O_WRONLY,
            0o600,
        )
    except FileExistsError:
        return False
    try:
        written = 0
        while written < len(payload):
            count = os.write(descriptor, payload[written:])
            if count <= 0:
                raise OSError("started marker write did not progress")
            written += count
        os.fsync(descriptor)
    finally:
        os.close(descriptor)
    return True


def _open_manifest(archive):
    manifest_member = archive.getmember("restore-manifest.json")
    manifest_handle = archive.extractfile(manifest_member)
    if manifest_handle is None:
        raise ValueError("restore manifest is not readable")
    return json.loads(manifest_handle.read().decode("utf-8"))


def _selection_digest(files):
    payload = json.dumps(
        files,
        ensure_ascii=False,
        separators=(",", ":"),
        sort_keys=True,
    ).encode("utf-8")
    return _digest(payload)


def _settings_values(payload):
    root = ET.fromstring(payload)
    values = {}
    for setting in root.findall(".//setting"):
        setting_id = setting.attrib.get("id")
        if not setting_id:
            raise ValueError("add-on settings contain an entry without an ID")
        if setting_id in values:
            raise ValueError("add-on settings contain a duplicate ID")
        values[setting_id] = setting.text or ""
    return values


def _settings_digest(values):
    payload = json.dumps(
        values,
        ensure_ascii=False,
        separators=(",", ":"),
        sort_keys=True,
    ).encode("utf-8")
    return _digest(payload)


def _apply_addon_settings(addon, payload, expected):
    settings = _settings_values(payload)
    if sorted(settings) != expected["setting_ids"]:
        raise ValueError("restore add-on settings inventory mismatch")
    preimage = {
        setting_id: addon.getSetting(setting_id)
        for setting_id in settings
    }
    try:
        for setting_id, value in settings.items():
            result = addon.setSetting(setting_id, value)
            if result is False or addon.getSetting(setting_id) != value:
                raise ValueError("Kodi rejected an add-on setting")
    except Exception:
        rollback_failed = False
        for setting_id, original in reversed(tuple(preimage.items())):
            try:
                result = addon.setSetting(setting_id, original)
                if (
                    result is False
                    or addon.getSetting(setting_id) != original
                ):
                    rollback_failed = True
            except Exception:
                rollback_failed = True
        if rollback_failed:
            raise RuntimeError("add-on settings rollback failed")
        raise


def _verify_current(home, manifest):
    verified = 0
    for relative, expected in manifest["files"].items():
        parts = relative.split("/")
        if not relative or any(part in ("", ".", "..") for part in parts):
            raise ValueError("unsafe restore path")
        target = os.path.realpath(os.path.join(home, *parts))
        if target != home and not target.startswith(home + os.sep):
            raise ValueError("restore target escaped Kodi home")
        with open(target, "rb") as handle:
            if "settings_sha256" in expected:
                current = _settings_values(handle.read())
                selected = {
                    setting_id: current[setting_id]
                    for setting_id in expected["setting_ids"]
                }
                if (
                    _settings_digest(selected)
                    != expected["settings_sha256"]
                ):
                    raise ValueError(
                        "restored add-on settings verification mismatch"
                    )
                verified += 1
                continue
            checksum = hashlib.sha256()
            size = 0
            for block in iter(lambda: handle.read(1024 * 1024), b""):
                checksum.update(block)
                size += len(block)
        if (
            checksum.hexdigest() != expected["sha256"]
            or size != expected["size"]
        ):
            raise ValueError("restored file verification mismatch")
        verified += 1
    return verified


def main():
    import xbmcvfs
    import xbmcaddon

    archive_path, marker_path = sys.argv[1:3]
    started_path = sys.argv[3] if len(sys.argv) > 3 else None
    operation_id = sys.argv[4] if len(sys.argv) > 4 else None
    mode = sys.argv[5] if len(sys.argv) > 5 else "restore"
    home = os.path.realpath(xbmcvfs.translatePath("special://home"))
    restored = 0
    selection_sha256 = None
    try:
        if mode not in {"restore", "verify"}:
            raise ValueError("unsupported restore mode")
        if started_path is not None and not _claim_marker(
            started_path,
            operation_id,
        ):
            # A retried EventServer command for the same staged operation may
            # already be queued. Only the invocation that atomically claimed
            # the marker is allowed to modify the profile.
            return
        with tarfile.open(archive_path, "r:") as archive:
            manifest = _open_manifest(archive)
            if (
                operation_id is not None
                and manifest.get("operation_id") != operation_id
            ):
                raise ValueError("restore operation identifier mismatch")
            selection_sha256 = _selection_digest(manifest["files"])
            if manifest.get("selection_sha256") != selection_sha256:
                raise ValueError("restore selection digest mismatch")
            if mode == "verify":
                verified = _verify_current(home, manifest)
                _write_marker(
                    marker_path,
                    {
                        "ok": True,
                        "operation_id": manifest.get("operation_id"),
                        "selection_sha256": manifest.get(
                            "selection_sha256"
                        ),
                        "snapshot_id": manifest["snapshot_id"],
                        "verified_files": verified,
                    },
                )
                return
            expected = manifest["files"]
            seen = set()
            for member in archive:
                if member.name == "restore-manifest.json" or member.isdir():
                    continue
                if not member.isfile() or not member.name.startswith("payload/"):
                    raise ValueError("unsafe restore member")
                relative = member.name[len("payload/") :]
                parts = relative.split("/")
                if not relative or any(part in ("", ".", "..") for part in parts):
                    raise ValueError("unsafe restore path")
                if relative not in expected:
                    raise ValueError("unexpected restore file")
                source = archive.extractfile(member)
                payload = source.read() if source else b""
                if _digest(payload) != expected[relative]["sha256"]:
                    raise ValueError("restore payload digest mismatch")
                target = os.path.realpath(os.path.join(home, *parts))
                if target != home and not target.startswith(home + os.sep):
                    raise ValueError("restore target escaped Kodi home")
                if "settings_sha256" in expected[relative]:
                    addon_id = parts[2]
                    addon = xbmcaddon.Addon(addon_id)
                    _apply_addon_settings(
                        addon,
                        payload,
                        expected[relative],
                    )
                    seen.add(relative)
                    restored += 1
                    continue
                os.makedirs(os.path.dirname(target), exist_ok=True)
                temporary = target + ".mwo-restore"
                with open(temporary, "wb") as handle:
                    handle.write(payload)
                    handle.flush()
                    os.fsync(handle.fileno())
                os.replace(temporary, target)
                seen.add(relative)
                restored += 1
            if seen != set(expected):
                raise ValueError("restore archive inventory mismatch")
        _write_marker(
            marker_path,
            {
                "ok": True,
                "operation_id": manifest.get("operation_id"),
                "restored_files": restored,
                "selection_sha256": manifest.get("selection_sha256"),
                "snapshot_id": manifest["snapshot_id"],
            },
        )
    except Exception as exc:
        _write_marker(
            marker_path,
            {
                "ok": False,
                "error_type": type(exc).__name__,
                "operation_id": operation_id,
                "selection_sha256": selection_sha256,
            },
        )


if __name__ == "__main__":
    main()
