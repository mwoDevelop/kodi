#!/usr/bin/env python3
"""Prove RFC 9180 X25519/ChaCha20-Poly1305 inside Kodi with canary data."""

from __future__ import annotations

import argparse
import json
import subprocess
import tempfile
import time
from pathlib import Path

from pyhpke import AEADId, CipherSuite, KDFId, KEMId

from kodi_secret_broker.crypto import seal
from kodi_secret_broker.model import b64url_encode
from tools.kodi_devices import load_registry, resolve_device
from tools.kodi_profile import AdbEventClient, adb_command, adb_output


REMOTE_SCRIPT = "/sdcard/Download/.mwo-profile-sync-hpke-spike.py"
REMOTE_RESULT = "/sdcard/Download/.mwo-profile-sync-hpke-result.json"


def _envelope():
    suite = CipherSuite.new(
        KEMId.DHKEM_X25519_HKDF_SHA256,
        KDFId.HKDF_SHA256,
        AEADId.CHACHA20_POLY1305,
    )
    pair = suite.kem.derive_key_pair(b"mwo-hpke-device-canary-seed-0001")
    public = b64url_encode(pair.public_key.to_public_bytes())
    private = b64url_encode(pair.private_key.to_private_bytes())
    now = int(time.time())
    metadata = {
        "schema": 1,
        "envelope_type": "secret-envelope-v1",
        "secret_type": "youtube-session-v1",
        "secret_set_id": "synthetic-canary",
        "secret_set_generation": 1,
        "secret_lifecycle": "PREPARED",
        "logical_device_id": "synthetic-device",
        "enrollment_id": "enr:syntheticcanary001",
        "enrollment_generation": 1,
        "encryption_key_id": "synthetic-x25519-key",
        "adapter": "youtube-oauth-v1",
        "addon_id": "plugin.video.youtube",
        "addon_version": "7.4.4",
        "nonce": "synthetic-nonce-0001",
        "issued_at": now - 10,
        "expires_at": now + 600,
    }
    return seal(metadata, public, {"canary": "mwo-hpke-pass"}), private


def _script(repository):
    source = (
        repository.parent
        / "service.mwodevelop.profilesync/resources/lib/mwoprofilesync/hpke.py"
    ).read_text(encoding="utf-8")
    envelope, private = _envelope()
    return source + "\n" + (
        "\ntry:\n"
        "    value = decrypt_envelope(%r, %r, now=%d)\n"
        "    result = {'schema': 1, 'ok': value == {'canary': 'mwo-hpke-pass'}}\n"
        "except Exception as error:\n"
        "    result = {'schema': 1, 'ok': False, 'error_type': type(error).__name__}\n"
        "with open(%r, 'w', encoding='utf-8') as handle:\n"
        "    json.dump(result, handle, sort_keys=True)\n"
        % (envelope, private, int(time.time()), REMOTE_RESULT)
    )


def _execute(adb, port, serial, command):
    try:
        AdbEventClient(adb, port, serial).execute_builtin(command)
    except (OSError, subprocess.CalledProcessError):
        raise RuntimeError("Kodi EventServer is unavailable") from None


def run_device(repository, device, adb, port):
    registry = load_registry(repository / ".kodi-private/devices.json")
    serial = resolve_device(registry, device)["endpoints"]["adb"]
    if adb_output(adb, port, serial, "get-state").strip() != "device":
        raise RuntimeError("device is unavailable: %s" % device)
    with tempfile.NamedTemporaryFile("w", suffix=".py", delete=False) as handle:
        handle.write(_script(repository))
        local_script = Path(handle.name)
    try:
        adb_command(adb, port, serial, "push", str(local_script), REMOTE_SCRIPT)
        _execute(adb, port, serial, "RunScript(%s)" % REMOTE_SCRIPT)
        deadline = time.monotonic() + 45
        result = None
        while time.monotonic() < deadline:
            probe = adb_command(
                adb,
                port,
                serial,
                "exec-out",
                "cat",
                REMOTE_RESULT,
                check=False,
                text=True,
            )
            if probe.returncode == 0 and probe.stdout.startswith("{"):
                result = json.loads(probe.stdout)
                break
            time.sleep(1)
        if not result or not result.get("ok"):
            raise RuntimeError(
                "%s HPKE canary failed: %s"
                % (device, (result or {}).get("error_type", "timeout"))
            )
        return {"device": device, "hpke": "pass", "cleanup": "pass"}
    finally:
        local_script.unlink(missing_ok=True)
        adb_command(
            adb,
            port,
            serial,
            "shell",
            "rm -f '%s' '%s'" % (REMOTE_SCRIPT, REMOTE_RESULT),
            check=False,
        )


def main():
    repository = Path(__file__).resolve().parents[2]
    parser = argparse.ArgumentParser()
    parser.add_argument("--device", action="append", required=True)
    parser.add_argument("--adb", default="/home/mwo/android-sdk/platform-tools/adb")
    parser.add_argument("--adb-server-port", type=int, default=5038)
    args = parser.parse_args()
    results = [
        run_device(repository, item, args.adb, args.adb_server_port)
        for item in args.device
    ]
    print(json.dumps({"schema": 1, "results": results}, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
