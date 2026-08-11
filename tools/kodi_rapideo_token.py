#!/usr/bin/env python3
"""Export the authoritative Rapideo token without exposing it in reports."""

from __future__ import annotations

import argparse
import hashlib
import io
import json
import os
import pickle
import stat
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from tools.kodi_profile import adb_command
from tools.kodi_sync_inventory import load_sync_inventory


REMOTE_AUTH = (
    "/sdcard/Android/data/org.xbmc.kodi/files/.kodi/userdata/addon_data/"
    "plugin.video.rapideo_pl/.storage/auth"
)


class _RestrictedUnpickler(pickle.Unpickler):
    def find_class(self, module, name):
        raise pickle.UnpicklingError("Rapideo token cache contains a global")


def _token(payload: bytes) -> str:
    value = _RestrictedUnpickler(io.BytesIO(payload)).load()
    if not isinstance(value, dict):
        raise ValueError("Rapideo auth store is invalid")
    stored = value.get("authtoken")
    token = (
        stored[0]
        if isinstance(stored, tuple)
        and len(stored) == 2
        and isinstance(stored[1], (int, float))
        else stored
    )
    if not isinstance(token, str) or not token or len(token) > 2048:
        raise ValueError("Rapideo auth store has no valid token")
    return token


def export_token(repository: Path, device: str, output: Path, adb: str, port: int):
    inventory = load_sync_inventory(repository)
    if device not in inventory["devices"]:
        raise ValueError("unknown Rapideo token publisher")
    target = inventory["devices"][device]
    if target["platform"] not in {"android", "android-emulator"}:
        raise ValueError("Rapideo token publisher must use Android")
    serial = target["endpoints"]["adb"]
    with tempfile.TemporaryDirectory(prefix=".rapideo-auth-") as temporary:
        downloaded = Path(temporary) / "auth"
        adb_command(
            adb,
            port,
            serial,
            "pull",
            REMOTE_AUTH,
            str(downloaded),
            timeout=30,
        )
        token = _token(downloaded.read_bytes())
    output = Path(output).resolve()
    private_root = (repository / ".kodi-private").resolve()
    if private_root not in output.parents:
        raise ValueError("Rapideo token output must be private")
    output.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
    output.parent.chmod(0o700)
    payload = (
        json.dumps({"schema": 1, "authtoken": token}, sort_keys=True) + "\n"
    ).encode("utf-8")
    descriptor, name = tempfile.mkstemp(prefix=".token-", dir=output.parent)
    temporary_path = Path(name)
    try:
        with os.fdopen(descriptor, "wb") as handle:
            handle.write(payload)
            handle.flush()
            os.fsync(handle.fileno())
        os.chmod(temporary_path, 0o600)
        os.replace(temporary_path, output)
    finally:
        temporary_path.unlink(missing_ok=True)
    metadata = output.lstat()
    if not stat.S_ISREG(metadata.st_mode) or stat.S_IMODE(metadata.st_mode) != 0o600:
        raise RuntimeError("Rapideo token output permissions differ")
    return {
        "schema": 1,
        "device": device,
        "token_sha256": hashlib.sha256(token.encode("utf-8")).hexdigest(),
        "output": str(output.relative_to(repository)),
    }


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("command", choices=("export",))
    parser.add_argument("--device", required=True)
    parser.add_argument("--output", default=".kodi-private/rapideo/token.json")
    parser.add_argument("--adb", default="/home/mwo/android-sdk/platform-tools/adb")
    parser.add_argument("--adb-server-port", type=int, default=5038)
    args = parser.parse_args()
    result = export_token(
        ROOT,
        args.device,
        ROOT / args.output,
        args.adb,
        args.adb_server_port,
    )
    print(json.dumps(result, indent=2, sort_keys=True))


if __name__ == "__main__":
    main()
