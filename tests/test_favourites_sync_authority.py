import json

import pytest

from tools.favourites_sync_authority import generate, validate


def test_authority_generation_is_private_valid_and_redacted(tmp_path):
    path = tmp_path / "private" / "authority.json"

    result = generate(path, "favourites-authority-1")

    assert result == {
        "schema": 1,
        "key_id": "favourites-authority-1",
        "status": "VALID",
    }
    assert path.stat().st_mode & 0o077 == 0
    assert len(json.loads(path.read_text())["seed"]) == 43
    assert "seed" not in result
    assert validate(path) == result


def test_generation_never_overwrites_existing_authority(tmp_path):
    path = tmp_path / "authority.json"
    generate(path, "favourites-authority-1")

    with pytest.raises(FileExistsError):
        generate(path, "favourites-authority-2")
