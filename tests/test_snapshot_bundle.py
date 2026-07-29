import json

import pytest

from tools.snapshot_bundle import create_bundle, extract_section, verify_bundle


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


def test_snapshot_keeps_distinct_prebuilt_promotion_payload(tmp_path):
    dist, lock = _fixture(tmp_path)
    promotion = tmp_path / "promotion"
    (promotion / "testing" / "omega").mkdir(parents=True)
    (promotion / "testing" / "omega" / "addons.xml").write_text(
        "<testing/>\n", encoding="utf-8"
    )
    (promotion / "stable" / "omega").mkdir(parents=True)
    (promotion / "stable" / "omega" / "addons.xml").write_text(
        "<stable/>\n", encoding="utf-8"
    )
    (promotion / "artifact-manifest.sha256").write_text(
        "1" * 64 + "  stable/omega/addons.xml\n", encoding="ascii"
    )
    bundle = tmp_path / "snapshot.tar"
    metadata = create_bundle(
        dist, lock, "c" * 40, bundle, promotion_dist=promotion
    )

    extracted = tmp_path / "extracted"
    verified = extract_section(bundle, "promotion", extracted)

    assert verified["snapshot_id"] == metadata["snapshot_id"]
    assert (extracted / "stable/omega/addons.xml").read_text() == "<stable/>\n"
    assert not (extracted / "payload").exists()
