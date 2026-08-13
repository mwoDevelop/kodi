from xml.etree import ElementTree

import pytest

from tools.kodi_flatpak_profile_sync_rollout import (
    OPENSUBTITLES_COM_ID,
    _xml_settings_match,
    opensubtitles_com_documents,
)


def _values(document):
    return {
        element.attrib.get("id"): element.text or ""
        for element in ElementTree.fromstring(document).iter("setting")
    }


API_KEY_FIXTURE = "not-a-secret-test-value"


def test_documents_configure_credentials_and_global_defaults():
    settings, gui = opensubtitles_com_documents(
        b'<settings version="2"><setting id="search_cache_duration">5</setting></settings>',
        b'<settings><setting id="subtitles.movie"></setting><setting id="subtitles.tv">old</setting></settings>',
        "account",
        "secret",
        API_KEY_FIXTURE,
    )

    assert _values(settings) == {
        "APIKey": API_KEY_FIXTURE,
        "OSpass": "secret",
        "OSuser": "account",
        "search_cache_duration": "5",
    }
    assert _values(gui) == {
        "subtitles.movie": OPENSUBTITLES_COM_ID,
        "subtitles.tv": OPENSUBTITLES_COM_ID,
    }


def test_documents_create_addon_settings_but_require_existing_gui_settings():
    settings, _gui = opensubtitles_com_documents(
        None,
        b"<settings/>",
        "account",
        "secret",
        API_KEY_FIXTURE,
    )
    assert ElementTree.fromstring(settings).attrib == {"version": "2"}

    with pytest.raises(ValueError, match="guisettings.xml is missing"):
        opensubtitles_com_documents(
            None, None, "account", "secret", API_KEY_FIXTURE
        )


def test_documents_reject_duplicate_security_sensitive_settings():
    with pytest.raises(ValueError, match="duplicate Kodi setting"):
        opensubtitles_com_documents(
            b'<settings><setting id="OSuser"/><setting id="OSuser"/></settings>',
            b"<settings/>",
            "account",
            "secret",
            API_KEY_FIXTURE,
        )


def test_semantic_match_ignores_kodi_xml_formatting_but_rejects_duplicates():
    payload = b'''<?xml version="1.0" encoding="UTF-8" standalone="yes" ?>
<settings version="2">
  <setting id="unmanaged">keep</setting>
  <setting id="OSuser">account</setting>
</settings>'''
    assert _xml_settings_match(payload, {"OSuser": "account"}) is True
    assert _xml_settings_match(payload, {"OSuser": "different"}) is False
    assert (
        _xml_settings_match(
            b'<settings><setting id="OSuser">account</setting>'
            b'<setting id="OSuser">account</setting></settings>',
            {"OSuser": "account"},
        )
        is False
    )
