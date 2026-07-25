import sqlite3

import pytest

from tests.e2e.bluestacks_e2e import (
    addon_origins,
    expected_versions,
    playback_log_evidence,
)


def test_playback_log_evidence_uses_the_last_matching_run():
    log = """
VideoPlayer::OpenFile: plugin://plugin.video.umbrella/?title=Sintel&imdb=tt1727587
Creating InputStream
Creating Demuxer
CDVDVideoCodecAndroidMediaCodec::Open Using codec: old
CDVDAudioCodecFFmpeg::Open() Successful opened audio decoder aac
CVideoPlayer::CloseFile()
VideoPlayer::OpenFile: plugin://plugin.video.umbrella/?title=Sintel&imdb=tt1727587
Creating InputStream
Creating Demuxer
CDVDVideoCodecAndroidMediaCodec::Open Using codec: current
CDVDAudioCodecFFmpeg::Open() Successful opened audio decoder aac
CVideoPlayer::CloseFile()
"""
    evidence = playback_log_evidence(log, "Sintel", "tt1727587")

    assert any("Using codec: current" in line for line in evidence)
    assert not any("Using codec: old" in line for line in evidence)


def test_playback_log_evidence_requires_a_closed_player():
    log = """
VideoPlayer::OpenFile: plugin://plugin.video.umbrella/?title=Sintel&imdb=tt1727587
Creating InputStream
Creating Demuxer
CDVDVideoCodecAndroidMediaCodec::Open Using codec: current
CDVDAudioCodecFFmpeg::Open() Successful opened audio decoder aac
"""
    with pytest.raises(RuntimeError, match="CVideoPlayer::CloseFile"):
        playback_log_evidence(log, "Sintel", "tt1727587")


def test_addon_origins_reads_kodi_installed_table(tmp_path):
    database = tmp_path / "Addons33.db"
    with sqlite3.connect(database) as connection:
        connection.execute(
            "CREATE TABLE installed (addonID TEXT PRIMARY KEY, origin TEXT)"
        )
        connection.executemany(
            "INSERT INTO installed (addonID, origin) VALUES (?, ?)",
            (
                ("plugin.video.umbrella", "repository.mwodevelop"),
                ("script.module.mwoscrapers", "repository.mwodevelop"),
                (
                    "repository.mwodevelop.testing",
                    "repository.mwodevelop.testing",
                ),
            ),
        )

    assert addon_origins(
        database, ("plugin.video.umbrella", "script.module.mwoscrapers")
    ) == {
        "plugin.video.umbrella": "repository.mwodevelop",
        "script.module.mwoscrapers": "repository.mwodevelop",
    }


def test_expected_versions_come_from_exact_channel_locks():
    stable = expected_versions("repository.mwodevelop")
    testing = expected_versions("repository.mwodevelop.testing")

    assert stable["plugin.video.umbrella"] == "6.7.81.9"
    assert testing["script.module.mwoscrapers"] == "0.1.3"
    assert stable["repository.mwodevelop"] == "1.0.0"
