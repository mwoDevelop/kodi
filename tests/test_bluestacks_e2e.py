import json
import sqlite3

import pytest

from tests.e2e import bluestacks_e2e
from tests.e2e.bluestacks_e2e import (
    addon_origins,
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


def test_expected_versions_come_from_exact_channel_locks(tmp_path, monkeypatch):
    locks = tmp_path / "manifests" / "locks"
    locks.mkdir(parents=True)
    channels = (("stable", "stable-version"), ("testing", "testing-version"))
    for channel, umbrella_version in channels:
        (locks / f"{channel}.json").write_text(
            json.dumps(
                {
                    "components": {
                        "plugin.video.umbrella": {"version": umbrella_version},
                        "script.module.mwoscrapers": {"version": "scraper-version"},
                    }
                }
            ),
            encoding="utf-8",
        )
    for repository_id in (
        "repository.mwodevelop",
        "repository.mwodevelop.testing",
    ):
        repository = tmp_path / "repository" / repository_id
        repository.mkdir(parents=True)
        (repository / "addon.xml").write_text(
            f'<addon id="{repository_id}" version="1.0.0"/>',
            encoding="utf-8",
        )
    monkeypatch.setattr(bluestacks_e2e, "ROOT", tmp_path)

    stable = bluestacks_e2e.expected_versions("repository.mwodevelop")
    testing = bluestacks_e2e.expected_versions("repository.mwodevelop.testing")

    assert stable["plugin.video.umbrella"] == "stable-version"
    assert testing["plugin.video.umbrella"] == "testing-version"
    assert stable["script.module.mwoscrapers"] == "scraper-version"
    assert stable["repository.mwodevelop"] == "1.0.0"
