"""Restore a verified Kodi profile archive from inside the Kodi process."""

import hashlib
import json
import os
import sys
import tarfile

import xbmcvfs


def _digest(payload):
    return hashlib.sha256(payload).hexdigest()


def _write_marker(path, value):
    temporary = path + ".tmp"
    with open(temporary, "w", encoding="utf-8") as handle:
        json.dump(value, handle, sort_keys=True)
        handle.flush()
        os.fsync(handle.fileno())
    os.replace(temporary, path)


def main():
    archive_path, marker_path = sys.argv[1:3]
    home = os.path.realpath(xbmcvfs.translatePath("special://home"))
    restored = 0
    try:
        with tarfile.open(archive_path, "r:") as archive:
            manifest_member = archive.getmember("restore-manifest.json")
            manifest_handle = archive.extractfile(manifest_member)
            manifest = json.loads(manifest_handle.read().decode("utf-8"))
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
                "restored_files": restored,
                "snapshot_id": manifest["snapshot_id"],
            },
        )
    except Exception as exc:
        _write_marker(
            marker_path,
            {"ok": False, "error_type": type(exc).__name__},
        )


if __name__ == "__main__":
    main()
