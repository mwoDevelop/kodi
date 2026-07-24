import pytest

from tests.e2e.bluestacks_e2e import playback_log_evidence


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
