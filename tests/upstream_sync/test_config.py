import json
from pathlib import Path

import pytest

from tools.upstream_sync.config import load_manifest, load_release_groups


ROOT = Path(__file__).parents[2]


def test_checked_in_manifests_are_valid():
    manifest = load_manifest(ROOT / "manifests/upstreams.json")
    groups = load_release_groups(ROOT / "manifests/release-groups.json")

    assert set(manifest["components"]) == {
        "umbrella",
        "watchnixtoons2",
        "provider_observations",
    }
    assert groups["groups"]["mwoscrapers"]["components"] == [
        "script.module.mwoscrapers",
        "script.mwoscrapers",
    ]


def test_manifest_rejects_target_escape(tmp_path):
    payload = json.loads((ROOT / "manifests/upstreams.json").read_text())
    payload["components"]["umbrella"]["local_path"] = "../umbrella"
    path = tmp_path / "upstreams.json"
    path.write_text(json.dumps(payload), encoding="utf-8")

    with pytest.raises(ValueError, match="unsafe"):
        load_manifest(path)


def test_manifest_rejects_unknown_adapter(tmp_path):
    payload = json.loads((ROOT / "manifests/upstreams.json").read_text())
    payload["components"]["umbrella"]["adapter"] = "shell"
    path = tmp_path / "upstreams.json"
    path.write_text(json.dumps(payload), encoding="utf-8")

    with pytest.raises(ValueError, match="unknown adapter"):
        load_manifest(path)
