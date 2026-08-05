from types import SimpleNamespace

from tools import kodi_addon_candidate_rollout as rollout


def test_restart_unsuspends_and_enables_kodi_before_launch(monkeypatch):
    commands = []
    options = []
    readiness = []
    monkeypatch.setattr(
        rollout,
        "adb_command",
        lambda *args, **kwargs: (
            commands.append(args[4]), options.append(kwargs)
        ),
    )
    monkeypatch.setattr(
        rollout,
        "_wait_for_kodi_ready",
        lambda *args: readiness.append(args),
    )

    rollout._restart_kodi("adb", 5038, "device")

    assert commands == [
        "input keyevent KEYCODE_WAKEUP",
        "cmd package unsuspend org.xbmc.kodi",
        "pm enable org.xbmc.kodi",
        "monkey -p org.xbmc.kodi "
        "-c android.intent.category.LAUNCHER 1 >/dev/null",
    ]
    assert options[0] == {"check": False}
    assert options[1] == {"check": False}
    assert readiness == [("adb", 5038, "device")]


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


def test_execute_falls_back_to_host_eventserver_for_lan_target(monkeypatch):
    commands = []
    markers = iter([None, {"ok": True}])

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
            commands.append(("device", command))

        def execute_builtin_from_host(self, command):
            commands.append(("host", command))

    monkeypatch.setattr(rollout, "AdbJsonRpcClient", JsonRpc)
    monkeypatch.setattr(rollout, "AdbEventClient", Events)
    monkeypatch.setattr(rollout, "_wait_marker", lambda *args: next(markers))

    result = rollout._execute(
        "adb", 5038, "192.168.1.18:5555", "RunScript(x)", 10**9
    )

    assert result == {"ok": True}
    assert commands == [
        ("device", "RunScript(x)"),
        ("host", "RunScript(x)"),
    ]
