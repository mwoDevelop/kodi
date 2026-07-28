import base64
import hashlib
import struct

import sony_kodi_matrix
from sony_kodi_matrix import (
    AdbEventClient,
    EventClient,
    diagnostic_lines,
    open_media,
    playback_log_state,
    plugin_url,
    redact,
    successful_source_fingerprint,
    terminal_failure_state,
)


def test_redaction_removes_resolver_urls_and_tokens():
    line = (
        "path [plugin://plugin.video.umbrella/?token=secret] "
        "magnet:?xt=urn:btih:abc&dn=name "
        "https://example.invalid/file?auth=secret"
    )
    redacted = redact(line)
    assert "secret" not in redacted
    assert "btih:abc" not in redacted
    assert "plugin.video.umbrella" not in redacted


def test_redaction_removes_pipe_delimited_refresh_credentials():
    line = (
        "Refreshing Expired Real Debrid Token: | client-id | "
        "refresh-credential |"
    )
    redacted = redact(line)
    assert redacted.endswith("Token: <redacted>")
    assert "client-id" not in redacted
    assert "refresh-credential" not in redacted


def test_redaction_removes_real_debrid_torrent_identifier():
    redacted = redact("Real-Debrid: Torrent ID MYYKMTBV447VE was removed")
    assert redacted == "Real-Debrid: Torrent ID <redacted> was removed"
    assert "MYYKMTBV447VE" not in redacted


def test_eventserver_header_matches_kodi_packet_contract():
    client = EventClient("127.0.0.1")
    header = client._header(
        client.PT_ACTION,
        sequence=1,
        packet_count=1,
        payload_size=12,
    )
    assert len(header) == client.HEADER_SIZE
    assert header[:6] == b"XBMC\x02\x00"
    assert struct.unpack("!H", header[6:8])[0] == client.PT_ACTION
    assert struct.unpack("!I", header[8:12])[0] == 1
    assert struct.unpack("!I", header[12:16])[0] == 1
    assert struct.unpack("!H", header[16:18])[0] == 12


def test_adb_event_client_sends_one_session_from_a_fixed_source_port(monkeypatch):
    calls = []

    def fake_run(adb, serial, *args, **_kwargs):
        calls.append((adb, serial, args))
        return ""

    monkeypatch.setattr(sony_kodi_matrix, "run", fake_run)
    client = AdbEventClient("adb", "serial", source_port=40140)
    client.uid = 123
    client.execute_builtin("ActivateWindow(Home)")

    assert len(calls) == 3
    assert all(call[:2] == ("adb", "serial") for call in calls)
    commands = [call[2][1] for call in calls]
    assert all("-p 40140" in command for command in commands)
    action_packet = base64.b64decode(commands[1].split()[1])
    assert action_packet[:4] == b"XBMC"
    assert b"ActivateWindow(Home)\0" in action_packet


def test_diagnostics_separate_errors_from_normal_playback():
    diagnostics, errors = diagnostic_lines(
        "Real-Debrid resolver started\n"
        "VideoPlayer::OpenFile\n"
        "Real-Debrid resolver failed safely\n"
    )
    assert len(diagnostics) == 3
    assert errors == ["Real-Debrid resolver failed safely"]


def test_terminal_failure_state_detects_kodi_unplayable_result():
    log = (
        "Loading source progress\n"
        "Playlist Player: skipping unplayable item: 0, path [<redacted>]\n"
    )
    assert terminal_failure_state(log) == "unplayable"
    assert terminal_failure_state("Creating Demuxer") is None


def test_playback_log_state_detects_transient_player_between_rpc_polls():
    started = "VideoPlayer::OpenFile\nCreating Demuxer\n"
    assert playback_log_state(started) == "playback_started"
    assert (
        playback_log_state(started + "CVideoPlayer::CloseFile\n")
        == "playback_stopped_early"
    )
    assert playback_log_state("VideoPlayer::OpenFile\n") is None


def test_successful_source_fingerprint_tracks_last_magnet_before_playback():
    failed_hash = "a" * 40
    played_hash = "b" * 40
    log = (
        "Sending MAGNET: magnet:?xt=urn:btih:%s\n"
        "no_playable_url\n"
        "Sending MAGNET: magnet:?xt=urn:btih:%s&dn=title\n"
        "Played file as resolve\n" % (failed_hash, played_hash)
    )
    expected = hashlib.sha256(played_hash.encode("ascii")).hexdigest()[:16]
    assert successful_source_fingerprint(log) == expected
    assert successful_source_fingerprint("Played file as resolve\n") is None


def test_plugin_url_nonce_prevents_kodi_from_reusing_a_previous_invocation():
    url = plugin_url(sony_kodi_matrix.CASES["sintel"], e2e_nonce=123456)
    assert "e2e_nonce=123456" in url
    assert "action=play_Item" in url


def test_house_of_the_dragon_season_three_case_has_episode_metadata():
    case = sony_kodi_matrix.CASES["house_of_the_dragon_s03e01"]
    assert case["media_type"] == "episode"
    assert case["season"] == 3
    assert case["episode"] == 1
    assert case["premiered"] == "2026-06-21"


def test_open_media_uses_acknowledged_jsonrpc_player_open():
    class FakeRpc:
        def __init__(self):
            self.calls = []

        def call(self, method, params=None):
            self.calls.append((method, params))
            return "OK"

    rpc = FakeRpc()
    open_media(rpc, "plugin://plugin.video.umbrella/?action=play_Item")
    assert rpc.calls == [
        (
            "Player.Open",
            {
                "item": {
                    "file": "plugin://plugin.video.umbrella/?action=play_Item"
                }
            },
        )
    ]
