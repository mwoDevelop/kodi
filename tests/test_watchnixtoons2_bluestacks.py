import sqlite3

import pytest

from tests.e2e.watchnixtoons2_bluestacks import (
    ADDON_ID,
    installed_rows,
    playback_log_evidence,
)


def test_installed_rows_exposes_origin_and_enabled_state(tmp_path):
    database = tmp_path / "addons.db"
    with sqlite3.connect(database) as connection:
        connection.execute(
            "CREATE TABLE installed ("
            "addonID TEXT, enabled INTEGER, origin TEXT, disabledReason INTEGER)"
        )
        connection.execute(
            "INSERT INTO installed VALUES (?, ?, ?, ?)",
            (ADDON_ID, 1, "repository.mwodevelop", 0),
        )

    assert installed_rows(database)[ADDON_ID] == {
        "enabled": True,
        "origin": "repository.mwodevelop",
        "disabled_reason": 0,
    }


def test_playback_log_evidence_requires_complete_pipeline():
    log = "\n".join(
        [
            "VideoPlayer::OpenFile: plugin://%s/?url=%%2Fsample-title" % ADDON_ID,
            "Creating InputStream",
            "Creating Demuxer",
            "Successful opened audio decoder aac",
            "CVideoPlayer::CloseFile()",
        ]
    )

    assert len(playback_log_evidence(log, "sample-title")) == 5


def test_playback_log_evidence_rejects_missing_decoder():
    log = "\n".join(
        [
            "VideoPlayer::OpenFile: plugin://%s/?url=%%2Fsample-title" % ADDON_ID,
            "Creating InputStream",
            "Creating Demuxer",
            "CVideoPlayer::CloseFile()",
        ]
    )

    with pytest.raises(RuntimeError, match="Successful opened audio decoder"):
        playback_log_evidence(log, "sample-title")
