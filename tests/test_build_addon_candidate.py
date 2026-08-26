from pathlib import Path

import pytest

from tools.build_addon_candidate import build


def test_local_candidate_is_deterministic_and_identified(tmp_path):
    first = tmp_path / "first.zip"
    second = tmp_path / "second.zip"

    one = build("script.module.mwoscrapers", first)
    two = build("script.module.mwoscrapers", second)

    assert one["addon_id"] == "script.module.mwoscrapers"
    assert one["version"] == "0.2.1"
    assert one["zip_sha256"] == two["zip_sha256"]
    assert one["files"] == two["files"]


def test_local_candidate_ignores_packaging_residue(tmp_path):
    residue = Path("mwoscrapers/lib/mwoscrapers.egg-info/LOCAL")
    residue.parent.mkdir(parents=True, exist_ok=True)
    residue.write_text("untracked metadata", encoding="utf-8")
    try:
        candidate = build("script.module.mwoscrapers", tmp_path / "candidate.zip")
    finally:
        residue.unlink()

    import zipfile

    with zipfile.ZipFile(candidate["zip"]) as archive:
        assert not any(".egg-info/" in name for name in archive.namelist())


def test_local_candidate_rejects_output_inside_component_source():
    with pytest.raises(ValueError, match="outside component source"):
        build(
            "script.module.mwoscrapers",
            Path("mwoscrapers") / "candidate-inside-source.zip",
        )
