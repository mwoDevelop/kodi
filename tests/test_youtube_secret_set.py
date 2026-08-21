import json
import os

import pytest

from tools.youtube_secret_set import build, write_exclusive


def session():
    return {
        "schema": 1,
        "addon_id": "plugin.video.youtube",
        "addon_version": "7.4.4",
        "account_hint": "account@example.invalid",
        "api_key": "api",
        "client_id": "client",
        "client_secret": "secret",
        "expected_channel_id": "channel",
        "personal_refresh_token": "personal",
        "tv_refresh_token": "tv",
        "vr_refresh_token": "vr",
    }


def test_builds_prepared_secret_set_and_writes_private_file(tmp_path):
    document = build(session(), "youtube-home", 4)
    assert document["lifecycle"] == "PREPARED"
    assert document["generation"] == 4
    assert set(document["secret"]) == {
        "account_hint",
        "api_key",
        "client_id",
        "client_secret",
        "expected_channel_id",
        "personal_refresh_token",
        "tv_refresh_token",
        "vr_refresh_token",
    }
    path = tmp_path / "secret.json"
    write_exclusive(path, document)
    assert json.loads(path.read_text()) == document
    assert os.stat(path).st_mode & 0o077 == 0
    with pytest.raises(FileExistsError):
        write_exclusive(path, document)
