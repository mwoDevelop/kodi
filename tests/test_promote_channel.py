import hashlib
import json
import datetime as dt

import pytest

from tools import promote_channel
from tools.device_attestation import create as create_attestation
from tools.snapshot_bundle import create_bundle


def _lock(path, channel, digest):
    payload = {
        "schema": 1,
        "channel": channel,
        "components": {
            "plugin.video.example": {
                "commit": "a" * 40,
                "version": "1.2.3",
                "zip_sha256": digest,
            }
        },
    }
    path.write_text(json.dumps(payload), encoding="utf-8")
    return payload


def test_fetch_and_lock_exact_public_candidate(tmp_path, monkeypatch):
    package = b"exact testing zip"
    index = b"<addons />\n"
    digest = hashlib.sha256(package).hexdigest()
    index_digest = hashlib.sha256(index).hexdigest()
    testing_lock = tmp_path / "testing.json"
    stable_lock = tmp_path / "stable.json"
    _lock(testing_lock, "testing", digest)

    def fetch(url):
        if url.endswith("testing/omega/addons.xml.sha256"):
            return (index_digest + "\n").encode()
        if url.endswith("testing/omega/addons.xml"):
            return index
        if url.endswith("plugin.video.example-1.2.3.zip"):
            return package
        raise AssertionError(url)

    monkeypatch.setattr(promote_channel, "fetch", fetch)
    candidate_dir = tmp_path / "candidate"
    candidate = promote_channel.fetch_candidate(
        "https://example.invalid/",
        testing_lock,
        index_digest,
        candidate_dir,
    )
    stable = promote_channel.write_stable_lock(
        testing_lock, stable_lock, candidate_dir
    )

    assert candidate["components"]["plugin.video.example"]["sha256"] == digest
    assert stable["channel"] == "stable"
    assert stable["components"] == _lock(
        tmp_path / "expected.json", "testing", digest
    )["components"]


def test_inject_rejects_nonidentical_stable_build(tmp_path):
    package = b"exact testing zip"
    digest = hashlib.sha256(package).hexdigest()
    candidate_dir = tmp_path / "candidate"
    candidate_dir.mkdir()
    filename = "plugin.video.example-1.2.3.zip"
    (candidate_dir / filename).write_bytes(package)
    (candidate_dir / "candidate.json").write_text(
        json.dumps(
            {
                "schema": 1,
                "components": {
                    "plugin.video.example": {
                        "filename": filename,
                        "sha256": digest,
                        "version": "1.2.3",
                    }
                },
            }
        ),
        encoding="utf-8",
    )
    target = (
        tmp_path
        / "dist/stable/omega/plugin.video.example/plugin.video.example-1.2.3.zip"
    )
    target.parent.mkdir(parents=True)
    target.write_bytes(b"different")

    with pytest.raises(ValueError, match="differs from exact testing ZIP"):
        promote_channel.inject_candidate(tmp_path / "dist", candidate_dir)


def _snapshot_and_attestation(tmp_path):
    dist = tmp_path / "dist"
    (dist / "testing/omega").mkdir(parents=True)
    (dist / "testing/omega/addons.xml").write_text("<addons/>\n")
    (dist / "artifact-manifest.sha256").write_text("payload manifest\n")
    promotion = tmp_path / "promotion"
    (promotion / "testing/omega").mkdir(parents=True)
    (promotion / "testing/omega/addons.xml").write_text("<addons/>\n")
    (promotion / "artifact-manifest.sha256").write_text("promotion manifest\n")
    testing_lock = tmp_path / "testing.json"
    testing_lock.write_text(
        json.dumps({"schema": 1, "channel": "testing", "components": {}})
    )
    snapshot = tmp_path / "snapshot.tar"
    create_bundle(
        dist,
        testing_lock,
        "d" * 40,
        snapshot,
        promotion_dist=promotion,
    )
    matrix = tmp_path / "matrix.json"
    check = {
        "name": "repository-install",
        "result": "passed",
        "evidence_sha256": "1" * 64,
    }
    matrix.write_text(
        json.dumps(
            {
                "schema": 1,
                "result": "passed",
                "devices": [
                    {
                        "logical_device_id": "bluestacks1",
                        "device_class": "android-emulator",
                        "kodi_version": "21.2",
                        "addons": {"plugin.video.umbrella": "1.0.0"},
                        "checks": [check],
                    },
                    {
                        "logical_device_id": "sony-tv",
                        "device_class": "android-tv",
                        "kodi_version": "21.2",
                        "addons": {"plugin.video.umbrella": "1.0.0"},
                        "checks": [check],
                    },
                ],
            }
        )
    )
    issued = dt.datetime.now(dt.timezone.utc)
    attestation = tmp_path / "device-attestation.json"
    create_attestation(
        snapshot,
        matrix,
        "mwoDevelop/kodi",
        "d" * 40,
        "123",
        1,
        "kodi-release-runner",
        "ab" * 32,
        issued.isoformat(),
        (issued + dt.timedelta(days=1)).isoformat(),
        attestation,
    )
    return snapshot, attestation


def test_snapshot_lock_is_content_addressed_and_applies_only_once(tmp_path):
    snapshot, attestation = _snapshot_and_attestation(tmp_path)
    # Exercise a valid but non-canonical asset representation. The stable lock
    # must bind the bytes published in the release, not a re-serialized object.
    attestation_document = json.loads(attestation.read_text())
    attestation.write_text(
        json.dumps(attestation_document, indent=4, sort_keys=False) + "\n",
        encoding="utf-8",
    )
    attestation_asset_sha256 = hashlib.sha256(attestation.read_bytes()).hexdigest()
    stable_lock = tmp_path / "stable.json"
    stable_lock.write_text(
        json.dumps({"schema": 1, "channel": "stable", "components": {}})
    )
    bundle = tmp_path / "candidate"

    candidate = promote_channel.prepare_snapshot_lock(
        snapshot, attestation, stable_lock, bundle
    )
    promote_channel.apply_snapshot_lock_candidate(bundle, stable_lock)
    promoted = json.loads(stable_lock.read_text())

    assert promoted["schema"] == 2
    assert promoted["source_snapshot_id"] == candidate["snapshot_id"]
    assert promoted["attestation_id"] == candidate["attestation_id"]
    assert promoted["attestation_sha256"] == candidate["attestation_sha256"]
    assert promoted["attestation_sha256"] == attestation_asset_sha256
    with pytest.raises(ValueError, match="changed after candidate preparation"):
        promote_channel.apply_snapshot_lock_candidate(bundle, stable_lock)
