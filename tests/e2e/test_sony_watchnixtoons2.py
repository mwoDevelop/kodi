import sony_watchnixtoons2


def test_playback_method_prefers_user_override(monkeypatch):
    payloads = iter(
        [
            '<setting id="playbackMethod">2</setting>',
        ]
    )
    monkeypatch.setattr(
        sony_watchnixtoons2,
        "shell",
        lambda *_args, **_kwargs: next(payloads),
    )

    assert sony_watchnixtoons2.playback_method("adb", "serial") == "2"


def test_playback_method_uses_addon_default_without_user_override(monkeypatch):
    payloads = iter(
        [
            "",
            (
                '<setting id="playbackMethod" type="enum" default="1" '
                'values="Select|Highest|Lowest" />'
            ),
        ]
    )
    monkeypatch.setattr(
        sony_watchnixtoons2,
        "shell",
        lambda *_args, **_kwargs: next(payloads),
    )

    assert sony_watchnixtoons2.playback_method("adb", "serial") == "1"


def test_quality_dialog_uses_adb_fallback_when_jsonrpc_does_not_close(
    monkeypatch,
):
    class Rpc:
        def __init__(self):
            self.calls = []

        def call(self, method, params=None):
            self.calls.append((method, params))
            if method == "Player.GetActivePlayers":
                return []
            if method == "GUI.GetProperties":
                properties = params["properties"]
                if "currentcontrol" in properties:
                    return {
                        "currentwindow": {
                            "id": 12000,
                            "label": "Select dialog",
                        },
                        "currentcontrol": {"label": "480 (SD)"},
                    }
                return {
                    "currentwindow": {
                        "id": 12000,
                        "label": "Select dialog",
                    }
                }
            return "OK"

    fallback = []
    monkeypatch.setattr(
        sony_watchnixtoons2.time,
        "sleep",
        lambda _seconds: None,
    )

    selected = sony_watchnixtoons2.accept_quality_dialog(
        Rpc(),
        timeout=1,
        select_fallback=lambda: fallback.append("enter"),
    )

    assert selected == "480 (SD)"
    assert fallback == ["enter"]
