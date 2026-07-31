import pytest

from tests.e2e import profile_sync_addon_device as addon_device
from tests.e2e import profile_sync_production_device as production_device


class _Rpc:
    def __init__(self, error=None):
        self.error = error
        self.calls = []

    def __enter__(self):
        return self

    def __exit__(self, *_args):
        return False

    def call(self, method, arguments):
        self.calls.append((method, arguments))
        if self.error is not None:
            raise self.error


def test_production_probe_prefers_jsonrpc(monkeypatch):
    rpc = _Rpc()
    monkeypatch.setattr(
        production_device, "AdbJsonRpcClient", lambda *_args: rpc
    )

    class UnexpectedEventClient:
        def __init__(self, *_args):
            raise AssertionError("EventServer fallback was not expected")

    monkeypatch.setattr(
        production_device, "AdbEventClient", UnexpectedEventClient
    )
    assert (
        production_device.execute_builtin("adb", 5038, "device", "RunScript(x)")
        == "jsonrpc"
    )
    assert rpc.calls == [
        (
            "XBMC.ExecuteBuiltin",
            {"command": "RunScript(x)", "wait": False},
        )
    ]


def test_production_probe_falls_back_to_eventserver(monkeypatch):
    rpc = _Rpc(RuntimeError("JSON-RPC unavailable"))
    event_calls = []
    monkeypatch.setattr(
        production_device, "AdbJsonRpcClient", lambda *_args: rpc
    )

    class EventClient:
        def __init__(self, *args):
            event_calls.append(("init", args))

        def execute_builtin(self, command):
            event_calls.append(("execute", command))

    monkeypatch.setattr(production_device, "AdbEventClient", EventClient)
    assert (
        production_device.execute_builtin("adb", 5038, "device", "RunScript(x)")
        == "eventserver"
    )
    assert event_calls[-1] == ("execute", "RunScript(x)")


def test_addon_probe_refuses_failed_state_restoration(monkeypatch):
    monkeypatch.setattr(
        addon_device,
        "_wait_json",
        lambda *_args, **_kwargs: {
            "ok": False,
            "error_type": "PermissionError",
        },
    )
    with pytest.raises(RuntimeError, match="state restoration failed"):
        addon_device._wait_probe_cleanup("adb", 5038, "device")
