import hashlib
import json
from pathlib import Path

import pytest

from tools.qualify_umbrella_snapshot import report


def test_report_binds_named_evidence(tmp_path):
    context = tmp_path / "context.json"
    evidence = tmp_path / "pytest.txt"
    output = tmp_path / "report.json"
    context.write_text(
        json.dumps(
            {
                "schema": 1,
                "component": "plugin.video.umbrella",
                "changed_components": ["plugin.video.umbrella"],
            }
        ),
        encoding="utf-8",
    )
    evidence.write_text("55 passed\n", encoding="utf-8")

    value = report(context, ["umbrella-tests=%s" % evidence], output)

    assert value["result"] == "passed"
    assert value["checks"] == [
        {
            "name": "umbrella-tests",
            "result": "passed",
            "evidence_sha256": hashlib.sha256(evidence.read_bytes()).hexdigest(),
        }
    ]


def test_report_rejects_duplicate_or_missing_evidence(tmp_path):
    context = tmp_path / "context.json"
    evidence = tmp_path / "pytest.txt"
    context.write_text(
        json.dumps(
            {
                "schema": 1,
                "component": "plugin.video.umbrella",
                "changed_components": ["plugin.video.umbrella"],
            }
        ),
        encoding="utf-8",
    )
    evidence.write_text("ok", encoding="utf-8")

    with pytest.raises(ValueError, match="evidence"):
        report(
            context,
            ["same=%s" % evidence, "same=%s" % evidence],
            tmp_path / "report.json",
        )
