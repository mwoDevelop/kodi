from types import SimpleNamespace

from tools import kodi_addon_candidate_rollout as rollout


def test_execute_retries_dropped_eventserver_command(monkeypatch):
    commands = []
    markers = iter([None, None, {"ok": True}])

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
            commands.append(command)

    monkeypatch.setattr(rollout, "AdbJsonRpcClient", JsonRpc)
    monkeypatch.setattr(rollout, "AdbEventClient", Events)
    monkeypatch.setattr(rollout, "_wait_marker", lambda *args: next(markers))

    result = rollout._execute("adb", 5038, "device", "RunScript(x)", 10**9)

    assert result == {"ok": True}
    assert len(commands) == 3
