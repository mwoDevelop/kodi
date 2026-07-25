import json

import pytest

from tools.snapshot_bundle import create_bundle, verify_bundle


def _fixture(tmp_path):
    dist = tmp_path / "dist"
    (dist / "testing" / "omega").mkdir(parents=True)
    (dist / "testing" / "omega" / "addons.xml").write_text(
        "<addons/>\n", encoding="utf-8"
    )
    (dist / "artifact-manifest.sha256").write_text(
        "0" * 64 + "  testing/omega/addons.xml\n", encoding="ascii"
    )
    lock = tmp_path / "testing.json"
    lock.write_text(
        json.dumps({"schema": 1, "channel": "testing", "components": {}}),
        encoding="utf-8",
    )
    return dist, lock


def test_snapshot_bundle_is_deterministic_and_verifiable(tmp_path):
    dist, lock = _fixture(tmp_path)
    first = tmp_path / "first.tar"
    second = tmp_path / "second.tar"
    commit = "a" * 40

    one = create_bundle(dist, lock, commit, first)
    two = create_bundle(dist, lock, commit, second)

    assert one["snapshot_id"] == two["snapshot_id"]
    assert first.read_bytes() == second.read_bytes()
    assert verify_bundle(first)["snapshot_id"] == one["snapshot_id"]


def test_snapshot_verification_rejects_tampering(tmp_path):
    dist, lock = _fixture(tmp_path)
    bundle = tmp_path / "snapshot.tar"
    create_bundle(dist, lock, "b" * 40, bundle)
    payload = bytearray(bundle.read_bytes())
    marker = payload.index(b"<addons/>")
    payload[marker] ^= 1
    bundle.write_bytes(payload)

    with pytest.raises((ValueError, OSError)):
        verify_bundle(bundle)
