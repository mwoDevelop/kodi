import json

import pytest

from tools.umbrella_promotion_approval import verify


def put(path, value):
    path.write_text(json.dumps(value), encoding="utf-8")
    return path


def inputs(tmp_path):
    old_pin = {"commit": "1" * 40, "version": "6.7.81.20", "zip_sha256": "2" * 64}
    new_pin = {"commit": "3" * 40, "version": "6.7.84.1", "zip_sha256": "4" * 64}
    other = {"commit": "5" * 40, "version": "1.0.0", "zip_sha256": "6" * 64}
    base = {"schema": 2, "channel": "stable", "components": {"plugin.video.umbrella": old_pin, "other": other}}
    head = {
        "schema": 2,
        "channel": "stable",
        "components": {"plugin.video.umbrella": new_pin, "other": other},
        "source_snapshot_id": "7" * 64,
        "source_index_sha256": "8" * 64,
        "source_artifact_manifest_sha256": "9" * 64,
        "attestation_kind": "hermetic_ci",
        "promotion_kind": "normal",
        "attestation_id": "a" * 64,
        "attestation_sha256": "b" * 64,
    }
    testing = {"schema": 1, "channel": "testing", "components": head["components"]}
    qnap = {"schema": 1, "channel": "stable", "candidate_id": "c" * 64, "services": {}}
    sha = "d" * 40
    pr = {
        "number": 22,
        "author": "app/github-actions",
        "base": "main",
        "head": "automation/promote-stable-777777777777",
        "head_sha": sha,
        "draft": False,
        "files": ["manifests/locks/stable.json"],
    }
    checks = [{"name": "e2e", "status": "completed", "conclusion": "success", "head_sha": sha}]
    return tuple(
        put(tmp_path / name, value)
        for name, value in (
            ("base.json", base), ("head.json", head), ("testing.json", testing),
            ("base-qnap.json", qnap), ("head-qnap.json", qnap), ("pr.json", pr),
            ("checks.json", checks),
        )
    )


def test_accepts_exact_qualified_umbrella_promotion(tmp_path):
    value = verify(*inputs(tmp_path))
    assert value["eligible"] is True
    assert value["to_version"] == "6.7.84.1"


def test_rejects_qnap_drift(tmp_path):
    args = list(inputs(tmp_path))
    value = json.loads(args[4].read_text())
    value["candidate_id"] = "e" * 64
    put(args[4], value)
    with pytest.raises(ValueError, match="QNAP"):
        verify(*args)
