import json

from tools.upstream_sync.engine import AdapterRegistry, discover_all, render_markdown
from tools.upstream_sync.models import (
    ContentState,
    Discovery,
    HistoryState,
    Identity,
    ProvenanceState,
)


class FakeAdapter:
    def __init__(self, context):
        self.context = context

    def discover(self):
        return Discovery(
            component=self.context.name,
            accepted=Identity(commit="a" * 40),
            observed=Identity(commit="b" * 40),
            content=ContentState.CHANGED,
            provenance=ProvenanceState.CHANGED,
            history=HistoryState.FAST_FORWARD,
            changed_paths=("addon.xml",),
        )


def test_engine_is_extended_through_registry(tmp_path):
    (tmp_path / "component").mkdir()
    manifest = {
        "schema": 1,
        "schedule_slots": {"daily": {"cron": "20 4 * * *"}},
        "components": {
            "sample": {
                "enabled": True,
                "adapter": "git_patch_stack",
                "schedule_slot": "daily",
                "local_path": "component",
                "target": {"repository": "owner/repo", "branch": "main"},
                "version_policy": "sample",
            }
        },
    }
    path = tmp_path / "manifest.json"
    path.write_text(json.dumps(manifest), encoding="utf-8")
    registry = AdapterRegistry()
    registry.register("git_patch_stack", FakeAdapter)

    report = discover_all(tmp_path, path, registry=registry)

    assert report["sources"][0]["action"] == "open_or_update_pr"
    assert report["sources"][0]["changed_paths"] == ["addon.xml"]
    assert "sample" in render_markdown(report)


def test_disabled_component_is_skipped(tmp_path):
    (tmp_path / "component").mkdir()
    manifest = {
        "schema": 1,
        "schedule_slots": {"daily": {"cron": "20 4 * * *"}},
        "components": {
            "sample": {
                "enabled": False,
                "adapter": "git_patch_stack",
                "schedule_slot": "daily",
                "local_path": "component",
                "target": {"repository": "owner/repo", "branch": "main"},
                "version_policy": "sample",
            }
        },
    }
    path = tmp_path / "manifest.json"
    path.write_text(json.dumps(manifest), encoding="utf-8")
    registry = AdapterRegistry()
    registry.register("git_patch_stack", FakeAdapter)

    assert discover_all(tmp_path, path, registry=registry)["sources"] == []
