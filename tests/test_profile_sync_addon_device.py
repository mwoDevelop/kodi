import sqlite3
from pathlib import Path
from types import SimpleNamespace

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


def test_repository_version_picker_uses_supported_private_repo_switch(
    monkeypatch,
):
    jsonrpc = FakeJsonRpc(
        [
            profile_sync_addon_device.ADDON_LABEL,
            "Versions",
            "Version 1.0.3",
        ],
        window_id=10040,
    )

    class Client:
        def __enter__(self):
            return jsonrpc

        def __exit__(self, *_):
            return None

    builtins = []
    monkeypatch.setattr(profile_sync_addon_device.time, "sleep", lambda _: None)
    monkeypatch.setattr(
        profile_sync_addon_device, "AdbJsonRpcClient", lambda *_: Client()
    )
    monkeypatch.setattr(
        profile_sync_addon_device,
        "_ensure_kodi_foreground",
        lambda *_: None,
    )
    monkeypatch.setattr(
        profile_sync_addon_device,
        "_execute_event_builtin",
        lambda *_args: builtins.append(_args[-1]),
    )

    profile_sync_addon_device._select_repository_version(
        "adb",
        5038,
        "device",
        "1.0.3",
        "repository.mwodevelop",
    )

    assert builtins == [
        "ActivateWindow(AddonBrowser,addons://user/xbmc.service,return)"
    ]
    assert [call for call in jsonrpc.calls if call[0] == "Input.Select"] == [
        ("Input.Select", None),
        ("Input.Select", None),
        ("Input.Select", None),
    ]


def test_repository_update_button_is_used_for_matching_origin(monkeypatch):
    jsonrpc = FakeJsonRpc(
        [profile_sync_addon_device.ADDON_LABEL, "Update"],
        window_id=10040,
    )

    class Client:
        def __enter__(self):
            return jsonrpc

        def __exit__(self, *_):
            return None

    monkeypatch.setattr(profile_sync_addon_device.time, "sleep", lambda _: None)
    monkeypatch.setattr(
        profile_sync_addon_device, "AdbJsonRpcClient", lambda *_: Client()
    )
    monkeypatch.setattr(
        profile_sync_addon_device,
        "_ensure_kodi_foreground",
        lambda *_: None,
    )
    monkeypatch.setattr(
        profile_sync_addon_device,
        "_execute_event_builtin",
        lambda *_args: None,
    )
    monkeypatch.setattr(
        profile_sync_addon_device,
        "ORIGIN",
        "repository.mwodevelop",
    )

    profile_sync_addon_device._select_repository_version(
        "adb",
        5038,
        "device",
        "1.0.3",
        "repository.mwodevelop",
    )

    assert [call for call in jsonrpc.calls if call[0] == "Input.Select"] == [
        ("Input.Select", None),
        ("Input.Select", None),
    ]


def test_matching_version_origin_switch_is_validated_in_kodi(monkeypatch):
    calls = []
    monkeypatch.setattr(
        profile_sync_addon_device,
        "assign_addon_origins_in_kodi",
        lambda *args: calls.append(args),
    )
    monkeypatch.setattr(
        profile_sync_addon_device,
        "ORIGIN",
        "repository.mwodevelop",
    )

    profile_sync_addon_device._switch_matching_version_origin(
        "adb", 5038, "device", "repository.mwodevelop.testing"
    )

    assert calls[0][2] == {
        "serial": "device",
        "addon_origins": {
            profile_sync_addon_device.ADDON_ID: "repository.mwodevelop"
        },
        "addon_previous_origins": {
            profile_sync_addon_device.ADDON_ID: (
                "repository.mwodevelop.testing"
            )
        },
        "addon_repository_checksums": {},
        "addon_version_transitions": {},
    }


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


def test_foreground_wakes_android_without_blocking_am_start(monkeypatch):
    commands = []

    def fake_command(_adb, _port, _serial, *args, **kwargs):
        commands.append((args, kwargs))

    monkeypatch.setattr(profile_sync_addon_device, "adb_command", fake_command)
    monkeypatch.setattr(
        profile_sync_addon_device,
        "adb_output",
        lambda *_args, **_kwargs: (
            "mCurrentFocus=Window{1 u0 org.xbmc.kodi/org.xbmc.kodi.Main}"
        ),
    )

    profile_sync_addon_device._ensure_kodi_foreground(
        "adb", 5038, "device"
    )

    assert commands[0][0] == (
        "shell",
        "input",
        "keyevent",
        "KEYCODE_WAKEUP",
    )
    assert commands[1][0] == (
        "shell",
        "am",
        "start",
        "-n",
        "org.xbmc.kodi/.Splash",
    )
    assert "-W" not in commands[1][0]


def test_repository_install_and_index_are_distinct_states(monkeypatch):
    monkeypatch.setattr(
        profile_sync_addon_device,
        "adb_output",
        lambda *_args, **_kwargs: "/remote/Addons33.db",
    )

    def fake_command(_adb, _port, _serial, *args, **_kwargs):
        if args[0] == "shell":
            return SimpleNamespace(returncode=0)
        if args[0] == "pull":
            database = Path(args[-1])
            with sqlite3.connect(database) as connection:
                connection.execute(
                    "CREATE TABLE installed (addonID TEXT)"
                )
                connection.execute("CREATE TABLE repo (addonID TEXT)")
                connection.execute(
                    "INSERT INTO installed VALUES (?)",
                    (profile_sync_addon_device.ORIGIN,),
                )
            return SimpleNamespace(returncode=0)
        raise AssertionError("unexpected ADB command: %s" % (args,))

    monkeypatch.setattr(
        profile_sync_addon_device, "adb_command", fake_command
    )

    assert profile_sync_addon_device._repository_installed(
        "adb", 5038, "device"
    )
    assert not profile_sync_addon_device._repository_indexed(
        "adb", 5038, "device"
    )


def test_repository_install_uses_jsonrpc_when_scoped_storage_is_opaque(
    monkeypatch,
):
    monkeypatch.setattr(
        profile_sync_addon_device,
        "adb_command",
        lambda *_args, **_kwargs: SimpleNamespace(returncode=1),
    )

    class Client:
        def __enter__(self):
            return self

        def __exit__(self, *_args):
            return None

        def call(self, method, params=None):
            assert method == "Addons.GetAddonDetails"
            assert params["addonid"] == profile_sync_addon_device.ORIGIN
            return {
                "addon": {
                    "enabled": True,
                    "version": profile_sync_addon_device.ORIGIN_VERSION,
                }
            }

    monkeypatch.setattr(
        profile_sync_addon_device,
        "AdbJsonRpcClient",
        lambda *_args: Client(),
    )

    assert profile_sync_addon_device._repository_installed(
        "adb", 5037, "device"
    )


def test_addon_version_uses_jsonrpc_when_manifest_is_opaque(monkeypatch):
    monkeypatch.setattr(
        profile_sync_addon_device,
        "adb_command",
        lambda *_args, **_kwargs: SimpleNamespace(
            returncode=0,
            stdout="cat: Permission denied",
        ),
    )

    class Client:
        def __enter__(self):
            return self

        def __exit__(self, *_args):
            return None

        def call(self, method, params=None):
            assert method == "Addons.GetAddonDetails"
            assert params["addonid"] == profile_sync_addon_device.ADDON_ID
            return {"addon": {"version": "0.1.6"}}

    monkeypatch.setattr(
        profile_sync_addon_device,
        "AdbJsonRpcClient",
        lambda *_args: Client(),
    )

    assert (
        profile_sync_addon_device._addon_version("adb", 5037, "device")
        == "0.1.6"
    )


def test_repository_channel_selects_stable_origin(monkeypatch):
    original = {
        "ORIGIN": profile_sync_addon_device.ORIGIN,
        "ORIGIN_ARCHIVE": profile_sync_addon_device.ORIGIN_ARCHIVE,
        "ORIGIN_URL": profile_sync_addon_device.ORIGIN_URL,
        "ORIGIN_SHA256": profile_sync_addon_device.ORIGIN_SHA256,
        "REMOTE_ORIGIN_ARCHIVE": (
            profile_sync_addon_device.REMOTE_ORIGIN_ARCHIVE
        ),
    }
    for name, value in original.items():
        monkeypatch.setattr(profile_sync_addon_device, name, value)

    profile_sync_addon_device._configure_repository_channel("stable")

    assert profile_sync_addon_device.ORIGIN == "repository.mwodevelop"
    assert (
        profile_sync_addon_device.ORIGIN_ARCHIVE
        == "repository.mwodevelop-1.0.0.zip"
    )
    assert profile_sync_addon_device.ORIGIN_URL.endswith(
        "/repository.mwodevelop-1.0.0.zip"
    )
    assert (
        profile_sync_addon_device.REMOTE_ORIGIN_ARCHIVE
        == "/sdcard/Download/repository.mwodevelop-1.0.0.zip"
    )
