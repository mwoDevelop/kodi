#!/usr/bin/env python3
"""Audit and converge portable Kodi user state on registered devices."""

from __future__ import annotations

import argparse
import json
import os
import sys
import tempfile
import time
import zipfile
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from tools.kodi_inventory import inventory_device
from tools.kodi_portable_state import validate_bundle
from tools.kodi_profile import (
    AdbEventClient,
    AdbJsonRpcClient,
    KODI_PACKAGE,
    _wait_for_kodi_ready,
    adb_command,
)
from tools.kodi_sync_inventory import load_sync_inventory


REMOTE_STATE_SCRIPT = "/sdcard/Download/mwo-kodi-portable-state.py"
REMOTE_ARTWORK_SCRIPT = "/sdcard/Download/mwo-favourite-artwork.py"
REMOTE_PROFILE_SYNC_SCRIPT = "/sdcard/Download/mwo-profile-sync-state.py"
REMOTE_BUNDLE = "/sdcard/Download/mwo-kodi-portable-state.zip"
REMOTE_MARKER = "/sdcard/Download/mwo-kodi-portable-state-result.json"
PROFILE = "special://profile"
FAVOURITES = "special://profile/favourites.xml"
ARTWORK = "special://profile/favourite-artwork"


def utc_now():
    return (
        datetime.now(timezone.utc)
        .replace(microsecond=0)
        .isoformat()
        .replace("+00:00", "Z")
    )


def _read_marker(adb, port, serial):
    marker = adb_command(
        adb,
        port,
        serial,
        "shell",
        "cat '%s'" % REMOTE_MARKER,
        check=False,
        text=True,
        timeout=10,
    )
    payload = (marker.stdout or "").strip()
    if marker.returncode or not payload.startswith("{"):
        return None
    return json.loads(payload)


def _wait_marker(adb, port, serial, deadline):
    while time.monotonic() < deadline:
        try:
            result = _read_marker(adb, port, serial)
        except Exception:
            result = None
        if result is not None:
            return result
        time.sleep(1)
    return None


def run_kodi_script(adb, port, serial, command, timeout=120):
    adb_command(
        adb,
        port,
        serial,
        "shell",
        "rm -f '%s'" % REMOTE_MARKER,
        check=False,
    )
    _ensure_kodi_started(adb, port, serial)
    try:
        with AdbJsonRpcClient(adb, port, serial) as jsonrpc:
            jsonrpc.call(
                "XBMC.ExecuteBuiltin",
                {"command": command, "wait": False},
            )
        result = _wait_marker(
            adb,
            port,
            serial,
            min(time.monotonic() + timeout, time.monotonic() + 12),
        )
        if result is not None:
            if not result.get("ok"):
                raise RuntimeError(
                    "Kodi portable-state operation failed: %s: %s"
                    % (
                        result.get("error_type", "unknown"),
                        result.get("error", "no detail"),
                    )
                )
            return result
    except (OSError, RuntimeError, TimeoutError):
        pass
    client = AdbEventClient(adb, port, serial)
    deadline = time.monotonic() + timeout
    result = None
    try:
        client.execute_builtin(command)
        result = _wait_marker(
            adb, port, serial, min(deadline, time.monotonic() + 12)
        )
    except Exception:
        result = None
    if result is None:
        try:
            client.execute_builtin_from_host(command)
        except RuntimeError:
            pass
        result = _wait_marker(adb, port, serial, deadline)
    if result is None:
        raise TimeoutError("Kodi portable-state operation timed out")
    if not result.get("ok"):
        raise RuntimeError(
            "Kodi portable-state operation failed: %s: %s"
            % (
                result.get("error_type", "unknown"),
                result.get("error", "no detail"),
            )
        )
    return result


def _push_tools(
    adb,
    port,
    serial,
    include_artwork=False,
    include_profile_sync=False,
):
    adb_command(
        adb,
        port,
        serial,
        "push",
        str(ROOT / "tools/kodi_portable_state.py"),
        REMOTE_STATE_SCRIPT,
    )
    if include_artwork:
        adb_command(
            adb,
            port,
            serial,
            "push",
            str(ROOT / "tools/favourite_artwork.py"),
            REMOTE_ARTWORK_SCRIPT,
        )
    if include_profile_sync:
        adb_command(
            adb,
            port,
            serial,
            "push",
            str(ROOT / "tools/kodi_profile_sync_state.py"),
            REMOTE_PROFILE_SYNC_SCRIPT,
        )


def _cleanup(adb, port, serial):
    try:
        adb_command(
            adb,
            port,
            serial,
            "shell",
            "rm -f '%s' '%s' '%s' '%s' '%s'"
            % (
                REMOTE_STATE_SCRIPT,
                REMOTE_ARTWORK_SCRIPT,
                REMOTE_PROFILE_SYNC_SCRIPT,
                REMOTE_BUNDLE,
                REMOTE_MARKER,
            ),
            check=False,
            timeout=10,
        )
    except Exception:
        pass


def _restart(adb, port, serial):
    adb_command(
        adb, port, serial, "shell", "am force-stop %s" % KODI_PACKAGE
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


def _ensure_kodi_started(adb, port, serial):
    for command in (
        "input keyevent KEYCODE_WAKEUP",
        "wm dismiss-keyguard",
    ):
        adb_command(
            adb,
            port,
            serial,
            "shell",
            command,
            check=False,
        )
    running = adb_command(
        adb,
        port,
        serial,
        "shell",
        "pidof %s" % KODI_PACKAGE,
        check=False,
        text=True,
    )
    if running.returncode != 0 or not (running.stdout or "").strip():
        adb_command(
            adb,
            port,
            serial,
            "shell",
            "monkey -p %s -c android.intent.category.LAUNCHER 1 >/dev/null"
            % KODI_PACKAGE,
        )
    _wait_for_kodi_ready(adb, port, serial)


def _android_probe(adb, port, serial):
    _push_tools(adb, port, serial)
    return run_kodi_script(
        adb,
        port,
        serial,
        "RunScript(%s,probe,%s,%s)"
        % (REMOTE_STATE_SCRIPT, PROFILE, REMOTE_MARKER),
        timeout=45,
    )


def _profile_sync_probe(adb, port, serial):
    _push_tools(adb, port, serial, include_profile_sync=True)
    return run_kodi_script(
        adb,
        port,
        serial,
        "RunScript(%s,probe,%s)"
        % (REMOTE_PROFILE_SYNC_SCRIPT, REMOTE_MARKER),
        timeout=45,
    )


def _configure_profile_sync(
    adb, port, serial, logical_device_id, policy
):
    _push_tools(adb, port, serial, include_profile_sync=True)
    return run_kodi_script(
        adb,
        port,
        serial,
        "RunScript(%s,configure-identity,%s,%s,%s,%s,%s,%s)"
        % (
            REMOTE_PROFILE_SYNC_SCRIPT,
            REMOTE_MARKER,
            logical_device_id,
            policy["channel"],
            policy["startup_delay_seconds"],
            policy["interval_hours"],
            policy["read_only"],
        ),
        timeout=45,
    )


def _prepare_and_export(adb, port, serial, private_root):
    _ensure_kodi_started(adb, port, serial)
    _push_tools(adb, port, serial, include_artwork=True)
    artwork = run_kodi_script(
        adb,
        port,
        serial,
        "RunScript(%s,%s,%s,%s)"
        % (
            REMOTE_ARTWORK_SCRIPT,
            FAVOURITES,
            ARTWORK,
            REMOTE_MARKER,
        ),
        timeout=180,
    )
    if artwork.get("failed"):
        raise RuntimeError(
            "publisher has %s unresolved favourite thumbnails"
            % artwork["failed"]
        )
    exported = run_kodi_script(
        adb,
        port,
        serial,
        "RunScript(%s,export,%s,%s,%s)"
        % (REMOTE_STATE_SCRIPT, PROFILE, REMOTE_MARKER, REMOTE_BUNDLE),
        timeout=120,
    )
    private_root.mkdir(parents=True, exist_ok=True, mode=0o700)
    private_root.chmod(0o700)
    with tempfile.NamedTemporaryFile(
        prefix=".portable-state-", suffix=".zip", dir=private_root, delete=False
    ) as handle:
        temporary = Path(handle.name)
    try:
        adb_command(
            adb, port, serial, "pull", REMOTE_BUNDLE, str(temporary)
        )
        manifest = validate_bundle(temporary)
        if manifest["bundle_id"] != exported["bundle_id"]:
            raise RuntimeError("pulled bundle differs from publisher marker")
        output = private_root / (
            manifest["bundle_id"].split(":", 1)[1] + ".zip"
        )
        if output.exists():
            if output.read_bytes() != temporary.read_bytes():
                raise RuntimeError("stored bundle id collides with different bytes")
            temporary.unlink()
        else:
            os.replace(temporary, output)
            output.chmod(0o600)
        current = private_root / "current.json"
        current_document = {
            "schema": 1,
            "bundle_id": manifest["bundle_id"],
            "filename": output.name,
        }
        current_payload = (
            json.dumps(current_document, indent=2, sort_keys=True) + "\n"
        )
        if not current.is_file() or current.read_text(encoding="utf-8") != current_payload:
            with tempfile.NamedTemporaryFile(
                "w",
                encoding="utf-8",
                prefix=".current-",
                suffix=".json",
                dir=private_root,
                delete=False,
            ) as pointer:
                pointer.write(current_payload)
                pointer.flush()
                os.fsync(pointer.fileno())
                temporary_pointer = Path(pointer.name)
            temporary_pointer.chmod(0o600)
            os.replace(temporary_pointer, current)
            current.chmod(0o600)
        return output, manifest, artwork
    finally:
        if temporary.exists():
            temporary.unlink()


def _apply_android(adb, port, serial, bundle):
    _push_tools(adb, port, serial)
    adb_command(adb, port, serial, "push", str(bundle), REMOTE_BUNDLE)
    result = run_kodi_script(
        adb,
        port,
        serial,
        "RunScript(%s,apply,%s,%s,%s)"
        % (REMOTE_STATE_SCRIPT, PROFILE, REMOTE_MARKER, REMOTE_BUNDLE),
        timeout=120,
    )
    return result


def _verify_android(adb, port, serial, bundle):
    _push_tools(adb, port, serial)
    adb_command(adb, port, serial, "push", str(bundle), REMOTE_BUNDLE)
    return run_kodi_script(
        adb,
        port,
        serial,
        "RunScript(%s,verify,%s,%s,%s)"
        % (REMOTE_STATE_SCRIPT, PROFILE, REMOTE_MARKER, REMOTE_BUNDLE),
        timeout=60,
    )


def _android_available(adb, port, serial):
    result = adb_command(
        adb,
        port,
        serial,
        "get-state",
        check=False,
        text=True,
        timeout=10,
    )
    if result.returncode or (result.stdout or "").strip() != "device":
        return False
    try:
        shell = adb_command(
            adb,
            port,
            serial,
            "shell",
            "echo mwo-kodi-sync-ready",
            check=False,
            text=True,
            timeout=10,
        )
    except Exception:
        return False
    return (
        shell.returncode == 0
        and (shell.stdout or "").strip() == "mwo-kodi-sync-ready"
    )


def _record_unavailable(device, repository, adb, port):
    if device["platform"] in {"android", "android-emulator"}:
        serial = device["endpoints"]["adb"]
        if not _android_available(adb, port, serial):
            return "ADB endpoint is unavailable"
        return None
    try:
        inventory_device(
            repository,
            device["logical_device_id"],
            adb=adb,
            adb_server_port=port,
        )
    except Exception as error:
        return "%s: %s" % (type(error).__name__, str(error))
    return (
        "reachable Linux Flatpak profile still requires an in-process "
        "runtime path qualification before mutation"
    )


def audit(inventory, repository, adb, port):
    results = {}
    for logical_id in inventory["order"]:
        device = inventory["devices"][logical_id]
        reason = _record_unavailable(device, repository, adb, port)
        if reason is not None:
            results[logical_id] = {
                "status": "UNAVAILABLE",
                "reason": reason,
            }
            continue
        serial = device["endpoints"]["adb"]
        try:
            portable = _android_probe(adb, port, serial)
            profile_sync = _profile_sync_probe(adb, port, serial)
            results[logical_id] = {
                "status": "OK",
                **portable,
                "profile_sync": profile_sync,
            }
        except Exception as error:
            results[logical_id] = {
                "status": "ERROR",
                "error_type": type(error).__name__,
                "error": str(error),
            }
        finally:
            _cleanup(adb, port, serial)
    return results


def _current_bundle(repository):
    private_root = repository / ".kodi-private/portable-state"
    pointer = private_root / "current.json"
    if not pointer.is_file() or pointer.is_symlink():
        raise RuntimeError("portable-state current bundle is not published")
    document = json.loads(pointer.read_text(encoding="utf-8"))
    if set(document) != {"schema", "bundle_id", "filename"} or document["schema"] != 1:
        raise RuntimeError("portable-state current pointer is invalid")
    filename = document["filename"]
    if not isinstance(filename, str) or Path(filename).name != filename:
        raise RuntimeError("portable-state current filename is invalid")
    bundle = private_root / filename
    if not bundle.is_file() or bundle.is_symlink():
        raise RuntimeError("portable-state current bundle is missing")
    manifest = validate_bundle(bundle)
    if manifest["bundle_id"] != document["bundle_id"]:
        raise RuntimeError("portable-state current pointer differs from bundle")
    return bundle, manifest


def _bundle_semantic_identity(bundle, manifest):
    from tools.kodi_portable_state import _favourites_semantics, canonical_json, digest

    with zipfile.ZipFile(bundle, "r") as archive:
        favourites = archive.read("payload/favourites.xml")
    artwork = sorted(
        Path(item["path"]).name
        for item in manifest["adapters"]["kodi.favourites"]["files"]
        if item["path"].startswith("favourite-artwork/")
        and item["path"] != "favourite-artwork/manifest.json"
    )
    return {
        "favourites_semantic_sha256": digest(
            canonical_json(_favourites_semantics(favourites))
        ),
        "artwork_inventory_sha256": digest(canonical_json(artwork)),
    }


def converge(inventory, repository, adb, port, publish=True):
    publisher_id = inventory["publisher"]
    if publish:
        publisher = inventory["devices"][publisher_id]
        if publisher["platform"] not in {"android", "android-emulator"}:
            raise ValueError("portable-state publisher must currently use ADB")
        publisher_serial = publisher["endpoints"]["adb"]
        if not _android_available(adb, port, publisher_serial):
            raise RuntimeError("portable-state publisher is unavailable")
        try:
            bundle, manifest, artwork = _prepare_and_export(
                adb,
                port,
                publisher_serial,
                repository / ".kodi-private/portable-state",
            )
        finally:
            _cleanup(adb, port, publisher_serial)
    else:
        bundle, manifest = _current_bundle(repository)
        artwork = {"migrated_actions": 0}
    expected_identity = _bundle_semantic_identity(bundle, manifest)
    results = {}
    for logical_id in inventory["order"]:
        device = inventory["devices"][logical_id]
        reason = _record_unavailable(device, repository, adb, port)
        if reason is not None:
            results[logical_id] = {
                "status": "UNAVAILABLE",
                "reason": reason,
            }
            continue
        serial = device["endpoints"]["adb"]
        try:
            profile_sync = _configure_profile_sync(
                adb,
                port,
                serial,
                logical_id,
                inventory["profile_sync"],
            )
            if (
                profile_sync["logical_device_id"] != logical_id
                or profile_sync["channel"]
                != inventory["profile_sync"]["channel"]
                or profile_sync["read_only"]
                != (inventory["profile_sync"]["read_only"] == "true")
            ):
                raise RuntimeError(
                    "Profile Sync identity profile did not converge"
                )
            observed_before = _android_probe(adb, port, serial)
            if (
                all(
                    observed_before.get(key) == value
                    for key, value in expected_identity.items()
                )
                and not observed_before.get("missing_artwork_files")
                and profile_sync.get("status") == "NO_CHANGE"
                and profile_sync.get("assigned_revision")
                and profile_sync.get("assigned_revision")
                == profile_sync.get("applied_revision")
            ):
                applied = {
                    "status": "NO_CHANGE",
                    "bundle_id": manifest["bundle_id"],
                    "source": "profile-sync-authority",
                }
            else:
                applied = _apply_android(adb, port, serial, bundle)
            if (
                applied["status"] == "APPLIED"
                or logical_id == publisher_id
                and artwork.get("migrated_actions", 0)
            ):
                _restart(adb, port, serial)
            observed = _android_probe(adb, port, serial)
            profile_sync = _profile_sync_probe(adb, port, serial)
            verified_bundle = _verify_android(adb, port, serial, bundle)
            if not verified_bundle.get("matches") or observed.get(
                "missing_artwork_files"
            ):
                raise RuntimeError("post-rollout portable-state mismatch")
            if not (
                profile_sync.get("enabled")
                and profile_sync.get("paired")
                and profile_sync.get("identity_consistent")
                and profile_sync.get("server_url_configured")
                and profile_sync.get("ca_certificate_configured")
                and profile_sync.get("has_access_token")
                and profile_sync.get("has_signing_seed")
            ):
                raise RuntimeError(
                    "Profile Sync production identity is incomplete"
                )
            results[logical_id] = {
                "status": "CONVERGED",
                "apply_status": applied["status"],
                "bundle_id": manifest["bundle_id"],
                "favourites": observed["favourites"],
                "watchnixtoons2": observed["watchnixtoons2"],
                "portable": observed["portable"],
                "current_watch_actions": observed[
                    "current_watch_actions"
                ],
                "profile_sync": {
                    key: profile_sync[key]
                    for key in (
                        "addon_version",
                        "channel",
                        "enabled",
                        "identity_consistent",
                        "logical_device_id",
                        "paired",
                        "read_only",
                        "server_url_configured",
                        "status",
                    )
                },
            }
        except Exception as error:
            results[logical_id] = {
                "status": "ERROR",
                "error_type": type(error).__name__,
                "error": str(error),
            }
        finally:
            _cleanup(adb, port, serial)
    return {
        "bundle": str(bundle.relative_to(repository)),
        "bundle_id": manifest["bundle_id"],
        "publisher": publisher_id,
        "publisher_artwork": artwork,
        "devices": results,
    }


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "command", choices=("audit", "sync", "publish", "apply")
    )
    parser.add_argument(
        "--adb", default="/home/mwo/android-sdk/platform-tools/adb"
    )
    parser.add_argument("--adb-server-port", type=int, default=5038)
    parser.add_argument("--devices", default=".kodi-private/devices.json")
    parser.add_argument("--references", default=".env")
    parser.add_argument(
        "--device",
        action="append",
        default=[],
        help="limit audit/apply targets to a logical device (repeatable)",
    )
    parser.add_argument("--result")
    args = parser.parse_args()
    inventory = load_sync_inventory(
        ROOT,
        devices_file=args.devices,
        references_file=args.references,
    )
    if args.device:
        requested = list(dict.fromkeys(args.device))
        unknown = sorted(set(requested).difference(inventory["devices"]))
        if unknown:
            raise ValueError(
                "unknown requested devices: %s" % ", ".join(unknown)
            )
        inventory["order"] = requested
    started = utc_now()
    if args.command == "audit":
        devices = audit(
            inventory, ROOT, args.adb, args.adb_server_port
        )
        result = {
            "schema": 1,
            "operation": "audit",
            "started_utc": started,
            "finished_utc": utc_now(),
            "publisher": inventory["publisher"],
            "devices": devices,
        }
    else:
        converged = converge(
            inventory,
            ROOT,
            args.adb,
            args.adb_server_port,
            publish=args.command in {"sync", "publish"},
        )
        result = {
            "schema": 1,
            "operation": args.command,
            "started_utc": started,
            "finished_utc": utc_now(),
            **converged,
        }
    if args.result:
        output = (ROOT / args.result).resolve()
        private = (ROOT / ".kodi-private").resolve()
        if private not in output.parents:
            raise ValueError("result must be stored below .kodi-private")
        output.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
        output.write_text(
            json.dumps(result, indent=2, sort_keys=True) + "\n",
            encoding="utf-8",
        )
        output.chmod(0o600)
    print(json.dumps(result, indent=2, sort_keys=True))
    statuses = [item["status"] for item in result["devices"].values()]
    return 1 if "ERROR" in statuses else 0


if __name__ == "__main__":
    raise SystemExit(main())
