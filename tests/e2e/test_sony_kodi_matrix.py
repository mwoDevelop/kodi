import struct

from sony_kodi_matrix import EventClient, diagnostic_lines, redact


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


def test_diagnostics_separate_errors_from_normal_playback():
    diagnostics, errors = diagnostic_lines(
        "Real-Debrid resolver started\n"
        "VideoPlayer::OpenFile\n"
        "Real-Debrid resolver failed safely\n"
    )
    assert len(diagnostics) == 3
    assert errors == ["Real-Debrid resolver failed safely"]
