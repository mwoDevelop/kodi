import json

import pytest

from tools.umbrella_auto_approval import verify


def write(path, value):
    path.write_text(json.dumps(value), encoding="utf-8")
    return path


def locks():
    old = {
        "schema": 1,
        "channel": "testing",
        "components": {
            "plugin.video.umbrella": {
                "commit": "1" * 40,
                "version": "6.7.81.20",
                "zip_sha256": "2" * 64,
            },
            "script.module.mwoscrapers": {
                "commit": "3" * 40,
                "version": "0.2.0",
                "zip_sha256": "4" * 64,
            },
        },
    }
    new = json.loads(json.dumps(old))
    new["components"]["plugin.video.umbrella"] = {
        "commit": "5" * 40,
        "version": "6.7.84.1",
        "zip_sha256": "6" * 64,
    }
    return old, new


def inputs(tmp_path):
    old, new = locks()
    sha = "7" * 40
    return (
        write(tmp_path / "base.json", old),
        write(tmp_path / "head.json", new),
        write(
            tmp_path / "pr.json",
            {
                "number": 12,
                "author": "app/github-actions",
                "base": "main",
                "head": "automation/testing-lock-plugin-video-umbrella",
                "head_sha": sha,
                "draft": False,
                "files": ["manifests/locks/testing.json"],
            },
        ),
        write(
            tmp_path / "checks.json",
            [
                {
                    "name": "e2e",
                    "status": "completed",
                    "conclusion": "success",
                    "head_sha": sha,
                }
            ],
        ),
    )


def test_accepts_exact_forward_umbrella_lock_pr(tmp_path):
    value = verify(*inputs(tmp_path))
    assert value["eligible"] is True
    assert value["to_version"] == "6.7.84.1"


def test_rejects_an_additional_changed_component(tmp_path):
    base, head, pr, checks = inputs(tmp_path)
    value = json.loads(head.read_text())
    value["components"]["script.module.mwoscrapers"]["version"] = "0.3.0"
    write(head, value)
    with pytest.raises(ValueError, match="Umbrella-only"):
        verify(base, head, pr, checks)


def test_rejects_pending_checks(tmp_path):
    base, head, pr, checks = inputs(tmp_path)
    value = json.loads(checks.read_text())
    value[0]["status"] = "in_progress"
    value[0]["conclusion"] = None
    write(checks, value)
    with pytest.raises(ValueError, match="not successful"):
        verify(base, head, pr, checks)
