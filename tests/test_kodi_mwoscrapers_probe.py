import pytest

from tools import kodi_mwoscrapers_probe
from tools.kodi_mwoscrapers_probe import (
    EXPECTED_CASES,
    EXPECTED_PROVIDERS,
    _validate,
)


def _report(negative=0, movie=1, episode=1):
    counts = {"movie": movie, "episode": episode, "negative": negative}
    return {
        "capabilities": {
            provider: {"movies": True, "episodes": True}
            for provider in EXPECTED_PROVIDERS
        },
        "probe": [
            {
                "provider": provider,
                "case": case,
                "kind": kind,
                "result_count": counts[kind],
                "error_type": None,
            }
            for provider in EXPECTED_PROVIDERS
            for case, kind in EXPECTED_CASES.items()
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

    report = _report()
    target = next(
        row
        for row in report["probe"]
        if row["provider"] == "torrentio" and row["case"] == "movie-older"
    )
    target["result_count"] = 0
    with pytest.raises(RuntimeError, match="movie-older"):
        _validate(report)


def test_provider_probe_gate_rejects_incomplete_registry_and_matrix():
    report = _report()
    report["capabilities"].pop("torz")
    with pytest.raises(RuntimeError, match="registry differs"):
        _validate(report)

    report = _report()
    report["probe"].pop()
    with pytest.raises(RuntimeError, match="matrix is incomplete"):
        _validate(report)

    report = _report()
    report["probe"].append(dict(report["probe"][0]))
    with pytest.raises(RuntimeError, match="matrix is incomplete"):
        _validate(report)


def test_provider_probe_dispatches_once_then_waits_for_final_report(monkeypatch):
    calls = []
    expected = {"schema": 1, "probe": []}

    class Rpc:
        def __init__(self, *_args):
            pass

        def __enter__(self):
            return self

        def __exit__(self, *_args):
            return None

        def call(self, method, payload):
            calls.append((method, payload))

    monkeypatch.setattr(kodi_mwoscrapers_probe, "AdbJsonRpcClient", Rpc)
    monkeypatch.setattr(
        kodi_mwoscrapers_probe,
        "AdbEventClient",
        lambda *_args: pytest.fail("EventServer must not relaunch a dispatched probe"),
    )
    monkeypatch.setattr(
        kodi_mwoscrapers_probe,
        "_wait_report",
        lambda *_args: expected,
    )

    result = kodi_mwoscrapers_probe._dispatch_and_wait(
        "adb", 5038, "serial", "RunScript(probe.py)", 123.0
    )

    assert result is expected
    assert calls == [
        (
            "XBMC.ExecuteBuiltin",
            {"command": "RunScript(probe.py)", "wait": False},
        )
    ]
