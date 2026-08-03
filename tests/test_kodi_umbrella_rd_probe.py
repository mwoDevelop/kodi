from types import SimpleNamespace

from tools import kodi_umbrella_rd_probe as rd_probe


def _install_probe_mocks(monkeypatch, reports):
    class JsonRpc:
        def __init__(self, *args):
            del args

        def __enter__(self):
            return self

        def __exit__(self, *args):
            del args

        def call(self, *args):
            del args
            return None

    monkeypatch.setattr(
        rd_probe,
        "adb_command",
        lambda *args, **kwargs: SimpleNamespace(returncode=0, stdout=""),
    )
    monkeypatch.setattr(rd_probe, "_wait_for_kodi_ready", lambda *args: None)
    monkeypatch.setattr(rd_probe, "AdbJsonRpcClient", JsonRpc)
    monkeypatch.setattr(rd_probe, "_wait_report", lambda *args: next(reports))


def test_probe_preserves_sanitized_negative_health_report(monkeypatch):
    report = {
        "ok": False,
        "schema": 1,
        "stage": "account",
        "account": {
            "ok": False,
            "token_present": True,
            "error": {"http_status": 401, "error_code": 8},
        },
    }
    _install_probe_mocks(monkeypatch, iter([report]))

    result = rd_probe.probe("adb", 5038, "device", 60)

    assert result == {
        "healthy": False,
        "report": report,
        "serial": "device",
    }


def test_probe_marks_complete_health_report_healthy(monkeypatch):
    report = {
        "ok": True,
        "schema": 1,
        "stage": "complete",
        "account": {"ok": True},
        "instant_availability": {"ok": True},
    }
    _install_probe_mocks(monkeypatch, iter([report]))

    result = rd_probe.probe("adb", 5038, "device", 60)

    assert result["healthy"] is True
    assert result["report"] is report
