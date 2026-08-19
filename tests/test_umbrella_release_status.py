import datetime as dt
import json

import pytest

from tools.umbrella_release_status import create, validate


NOW = dt.datetime(2026, 8, 19, 10, tzinfo=dt.timezone.utc)


def stable_lock(tmp_path):
    path = tmp_path / "stable.json"
    path.write_text(
        json.dumps(
            {
                "schema": 2,
                "channel": "stable",
                "components": {
                    "plugin.video.umbrella": {"version": "6.7.81.20"}
                },
            }
        )
    )
    return path


def document(tmp_path, **overrides):
    values = {
        "stable_lock": overrides.pop("stable_lock", None) or stable_lock(tmp_path),
        "upstream_version": "6.7.84",
        "upstream_commit": "a" * 40,
        "stable_base_commit": "c" * 40,
        "stable_upstream_base": "6.7.81",
        "pipeline_state": "qualifying",
        "release_health": "healthy",
        "generated_at": "2026-08-19T10:00:00Z",
        "expires_at": "2026-08-21T10:00:00Z",
        "candidate_id": "b" * 64,
    }
    values.update(overrides)
    return create(**values)


def test_status_keeps_pipeline_release_and_versions_independent(tmp_path):
    result = document(tmp_path)

    assert result["pipeline"]["state"] == "qualifying"
    assert result["release"]["health"] == "healthy"
    assert result["versions"] == {
        "upstream": "6.7.84",
        "stable": "6.7.81.20",
        "stable_upstream_base": "6.7.81",
    }
    assert result["upstream"] == {
        "commit": "a" * 40,
        "stable_base_commit": "c" * 40,
    }


def test_status_rejects_expiry_unknown_fields_and_unsafe_errors(tmp_path):
    value = document(tmp_path)
    with pytest.raises(ValueError, match="expired"):
        validate(value, now=NOW + dt.timedelta(hours=49))

    value = document(tmp_path)
    value["extra"] = True
    with pytest.raises(ValueError, match="unsupported"):
        validate(value, now=NOW)

    with pytest.raises(ValueError, match="failure code"):
        document(tmp_path, pipeline_state="blocked", failure_code="token=secret")


def test_forward_rollback_keeps_true_upstream_base(tmp_path):
    path = stable_lock(tmp_path)
    payload = json.loads(path.read_text())
    payload["components"]["plugin.video.umbrella"]["version"] = "6.7.84.2"
    path.write_text(json.dumps(payload))

    result = document(
        tmp_path,
        stable_lock=path,
        upstream_version="6.7.84",
        stable_upstream_base="6.7.81",
        pipeline_state="in_sync",
        candidate_id=None,
    )
    assert result["versions"]["stable"] == "6.7.84.2"
    assert result["versions"]["stable_upstream_base"] == "6.7.81"
