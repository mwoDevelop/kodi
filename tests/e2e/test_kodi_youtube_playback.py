from kodi_youtube_playback import (
    diagnostic_counts,
    stalled_intervals,
    successful_probe,
)


def test_diagnostics_detect_the_android_vr_segment_failure_without_urls():
    log = """
Client: 28 (ANDROID_VR)
Status: 403 Forbidden
Download failed, HTTP error 403: https://signed.invalid/private
Segment download failed, attempt 6...
ActiveAE - large audio sync error: -1000
CVideoPlayerVideo - Stillframe detected
"""

    assert diagnostic_counts(log) == {
        "http_403": 2,
        "segment_download_failed": 2,
        "large_audio_sync_error": 1,
        "stillframe": 1,
        "android_vr_client": 1,
    }


def test_stall_detection_ignores_startup_but_rejects_a_later_freeze():
    samples = [
        {"wall_seconds": 2, "media_seconds": 0},
        {"wall_seconds": 4, "media_seconds": 0},
        {"wall_seconds": 6, "media_seconds": 2},
        {"wall_seconds": 8, "media_seconds": 2},
    ]

    assert stalled_intervals(samples) == 1


def test_success_requires_progress_and_clean_segment_diagnostics():
    report = {
        "state": "played",
        "media_progress_seconds": 92,
        "stalled_intervals": 0,
        "diagnostics": {
            "http_403": 0,
            "segment_download_failed": 0,
            "large_audio_sync_error": 0,
            "stillframe": 0,
            "android_vr_client": 0,
        },
    }

    assert successful_probe(report, 80) is True
    report["diagnostics"]["http_403"] = 1
    assert successful_probe(report, 80) is False
