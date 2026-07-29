import json
import urllib.error
import xml.etree.ElementTree as ET

from tools.favourite_artwork import ARTWORK_URI, materialize


JPEG = b"\xff\xd8\xff\xe0" + (b"image" * 20)


class Response:
    def __init__(self, request, payload=JPEG, content_type="image/jpeg"):
        self.request = request
        self.payload = payload
        self.headers = {"Content-Type": content_type}

    def __enter__(self):
        return self

    def __exit__(self, *_args):
        return None

    def read(self, _limit):
        return self.payload

    def geturl(self):
        return self.request.full_url


def _favourites(path, thumbnail, action=None):
    root = ET.Element("favourites")
    item = ET.SubElement(
        root,
        "favourite",
        {"name": "Bluey", "thumb": thumbnail},
    )
    item.text = action or (
        'ActivateWindow(10025,"plugin://plugin.video.watchnixtoons2/'
        '?action=actionEpisodesMenu&url=%2fanime%2fbluey",return)'
    )
    ET.ElementTree(root).write(path, encoding="utf-8")


def test_legacy_watch_artwork_is_rewritten_to_portable_file(tmp_path):
    favourites = tmp_path / "favourites.xml"
    artwork = tmp_path / "favourite-artwork"
    _favourites(
        favourites,
        "https://cdn.animationexplore.com/catimg/775209.jpg"
        "|User-Agent=obsolete&Cookie=secret",
    )
    requests = []

    def opener(request, timeout):
        assert timeout == 20
        requests.append(request)
        return Response(request)

    result = materialize(favourites, artwork, opener=opener)

    assert result == {
        "matched": 1,
        "materialized": 1,
        "retained": 0,
        "failed": 0,
    }
    node = ET.parse(favourites).getroot().find("favourite")
    assert node.attrib["thumb"].startswith(ARTWORK_URI)
    assert requests[0].full_url == (
        "https://images.wcostream.com/catimg/775209.jpg"
    )
    assert "Cookie" not in requests[0].headers
    assert requests[0].headers["Referer"] == "https://www.wcostream.tv/"
    manifest = json.loads((artwork / "manifest.json").read_text())
    entry = next(iter(manifest["entries"].values()))
    assert entry["source_url"] == requests[0].full_url
    assert (artwork / entry["file"]).read_bytes() == JPEG


def test_refresh_failure_retains_previously_materialized_artwork(tmp_path):
    favourites = tmp_path / "favourites.xml"
    artwork = tmp_path / "favourite-artwork"
    _favourites(
        favourites,
        "https://images.wcostream.com/catimg/775209.jpg",
    )
    materialize(
        favourites,
        artwork,
        opener=lambda request, timeout: Response(request),
    )

    def unavailable(_request, timeout):
        assert timeout == 20
        raise urllib.error.URLError("offline")

    result = materialize(favourites, artwork, opener=unavailable)

    assert result["retained"] == 1
    assert result["failed"] == 0
    node = ET.parse(favourites).getroot().find("favourite")
    assert node.attrib["thumb"].startswith(ARTWORK_URI)


def test_non_watch_favourite_is_not_downloaded(tmp_path):
    favourites = tmp_path / "favourites.xml"
    artwork = tmp_path / "favourite-artwork"
    remote = "https://image.tmdb.org/t/p/w342/poster.jpg"
    _favourites(
        favourites,
        remote,
        action='ActivateWindow(10025,"plugin://plugin.video.umbrella/",return)',
    )

    result = materialize(
        favourites,
        artwork,
        opener=lambda *_args, **_kwargs: (_ for _ in ()).throw(
            AssertionError("unexpected download")
        ),
    )

    assert result["matched"] == 0
    assert ET.parse(favourites).getroot().find("favourite").attrib[
        "thumb"
    ] == remote
    assert not artwork.exists()
