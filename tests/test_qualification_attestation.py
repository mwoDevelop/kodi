import datetime as dt
import json

import pytest

from tools.qualification_attestation import create, verify
from tools.snapshot_bundle import create_bundle


def fixture(tmp_path):
    dist = tmp_path / "dist"
    (dist / "testing/omega").mkdir(parents=True)
    (dist / "testing/omega/addons.xml").write_text("<addons/>\n")
    (dist / "artifact-manifest.sha256").write_text("manifest\n")
    lock = tmp_path / "testing.json"
    lock.write_text(json.dumps({"schema": 1, "channel": "testing", "components": {}}))
    snapshot = tmp_path / "snapshot.tar"
    create_bundle(dist, lock, "a" * 40, snapshot)
    report = tmp_path / "report.json"
    report.write_text(
        json.dumps(
            {
                "schema": 1,
                "qualification_type": "hermetic_ci",
                "component": "plugin.video.umbrella",
                "result": "passed",
                "checks": [
                    {
                        "name": "deterministic-build",
                        "result": "passed",
                        "evidence_sha256": "b" * 64,
                    }
                ],
            }
        )
    )
    return snapshot, report


def test_qualification_binds_exact_snapshot_and_report(tmp_path):
    snapshot, report = fixture(tmp_path)
    output = tmp_path / "qualification.json"
    issued = dt.datetime.now(dt.timezone.utc)
    document = create(
        snapshot,
        report,
        "mwoDevelop/kodi",
        "a" * 40,
        "42",
        1,
        "ab" * 32,
        issued.isoformat(),
        (issued + dt.timedelta(hours=1)).isoformat(),
        output,
    )

    assert verify(output, snapshot)["attestation_id"] == document["attestation_id"]


def test_qualification_rejects_failed_or_tampered_report(tmp_path):
    snapshot, report = fixture(tmp_path)
    payload = json.loads(report.read_text())
    payload["result"] = "failed"
    report.write_text(json.dumps(payload))
    issued = dt.datetime.now(dt.timezone.utc)

    with pytest.raises(ValueError, match="not a passing"):
        create(
            snapshot,
            report,
            "mwoDevelop/kodi",
            "a" * 40,
            "42",
            1,
            "ab" * 32,
            issued.isoformat(),
            (issued + dt.timedelta(hours=1)).isoformat(),
            tmp_path / "qualification.json",
        )
