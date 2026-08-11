#!/usr/bin/env python3
"""Promote exact public testing ZIPs into the independently locked stable channel."""

import argparse
import hashlib
import json
import re
import shutil
import sys
from pathlib import Path
from urllib.parse import urljoin
from urllib.request import Request, urlopen

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from tools.snapshot_bundle import canonical_json, verify_bundle
from tools.device_attestation import verify as verify_device_attestation

def sha256_bytes(payload):
    return hashlib.sha256(payload).hexdigest()


def fetch(url):
    request = Request(url, headers={"User-Agent": "mwo-kodi-promote/1"})
    with urlopen(request, timeout=30) as response:
        if response.status != 200:
            raise RuntimeError("%s returned %s" % (url, response.status))
        return response.read()


def load_lock(path, channel):
    payload = json.loads(Path(path).read_text(encoding="utf-8"))
    if payload.get("schema") != 1 or payload.get("channel") != channel:
        raise ValueError("invalid %s channel lock" % channel)
    return payload


def fetch_candidate(base, testing_lock_path, expected_index_sha256, output):
    if not re.fullmatch(r"[0-9a-f]{64}", expected_index_sha256):
        raise ValueError("expected testing index SHA-256 must be 64 lowercase hex digits")
    base = base.rstrip("/") + "/"
    published_index_sha = fetch(
        urljoin(base, "testing/omega/addons.xml.sha256")
    ).decode("ascii").strip()
    if published_index_sha != expected_index_sha256:
        raise ValueError(
            "public testing index drift: expected %s, got %s"
            % (expected_index_sha256, published_index_sha)
        )
    published_index = fetch(urljoin(base, "testing/omega/addons.xml"))
    actual_index_sha = sha256_bytes(published_index)
    if actual_index_sha != published_index_sha:
        raise ValueError(
            "public testing index checksum mismatch: declared %s, got %s"
            % (published_index_sha, actual_index_sha)
        )
    lock = load_lock(testing_lock_path, "testing")
    output = Path(output)
    output.mkdir(parents=True, exist_ok=True)
    artifacts = {}
    for addon_id, pin in sorted(lock["components"].items()):
        filename = "%s-%s.zip" % (addon_id, pin["version"])
        relative = "testing/omega/%s/%s" % (addon_id, filename)
        payload = fetch(urljoin(base, relative))
        digest = sha256_bytes(payload)
        if digest != pin["zip_sha256"]:
            raise ValueError(
                "%s public ZIP drift: expected %s, got %s"
                % (addon_id, pin["zip_sha256"], digest)
            )
        (output / filename).write_bytes(payload)
        artifacts[addon_id] = {
            "filename": filename,
            "sha256": digest,
            "version": pin["version"],
        }
    candidate = {
        "schema": 1,
        "testing_index_sha256": published_index_sha,
        "components": artifacts,
    }
    (output / "candidate.json").write_text(
        json.dumps(candidate, indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )
    return candidate


def write_stable_lock(testing_lock_path, stable_lock_path, candidate_dir):
    testing = load_lock(testing_lock_path, "testing")
    candidate = json.loads(
        (Path(candidate_dir) / "candidate.json").read_text(encoding="utf-8")
    )
    for addon_id, pin in testing["components"].items():
        artifact = candidate["components"].get(addon_id)
        if not artifact or artifact["sha256"] != pin["zip_sha256"]:
            raise ValueError("candidate does not match testing lock: %s" % addon_id)
    stable = dict(testing)
    stable["channel"] = "stable"
    Path(stable_lock_path).write_text(
        json.dumps(stable, indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )
    return stable


def inject_candidate(dist, candidate_dir):
    dist = Path(dist)
    candidate_dir = Path(candidate_dir)
    candidate = json.loads(
        (candidate_dir / "candidate.json").read_text(encoding="utf-8")
    )
    for addon_id, artifact in candidate["components"].items():
        source = candidate_dir / artifact["filename"]
        target = dist / "stable" / "omega" / addon_id / artifact["filename"]
        generated = target.read_bytes()
        exact = source.read_bytes()
        if sha256_bytes(generated) != artifact["sha256"] or generated != exact:
            raise ValueError("stable build differs from exact testing ZIP: %s" % addon_id)
        shutil.copyfile(source, target)


def prepare_snapshot_lock(snapshot, attestation_path, current_stable, output):
    metadata = verify_bundle(snapshot)
    attestation = verify_device_attestation(attestation_path, snapshot)
    # Stable deployment downloads this exact release asset and verifies its
    # byte digest before validating the signed document. Preserve that digest
    # here; a canonical JSON digest would identify different bytes.
    attestation_digest = sha256_bytes(Path(attestation_path).read_bytes())
    testing = metadata["testing_lock"]
    stable = json.loads(json.dumps(testing))
    stable.update(
        {
            "schema": 2,
            "channel": "stable",
            "source_snapshot_id": metadata["snapshot_id"],
            "source_index_sha256": metadata["testing_index_sha256"],
            "source_artifact_manifest_sha256": metadata[
                "promotion_artifact_manifest_sha256"
            ],
            "attestation_sha256": attestation_digest,
            "attestation_id": attestation["attestation_id"],
        }
    )
    current = json.loads(Path(current_stable).read_text(encoding="utf-8"))
    identity = {
        "schema": 1,
        "base_lock_sha256": sha256_bytes(canonical_json(current)),
        "proposed_lock_sha256": sha256_bytes(canonical_json(stable)),
        "snapshot_id": metadata["snapshot_id"],
        "attestation_id": attestation["attestation_id"],
        "attestation_sha256": attestation_digest,
    }
    candidate = {**identity, "candidate_id": sha256_bytes(canonical_json(identity))}
    output = Path(output)
    if output.exists():
        raise ValueError("stable lock candidate output already exists")
    output.mkdir(parents=True)
    (output / "candidate.json").write_bytes(canonical_json(candidate))
    (output / "stable-lock.json").write_text(
        json.dumps(stable, indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )
    return candidate


def apply_snapshot_lock_candidate(bundle, stable_lock):
    bundle = Path(bundle)
    candidate = json.loads((bundle / "candidate.json").read_text(encoding="utf-8"))
    proposed = json.loads((bundle / "stable-lock.json").read_text(encoding="utf-8"))
    identity = {
        key: candidate[key]
        for key in (
            "schema",
            "base_lock_sha256",
            "proposed_lock_sha256",
            "snapshot_id",
            "attestation_id",
            "attestation_sha256",
        )
    }
    if candidate.get("candidate_id") != sha256_bytes(canonical_json(identity)):
        raise ValueError("stable lock candidate identity mismatch")
    current = json.loads(Path(stable_lock).read_text(encoding="utf-8"))
    if sha256_bytes(canonical_json(current)) != candidate["base_lock_sha256"]:
        raise ValueError("stable lock changed after candidate preparation")
    if sha256_bytes(canonical_json(proposed)) != candidate["proposed_lock_sha256"]:
        raise ValueError("proposed stable lock digest mismatch")
    if (
        proposed.get("source_snapshot_id") != candidate["snapshot_id"]
        or proposed.get("attestation_id") != candidate["attestation_id"]
        or proposed.get("attestation_sha256") != candidate["attestation_sha256"]
    ):
        raise ValueError("stable lock lost snapshot provenance")
    Path(stable_lock).write_text(
        json.dumps(proposed, indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )
    return candidate


def main():
    parser = argparse.ArgumentParser()
    subparsers = parser.add_subparsers(dest="command", required=True)
    fetch_parser = subparsers.add_parser("fetch")
    fetch_parser.add_argument("--base", required=True)
    fetch_parser.add_argument("--testing-lock", required=True)
    fetch_parser.add_argument("--expected-index-sha256", required=True)
    fetch_parser.add_argument("--output", required=True)
    lock_parser = subparsers.add_parser("lock")
    lock_parser.add_argument("--testing-lock", required=True)
    lock_parser.add_argument("--stable-lock", required=True)
    lock_parser.add_argument("--candidate", required=True)
    inject_parser = subparsers.add_parser("inject")
    inject_parser.add_argument("--dist", required=True)
    inject_parser.add_argument("--candidate", required=True)
    snapshot_lock = subparsers.add_parser("snapshot-lock")
    snapshot_lock.add_argument("--snapshot", required=True)
    snapshot_lock.add_argument("--attestation", required=True)
    snapshot_lock.add_argument("--stable-lock", required=True)
    snapshot_lock.add_argument("--output", required=True)
    apply_lock = subparsers.add_parser("apply-lock-candidate")
    apply_lock.add_argument("--bundle", required=True)
    apply_lock.add_argument("--stable-lock", required=True)
    args = parser.parse_args()
    if args.command == "fetch":
        fetch_candidate(
            args.base,
            args.testing_lock,
            args.expected_index_sha256,
            args.output,
        )
    elif args.command == "lock":
        write_stable_lock(args.testing_lock, args.stable_lock, args.candidate)
    elif args.command == "inject":
        inject_candidate(args.dist, args.candidate)
    elif args.command == "snapshot-lock":
        prepare_snapshot_lock(
            args.snapshot, args.attestation, args.stable_lock, args.output
        )
    else:
        apply_snapshot_lock_candidate(args.bundle, args.stable_lock)


if __name__ == "__main__":
    main()
