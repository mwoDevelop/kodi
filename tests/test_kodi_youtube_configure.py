import json
from pathlib import Path
from types import SimpleNamespace

import pytest

from tools import kodi_youtube_configure as youtube
from tools.kodi_default_addons import load_manifest

PROFILE = {
    "adapter": "youtube-oauth-v1",
    "api_key_ref": "YOUTUBE_API_KEY",
    "client_id_ref": "YOUTUBE_CLIENT_ID",
    "client_secret_ref": "YOUTUBE_CLIENT_SECRET",
    "account_hint_ref": "YOUTUBE_USER",
}
REFERENCES = {
    "YOUTUBE_API_KEY": "AIza" + "a" * 35,
    "YOUTUBE_CLIENT_ID": "123456789-example.apps.googleusercontent.com",
    "YOUTUBE_CLIENT_SECRET": "GOCSPX-private",
    "YOUTUBE_USER": "youtube@example.invalid",
    "YOUTUBE_PASS": "must-never-be-read",
}


def _write_session(root, account="youtube@example.invalid", mode=0o600):
    path = root / ".kodi-private/youtube/session.json"
    path.parent.mkdir(parents=True)
    document = {
        "schema": 1,
        "addon_id": "plugin.video.youtube",
        "addon_version": "7.4.4",
        "account_hint": account,
        "expected_channel_id": "UC" + "c" * 22,
        "api_key": REFERENCES["YOUTUBE_API_KEY"],
        "client_id": REFERENCES["YOUTUBE_CLIENT_ID"],
        "client_secret": REFERENCES["YOUTUBE_CLIENT_SECRET"],
        "tv_refresh_token": "tv_" + "t" * 30,
        "personal_refresh_token": "personal_" + "p" * 30,
        "vr_refresh_token": "vr_" + "v" * 30,
    }
    path.write_text(json.dumps(document) + "\n", encoding="utf-8")
    path.chmod(mode)
    return path, document


def test_resolve_credentials_uses_only_allowlisted_references():
    assert youtube.resolve_credentials(PROFILE, REFERENCES) == (
        REFERENCES["YOUTUBE_API_KEY"],
        REFERENCES["YOUTUBE_CLIENT_ID"],
        REFERENCES["YOUTUBE_CLIENT_SECRET"],
        REFERENCES["YOUTUBE_USER"],
    )
    assert "YOUTUBE_PASS" not in youtube.ENVIRONMENT_NAMES


def test_adapter_version_is_bound_to_qualified_official_manifest():
    manifest = load_manifest("manifests/kodi-default-addons.json")
    entry = next(
        addon for addon in manifest["addons"] if addon["id"] == "plugin.video.youtube"
    )
    assert youtube.EXPECTED_ADDON_VERSION == entry["version"]


def test_private_adapter_timeout_covers_sequential_network_budget():
    assert youtube.PRIVATE_ADAPTER_TIMEOUT_SECONDS >= 5 * 30 + 30
    args = youtube._parser().parse_args(["--serial", "192.0.2.1:5555"])
    assert args.timeout == youtube.PRIVATE_ADAPTER_TIMEOUT_SECONDS


def test_profile_rejects_password_and_arbitrary_references():
    with pytest.raises(ValueError, match="invalid private YouTube profile"):
        youtube.validate_profile({**PROFILE, "password_ref": "YOUTUBE_PASS"})
    with pytest.raises(ValueError, match="unsupported YouTube reference"):
        youtube.validate_profile({**PROFILE, "api_key_ref": "OTHER"})


def test_configure_cleans_remote_secrets_and_returns_redacted_report(
    monkeypatch, tmp_path
):
    calls = []
    pushed_payload = {}

    def command(*args, **kwargs):
        calls.append(args[3:])
        if args[3] == "push" and args[5] == youtube.REMOTE_CONFIG:
            pushed_payload.update(json.loads(Path(args[4]).read_text()))
        return SimpleNamespace(returncode=0, stdout="")

    monkeypatch.setattr(youtube, "adb_command", command)
    monkeypatch.setattr(youtube, "_wait_for_kodi_ready", lambda *_args: None)
    monkeypatch.setattr(
        youtube,
        "_dispatch",
        lambda *_args: {
            "ok": True,
            "schema": 1,
            "stage": "complete",
            "addon_id": "plugin.video.youtube",
            "addon_version": "7.4.4",
            "api_status": 200,
            "authorization": "AUTHORIZATION_REQUIRED",
            "changed": True,
            "http_loopback_only": True,
            "personal_api_configured": True,
            "setup_wizard_disabled": True,
        },
    )
    script = tmp_path / "device.py"
    script.write_text("pass\n", encoding="utf-8")

    result = youtube.configure(
        "adb", 5038, "serial", PROFILE, REFERENCES, script, root=tmp_path
    )

    assert set(pushed_payload) == {
        "schema",
        "addon_version",
        "api_key",
        "client_id",
        "client_secret",
    }
    serialized = json.dumps(result)
    for secret in REFERENCES.values():
        assert secret not in serialized
    assert result["account_hint_configured"] is True
    assert any(
        item[0] == "shell" and youtube.REMOTE_CONFIG in item[1] for item in calls
    )


def test_invalid_api_key_is_rejected_before_transport():
    with pytest.raises(ValueError, match="invalid YouTube API key"):
        youtube.resolve_credentials(
            PROFILE, {**REFERENCES, "YOUTUBE_API_KEY": "not-a-key"}
        )


def test_absent_api_profile_returns_explicit_non_mutating_status(tmp_path):
    result = youtube.configure(
        "adb",
        5038,
        "serial",
        PROFILE,
        {"YOUTUBE_USER": "youtube@example.invalid"},
        tmp_path / "unused.py",
        root=tmp_path,
    )

    assert result == {
        "account_hint_configured": True,
        "adapter": "youtube-oauth-v1",
        "authorization": "API_CONFIG_REQUIRED",
        "changed": False,
        "ok": True,
        "personal_api_configured": False,
        "schema": 1,
        "serial": "serial",
        "status": "API_CONFIG_REQUIRED",
    }


def test_partial_api_profile_is_rejected_before_transport(tmp_path):
    with pytest.raises(ValueError, match="YOUTUBE_CLIENT_ID"):
        youtube.configure(
            "adb",
            5038,
            "serial",
            PROFILE,
            {
                "YOUTUBE_API_KEY": REFERENCES["YOUTUBE_API_KEY"],
                "YOUTUBE_USER": REFERENCES["YOUTUBE_USER"],
            },
            tmp_path / "unused.py",
            root=tmp_path,
        )


def test_private_session_supplies_api_and_oauth_without_api_env(tmp_path):
    _path, session = _write_session(tmp_path)

    configured = youtube.configuration(
        tmp_path,
        PROFILE,
        {"YOUTUBE_USER": session["account_hint"]},
    )

    assert configured == (
        session["api_key"],
        session["client_id"],
        session["client_secret"],
        session["account_hint"],
        session,
    )


def test_private_session_rejects_account_mismatch_and_unsafe_mode(tmp_path):
    path, _session = _write_session(tmp_path)
    with pytest.raises(ValueError, match="account differs"):
        youtube.load_session(
            tmp_path, {"YOUTUBE_USER": "different@example.invalid"}
        )

    path.chmod(0o640)
    with pytest.raises(ValueError, match="unsafe"):
        youtube.load_session(
            tmp_path, {"YOUTUBE_USER": "youtube@example.invalid"}
        )


def test_private_session_path_cannot_escape_private_root(tmp_path):
    with pytest.raises(ValueError, match="below .kodi-private"):
        youtube.load_session(
            tmp_path,
            {
                "YOUTUBE_USER": "youtube@example.invalid",
                "YOUTUBE_SESSION_FILE": "outside.json",
            },
        )


def test_dispatch_uses_device_local_event_transport_for_lan_android(monkeypatch):
    calls = []

    class Rpc:
        def __init__(self, *_args):
            pass

        def __enter__(self):
            return self

        def __exit__(self, *_args):
            pass

        def call(self, *_args, **_kwargs):
            raise RuntimeError("method unavailable")

    class Events:
        def __init__(self, *_args):
            pass

        def execute_builtin_from_host(self, command):
            calls.append(("host", command))

        def execute_builtin(self, command):
            calls.append(("device", command))

    monkeypatch.setattr(youtube, "AdbJsonRpcClient", Rpc)
    monkeypatch.setattr(youtube, "AdbEventClient", Events)
    monkeypatch.setattr(youtube, "_wait_report", lambda *_args: {"ok": True})

    result = youtube._dispatch(
        "adb", 5038, "192.0.2.8:5555", "RunScript(test)", 0
    )

    assert result == {"ok": True}
    assert calls == [("device", "RunScript(test)")]


def test_dispatch_falls_back_to_json_rpc_when_event_transport_fails(monkeypatch):
    calls = []

    class Events:
        def __init__(self, *_args):
            pass

        def execute_builtin(self, _command):
            raise OSError("event transport unavailable")

    class Rpc:
        def __init__(self, *_args):
            pass

        def __enter__(self):
            return self

        def __exit__(self, *_args):
            pass

        def call(self, method, params):
            calls.append((method, params))

    monkeypatch.setattr(youtube, "AdbEventClient", Events)
    monkeypatch.setattr(youtube, "AdbJsonRpcClient", Rpc)
    monkeypatch.setattr(youtube, "_wait_report", lambda *_args: {"ok": True})

    assert youtube._dispatch(
        "adb", 5038, "192.0.2.8:5555", "RunScript(test)", 0
    ) == {"ok": True}
    assert calls == [
        (
            "XBMC.ExecuteBuiltin",
            {"command": "RunScript(test)", "wait": False},
        )
    ]
