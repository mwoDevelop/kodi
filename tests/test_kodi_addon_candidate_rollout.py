from types import SimpleNamespace

import pytest

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


def test_android_runtime_facts_bind_kodi_version_abi_and_enabled_addons(
    monkeypatch,
):
    class Rpc:
        def __init__(self, *_args):
            pass

        def __enter__(self):
            return self

        def __exit__(self, *_args):
            pass

        def call(self, method, _params):
            if method == "Application.GetProperties":
                return {
                    "version": {
                        "major": 21,
                        "minor": 2,
                        "revision": "20251031-a3a448d26b",
                        "tag": "stable",
                        "tagversion": "",
                    }
                }
            return {
                "addons": [
                    {
                        "addonid": "plugin.video.test",
                        "version": "1.2.3",
                        "enabled": True,
                    },
                    {
                        "addonid": "plugin.video.disabled",
                        "version": "2.0.0",
                        "enabled": False,
                    },
                ]
            }

    outputs = iter(
        [
            "primaryCpuAbi=arm64-v8a\n",
            "arm64-v8a,armeabi-v7a\n",
        ]
    )
    monkeypatch.setattr(rollout, "AdbJsonRpcClient", Rpc)
    monkeypatch.setattr(
        rollout,
        "adb_command",
        lambda *_args, **_kwargs: SimpleNamespace(stdout=next(outputs)),
    )

    assert rollout.android_runtime_facts(
        "adb", 5038, "device", platform="android"
    ) == {
        "platform": "android",
        "kodi_version": "21.2+20251031.a3a448d26b",
        "abis": ["arm64-v8a", "armeabi-v7a"],
        "installed_addons": {
            "plugin.video.test": {"version": "1.2.3", "enabled": True},
            "plugin.video.disabled": {
                "version": "2.0.0",
                "enabled": False,
            },
        },
    }


def test_candidate_compatibility_failure_happens_before_any_device_write(
    monkeypatch, tmp_path
):
    candidate = tmp_path / "candidate.zip"
    candidate.write_bytes(b"candidate")
    writes = []
    monkeypatch.setattr(
        rollout,
        "inspect_archive",
        lambda *_args, **_kwargs: {"id": "plugin.video.test"},
    )
    monkeypatch.setattr(
        rollout, "android_runtime_facts", lambda *_args, **_kwargs: {}
    )
    monkeypatch.setattr(rollout, "load_policy", lambda _path: {})
    monkeypatch.setattr(
        rollout,
        "assert_compatible",
        lambda *_args, **_kwargs: (_ for _ in ()).throw(
            RuntimeError("INCOMPATIBLE")
        ),
    )
    monkeypatch.setattr(
        rollout, "adb_command", lambda *_args, **_kwargs: writes.append(_args)
    )

    with pytest.raises(RuntimeError, match="INCOMPATIBLE"):
        rollout.rollout(
            "adb",
            5038,
            "device",
            candidate,
            "plugin.video.test",
            "1.0.0",
            30,
        )

    assert writes == []
