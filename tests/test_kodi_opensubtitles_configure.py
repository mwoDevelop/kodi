import json
from pathlib import Path
from types import SimpleNamespace

import pytest

from tools import kodi_opensubtitles_configure as opensubtitles


PROFILE = {
    "adapter": "opensubtitles-org-v1",
    "username_ref": "OPENSUBTITLES_USER",
    "password_ref": "OPENSUBTITLES_PASS",
}


def test_resolve_credentials_uses_named_private_references():
    assert opensubtitles.resolve_credentials(
        PROFILE,
        {
            "OPENSUBTITLES_USER": "user",
            "OPENSUBTITLES_PASS": "pass",
        },
    ) == ("user", "pass")


def test_profile_rejects_unknown_adapter_and_reference():
    with pytest.raises(ValueError, match="unsupported OpenSubtitles adapter"):
        opensubtitles.validate_profile({**PROFILE, "adapter": "arbitrary"})
    with pytest.raises(ValueError, match="unsupported OpenSubtitles reference"):
        opensubtitles.validate_profile({**PROFILE, "username_ref": "OTHER"})


def test_configure_cleans_remote_credentials_and_returns_sanitized_report(
    monkeypatch, tmp_path
):
    calls = []
    pushed_payload = {}

    def command(*args, **kwargs):
        calls.append(args[3:])
        if args[3] == "push" and args[5] == opensubtitles.REMOTE_CONFIG:
            pushed_payload.update(json.loads(Path(args[4]).read_text()))
        return SimpleNamespace(returncode=0, stdout="")

    monkeypatch.setattr(opensubtitles, "adb_command", command)
    monkeypatch.setattr(opensubtitles, "_wait_for_kodi_ready", lambda *_args: None)
    monkeypatch.setattr(
        opensubtitles,
        "_dispatch",
        lambda *_args: {
            "ok": True,
            "schema": 1,
            "stage": "complete",
            "addon_id": "service.subtitles.opensubtitles",
            "addon_version": "5.1.5",
            "credentials_stored": True,
            "default_movie_service": True,
            "default_tv_service": True,
            "login_status": "200 OK",
            "search_status": "200 OK",
            "search_results": 7,
            "download_bytes": 1024,
        },
    )
    script = tmp_path / "device.py"
    script.write_text("pass\n", encoding="utf-8")

    result = opensubtitles.configure(
        "adb",
        5038,
        "serial",
        PROFILE,
        {
            "OPENSUBTITLES_USER": "secret-user",
            "OPENSUBTITLES_PASS": "secret-pass",
        },
        script,
    )

    assert pushed_payload == {
        "schema": 1,
        "username": "secret-user",
        "password": "secret-pass",
    }
    serialized = json.dumps(result)
    assert "secret-user" not in serialized
    assert "secret-pass" not in serialized
    assert any(
        item[0] == "shell" and opensubtitles.REMOTE_CONFIG in item[1] for item in calls
    )
