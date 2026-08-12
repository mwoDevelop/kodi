import pytest

from tools.kodi_mwoscrapers_probe import _validate


def _report(negative=0, movie=1, episode=1):
    return {
        "capabilities": {"provider": {"movies": True, "episodes": True}},
        "probe": [
            {
                "provider": "provider",
                "kind": "movie",
                "result_count": movie,
                "error_type": None,
            },
            {
                "provider": "provider",
                "kind": "episode",
                "result_count": episode,
                "error_type": None,
            },
            {
                "provider": "provider",
                "kind": "negative",
                "result_count": negative,
                "error_type": None,
            },
        ],
    }


def test_provider_probe_gate_requires_coverage_and_no_false_positive():
    _validate(_report())

    with pytest.raises(RuntimeError, match="false-positive"):
        _validate(_report(negative=1))
    with pytest.raises(RuntimeError, match="movie coverage"):
        _validate(_report(movie=0))
    with pytest.raises(RuntimeError, match="episode coverage"):
        _validate(_report(episode=0))
