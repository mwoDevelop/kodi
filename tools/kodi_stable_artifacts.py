#!/usr/bin/env python3
"""Fetch and verify exact public Kodi channel artifacts into private cache."""

from __future__ import annotations

import hashlib
import json
import os
import re
import tempfile
import urllib.request
from pathlib import Path, PurePosixPath
from zipfile import ZipFile


ROOT = Path(__file__).resolve().parents[1]
PUBLIC = "https://mwodevelop.github.io/kodi"
SHA256 = re.compile(r"^[0-9a-f]{64}$")
CHANNELS = {
    "stable": {"schema": 2, "repository_id": "repository.mwodevelop"},
    "testing": {
        "schema": 1,
        "repository_id": "repository.mwodevelop.testing",
    },
}


def digest(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def _download(url, destination, opener=urllib.request.urlopen):
    destination = Path(destination)
    destination.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
    destination.parent.chmod(0o700)
    with opener(url, timeout=60) as response:
        if not str(response.geturl()).startswith("https://"):
            raise ValueError("stable artifact redirect must use HTTPS")
        payload = response.read(64 * 1024 * 1024 + 1)
    if len(payload) > 64 * 1024 * 1024:
        raise ValueError("stable artifact exceeds size policy")
    descriptor, temporary = tempfile.mkstemp(
        prefix=".%s." % destination.name,
        dir=str(destination.parent),
    )
    try:
        with os.fdopen(descriptor, "wb") as handle:
            handle.write(payload)
            handle.flush()
            os.fsync(handle.fileno())
        os.chmod(temporary, 0o600)
        os.replace(temporary, destination)
        destination.chmod(0o600)
    finally:
        if os.path.exists(temporary):
            os.unlink(temporary)


def artifact_manifest(opener=urllib.request.urlopen):
    with opener(PUBLIC + "/artifact-manifest.sha256", timeout=30) as response:
        if not str(response.geturl()).startswith("https://"):
            raise ValueError("artifact manifest redirect must use HTTPS")
        text = response.read(2 * 1024 * 1024).decode("utf-8")
    result = {}
    for line in text.splitlines():
        checksum, separator, relative = line.partition("  ")
        if not separator or not SHA256.fullmatch(checksum):
            raise ValueError("invalid public artifact manifest")
        path = PurePosixPath(relative)
        if path.is_absolute() or ".." in path.parts or relative in result:
            raise ValueError("unsafe public artifact manifest path")
        result[relative] = checksum
    return result


def _validate_zip(path, addon_id, version):
    expected = "%s/addon.xml" % addon_id
    with ZipFile(path) as archive:
        names = archive.namelist()
        if expected not in names or len(names) > 10000:
            raise ValueError("stable ZIP identity is invalid")
        if any(
            PurePosixPath(name).is_absolute()
            or ".." in PurePosixPath(name).parts
            or PurePosixPath(name).parts[0] != addon_id
            for name in names
        ):
            raise ValueError("stable ZIP contains an unsafe path")
        metadata = archive.read(expected).decode("utf-8-sig")
    if ('id="%s"' % addon_id) not in metadata or ('version="%s"' % version) not in metadata:
        raise ValueError("stable ZIP metadata differs from lock")


def prepare(repository=ROOT, opener=urllib.request.urlopen, channel="stable"):
    repository = Path(repository).resolve()
    if channel not in CHANNELS:
        raise ValueError("unsupported Kodi repository channel")
    channel_config = CHANNELS[channel]
    lock_path = repository / "manifests/locks" / (channel + ".json")
    lock = json.loads(lock_path.read_text(encoding="utf-8"))
    if (
        lock.get("schema") != channel_config["schema"]
        or lock.get("channel") != channel
    ):
        raise ValueError("Kodi channel lock identity is invalid")
    lock_sha = digest(lock_path)
    cache = repository / ".kodi-private/kodi-ops/artifacts" / lock_sha
    cache.mkdir(parents=True, exist_ok=True, mode=0o700)
    cache.chmod(0o700)
    public = artifact_manifest(opener=opener)
    artifacts = {}
    for addon_id, pin in lock["components"].items():
        version = pin["version"]
        relative = "%s/omega/%s/%s-%s.zip" % (
            channel,
            addon_id,
            addon_id,
            version,
        )
        expected = pin["zip_sha256"]
        if public.get(relative) != expected:
            raise ValueError("public artifact manifest differs from channel lock")
        destination = cache / (addon_id + ".zip")
        if not destination.is_file() or digest(destination) != expected:
            _download(PUBLIC + "/" + relative, destination, opener=opener)
        if digest(destination) != expected:
            raise ValueError("downloaded channel artifact digest differs")
        _validate_zip(destination, addon_id, version)
        artifacts[addon_id] = {
            "path": destination,
            "sha256": expected,
            "version": version,
        }
    repository_id = channel_config["repository_id"]
    repository_version = "1.0.0"
    relative = "%s-%s.zip" % (repository_id, repository_version)
    expected = public.get(relative)
    if not expected:
        raise ValueError("public artifact manifest lacks channel repository ZIP")
    destination = cache / (repository_id + ".zip")
    if not destination.is_file() or digest(destination) != expected:
        _download(PUBLIC + "/" + relative, destination, opener=opener)
    if digest(destination) != expected:
        raise ValueError("channel repository ZIP digest differs")
    _validate_zip(destination, repository_id, repository_version)
    return {
        "channel": channel,
        "repository_id": repository_id,
        "lock_sha256": lock_sha,
        "repository": {
            "path": destination,
            "sha256": expected,
            "version": repository_version,
        },
        "addons": artifacts,
    }
