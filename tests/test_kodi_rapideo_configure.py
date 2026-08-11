import json
from pathlib import Path
from types import SimpleNamespace

import pytest

from tools import kodi_rapideo_configure as rapideo


PROFILE = {
    "adapter": "rapideo-v1",
    "username_ref": "RAPIDEO_USER",
    "password_ref": "RAPIDEO_PASS",
}


def test_resolve_credentials_uses_named_private_references():
    assert rapideo.resolve_credentials(
        PROFILE,
        {"RAPIDEO_USER": "user", "RAPIDEO_PASS": "pass"},
    ) == ("user", "pass")


def test_profile_rejects_unknown_adapter_and_reference():
    with pytest.raises(ValueError, match="unsupported private add-on adapter"):
        rapideo.validate_profile({**PROFILE, "adapter": "arbitrary"})
    with pytest.raises(ValueError, match="unsupported Rapideo reference"):
        rapideo.validate_profile({**PROFILE, "username_ref": "OTHER"})


def test_configure_cleans_remote_credentials_and_returns_sanitized_report(
    monkeypatch, tmp_path
):
    calls = []
    pushed_payload = {}

    def command(*args, **kwargs):
        calls.append(args[3:])
        if args[3] == "push" and args[5] == rapideo.REMOTE_CONFIG:
            pushed_payload.update(json.loads(Path(args[4]).read_text()))
        return SimpleNamespace(returncode=0, stdout="")

    monkeypatch.setattr(rapideo, "adb_command", command)
    monkeypatch.setattr(rapideo, "_wait_for_kodi_ready", lambda *_args: None)
    monkeypatch.setattr(
        rapideo,
        "AdbJsonRpcClient",
        lambda *_args: type(
            "Rpc",
            (),
            {
                "__enter__": lambda self: self,
                "__exit__": lambda self, *_args: None,
                "call": lambda self, *_args, **_kwargs: None,
            },
        )(),
    )
    monkeypatch.setattr(
        rapideo,
        "_wait_report",
        lambda *_args: {
            "ok": True,
            "schema": 1,
            "stage": "complete",
            "token_present": True,
            "account_verified": True,
            "credentials_stored": True,
        },
    )
    script = tmp_path / "device.py"
    script.write_text("pass\n")

    result = rapideo.configure(
        "adb",
        5038,
        "serial",
        PROFILE,
        {"RAPIDEO_USER": "secret-user", "RAPIDEO_PASS": "secret-pass"},
        script,
    )

    assert pushed_payload == {
        "schema": 1,
        "username": "secret-user",
        "password": "secret-pass",
        "authtoken": None,
    }
    serialized = json.dumps(result)
    assert "secret-user" not in serialized
    assert "secret-pass" not in serialized
    assert any(
        item[0] == "shell" and rapideo.REMOTE_CONFIG in item[1]
        for item in calls
    )
