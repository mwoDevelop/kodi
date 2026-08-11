import json
from pathlib import Path

import pytest

from tools.build_legacy_migration_kit import build_kit
from tools.kodi_devices import validate_registry
from tools.kodi_profile import load_policy
from tools.kodi_reinstall import load_config
from tools.schema_lifecycle import load_lifecycle, validate_markdown


ROOT = Path(__file__).resolve().parents[1]


def test_lifecycle_documentation_matches_machine_manifest():
    document = load_lifecycle(ROOT / "manifests/schema-lifecycle.json")
    assert validate_markdown(ROOT / "docs/schema-lifecycle.md", document)
    for entry in document["formats"].values():
        reader = entry.get("production_reader")
        if reader and reader.startswith(("tools/", "profile-sync-addon/")):
            assert (ROOT / reader).is_file(), reader
        migrator = entry.get("offline_migrator")
        if migrator:
            assert (ROOT / migrator).is_file(), migrator


def test_production_readers_reject_retired_schema_one(tmp_path, monkeypatch):
    with pytest.raises(ValueError, match="unsupported device inventory schema"):
        validate_registry({"schema": 1, "devices": {"legacy": {}}})
    policy = tmp_path / "policy.json"
    policy.write_text(
        json.dumps({"schema": 1, "include": ["**"], "exclude": []}),
        encoding="utf-8",
    )
    with pytest.raises(ValueError, match="unsupported Kodi profile policy"):
        load_policy(policy)
    repository = tmp_path / "repo"
    private = repository / ".kodi-private"
    private.mkdir(parents=True)
    reinstall = private / "kodi-reinstall.json"
    reinstall.write_text(
        json.dumps({"schema": 1, "targets": [{"name": "legacy"}]}),
        encoding="utf-8",
    )
    monkeypatch.setattr(
        "tools.kodi_profile.subprocess.run",
        lambda *args, **kwargs: type("Result", (), {"returncode": 0})(),
    )
    with pytest.raises(ValueError, match="unsupported Kodi reinstall config"):
        load_config(reinstall, repository)


def test_offline_migration_kit_is_reproducible_and_self_describing(tmp_path):
    first = tmp_path / "first.zip"
    second = tmp_path / "second.zip"

    result = build_kit(ROOT, first)
    repeated = build_kit(ROOT, second)

    assert result["sha256"] == repeated["sha256"]
    assert first.read_bytes() == second.read_bytes()
