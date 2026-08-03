#!/usr/bin/env python3
"""Export typed Kodi favourites and verified content-addressed artwork."""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import tempfile
import xml.etree.ElementTree as ET
from pathlib import Path


ARTWORK_PREFIX = "special://profile/favourite-artwork/"
ARTWORK_FILE = re.compile(r"^([a-f0-9]{64})\.(jpg|png|webp)$")
ACTIVATE_WINDOW = re.compile(
    r'^ActivateWindow\((?:10025|videos),"([^"\r\n]+)",return\)$'
)
PLAY_MEDIA = re.compile(r'^PlayMedia\("([^"\r\n]+)"\)$')
RUN_SCRIPT = re.compile(r'^RunScript\("?([^"\r\n]+)"?\)$')
MEDIA_TYPES = {"jpg": "image/jpeg", "png": "image/png", "webp": "image/webp"}


def canonical_json(value):
    return json.dumps(
        value, sort_keys=True, separators=(",", ":"), ensure_ascii=False
    ).encode("utf-8")


def _action(value):
    match = ACTIVATE_WINDOW.fullmatch(value)
    if match:
        return {
            "type": "window",
            "window": "videos",
            "windowparameter": match.group(1),
        }
    match = PLAY_MEDIA.fullmatch(value)
    if match:
        return {"type": "media", "path": match.group(1)}
    match = RUN_SCRIPT.fullmatch(value)
    if match:
        return {"type": "script", "path": match.group(1)}
    raise ValueError("favourite uses an unsupported action")


def export_portable_favourites(profile_root):
    profile_root = Path(profile_root).resolve()
    source = profile_root / "userdata" / "favourites.xml"
    artwork_root = profile_root / "userdata" / "favourite-artwork"
    if source.is_symlink() or not source.is_file():
        raise ValueError("Kodi favourites source is unavailable")
    payload = source.read_bytes()
    if b"<!DOCTYPE" in payload.upper() or b"<!ENTITY" in payload.upper():
        raise ValueError("Kodi favourites contains a forbidden declaration")
    root = ET.fromstring(payload)
    if root.tag != "favourites":
        raise ValueError("invalid Kodi favourites document")
    items = []
    blobs = {}
    for node in root:
        if node.tag != "favourite" or set(node.attrib) - {"name", "thumb"}:
            raise ValueError("invalid Kodi favourite entry")
        title = node.attrib.get("name", "")
        if not title or len(title) > 200:
            raise ValueError("invalid Kodi favourite title")
        item = {"title": title, **_action((node.text or "").strip())}
        thumbnail = node.attrib.get("thumb", "")
        if thumbnail:
            if thumbnail.startswith(ARTWORK_PREFIX):
                filename = thumbnail[len(ARTWORK_PREFIX) :]
                match = ARTWORK_FILE.fullmatch(filename)
                if match is None:
                    raise ValueError("invalid portable favourite artwork path")
                artwork = artwork_root / filename
                if artwork.is_symlink() or not artwork.is_file():
                    raise ValueError("portable favourite artwork is missing")
                content = artwork.read_bytes()
                digest = hashlib.sha256(content).hexdigest()
                if digest != match.group(1):
                    raise ValueError("portable favourite artwork digest mismatch")
                media_type = MEDIA_TYPES[match.group(2)]
                blobs[digest] = {
                    "sha256": "sha256:" + digest,
                    "size": len(content),
                    "media_type": media_type,
                    "content": content,
                }
            elif "|" in thumbnail or not thumbnail.startswith("https://"):
                raise ValueError("favourite thumbnail is not portable")
            item["thumbnail"] = thumbnail
        items.append(item)
    if len(items) != len({canonical_json(item) for item in items}):
        raise ValueError("duplicate Kodi favourite")
    descriptors = [
        {key: value for key, value in blob.items() if key != "content"}
        for _digest, blob in sorted(blobs.items())
    ]
    return {
        "adapter": {
            "adapter": "kodi_favourites_v1",
            "apply_mode": "hot_apply",
            "ownership": "whole_document",
            "items": items,
            "artwork": descriptors,
        },
        "blobs": blobs,
    }


def write_export(output, exported):
    output = Path(output).resolve()
    if output.exists():
        raise ValueError("portable favourites output already exists")
    output.parent.mkdir(parents=True, exist_ok=True)
    temporary = Path(
        tempfile.mkdtemp(prefix=".%s." % output.name, dir=str(output.parent))
    )
    try:
        manifest = temporary / "adapter.json"
        manifest.write_bytes(canonical_json(exported["adapter"]) + b"\n")
        os.chmod(manifest, 0o600)
        for digest, blob in sorted(exported["blobs"].items()):
            target = temporary / "blobs" / digest[:2] / digest
            target.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
            target.write_bytes(blob["content"])
            os.chmod(target, 0o600)
        os.replace(temporary, output)
    except Exception:
        import shutil

        shutil.rmtree(temporary, ignore_errors=True)
        raise
    return {
        "output": str(output),
        "items": len(exported["adapter"]["items"]),
        "blobs": len(exported["blobs"]),
    }


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("profile_root")
    parser.add_argument("output")
    args = parser.parse_args()
    print(
        json.dumps(
            write_export(
                args.output, export_portable_favourites(args.profile_root)
            ),
            indent=2,
            sort_keys=True,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
