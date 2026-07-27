#!/usr/bin/env python3
"""Run an Ed25519/OpenSSL capability spike inside Kodi on real devices.

The test pushes a temporary, dependency-free script to shared storage,
executes it in Kodi's Python runtime, reads a non-sensitive result and removes
the script. Device endpoints stay in the ignored private registry and are
never printed.
"""

from __future__ import annotations

import argparse
import json
import re
import socket
import struct
import subprocess
import tempfile
import time
from pathlib import Path

from tools.kodi_devices import load_registry, resolve_device
from tools.kodi_profile import (
    AdbEventClient,
    adb_command,
    adb_output,
)


REMOTE_SCRIPT = "/sdcard/Download/.mwo-profile-sync-crypto-spike.py"
RESULT_PATH = "/sdcard/Download/.mwo-profile-sync-crypto-result.json"

SPIKE_SCRIPT = r'''import ctypes
import ctypes.util
import json
import ssl

SEED = bytes.fromhex(
    "9d61b19deffd5a60ba844af492ec2cc4"
    "4449c5697b326919703bac031cae7f60"
)
EXPECTED_PUBLIC = bytes.fromhex(
    "d75a980182b10ab7d54bfed3c964073a"
    "0ee172f3daa62325af021a68f707511a"
)
EXPECTED_SIGNATURE = bytes.fromhex(
    "e5564300c360ac729086e2cc806e828a"
    "84877f1eb8e5d974d873e06522490155"
    "5fb8821590a33bacc61e39701cf9b46b"
    "d25bf5f0595bbe24655141438e7a100b"
)


def bind(crypto):
    crypto.OBJ_sn2nid.argtypes = [ctypes.c_char_p]
    crypto.OBJ_sn2nid.restype = ctypes.c_int
    crypto.EVP_PKEY_new_raw_private_key.argtypes = [
        ctypes.c_int,
        ctypes.c_void_p,
        ctypes.c_void_p,
        ctypes.c_size_t,
    ]
    crypto.EVP_PKEY_new_raw_private_key.restype = ctypes.c_void_p
    crypto.EVP_PKEY_new_raw_public_key.argtypes = [
        ctypes.c_int,
        ctypes.c_void_p,
        ctypes.c_void_p,
        ctypes.c_size_t,
    ]
    crypto.EVP_PKEY_new_raw_public_key.restype = ctypes.c_void_p
    crypto.EVP_PKEY_get_raw_public_key.argtypes = [
        ctypes.c_void_p,
        ctypes.c_void_p,
        ctypes.POINTER(ctypes.c_size_t),
    ]
    crypto.EVP_PKEY_get_raw_public_key.restype = ctypes.c_int
    crypto.EVP_PKEY_free.argtypes = [ctypes.c_void_p]
    crypto.EVP_MD_CTX_new.restype = ctypes.c_void_p
    crypto.EVP_MD_CTX_free.argtypes = [ctypes.c_void_p]
    crypto.EVP_DigestSignInit.argtypes = [
        ctypes.c_void_p,
        ctypes.c_void_p,
        ctypes.c_void_p,
        ctypes.c_void_p,
        ctypes.c_void_p,
    ]
    crypto.EVP_DigestSignInit.restype = ctypes.c_int
    crypto.EVP_DigestSign.argtypes = [
        ctypes.c_void_p,
        ctypes.c_void_p,
        ctypes.POINTER(ctypes.c_size_t),
        ctypes.c_void_p,
        ctypes.c_size_t,
    ]
    crypto.EVP_DigestSign.restype = ctypes.c_int
    crypto.EVP_DigestVerifyInit.argtypes = [
        ctypes.c_void_p,
        ctypes.c_void_p,
        ctypes.c_void_p,
        ctypes.c_void_p,
        ctypes.c_void_p,
    ]
    crypto.EVP_DigestVerifyInit.restype = ctypes.c_int
    crypto.EVP_DigestVerify.argtypes = [
        ctypes.c_void_p,
        ctypes.c_void_p,
        ctypes.c_size_t,
        ctypes.c_void_p,
        ctypes.c_size_t,
    ]
    crypto.EVP_DigestVerify.restype = ctypes.c_int


def buffer(payload):
    return (ctypes.c_ubyte * len(payload)).from_buffer_copy(payload)


def run_boringssl(crypto, library_name):
    crypto.ED25519_keypair_from_seed.argtypes = [
        ctypes.c_void_p,
        ctypes.c_void_p,
        ctypes.c_void_p,
    ]
    crypto.ED25519_keypair_from_seed.restype = None
    crypto.ED25519_sign.argtypes = [
        ctypes.c_void_p,
        ctypes.c_void_p,
        ctypes.c_size_t,
        ctypes.c_void_p,
    ]
    crypto.ED25519_sign.restype = ctypes.c_int
    crypto.ED25519_verify.argtypes = [
        ctypes.c_void_p,
        ctypes.c_size_t,
        ctypes.c_void_p,
        ctypes.c_void_p,
    ]
    crypto.ED25519_verify.restype = ctypes.c_int

    public_key = (ctypes.c_ubyte * 32)()
    private_key = (ctypes.c_ubyte * 64)()
    crypto.ED25519_keypair_from_seed(
        public_key, private_key, buffer(SEED)
    )
    signature = (ctypes.c_ubyte * 64)()
    if crypto.ED25519_sign(signature, None, 0, private_key) != 1:
        raise RuntimeError("BoringSSL ED25519_sign failed")
    signature_bytes = bytes(signature)
    tampered = bytearray(signature_bytes)
    tampered[0] ^= 1
    result = {
        "schema": 1,
        "backend": "android-boringssl",
        "backend_version": library_name,
        "public_key_matches_rfc8032": bytes(public_key) == EXPECTED_PUBLIC,
        "signature_matches_rfc8032": (
            signature_bytes == EXPECTED_SIGNATURE
        ),
        "valid_signature_accepted": (
            crypto.ED25519_verify(
                None, 0, buffer(signature_bytes), public_key
            )
            == 1
        ),
        "tampered_signature_rejected": (
            crypto.ED25519_verify(
                None, 0, buffer(bytes(tampered)), public_key
            )
            == 0
        ),
    }
    result["ok"] = all(
        result[key]
        for key in (
            "public_key_matches_rfc8032",
            "signature_matches_rfc8032",
            "valid_signature_accepted",
            "tampered_signature_rejected",
        )
    )
    return result


def verify(crypto, nid, public_key, message, signature):
    public_buffer = buffer(public_key)
    signature_buffer = buffer(signature)
    message_buffer = buffer(message) if message else None
    key = crypto.EVP_PKEY_new_raw_public_key(
        nid, None, public_buffer, len(public_key)
    )
    if not key:
        raise RuntimeError("EVP_PKEY_new_raw_public_key failed")
    context = crypto.EVP_MD_CTX_new()
    if not context:
        crypto.EVP_PKEY_free(key)
        raise RuntimeError("EVP_MD_CTX_new failed")
    try:
        if crypto.EVP_DigestVerifyInit(context, None, None, None, key) != 1:
            raise RuntimeError("EVP_DigestVerifyInit failed")
        return (
            crypto.EVP_DigestVerify(
                context,
                signature_buffer,
                len(signature),
                message_buffer,
                len(message),
            )
            == 1
        )
    finally:
        crypto.EVP_MD_CTX_free(context)
        crypto.EVP_PKEY_free(key)


def run_openssl():
    candidates = [
        ("process-global", ctypes.CDLL(None)),
        (ctypes.util.find_library("crypto"), None),
        ("libcrypto.so.3", None),
        ("libcrypto.so", None),
        ("/system/lib64/libcrypto.so", None),
        ("/system/lib/libcrypto.so", None),
    ]
    crypto = None
    library_name = None
    for candidate, loaded in candidates:
        if not candidate:
            continue
        if loaded is None:
            try:
                loaded = ctypes.CDLL(candidate)
            except OSError:
                continue
        if all(
            hasattr(loaded, symbol)
            for symbol in (
                "ED25519_keypair_from_seed",
                "ED25519_sign",
                "ED25519_verify",
            )
        ):
            return run_boringssl(loaded, candidate)
        if hasattr(loaded, "EVP_PKEY_new_raw_private_key"):
            crypto = loaded
            library_name = candidate
            break
    if crypto is None:
        raise RuntimeError("no accessible native Ed25519 API")
    bind(crypto)
    nid = crypto.OBJ_sn2nid(b"ED25519")
    if nid <= 0:
        raise RuntimeError("OpenSSL has no ED25519 object identifier")

    seed_buffer = buffer(SEED)
    key = crypto.EVP_PKEY_new_raw_private_key(
        nid, None, seed_buffer, len(SEED)
    )
    if not key:
        raise RuntimeError("EVP_PKEY_new_raw_private_key failed")
    context = None
    try:
        public_buffer = (ctypes.c_ubyte * 32)()
        public_size = ctypes.c_size_t(len(public_buffer))
        if (
            crypto.EVP_PKEY_get_raw_public_key(
                key, public_buffer, ctypes.byref(public_size)
            )
            != 1
        ):
            raise RuntimeError("EVP_PKEY_get_raw_public_key failed")
        public_key = bytes(public_buffer[: public_size.value])

        context = crypto.EVP_MD_CTX_new()
        if not context:
            raise RuntimeError("EVP_MD_CTX_new failed")
        if crypto.EVP_DigestSignInit(context, None, None, None, key) != 1:
            raise RuntimeError("EVP_DigestSignInit failed")
        signature_buffer = (ctypes.c_ubyte * 64)()
        signature_size = ctypes.c_size_t(len(signature_buffer))
        if (
            crypto.EVP_DigestSign(
                context,
                signature_buffer,
                ctypes.byref(signature_size),
                None,
                0,
            )
            != 1
        ):
            raise RuntimeError("EVP_DigestSign failed")
        signature = bytes(signature_buffer[: signature_size.value])
    finally:
        if context:
            crypto.EVP_MD_CTX_free(context)
        crypto.EVP_PKEY_free(key)

    tampered = bytearray(signature)
    tampered[0] ^= 1
    result = {
        "schema": 1,
        "backend": "openssl",
        "backend_version": ssl.OPENSSL_VERSION,
        "ctypes_available": True,
        "crypto_library_resolved": bool(library_name),
        "ed25519_nid_available": True,
        "public_key_matches_rfc8032": public_key == EXPECTED_PUBLIC,
        "signature_matches_rfc8032": signature == EXPECTED_SIGNATURE,
        "valid_signature_accepted": verify(
            crypto, nid, public_key, b"", signature
        ),
        "tampered_signature_rejected": not verify(
            crypto, nid, public_key, b"", bytes(tampered)
        ),
    }
    result["ok"] = all(
        result[key]
        for key in (
            "ctypes_available",
            "crypto_library_resolved",
            "ed25519_nid_available",
            "public_key_matches_rfc8032",
            "signature_matches_rfc8032",
            "valid_signature_accepted",
            "tampered_signature_rejected",
        )
    )
    return result


def run():
    return run_openssl()


try:
    result = run()
except Exception as error:
    result = {
        "schema": 1,
        "ok": False,
        "error_type": type(error).__name__,
        "error": str(error),
    }
with open("/sdcard/Download/.mwo-profile-sync-crypto-result.json", "w", encoding="utf-8") as handle:
    json.dump(result, handle, sort_keys=True)
'''


def _push_file(adb, port, serial, source, destination):
    result = adb_command(
        adb,
        port,
        serial,
        "push",
        str(source),
        destination,
        text=True,
    )
    if result.returncode:
        raise RuntimeError("ADB push failed")


def _wait_for_result(adb, port, serial, timeout=45):
    started = time.monotonic()
    while time.monotonic() - started < timeout:
        result = adb_command(
            adb,
            port,
            serial,
            "exec-out",
            "cat",
            RESULT_PATH,
            check=False,
            text=True,
        )
        if result.returncode == 0 and result.stdout.strip().startswith("{"):
            return json.loads(result.stdout)
        time.sleep(1)
    raise TimeoutError("Kodi crypto spike result timed out")


def _execute_builtin(adb, port, serial, command):
    try:
        AdbEventClient(adb, port, serial).execute_builtin(command)
        return
    except (OSError, subprocess.CalledProcessError):
        pass
    host = serial.rsplit(":", 1)[0]
    client = AdbEventClient(adb, port, serial)
    hello = (
        b"mwoDevelop profile sync E2E\0"
        + bytes((0,))
        + struct.pack("!H", 0)
        + struct.pack("!I", 0)
        + struct.pack("!I", 0)
    )
    action = bytes((client.ACTION_EXECBUILTIN,)) + command.encode() + b"\0"
    with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as connection:
        for packet_type, payload in (
            (client.PT_HELO, hello),
            (client.PT_ACTION, action),
            (client.PT_BYE, b""),
        ):
            for packet in client._packets(packet_type, payload):
                connection.sendto(packet, (host, 9777))


def verify_device(repository, logical_device_id, adb, port):
    registry = load_registry(repository / ".kodi-private/devices.json")
    device = resolve_device(registry, logical_device_id)
    serial = device["endpoints"]["adb"]
    if adb_output(adb, port, serial, "get-state").strip() != "device":
        raise RuntimeError("%s is not an authorized ADB device" % logical_device_id)
    model = adb_output(
        adb, port, serial, "shell", "getprop ro.product.model"
    ).strip()
    if model != device["expected"]["model"]:
        raise RuntimeError("%s resolved to an unexpected model" % logical_device_id)

    package = adb_output(
        adb, port, serial, "shell", "dumpsys package org.xbmc.kodi"
    )
    abi_match = re.search(r"primaryCpuAbi=([^\s]+)", package)
    if not abi_match:
        raise RuntimeError("%s Kodi primary ABI is unknown" % logical_device_id)
    primary_abi = abi_match.group(1)

    with tempfile.TemporaryDirectory(prefix="mwo-crypto-spike-") as temporary:
        spike = Path(temporary) / "crypto_spike.py"
        spike.write_text(SPIKE_SCRIPT, encoding="utf-8")
        try:
            adb_command(
                adb,
                port,
                serial,
                "shell",
                "rm -f '%s' '%s'" % (REMOTE_SCRIPT, RESULT_PATH),
            )
            _push_file(adb, port, serial, spike, REMOTE_SCRIPT)
            _execute_builtin(
                adb, port, serial, "RunScript(%s)" % REMOTE_SCRIPT
            )
            result = _wait_for_result(adb, port, serial)
        finally:
            adb_command(
                adb,
                port,
                serial,
                "shell",
                "rm -f '%s' '%s'" % (REMOTE_SCRIPT, RESULT_PATH),
                check=False,
            )
    if not result.get("ok"):
        raise RuntimeError(
            "%s Kodi crypto spike failed: %s: %s"
            % (
                logical_device_id,
                result.get("error_type", "capability"),
                result.get("error", "unsatisfied capability"),
            )
        )
    return {
        "logical_device_id": logical_device_id,
        "crypto_backend": result["backend"],
        "crypto_version": result["backend_version"],
        "kodi_primary_abi": primary_abi,
        "rfc8032_vector": "pass",
        "tamper_rejection": "pass",
        "cleanup": "pass",
        "result": "pass",
    }


def main():
    repository = Path(__file__).resolve().parents[2]
    parser = argparse.ArgumentParser()
    parser.add_argument("--device", action="append")
    parser.add_argument(
        "--adb", default="/home/mwo/android-sdk/platform-tools/adb"
    )
    parser.add_argument("--adb-server-port", type=int, default=5038)
    args = parser.parse_args()
    registry = load_registry(repository / ".kodi-private/devices.json")
    selected = args.device or sorted(registry["devices"])
    results = [
        verify_device(
            repository,
            logical_device_id,
            args.adb,
            args.adb_server_port,
        )
        for logical_device_id in selected
    ]
    print(json.dumps({"schema": 1, "results": results}, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
