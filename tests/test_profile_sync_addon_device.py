from tests.e2e import profile_sync_addon_device


class FakeJsonRpc:
    def __init__(self, labels, window_id=10000):
        self.labels = list(labels)
        self.position = 0
        self.calls = []
        self.window_id = window_id

    def call(self, method, params=None):
        self.calls.append((method, params))
        if method == "GUI.GetProperties":
            return {
                "currentwindow": {"id": self.window_id},
                "currentcontrol": {"label": self.labels[self.position]},
            }
        if method == "Input.Down":
            self.position = (self.position + 1) % len(self.labels)
            return "OK"
        if method == "Input.Left":
            return "OK"
        if method == "Input.Select":
            return "OK"
        raise AssertionError("unexpected JSON-RPC method: %s" % method)


def test_select_control_walks_file_browser_by_label(monkeypatch):
    monkeypatch.setattr(profile_sync_addon_device.time, "sleep", lambda _: None)
    jsonrpc = FakeJsonRpc(["..", "External storage", "mwoDevelop"])

    profile_sync_addon_device._select_control(
        jsonrpc,
        {"External storage", "Pamięć zewnętrzna"},
    )

    assert jsonrpc.position == 1
    assert jsonrpc.calls[-1] == ("Input.Select", None)


def test_select_control_accepts_bracketed_kodi_source_label(monkeypatch):
    monkeypatch.setattr(profile_sync_addon_device.time, "sleep", lambda _: None)
    jsonrpc = FakeJsonRpc(["[..]", "[External storage]"])

    profile_sync_addon_device._select_control(
        jsonrpc,
        {"External storage", "Pamięć zewnętrzna"},
    )

    assert jsonrpc.position == 1
    assert jsonrpc.calls[-1] == ("Input.Select", None)


def test_select_control_rejects_missing_entry(monkeypatch):
    monkeypatch.setattr(profile_sync_addon_device.time, "sleep", lambda _: None)
    jsonrpc = FakeJsonRpc(["..", "External storage"])

    try:
        profile_sync_addon_device._select_control(
            jsonrpc,
            {"repository.mwodevelop.testing-1.0.0.zip"},
            maximum_steps=3,
        )
    except RuntimeError as error:
        assert "visible controls" in str(error)
    else:
        raise AssertionError("missing file browser entry must fail")


def test_accept_addon_install_prompt_moves_from_no_to_yes(monkeypatch):
    monkeypatch.setattr(profile_sync_addon_device.time, "sleep", lambda _: None)
    jsonrpc = FakeJsonRpc(["No"], window_id=10100)

    class Client:
        def __enter__(self):
            return jsonrpc

        def __exit__(self, *_):
            return None

    monkeypatch.setattr(
        profile_sync_addon_device,
        "AdbJsonRpcClient",
        lambda *_: Client(),
    )

    assert profile_sync_addon_device._accept_addon_install_prompt(
        "adb", 5038, "device"
    )
    assert ("Input.Left", None) in jsonrpc.calls
    assert jsonrpc.calls[-1] == ("Input.Select", None)


def test_latest_addons_database_is_selected_without_android_sort_v():
    listing = "\n".join(
        [
            "/storage/kodi/userdata/Database/Addons9.db",
            "/storage/kodi/userdata/Database/Addons35.db",
            "/storage/kodi/userdata/Database/Addons12.db",
        ]
    )

    assert profile_sync_addon_device._latest_addons_database(listing).endswith(
        "Addons35.db"
    )


def test_execute_builtin_prefers_kodi_jsonrpc(monkeypatch):
    calls = []

    class Client:
        def __enter__(self):
            return self

        def __exit__(self, *_):
            return None

        def call(self, method, params=None):
            calls.append((method, params))
            return "OK"

    monkeypatch.setattr(
        profile_sync_addon_device,
        "AdbJsonRpcClient",
        lambda *_: Client(),
    )
    monkeypatch.setattr(
        profile_sync_addon_device.AdbEventClient,
        "execute_builtin",
        lambda *_: (_ for _ in ()).throw(
            AssertionError("EventServer fallback must not run")
        ),
    )

    profile_sync_addon_device._execute_builtin(
        "adb", 5037, "device", "UpdateAddonRepos"
    )

    assert calls == [
        (
            "XBMC.ExecuteBuiltin",
            {"command": "UpdateAddonRepos", "wait": False},
        )
    ]
