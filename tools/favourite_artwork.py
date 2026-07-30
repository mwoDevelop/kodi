#!/usr/bin/env python3
"""Make WatchNixtoons2 favourite artwork portable across Kodi restores."""

from __future__ import annotations

import hashlib
import json
import os
import sys
import urllib.request
import xml.etree.ElementTree as ET
from pathlib import Path
from urllib.parse import urlsplit, urlunsplit


LEGACY_ADDON_ID = "plugin.video.watchnixtoons2"
ADDON_ID = "plugin.video.watchnixtoons2.mwodevelop"
ADDON_IDS = (LEGACY_ADDON_ID, ADDON_ID)
ARTWORK_URI = "special://profile/favourite-artwork/"
MANIFEST_NAME = "manifest.json"
MAX_IMAGE_BYTES = 5 * 1024 * 1024
LEGACY_IMAGE_HOSTS = {
    "cdn.animationexplore.com",
    "cdn.animationexplorer.com",
}
WCO_IMAGE_HOST = "images.wcostream.com"
TMDB_IMAGE_HOST = "image.tmdb.org"
USER_AGENT = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
    "AppleWebKit/537.36 (KHTML, like Gecko) "
    "Chrome/150.0.0.0 Safari/537.36"
)


def _canonical_json(value):
    return json.dumps(
        value, sort_keys=True, separators=(",", ":"), ensure_ascii=False
    ).encode("utf-8")


def _atomic_write(path, payload):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_name(path.name + ".tmp")
    temporary.write_bytes(payload)
    os.replace(temporary, path)


def _load_manifest(path):
    path = Path(path)
    if not path.is_file():
        return {"schema": 1, "entries": {}}
    try:
        document = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return {"schema": 1, "entries": {}}
    if document.get("schema") != 1 or not isinstance(
        document.get("entries"), dict
    ):
        return {"schema": 1, "entries": {}}
    return document


def _favourite_id(node):
    return hashlib.sha256(
        _canonical_json(
            {
                "name": node.attrib.get("name", ""),
                "action": node.text or "",
            }
        )
    ).hexdigest()


def _migrate_action(action):
    legacy = "plugin://%s/" % LEGACY_ADDON_ID
    current = "plugin://%s/" % ADDON_ID
    return action.replace(legacy, current)


def _entry_for_thumbnail(entries, thumbnail):
    if not thumbnail.startswith(ARTWORK_URI):
        return {}
    file_name = thumbnail[len(ARTWORK_URI) :]
    if not file_name or "/" in file_name or "\\" in file_name:
        return {}
    for entry in entries.values():
        if isinstance(entry, dict) and entry.get("file") == file_name:
            return entry
    return {}


def _normalise_source(image_uri):
    remote = image_uri.split("|", 1)[0].strip()
    parts = urlsplit(remote)
    host = (parts.hostname or "").casefold()
    if parts.scheme != "https":
        return None
    if host in LEGACY_IMAGE_HOSTS:
        host = WCO_IMAGE_HOST
    if host == WCO_IMAGE_HOST:
        if not parts.path.startswith("/catimg/"):
            return None
    elif host == TMDB_IMAGE_HOST:
        if not parts.path.startswith("/t/p/"):
            return None
    else:
        return None
    return urlunsplit(("https", host, parts.path, parts.query, ""))


def _image_type(payload, content_type):
    content_type = content_type.split(";", 1)[0].strip().casefold()
    if payload.startswith(b"\xff\xd8\xff") and content_type in {
        "image/jpeg",
        "image/jpg",
    }:
        return "jpg"
    if payload.startswith(b"\x89PNG\r\n\x1a\n") and content_type == "image/png":
        return "png"
    if (
        len(payload) >= 12
        and payload[:4] == b"RIFF"
        and payload[8:12] == b"WEBP"
        and content_type == "image/webp"
    ):
        return "webp"
    if payload[:6] in {b"GIF87a", b"GIF89a"} and content_type == "image/gif":
        return "gif"
    raise ValueError("favourite artwork response is not a supported image")


def _download(source_url, opener):
    headers = {
        "User-Agent": USER_AGENT,
        "Accept": "image/webp,image/png,image/jpeg,image/gif,*/*;q=0.8",
    }
    if urlsplit(source_url).hostname == WCO_IMAGE_HOST:
        headers["Referer"] = "https://www.wcostream.tv/"
    request = urllib.request.Request(source_url, headers=headers)
    with opener(request, timeout=20) as response:
        final_url = (
            response.geturl() if hasattr(response, "geturl") else source_url
        )
        if _normalise_source(final_url) != source_url:
            raise ValueError("favourite artwork redirected outside its source")
        content_type = response.headers.get("Content-Type", "")
        payload = response.read(MAX_IMAGE_BYTES + 1)
    if not payload or len(payload) > MAX_IMAGE_BYTES:
        raise ValueError("favourite artwork response has an invalid size")
    return payload, _image_type(payload, content_type)


def materialize(favourites_path, artwork_directory, opener=None):
    """Download safe artwork and rewrite WatchNixtoons2 favourites locally."""

    favourites_path = Path(favourites_path)
    artwork_directory = Path(artwork_directory)
    if not favourites_path.is_file():
        return {"matched": 0, "materialized": 0, "retained": 0, "failed": 0}
    opener = opener or urllib.request.urlopen
    tree = ET.parse(favourites_path)
    root = tree.getroot()
    if root.tag != "favourites":
        raise ValueError("invalid Kodi favourites document")
    manifest_path = artwork_directory / MANIFEST_NAME
    manifest = _load_manifest(manifest_path)
    entries = manifest["entries"]
    active_entries = {}
    counts = {
        "matched": 0,
        "materialized": 0,
        "retained": 0,
        "failed": 0,
        "migrated_actions": 0,
    }
    changed = False

    for node in root.findall("favourite"):
        action = node.text or ""
        if not any(addon_id in action for addon_id in ADDON_IDS):
            continue
        counts["matched"] += 1
        migrated_action = _migrate_action(action)
        if migrated_action != action:
            node.text = migrated_action
            counts["migrated_actions"] += 1
            changed = True
        favourite_id = _favourite_id(node)
        thumbnail = node.attrib.get("thumb", "")
        existing = entries.get(favourite_id, {})
        if not existing:
            existing = _entry_for_thumbnail(entries, thumbnail)
        if thumbnail.startswith(ARTWORK_URI):
            source_url = _normalise_source(existing.get("source_url", ""))
        else:
            source_url = _normalise_source(thumbnail)
        if not isinstance(source_url, str) or not source_url:
            counts["failed"] += 1
            continue
        local_name = existing.get("file")
        local_path = (
            artwork_directory / local_name
            if isinstance(local_name, str) and "/" not in local_name
            else None
        )
        try:
            payload, extension = _download(source_url, opener)
        except (OSError, ValueError):
            if local_path is not None and local_path.is_file():
                counts["retained"] += 1
                active_entries[favourite_id] = dict(existing)
            else:
                counts["failed"] += 1
            continue
        sha256 = hashlib.sha256(payload).hexdigest()
        file_name = "%s.%s" % (sha256, extension)
        target = artwork_directory / file_name
        if not target.is_file() or target.read_bytes() != payload:
            _atomic_write(target, payload)
        portable_uri = ARTWORK_URI + file_name
        if node.attrib.get("thumb") != portable_uri:
            node.set("thumb", portable_uri)
            changed = True
        active_entries[favourite_id] = {
            "file": file_name,
            "sha256": sha256,
            "source_url": source_url,
        }
        counts["materialized"] += 1

    if changed:
        ET.indent(tree, space="    ")
        _atomic_write(
            favourites_path,
            ET.tostring(root, encoding="utf-8") + b"\n",
        )
    if counts["materialized"] or counts["retained"]:
        _atomic_write(
            manifest_path,
            _canonical_json({"schema": 1, "entries": active_entries}) + b"\n",
        )
    return counts


def _write_marker(path, document):
    _atomic_write(path, _canonical_json(document) + b"\n")


def main():
    if len(sys.argv) != 4:
        raise SystemExit(
            "usage: favourite_artwork.py FAVOURITES ARTWORK_DIR MARKER"
        )
    marker = sys.argv[3]
    try:
        import xbmcvfs

        result = materialize(
            xbmcvfs.translatePath(sys.argv[1]),
            xbmcvfs.translatePath(sys.argv[2]),
        )
        _write_marker(marker, {"ok": True, **result})
    except Exception as exc:
        _write_marker(marker, {"ok": False, "error_type": type(exc).__name__})


if __name__ == "__main__":
    main()
