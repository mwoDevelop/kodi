from types import SimpleNamespace

from tools import kodi_mwoscrapers_configure as configure


def test_configure_retries_dropped_eventserver_command(monkeypatch):
    event_commands = []
    reports = iter(
        [
            None,
            None,
            {
                "ok": True,
                "module_version": "0.1.8",
                "torrentio_endpoint_class": "public",
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
        configure,
        "adb_command",
        lambda *args, **kwargs: SimpleNamespace(
            returncode=0,
            stdout="",
        ),
    )
    monkeypatch.setattr(configure, "_wait_for_kodi_ready", lambda *args: None)
    monkeypatch.setattr(configure, "AdbJsonRpcClient", JsonRpc)
    monkeypatch.setattr(configure, "AdbEventClient", Events)
    monkeypatch.setattr(configure, "_wait_report", lambda *args: next(reports))

    result = configure.configure(
        "adb",
        5038,
        "device",
        configure.PUBLIC_TORRENTIO,
        configure.PUBLIC_COMET,
        60,
    )

    assert result["ok"] is True
    assert len(event_commands) == 3
