#!/usr/bin/env python3
"""Publish portable favourites through the verified production Profile Sync flow."""

from __future__ import annotations

import argparse
import base64
import fcntl
import hashlib
import json
import secrets
import sqlite3
import sys
import tempfile
import time
import zipfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from tools.kodi_portable_state import validate_bundle
from tools.kodi_portable_state_rollout import _cleanup, _profile_sync_probe
from tools.kodi_profile import AdbEventClient, _wait_for_kodi_ready
from tools.kodi_sync_inventory import load_sync_inventory
from tools.profile_portable_favourites import export_portable_favourites
from tools.profile_revision_compose import compose
from tools.profile_sync_admin import (
    sign_admin_request,
    sign_assignment_v2,
    sign_with_registry,
)
from tools.qnap_profile_sync import (
    backup_production,
    connect,
    production_admin_request,
)


CHANNEL = "home-stable"
ADDON_ENTRYPOINT = (
    "special://home/addons/service.mwodevelop.profilesync/default.py"
)


def _current_bundle(repository: Path) -> tuple[Path, dict]:
    root = repository / ".kodi-private/portable-state"
    pointer = root / "current.json"
    if not pointer.is_file() or pointer.is_symlink():
        raise RuntimeError("portable-state current pointer is unavailable")
    document = json.loads(pointer.read_text(encoding="utf-8"))
    if set(document) != {"schema", "bundle_id", "filename"} or document["schema"] != 1:
        raise RuntimeError("portable-state current pointer is invalid")
    filename = document["filename"]
    if not isinstance(filename, str) or Path(filename).name != filename:
        raise RuntimeError("portable-state current filename is invalid")
    bundle = root / filename
    if not bundle.is_file() or bundle.is_symlink():
        raise RuntimeError("portable-state current bundle is unavailable")
    manifest = validate_bundle(bundle)
    if manifest["bundle_id"] != document["bundle_id"]:
        raise RuntimeError("portable-state pointer differs from its bundle")
    return bundle, manifest


def _portable_export(bundle: Path) -> dict:
    manifest = validate_bundle(bundle)
    files = manifest["adapters"]["kodi.favourites"]["files"]
    with tempfile.TemporaryDirectory(prefix="profile-sync-portable-") as value:
        profile = Path(value)
        userdata = profile / "userdata"
        with zipfile.ZipFile(bundle) as archive:
            for record in files:
                relative = record["path"]
                target = userdata / relative
                target.parent.mkdir(parents=True, exist_ok=True)
                payload = archive.read("payload/" + relative)
                if (
                    len(payload) != record["size"]
                    or hashlib.sha256(payload).hexdigest() != record["sha256"]
                ):
                    raise RuntimeError("portable-state payload differs from manifest")
                target.write_bytes(payload)
        return export_portable_favourites(profile)


def _backup(session, repository: Path, label: str) -> tuple[Path, dict]:
    token = secrets.token_hex(3)
    backup_id = "ps-%s-%s-%s" % (int(time.time()), label, token)
    output = repository / ".kodi-private/profile-sync-backups" / backup_id
    result = backup_production(session, backup_id, output)
    return output, result


def _database_state(path: Path) -> dict:
    database = sqlite3.connect(path / "state.sqlite")
    database.row_factory = sqlite3.Row
    try:
        channel = database.execute(
            "SELECT * FROM channels WHERE channel=?", (CHANNEL,)
        ).fetchone()
        if channel is None or channel["active_revision"] is None:
            raise RuntimeError("Profile Sync channel has no active revision")
        revision = database.execute(
            "SELECT manifest FROM revisions WHERE revision_id=?",
            (channel["active_revision"],),
        ).fetchone()
        if revision is None:
            raise RuntimeError("Profile Sync active revision is unavailable")
        enrollments = [
            dict(row)
            for row in database.execute(
                """
                SELECT enrollment_id, logical_device_id, generation, channel,
                       target_tags, revoked, last_seen_at
                FROM enrollments WHERE channel=? ORDER BY logical_device_id, generation
                """,
                (CHANNEL,),
            )
        ]
        reports = [
            dict(row)
            for row in database.execute(
                """
                SELECT enrollment_id, revision_id, assignment_kind, result
                FROM assignment_reports
                """
            )
        ]
        return {
            "active_revision": channel["active_revision"],
            "candidate_revision": channel["candidate_revision"],
            "generation": channel["generation"],
            "manifest": json.loads(revision["manifest"]),
            "enrollments": enrollments,
            "reports": reports,
        }
    finally:
        database.close()


def _latest_enrollments(state: dict, logical_ids: set[str]) -> dict[str, dict]:
    selected: dict[str, dict] = {}
    for item in state["enrollments"]:
        logical_id = item["logical_device_id"]
        if item["revoked"] or logical_id not in logical_ids:
            continue
        previous = selected.get(logical_id)
        if previous is None or item["generation"] > previous["generation"]:
            selected[logical_id] = item
    missing = sorted(logical_ids.difference(selected))
    if missing:
        raise RuntimeError(
            "Profile Sync has no eligible enrollment for: %s" % ", ".join(missing)
        )
    for item in selected.values():
        item["target_tags"] = json.loads(item["target_tags"])
    return selected


def _admin(
    session,
    operation: str,
    role: str,
    path: str,
    payload: dict,
    idempotency_key: str,
    repository: Path,
) -> dict:
    key_id = "publisher-production" if role == "publish" else "promoter-production"
    document = sign_admin_request(
        operation,
        payload,
        role,
        idempotency_key,
        key_id,
        repository / ".kodi-private/profile-sync-production/signing-seeds.json",
        repository / ".kodi-private/profile-sync-production/key-registry.json",
    )
    return production_admin_request(session, path, document, idempotency_key)


def _put_candidate(
    session,
    repository: Path,
    state: dict,
    revision: dict,
    exported: dict,
) -> None:
    revision_id = revision["revision_id"]
    for digest, blob in sorted(exported["blobs"].items()):
        payload = {
            "content_base64": base64.urlsafe_b64encode(blob["content"])
            .rstrip(b"=")
            .decode("ascii"),
            "media_type": blob["media_type"],
        }
        _admin(
            session,
            "put_blob",
            "publish",
            "/v1/blobs/sha256:%s" % digest,
            payload,
            "portable-blob-%s" % digest,
            repository,
        )
    _admin(
        session,
        "put_revision",
        "publish",
        "/v1/revisions",
        revision,
        "portable-revision-%s" % revision_id.split(":", 1)[1],
        repository,
    )
    _admin(
        session,
        "publish_candidate",
        "publish",
        "/v1/channels/%s/candidates" % CHANNEL,
        {
            "revision_id": revision_id,
            "base_revision": state["active_revision"],
            "expected_candidate_head": state["candidate_revision"],
        },
        "portable-candidate-%s" % revision_id.split(":", 1)[1],
        repository,
    )


def _assignment(
    enrollment: dict,
    revision_id: str,
    generation: int,
    kind: str,
    repository: Path,
) -> dict:
    return sign_assignment_v2(
        CHANNEL,
        enrollment["enrollment_id"],
        enrollment["generation"],
        generation,
        revision_id,
        enrollment["target_tags"],
        kind,
        "enforce",
        "promoter-production",
        repository / ".kodi-private/profile-sync-production/signing-seeds.json",
        repository / ".kodi-private/profile-sync-production/key-registry.json",
        ttl_seconds=7 * 86400,
    )


def _assign_candidate(
    session, repository: Path, enrollment: dict, revision_id: str, generation: int
) -> None:
    document = _assignment(enrollment, revision_id, generation, "candidate", repository)
    logical_id = enrollment["logical_device_id"]
    _admin(
        session,
        "assign_candidate",
        "publish",
        "/v1/channels/%s/assignments" % CHANNEL,
        document,
        "portable-assign-%s-%s" % (logical_id, revision_id.split(":", 1)[1]),
        repository,
    )


def _trigger_sync(inventory: dict, logical_id: str, adb: str, port: int, revision: str):
    device = inventory["devices"][logical_id]
    if device["platform"] not in {"android", "android-emulator"}:
        raise RuntimeError("Profile Sync canary must use Android")
    serial = device["endpoints"]["adb"]
    try:
        probe = _profile_sync_probe(adb, port, serial)
        if probe.get("enrollment_id") is None:
            raise RuntimeError("Profile Sync canary is not paired")
        _wait_for_kodi_ready(adb, port, serial)
        command = "RunScript(%s,--sync-once)" % ADDON_ENTRYPOINT
        client = AdbEventClient(adb, port, serial)
        try:
            client.execute_builtin(command)
        except RuntimeError:
            client.execute_builtin_from_host(command)
        deadline = time.monotonic() + 180
        while time.monotonic() < deadline:
            time.sleep(3)
            probe = _profile_sync_probe(adb, port, serial)
            if (
                probe.get("assigned_revision") == revision
                and probe.get("applied_revision") == revision
                and probe.get("status") in {"APPLIED", "NO_CHANGE"}
            ):
                return {
                    "logical_device_id": logical_id,
                    "enrollment_id": probe["enrollment_id"],
                    "status": probe["status"],
                    "revision_id": revision,
                }
        raise TimeoutError("Profile Sync canary did not apply the candidate")
    finally:
        _cleanup(adb, port, serial)


def _require_report(state: dict, enrollment_id: str, revision: str, kind: str):
    matches = [
        item
        for item in state["reports"]
        if item["enrollment_id"] == enrollment_id
        and item["revision_id"] == revision
        and item["assignment_kind"] == kind
    ]
    if not matches or matches[-1]["result"] != "success":
        raise RuntimeError("required Profile Sync %s report is missing" % kind)


def converge(repository: Path, adb: str, port: int, canaries: list[str]) -> dict:
    inventory = load_sync_inventory(repository)
    unknown = sorted(set(canaries).difference(inventory["devices"]))
    if unknown:
        raise ValueError("unknown Profile Sync canary: %s" % ", ".join(unknown))
    bundle, bundle_manifest = _current_bundle(repository)
    exported = _portable_export(bundle)
    private = repository / ".kodi-private/profile-sync-portable"
    private.mkdir(parents=True, exist_ok=True, mode=0o700)
    lock_path = private / "operation.lock"
    with lock_path.open("a+b") as lock:
        lock_path.chmod(0o600)
        fcntl.flock(lock.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
        session = connect(repository, ".env")
        backups = []
        try:
            backup, evidence = _backup(session, repository, "before")
            backups.append(evidence["backup_id"])
            state = _database_state(backup)
            active_adapters = (
                state["manifest"]["adapters"]
                if state["manifest"]["schema"] == 2
                else state["manifest"]["base"]["adapters"]
            )
            if active_adapters.get("kodi.favourites") == exported["adapter"]:
                return {
                    "schema": 1,
                    "status": "NO_CHANGE",
                    "bundle_id": bundle_manifest["bundle_id"],
                    "active_revision": state["active_revision"],
                    "backups": backups,
                    "canaries": [],
                }
            unsigned = compose(state["manifest"], state["manifest"], exported["adapter"])
            revision = sign_with_registry(
                "revision",
                unsigned,
                "publisher-production",
                repository / ".kodi-private/profile-sync-production/signing-seeds.json",
                repository / ".kodi-private/profile-sync-production/key-registry.json",
            )
            if state["candidate_revision"] not in {None, revision["revision_id"]}:
                raise RuntimeError("Profile Sync channel already has a foreign candidate")
            _put_candidate(session, repository, state, revision, exported)
            revision_id = revision["revision_id"]
            logical_ids = set(inventory["devices"])
            enrollments = _latest_enrollments(state, logical_ids)
            canary_results = []
            canary_enrollments = []
            for logical_id in canaries:
                enrollment = enrollments[logical_id]
                _assign_candidate(
                    session, repository, enrollment, revision_id, state["generation"]
                )
                observed = _trigger_sync(inventory, logical_id, adb, port, revision_id)
                if observed["enrollment_id"] != enrollment["enrollment_id"]:
                    raise RuntimeError("Profile Sync canary uses a stale enrollment")
                report_backup, report_evidence = _backup(
                    session, repository, "candidate-%s" % logical_id
                )
                backups.append(report_evidence["backup_id"])
                report_state = _database_state(report_backup)
                _require_report(
                    report_state, enrollment["enrollment_id"], revision_id, "candidate"
                )
                canary_results.append(observed)
                canary_enrollments.append(enrollment["enrollment_id"])
            next_generation = state["generation"] + 1
            active_assignments = [
                _assignment(item, revision_id, next_generation, "active", repository)
                for _logical_id, item in sorted(enrollments.items())
            ]
            event = sign_with_registry(
                "promotion",
                {
                    "channel": CHANNEL,
                    "revision_id": revision_id,
                    "generation": next_generation,
                    "active_assignment_ids": sorted(
                        item["assignment_id"] for item in active_assignments
                    ),
                },
                "promoter-production",
                repository / ".kodi-private/profile-sync-production/signing-seeds.json",
                repository / ".kodi-private/profile-sync-production/key-registry.json",
            )
            _admin(
                session,
                "promote",
                "promote",
                "/v1/channels/%s/promote" % CHANNEL,
                {
                    "candidate_revision": revision_id,
                    "expected_active_revision": state["active_revision"],
                    "required_enrollments": canary_enrollments,
                    "event": event,
                    "active_assignments": active_assignments,
                },
                "portable-promote-%s" % revision_id.split(":", 1)[1],
                repository,
            )
            for logical_id in canaries:
                observed = _trigger_sync(inventory, logical_id, adb, port, revision_id)
                active_backup, active_evidence = _backup(
                    session, repository, "active-%s" % logical_id
                )
                backups.append(active_evidence["backup_id"])
                active_state = _database_state(active_backup)
                _require_report(
                    active_state,
                    enrollments[logical_id]["enrollment_id"],
                    revision_id,
                    "active",
                )
                canary_results.append({**observed, "assignment_kind": "active"})
            return {
                "schema": 1,
                "status": "PROMOTED",
                "bundle_id": bundle_manifest["bundle_id"],
                "previous_revision": state["active_revision"],
                "active_revision": revision_id,
                "generation": next_generation,
                "backups": backups,
                "canaries": canary_results,
            }
        finally:
            session.close()


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("command", choices=("converge",))
    parser.add_argument("--adb", default="/home/mwo/android-sdk/platform-tools/adb")
    parser.add_argument("--adb-server-port", type=int, default=5038)
    parser.add_argument("--canary", action="append", default=[])
    args = parser.parse_args()
    canaries = args.canary or ["bluestacks1", "x88pro20"]
    result = converge(ROOT, args.adb, args.adb_server_port, canaries)
    print(json.dumps(result, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
