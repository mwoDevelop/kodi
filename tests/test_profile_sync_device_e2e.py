import json
import stat

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


def test_production_probe_retries_until_marker(monkeypatch):
    launches = []
    clock = [0]
    markers = iter((None, None, {"ok": True}))
    monkeypatch.setattr(
        production_device,
        "execute_builtin",
        lambda *_args: launches.append("eventserver") or "eventserver",
    )
    monkeypatch.setattr(
        production_device.time, "monotonic", lambda: clock[0]
    )
    monkeypatch.setattr(
        production_device.time,
        "sleep",
        lambda value: clock.__setitem__(0, clock[0] + value),
    )

    result, transport = production_device.execute_until_marker(
        "adb",
        5038,
        "device",
        "RunScript(x)",
        lambda: next(markers),
        timeout=10,
        retry_seconds=2,
    )

    assert result == {"ok": True}
    assert transport == "eventserver"
    assert len(launches) == 2


def test_production_configs_are_isolated_per_invocation(tmp_path):
    first = production_device.write_local_config(
        tmp_path, {"logical_device_id": "sony-tv"}, "sony-tv"
    )
    second = production_device.write_local_config(
        tmp_path, {"logical_device_id": "x88pro20"}, "x88pro20"
    )
    try:
        assert first != second
        assert json.loads(first.read_text(encoding="utf-8")) == {
            "logical_device_id": "sony-tv"
        }
        assert json.loads(second.read_text(encoding="utf-8")) == {
            "logical_device_id": "x88pro20"
        }
        assert stat.S_IMODE(first.stat().st_mode) == 0o600
        assert stat.S_IMODE(second.stat().st_mode) == 0o600
    finally:
        first.unlink(missing_ok=True)
        second.unlink(missing_ok=True)


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
