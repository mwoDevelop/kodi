import hashlib
import xml.etree.ElementTree as ET

import pytest

from tools.profile_portable_favourites import (
    ARTWORK_PREFIX,
    export_portable_favourites,
    write_export,
)


def _profile(tmp_path, action=None):
    root = tmp_path / "kodi"
    userdata = root / "userdata"
    artwork = userdata / "favourite-artwork"
    artwork.mkdir(parents=True)
    payload = b"\x89PNG\r\n\x1a\nportable"
    digest = hashlib.sha256(payload).hexdigest()
    (artwork / (digest + ".png")).write_bytes(payload)
    favourites = ET.Element("favourites")
    node = ET.SubElement(
        favourites,
        "favourite",
        {
            "name": "CARTOONS",
            "thumb": ARTWORK_PREFIX + digest + ".png",
        },
    )
    node.text = action or (
        'ActivateWindow(10025,"plugin://'
        'plugin.video.watchnixtoons2.mwodevelop/",return)'
    )
    ET.ElementTree(favourites).write(userdata / "favourites.xml")
    return root, payload, digest


def test_export_is_typed_and_keeps_verified_artwork(tmp_path):
    root, payload, digest = _profile(tmp_path)

    exported = export_portable_favourites(root)

    item = exported["adapter"]["items"][0]
    assert item == {
        "title": "CARTOONS",
        "type": "window",
        "window": "videos",
        "windowparameter": "plugin://plugin.video.watchnixtoons2.mwodevelop/",
        "thumbnail": ARTWORK_PREFIX + digest + ".png",
    }
    assert exported["blobs"][digest]["content"] == payload
    output = tmp_path / "export"
    assert write_export(output, exported)["blobs"] == 1
    assert (output / "blobs" / digest[:2] / digest).read_bytes() == payload


def test_export_rejects_opaque_favourite_action(tmp_path):
    root, _payload, _digest = _profile(tmp_path, action="System.Exec(evil)")

    with pytest.raises(ValueError, match="unsupported action"):
        export_portable_favourites(root)
