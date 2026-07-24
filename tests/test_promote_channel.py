import hashlib
import json

import pytest

from tools import promote_channel


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
