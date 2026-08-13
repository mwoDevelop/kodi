import importlib.util
import json
import sys
from pathlib import Path
from types import SimpleNamespace

import pytest

from tools import kodi_opensubtitles_com_configure as opensubtitles_com

PROFILE = {
    "adapter": "opensubtitles-com-v1",
    "username_ref": "OPENSUBTITLES_USER",
    "password_ref": "OPENSUBTITLES_PASS",
    "token_ref": "OPENSUBTITLES_TOKEN",
}


def test_com_profile_reuses_the_explicit_shared_references():
    assert opensubtitles_com.resolve_credentials(
        PROFILE,
        {
            "OPENSUBTITLES_USER": "user",
            "OPENSUBTITLES_PASS": "pass",
            "OPENSUBTITLES_TOKEN": "token",
        },
    ) == ("user", "pass", "token")


def test_com_profile_rejects_reference_overloading():
    with pytest.raises(ValueError, match="unsupported OpenSubtitles.com reference"):
        opensubtitles_com.validate_profile(
            {**PROFILE, "token_ref": "OPENSUBTITLES_PASS"}
        )


def test_com_configure_cleans_secrets_and_returns_sanitized_report(
    monkeypatch, tmp_path
):
    calls = []
    pushed = {}

    def command(*args, **kwargs):
        calls.append(args[3:])
        if args[3] == "push" and args[5] == opensubtitles_com.REMOTE_CONFIG:
            pushed.update(json.loads(Path(args[4]).read_text()))
        return SimpleNamespace(returncode=0, stdout="")

    monkeypatch.setattr(opensubtitles_com, "adb_command", command)
    monkeypatch.setattr(
        opensubtitles_com, "_wait_for_kodi_ready", lambda *_args: None
    )
    monkeypatch.setattr(
        opensubtitles_com,
        "_dispatch",
        lambda *_args: {
            "ok": True,
            "schema": 1,
            "stage": "complete",
            "addon_id": "service.subtitles.opensubtitles-com",
            "addon_version": "1.0.13.1",
            "changed": True,
            "credentials_stored": True,
            "default_movie_service": True,
            "default_tv_service": True,
            "legacy_service_visible": True,
            "search_status": 200,
            "search_results": 25,
            "token_source": "bootstrap",
            "umbrella_addon_version": "6.7.81.20",
        },
    )
    script = tmp_path / "device.py"
    script.write_text("pass\n", encoding="utf-8")

    result = opensubtitles_com.configure(
        "adb",
        5038,
        "serial",
        PROFILE,
        {
            "OPENSUBTITLES_USER": "secret-user",
            "OPENSUBTITLES_PASS": "secret-pass",
            "OPENSUBTITLES_TOKEN": "Bearer secret-token",
        },
        script,
        probe_download=True,
    )

    assert pushed == {
        "schema": 1,
        "username": "secret-user",
        "password": "secret-pass",
        "token": "secret-token",
        "probe_download": True,
    }
    serialized = json.dumps(result)
    assert "secret-user" not in serialized
    assert "secret-pass" not in serialized
    assert "secret-token" not in serialized
    assert any(
        item[0] == "shell" and opensubtitles_com.REMOTE_CONFIG in item[1]
        for item in calls
    )


def test_device_probe_validates_real_subtitle_bytes(monkeypatch):
    for name in ("xbmc", "xbmcaddon", "xbmcvfs"):
        monkeypatch.setitem(sys.modules, name, SimpleNamespace())
    script = (
        Path(__file__).parent
        / "e2e"
        / "kodi_opensubtitles_com_configure.py"
    )
    spec = importlib.util.spec_from_file_location(
        "opensubtitles_com_device_probe", script
    )
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)

    assert module._subtitle_payload_is_valid(
        b"1\n00:00:01,000 --> 00:00:03,000\nPrawdziwe napisy.\n"
        + b"x" * 32
    )
    assert not module._subtitle_payload_is_valid(
        b"<html><body>rate limited</body></html>" + b"x" * 64
    )
