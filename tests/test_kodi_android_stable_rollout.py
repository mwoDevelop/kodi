from types import SimpleNamespace

from tools.kodi_android_stable_rollout import ensure_kodi_ready


def test_android_stable_preflight_restarts_a_stale_kodi_process(monkeypatch):
    commands = []
    waits = []

    def adb_command(_adb, _port, _serial, *argv, **_kwargs):
        commands.append(argv)
        if argv == ("shell", "pidof org.xbmc.kodi"):
            return SimpleNamespace(returncode=0, stdout="1234\n")
        return SimpleNamespace(returncode=0, stdout="")

    def wait(_adb, _port, _serial, timeout=90):
        waits.append(timeout)
        if len(waits) == 1:
            raise TimeoutError("stale")

    monkeypatch.setattr(
        "tools.kodi_android_stable_rollout.adb_command", adb_command
    )
    monkeypatch.setattr(
        "tools.kodi_android_stable_rollout._wait_for_kodi_ready", wait
    )
    monkeypatch.setattr(
        "tools.kodi_android_stable_rollout.time.sleep", lambda _seconds: None
    )

    assert ensure_kodi_ready("adb", 5038, "device") == "restarted"
    assert waits == [15, 90]
    assert ("shell", "am force-stop org.xbmc.kodi") in commands
    assert ("shell", "input keyevent KEYCODE_WAKEUP") in commands
    assert ("shell", "input keyevent KEYCODE_HOME") in commands
