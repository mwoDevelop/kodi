from types import SimpleNamespace

from tools import kodi_mwoscrapers_endpoint_probe as endpoint_probe


def test_probe_retries_dropped_eventserver_command(monkeypatch):
    event_commands = []
    reports = iter(
        [
            None,
            {
                "ok": True,
                "module_version": "0.1.8",
            },
        ]
    )

    class JsonRpc:
        def __init__(self, *args):
            del args

        def __enter__(self):
            return self

        def __exit__(self, *args):
            del args

        def call(self, *args):
            del args
            raise RuntimeError("method unavailable")

    class Events:
        def __init__(self, *args):
            del args

        def execute_builtin(self, command):
            event_commands.append(command)

    monkeypatch.setattr(
        endpoint_probe,
        "adb_command",
        lambda *args, **kwargs: SimpleNamespace(
            returncode=0,
            stdout="",
        ),
    )
    monkeypatch.setattr(
        endpoint_probe,
        "_wait_for_kodi_ready",
        lambda *args: None,
    )
    monkeypatch.setattr(endpoint_probe, "AdbJsonRpcClient", JsonRpc)
    monkeypatch.setattr(endpoint_probe, "AdbEventClient", Events)
    monkeypatch.setattr(
        endpoint_probe,
        "_wait_report",
        lambda *args: next(reports),
    )

    result = endpoint_probe.probe("adb", 5038, "device", 60)

    assert result["report"]["ok"] is True
    assert len(event_commands) == 2
