import xml.etree.ElementTree as ET

import pytest

from tools.kodi_umbrella_settings import (
    REQUIRED_PRIVATE,
    _private_settings_match,
    _validated_source,
)


def test_umbrella_authority_requires_complete_realdebrid_credentials(tmp_path):
    root = ET.Element("settings")
    for key in sorted(REQUIRED_PRIVATE):
        node = ET.SubElement(root, "setting", id=key)
        node.text = "private-value"
    path = tmp_path / "settings.xml"
    path.write_bytes(ET.tostring(root))

    source = _validated_source(path)

    assert set(REQUIRED_PRIVATE).issubset(source["values"])


def test_umbrella_authority_rejects_missing_token(tmp_path):
    root = ET.Element("settings")
    for key in sorted(REQUIRED_PRIVATE.difference({"realdebridtoken"})):
        node = ET.SubElement(root, "setting", id=key)
        node.text = "private-value"
    path = tmp_path / "settings.xml"
    path.write_bytes(ET.tostring(root))

    with pytest.raises(ValueError, match="lacks Real-Debrid"):
        _validated_source(path)


def test_umbrella_private_settings_match_requires_exact_authority():
    authoritative = {key: "authority-" + key for key in REQUIRED_PRIVATE}
    observed = {**authoritative, "realdebrid.enable": "true"}

    assert _private_settings_match(observed, authoritative)
    observed["realdebridtoken"] = "stale-token"
    assert not _private_settings_match(observed, authoritative)
