import datetime as dt
import json

import pytest

from tools.device_attestation import create, verify
from tools.snapshot_bundle import create_bundle


def _fixture(tmp_path):
    dist = tmp_path / "dist"
    (dist / "testing/omega").mkdir(parents=True)
    (dist / "testing/omega/addons.xml").write_text("<addons/>\n")
    (dist / "artifact-manifest.sha256").write_text("manifest\n")
    lock = tmp_path / "testing.json"
    lock.write_text(
        json.dumps({"schema": 1, "channel": "testing", "components": {}})
    )
    snapshot = tmp_path / "snapshot.tar"
    create_bundle(dist, lock, "a" * 40, snapshot)
    check = {
        "name": "functional",
        "result": "passed",
        "evidence_sha256": "2" * 64,
    }
    matrix = tmp_path / "matrix.json"
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
                        "addons": {"plugin.video.umbrella": "6.7.81.18"},
                        "checks": [check],
                    },
                    {
                        "logical_device_id": "sony-tv",
                        "device_class": "android-tv",
                        "kodi_version": "21.2",
                        "addons": {"plugin.video.umbrella": "6.7.81.18"},
                        "checks": [check],
                    },
                ],
            }
        )
    )
    return snapshot, matrix


def test_attestation_binds_snapshot_runner_nonce_and_matrix(tmp_path):
    snapshot, matrix = _fixture(tmp_path)
    output = tmp_path / "attestation.json"
    issued = dt.datetime.now(dt.timezone.utc)
    document = create(
        snapshot,
        matrix,
        "mwoDevelop/kodi",
        "a" * 40,
        "42",
        1,
        "runner",
        "ab" * 32,
        issued.isoformat(),
        (issued + dt.timedelta(hours=1)).isoformat(),
        output,
    )

    assert verify(output, snapshot)["attestation_id"] == document["attestation_id"]


def test_attestation_rejects_expiry_and_missing_canary_class(tmp_path):
    snapshot, matrix = _fixture(tmp_path)
    payload = json.loads(matrix.read_text())
    payload["devices"] = payload["devices"][:1]
    matrix.write_text(json.dumps(payload))
    issued = dt.datetime.now(dt.timezone.utc)

    with pytest.raises(ValueError, match="required canary"):
        create(
            snapshot,
            matrix,
            "mwoDevelop/kodi",
            "a" * 40,
            "42",
            1,
            "runner",
            "ab" * 32,
            issued.isoformat(),
            (issued + dt.timedelta(hours=1)).isoformat(),
            tmp_path / "attestation.json",
        )
