import json
import stat

from tools import youtube_session_authorize as authorize


def test_write_session_is_atomic_and_private(tmp_path):
    destination = tmp_path / "private/youtube/session.json"
    document = {"schema": 1, "refresh_token": "secret"}

    authorize.write_session(destination, document)

    assert json.loads(destination.read_text(encoding="utf-8")) == document
    assert stat.S_IMODE(destination.stat().st_mode) == 0o600
    assert stat.S_IMODE(destination.parent.stat().st_mode) == 0o700
    assert not destination.with_name(destination.name + ".tmp").exists()


def test_authorize_client_polls_without_returning_device_secret(monkeypatch, capsys):
    responses = iter(
        [
            (
                200,
                {
                    "device_code": "private-device-code",
                    "user_code": "PUBLIC-CODE",
                    "verification_url": "https://example.invalid/device",
                    "expires_in": 60,
                    "interval": 3,
                },
            ),
            (400, {"error": "authorization_pending"}),
            (200, {"access_token": "access", "refresh_token": "refresh"}),
        ]
    )
    monkeypatch.setattr(authorize, "_post", lambda *_args: next(responses))
    monkeypatch.setattr(authorize.time, "sleep", lambda *_args: None)

    result = authorize.authorize_client("TV", "client", "secret")

    output = capsys.readouterr().out
    assert result == {"access_token": "access", "refresh_token": "refresh"}
    assert "PUBLIC-CODE" in output
    assert "private-device-code" not in output
    assert "secret" not in output
