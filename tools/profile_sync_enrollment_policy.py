#!/usr/bin/env python3
"""Reconcile state opt-ins for an exact enrollment, without pairing or promotion."""

from __future__ import annotations

import argparse
import json
import re
import shlex
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from tools.kodi_sync_inventory import load_sync_inventory
from tools.qnap_profile_sync import (
    connect,
    container_station,
    set_production_favourites_state,
    set_production_playback_state,
)

IDENTITY = re.compile(r"^[a-z0-9][a-z0-9._-]{0,63}$")
ENROLLMENT = re.compile(r"^enr:[A-Za-z0-9._-]{8,128}$")
SCOPE = re.compile(r"^scope:[a-z0-9][a-z0-9._-]{0,63}$")
FEATURES = {
    "playback": "playback-state-lww-v1",
    "favourites": "favourites-state-lww-v1",
}

# Parameterized SELECT only. Never return tokens, keys or profile contents.
READ_STATE = """
import json, sqlite3, sys
c = sqlite3.connect('file:/data/state.sqlite?mode=ro', uri=True)
c.row_factory = sqlite3.Row
rows = c.execute('''SELECT enrollment_id, logical_device_id, generation, channel,
 revoked, client_capabilities, playback_state_enabled, playback_scope_id,
 favourites_state_enabled, favourites_scope_id FROM enrollments
 WHERE logical_device_id=? ORDER BY generation DESC''', (sys.argv[1],)).fetchall()
output = []
for row in rows:
    item = dict(row)
    assignment = c.execute('SELECT document FROM assignments WHERE enrollment_id=?', (row['enrollment_id'],)).fetchone()
    report = None
    if assignment:
        aid = json.loads(assignment['document']).get('assignment_id')
        report = c.execute('SELECT result FROM assignment_reports WHERE enrollment_id=? AND assignment_id=?', (row['enrollment_id'], aid)).fetchone()
    item['assignment_result'] = report['result'] if report else None
    output.append(item)
print(json.dumps(output))
c.close()
"""


def load_policy(repository, channel):
    document = json.loads(
        (Path(repository) / "manifests/profile-sync-state-policy.json").read_text()
    )
    if (
        set(document) != {"schema", "channels"}
        or type(document["schema"]) is not int
        or document["schema"] != 1
    ):
        raise ValueError("invalid enrollment state policy")
    channels = document["channels"]
    if not isinstance(channels, dict) or not channels:
        raise ValueError("invalid enrollment state channels")
    for name, features in channels.items():
        if (
            not IDENTITY.fullmatch(name)
            or not isinstance(features, dict)
            or set(features) != set(FEATURES)
        ):
            raise ValueError("invalid enrollment state channel")
        for settings in features.values():
            if (
                not isinstance(settings, dict)
                or set(settings) != {"enabled", "scope_id"}
                or type(settings["enabled"]) is not bool
                or not isinstance(settings["scope_id"], str)
                or not SCOPE.fullmatch(settings["scope_id"])
            ):
                raise ValueError("invalid enrollment state feature")
    if channel not in channels:
        raise ValueError("channel has no enrollment state policy")
    return channels[channel]


def read_enrollments(session, logical_id):
    if not isinstance(logical_id, str) or not IDENTITY.fullmatch(logical_id):
        raise ValueError("invalid enrollment device id")
    _, docker = container_station(session)
    raw = session.execute(
        docker
        + " exec qnap-profile-sync-profile-sync-1 python -c "
        + shlex.quote(READ_STATE)
        + " "
        + shlex.quote(logical_id),
        timeout=15,
    )
    document = json.loads(raw)
    if not isinstance(document, list):
        raise ValueError("invalid enrollment observation")
    return document


def select_enrollment(
    rows, logical_id, channel, expected_id=None, expected_generation=None
):
    if not rows:
        raise RuntimeError("device has no enrollment")
    for row in rows:
        if (
            not isinstance(row, dict)
            or row.get("logical_device_id") != logical_id
            or type(row.get("generation")) is not int
            or row["generation"] < 1
        ):
            raise RuntimeError("invalid enrollment identity observation")
    generation = max(row["generation"] for row in rows)
    newest = [row for row in rows if row["generation"] == generation]
    if len(newest) != 1:
        raise RuntimeError("ambiguous newest enrollment")
    row = newest[0]
    if (
        row.get("revoked") != 0
        or row.get("channel") != channel
        or not isinstance(row.get("enrollment_id"), str)
        or not ENROLLMENT.fullmatch(row["enrollment_id"])
    ):
        raise RuntimeError("newest enrollment is revoked or has a foreign channel")
    if (expected_id is not None and row["enrollment_id"] != expected_id) or (
        expected_generation is not None and generation != expected_generation
    ):
        raise RuntimeError("enrollment generation changed")
    if row.get("assignment_result") in {"failure", "drift_blocked"}:
        raise RuntimeError(
            "enrollment assignment requires diagnosis before policy changes"
        )
    return row


def reconcile(
    repository,
    logical_id,
    *,
    session=None,
    expected_id=None,
    expected_generation=None,
    dry_run=False,
):
    inventory = load_sync_inventory(repository)
    if logical_id not in inventory["devices"]:
        raise ValueError("unknown fleet device")
    channel = inventory["devices"][logical_id]["profile_channel"]
    policy = load_policy(repository, channel)
    owned = session is None
    if owned:
        session = connect(Path(repository), ".env")
    try:
        row = select_enrollment(
            read_enrollments(session, logical_id),
            logical_id,
            channel,
            expected_id,
            expected_generation,
        )
        identity = row["enrollment_id"]
        generation = row["generation"]
        capabilities = json.loads(row["client_capabilities"] or "[]")
        if not isinstance(capabilities, list) or any(
            not isinstance(c, str) for c in capabilities
        ):
            raise RuntimeError("invalid client capabilities")
        changes = []
        for feature, capability in FEATURES.items():
            desired = policy[feature]
            if desired["enabled"] and capability not in capabilities:
                raise RuntimeError("client has not reported required state capability")
            if row.get(feature + "_scope_id") not in {None, desired["scope_id"]}:
                raise RuntimeError(
                    "refusing to move enrollment to a different state scope"
                )
            observed = row.get(feature + "_state_enabled")
            if type(observed) is not int or observed not in {0, 1}:
                raise RuntimeError("invalid state enabled observation")
            if (
                observed != int(desired["enabled"])
                or row[feature + "_scope_id"] != desired["scope_id"]
            ):
                changes.append(feature)
        setters = {
            "playback": set_production_playback_state,
            "favourites": set_production_favourites_state,
        }
        if not dry_run:
            for feature in changes:
                # Guard every write. The setter itself atomically rejects revoked IDs.
                select_enrollment(
                    read_enrollments(session, logical_id),
                    logical_id,
                    channel,
                    identity,
                    generation,
                )
                setters[feature](
                    session,
                    identity,
                    policy[feature]["enabled"],
                    policy[feature]["scope_id"],
                )
            verified = select_enrollment(
                read_enrollments(session, logical_id),
                logical_id,
                channel,
                identity,
                generation,
            )
            for feature in FEATURES:
                if (
                    verified.get(feature + "_state_enabled")
                    != int(policy[feature]["enabled"])
                    or verified.get(feature + "_scope_id")
                    != policy[feature]["scope_id"]
                ):
                    raise RuntimeError("state policy did not converge")
        return {
            "schema": 1,
            "device": logical_id,
            "enrollment_id": identity,
            "generation": generation,
            "status": "WOULD_CHANGE"
            if dry_run and changes
            else "APPLIED"
            if changes
            else "NO_CHANGE",
            "changed_features": changes,
            "policy": policy,
        }
    finally:
        if owned:
            session.close()


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--device", required=True)
    p.add_argument("--expected-generation", type=int, required=True)
    p.add_argument("--dry-run", action="store_true")
    args = p.parse_args()
    print(
        json.dumps(
            reconcile(
                ROOT,
                args.device,
                expected_generation=args.expected_generation,
                dry_run=args.dry_run,
            ),
            indent=2,
        )
    )


if __name__ == "__main__":
    main()
