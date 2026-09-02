#!/usr/bin/env python3
"""Converge one Android Profile Sync enrollment against production QNAP."""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import sys
import tempfile
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from tools.kodi_flatpak_profile_sync_rollout import profile_sync_server_url
from tools.kodi_portable_state_rollout import _cleanup, _profile_sync_probe
from tools.kodi_profile import AdbEventClient, AdbJsonRpcClient, adb_command
from tools.kodi_sync_inventory import load_sync_inventory
from tools.profile_sync_portable_release import bootstrap_active
from tools.qnap_profile_sync import (
    connect,
    create_production_pairing,
    revoke_production_enrollment,
)

REMOTE_SCRIPT = "/sdcard/Download/.mwo-profile-sync-converge.py"
REMOTE_CONFIG = "/sdcard/Download/.mwo-profile-sync-converge.json"
REMOTE_CA = "/sdcard/Download/.mwo-profile-sync-ca.pem"
REMOTE_MARKER = "/sdcard/Download/.mwo-profile-sync-converge-result.json"


def _execute(adb, port, serial, command):
    try:
        with AdbJsonRpcClient(adb, port, serial) as rpc:
            rpc.call("XBMC.ExecuteBuiltin", {"command": command, "wait": False})
    except (OSError, RuntimeError, TimeoutError):
        AdbEventClient(adb, port, serial).execute_builtin(command)


def _marker(adb, port, serial):
    result = adb_command(
        adb,
        port,
        serial,
        "shell",
        "cat '%s'" % REMOTE_MARKER,
        check=False,
        text=True,
        timeout=10,
    )
    payload = (result.stdout or "").strip()
    return json.loads(payload) if payload.startswith("{") else None


def _run_until_marker(adb, port, serial, command, timeout=180):
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        _execute(adb, port, serial, command)
        attempt = min(deadline, time.monotonic() + 12)
        while time.monotonic() < attempt:
            time.sleep(1)
            result = _marker(adb, port, serial)
            if result is not None:
                return result
    return None


def _target_tags(device, adb, port, serial):
    result = adb_command(
        adb,
        port,
        serial,
        "shell",
        "getprop ro.product.cpu.abilist",
        text=True,
        timeout=10,
    )
    abi = (result.stdout or "").strip().split(",", 1)[0]
    if not abi:
        raise RuntimeError("Android device has no primary ABI")
    kind = "android-emulator" if device["platform"] == "android-emulator" else "android-tv"
    return [kind + ":" + abi, "home"]


def _pairing(repository, device_id, channel, tags):
    directory = repository / ".kodi-private/profile-sync-production/pairings"
    directory.mkdir(parents=True, exist_ok=True, mode=0o700)
    directory.chmod(0o700)
    descriptor, name = tempfile.mkstemp(prefix=".%s-" % device_id, dir=directory)
    os.close(descriptor)
    path = Path(name)
    path.unlink()
    session = connect(repository, ".env")
    try:
        create_production_pairing(session, device_id, channel, tags, path)
        return json.loads(path.read_text(encoding="utf-8"))
    finally:
        session.close()
        path.unlink(missing_ok=True)


def _requires_reenrollment(result):
    return bool(
        result
        and not result.get("ok")
        and result.get("error_type") == "ApiError"
        and result.get("error_code") == "invalid report signature"
        and result.get("http_status") == 400
    )


def _can_replace_quarantined_enrollment(observed, active_revision):
    """Allow an explicit replacement only for a failed first assignment.

    A quarantine after any successfully applied revision remains immutable: it
    may represent a genuinely unsafe or broken configuration and must not be
    erased by a routine convergence run.
    """

    return bool(
        observed.get("paired")
        and observed.get("identity_consistent")
        and observed.get("status") == "QUARANTINED"
        and observed.get("applied_revision") is None
        and observed.get("assigned_revision") == active_revision
    )


def _can_replace_enrollment(observed):
    """Confine an operator-requested rotation to the same enrolled identity."""

    return bool(
        observed.get("paired")
        and observed.get("identity_consistent")
        and isinstance(observed.get("enrollment_id"), str)
        and observed["enrollment_id"]
    )


def _replace_config(path, config):
    temporary = path.with_suffix(path.suffix + ".tmp")
    with temporary.open("w", encoding="utf-8") as handle:
        json.dump(config, handle, sort_keys=True)
        handle.flush()
        os.fsync(handle.fileno())
    temporary.chmod(0o600)
    temporary.replace(path)
    path.chmod(0o600)


def _revoke(repository, enrollment_id):
    session = connect(repository, ".env")
    try:
        revoke_production_enrollment(session, enrollment_id)
    finally:
        session.close()


def converge(
    repository,
    device_id,
    adb,
    port,
    replace_quarantined_enrollment=False,
    replace_enrollment=False,
):
    inventory = load_sync_inventory(repository)
    if device_id not in inventory["devices"]:
        raise ValueError("unknown Profile Sync Android device")
    device = inventory["devices"][device_id]
    if device["platform"] not in {"android", "android-emulator"}:
        raise ValueError("Profile Sync Android adapter requires Android")
    serial = device["endpoints"]["adb"]
    observed = _profile_sync_probe(adb, port, serial)
    if observed.get("paired") and not observed.get("identity_consistent"):
        raise RuntimeError("Profile Sync enrollment has a foreign identity")
    policy = inventory["profile_sync"]
    previous_enrollment_id = observed.get("enrollment_id")
    pairing = None
    replace_local_enrollment = False
    if replace_enrollment:
        if not _can_replace_enrollment(observed):
            raise RuntimeError(
                "Profile Sync enrollment is not eligible for explicit replacement"
            )
        replace_local_enrollment = True
        pairing = _pairing(
            repository,
            device_id,
            policy["channel"],
            _target_tags(device, adb, port, serial),
        )
    elif replace_quarantined_enrollment:
        current_assignment = bootstrap_active(repository, device_id)
        if not _can_replace_quarantined_enrollment(
            observed, current_assignment["active_revision"]
        ):
            raise RuntimeError(
                "Profile Sync quarantine is not eligible for safe replacement"
            )
        replace_local_enrollment = True
        pairing = _pairing(
            repository,
            device_id,
            policy["channel"],
            _target_tags(device, adb, port, serial),
        )
    elif not observed.get("paired"):
        pairing = _pairing(
            repository,
            device_id,
            policy["channel"],
            _target_tags(device, adb, port, serial),
        )
    ca = repository / ".kodi-private/profile-sync-production/tls/ca.crt"
    ca_payload = ca.read_bytes()
    config = {
        "ca_source": REMOTE_CA,
        "ca_sha256": hashlib.sha256(ca_payload).hexdigest(),
        "server_url": profile_sync_server_url(inventory["references"]["QNAP_HOST"]),
        "logical_device_id": device_id,
        "channel": policy["channel"],
        "startup_delay_seconds": policy["startup_delay_seconds"],
        "interval_hours": policy["interval_hours"],
        "read_only": policy["read_only"],
        **({"pairing_code": pairing["code"]} if pairing else {}),
        **({"replace_enrollment": True} if replace_local_enrollment else {}),
    }
    private = repository / ".kodi-private/profile-sync-production/runtime"
    private.mkdir(parents=True, exist_ok=True, mode=0o700)
    private.chmod(0o700)
    descriptor, name = tempfile.mkstemp(prefix=".%s-" % device_id, dir=private)
    local = Path(name)
    try:
        with os.fdopen(descriptor, "w", encoding="utf-8") as handle:
            json.dump(config, handle, sort_keys=True)
            handle.flush()
            os.fsync(handle.fileno())
        local.chmod(0o600)
        for source, target in (
            (repository / "tools/kodi_profile_sync_device.py", REMOTE_SCRIPT),
            (local, REMOTE_CONFIG),
            (ca, REMOTE_CA),
        ):
            adb_command(adb, port, serial, "push", str(source), target, timeout=60)
        adb_command(
            adb,
            port,
            serial,
            "shell",
            "rm -f '%s'" % REMOTE_MARKER,
            check=False,
        )
        command = "RunScript(%s,%s,%s)" % (
            REMOTE_SCRIPT,
            REMOTE_CONFIG,
            REMOTE_MARKER,
        )
        result = _run_until_marker(adb, port, serial, command)
        if _requires_reenrollment(result):
            pairing = _pairing(
                repository,
                device_id,
                policy["channel"],
                _target_tags(device, adb, port, serial),
            )
            config.update(
                {
                    "pairing_code": pairing["code"],
                    "replace_enrollment": True,
                }
            )
            _replace_config(local, config)
            adb_command(adb, port, serial, "push", str(local), REMOTE_CONFIG)
            adb_command(
                adb,
                port,
                serial,
                "shell",
                "rm -f '%s'" % REMOTE_MARKER,
                check=False,
            )
            result = _run_until_marker(adb, port, serial, command)
        if not result or not result.get("ok"):
            raise RuntimeError(
                "Profile Sync Android convergence failed: %s/%s/%s"
                % (
                    (result or {}).get("error_type", "missing-marker"),
                    (result or {}).get("error_code", "none"),
                    (result or {}).get("http_status", "none"),
                )
            )
        assignment = bootstrap_active(repository, device_id)
        if pairing is not None:
            # Pairing codes are single-use. A following pass may be needed to
            # fetch a newly assigned revision, but it must use the enrollment
            # created above instead of replaying the consumed code.
            config.pop("replace_enrollment", None)
            config.pop("pairing_code", None)
            _replace_config(local, config)
            adb_command(adb, port, serial, "push", str(local), REMOTE_CONFIG)
        verified = _profile_sync_probe(adb, port, serial)
        if (
            verified.get("assigned_revision") != assignment["active_revision"]
            or verified.get("applied_revision") != assignment["active_revision"]
            or verified.get("status") not in {"APPLIED", "NO_CHANGE"}
        ):
            adb_command(
                adb,
                port,
                serial,
                "shell",
                "rm -f '%s'" % REMOTE_MARKER,
                check=False,
            )
            result = _run_until_marker(adb, port, serial, command)
            if not result or not result.get("ok"):
                raise RuntimeError(
                    "Profile Sync active assignment failed: %s/%s/%s"
                    % (
                        (result or {}).get("error_type", "missing-marker"),
                        (result or {}).get("error_code", "none"),
                        (result or {}).get("http_status", "none"),
                    )
                )
            verified = _profile_sync_probe(adb, port, serial)
        if not (
            verified.get("paired")
            and verified.get("identity_consistent")
            and verified.get("server_url_configured")
            and verified.get("ca_certificate_configured")
            and verified.get("has_access_token")
            and verified.get("has_signing_seed")
            and verified.get("assigned_revision") == assignment["active_revision"]
            and verified.get("applied_revision") == assignment["active_revision"]
            and verified.get("status") in {"APPLIED", "NO_CHANGE"}
        ):
            raise RuntimeError("Profile Sync Android verification failed")
        if pairing is not None and previous_enrollment_id:
            _revoke(repository, previous_enrollment_id)
        return {
            "schema": 1,
            "device": device_id,
            "result": "pass",
            "paired": pairing is not None,
            "status": verified.get("status"),
            "assigned_revision": verified.get("assigned_revision"),
            "applied_revision": verified.get("applied_revision"),
            "skin_menu_status": verified.get("skin_menu_status"),
        }
    finally:
        local.unlink(missing_ok=True)
        _cleanup(adb, port, serial)
        adb_command(
            adb,
            port,
            serial,
            "shell",
            "rm -f '%s' '%s' '%s' '%s'"
            % (REMOTE_SCRIPT, REMOTE_CONFIG, REMOTE_CA, REMOTE_MARKER),
            check=False,
        )


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--device", required=True)
    parser.add_argument("--adb", default="/home/mwo/android-sdk/platform-tools/adb")
    parser.add_argument("--adb-server-port", type=int, default=5038)
    replacement = parser.add_mutually_exclusive_group()
    replacement.add_argument(
        "--replace-quarantined-enrollment",
        action="store_true",
        help=(
            "replace only a quarantined enrollment that has never applied "
            "the current active revision"
        ),
    )
    replacement.add_argument(
        "--replace-enrollment",
        action="store_true",
        help=(
            "explicitly rotate a same-identity enrollment and revoke the old "
            "generation only after successful convergence"
        ),
    )
    args = parser.parse_args()
    print(
        json.dumps(
            converge(
                ROOT,
                args.device,
                args.adb,
                args.adb_server_port,
                replace_quarantined_enrollment=(
                    args.replace_quarantined_enrollment
                ),
                replace_enrollment=args.replace_enrollment,
            ),
            indent=2,
            sort_keys=True,
        )
    )


if __name__ == "__main__":
    main()
