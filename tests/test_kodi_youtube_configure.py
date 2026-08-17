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

    result = youtube.configure("adb", 5038, "serial", PROFILE, REFERENCES, script)

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
