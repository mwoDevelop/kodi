#!/usr/bin/env python3
"""Materialize and propose exact official Kodi YouTube add-on candidates."""

from __future__ import annotations

import argparse
import hashlib
import html.parser
import json
import re
import tempfile
import urllib.parse
import urllib.request
from pathlib import Path, PurePosixPath
from xml.etree import ElementTree
from zipfile import ZipFile

try:
    from kodi_default_addons import load_manifest, validate_archive
except ModuleNotFoundError:
    from tools.kodi_default_addons import load_manifest, validate_archive


ADDON_ID = "plugin.video.youtube"
SCHEMA = 1
MAX_DOWNLOAD_BYTES = 32 * 1024 * 1024
SAFE_VERSION = re.compile(r"^\d+(?:\.\d+)+(?:[+._~-][A-Za-z0-9._~-]+)?$")
ARCHIVE_NAME = re.compile(r"^plugin\.video\.youtube-(?P<version>[^/]+)\.zip$")


class UpstreamError(ValueError):
    """Official upstream metadata or candidate is unsafe/inconsistent."""


class _Links(html.parser.HTMLParser):
    def __init__(self):
        super().__init__()
        self.values = []

    def handle_starttag(self, tag, attrs):
        if tag.lower() != "a":
            return
        value = dict(attrs).get("href")
        if value:
            self.values.append(value)


def _canonical(value):
    return (
        json.dumps(value, ensure_ascii=False, separators=(",", ":"), sort_keys=True)
        + "\n"
    )


def _sha256_bytes(value):
    return hashlib.sha256(value).hexdigest()


def _sha256_path(path):
    return _sha256_bytes(Path(path).read_bytes())


def _version_key(value):
    if not isinstance(value, str) or not SAFE_VERSION.fullmatch(value):
        raise UpstreamError("unsupported YouTube add-on version")
    prefix = re.match(r"^\d+(?:\.\d+)+", value).group(0)
    return tuple(int(part) for part in prefix.split(".")), value


def _youtube_entry(document):
    matches = [item for item in document["addons"] if item["id"] == ADDON_ID]
    if len(matches) != 1:
        raise UpstreamError("YouTube default add-on policy is missing or duplicated")
    entry = matches[0]
    if (
        entry.get("install_mode") != "kodi-native-official"
        or entry.get("origin") != "repository.xbmc.org"
    ):
        raise UpstreamError("YouTube policy is not native official")
    return entry


def discover_versions(index_payload):
    parser = _Links()
    try:
        parser.feed(index_payload.decode("utf-8"))
    except (UnicodeDecodeError, html.parser.HTMLParseError) as error:
        raise UpstreamError("official Kodi directory index is invalid") from error
    versions = set()
    for raw in parser.values:
        name = urllib.parse.unquote(urllib.parse.urlparse(raw).path.rsplit("/", 1)[-1])
        match = ARCHIVE_NAME.fullmatch(name)
        if match:
            version = match.group("version")
            _version_key(version)
            versions.add(version)
    if not versions:
        raise UpstreamError("official Kodi directory has no YouTube ZIP")
    return sorted(versions, key=_version_key)


def _read_https(url, opener=urllib.request.urlopen):
    if not url.startswith("https://"):
        raise UpstreamError("upstream URL must use HTTPS")
    with opener(url, timeout=30) as response:
        final_url = response.geturl() if hasattr(response, "geturl") else url
        if not str(final_url).startswith("https://"):
            raise UpstreamError("upstream redirect must use HTTPS")
        payload = response.read(MAX_DOWNLOAD_BYTES + 1)
    if len(payload) > MAX_DOWNLOAD_BYTES:
        raise UpstreamError("upstream response exceeds size policy")
    return payload


def _requirements(addon_xml):
    root = ElementTree.fromstring(addon_xml.decode("utf-8-sig"))
    if root.attrib.get("id") != ADDON_ID:
        raise UpstreamError("candidate addon.xml identity differs")
    dependencies = []
    requirements = {}
    for item in root.findall("./requires/import"):
        addon_id = item.attrib.get("addon", "")
        if item.attrib.get("optional") == "true" or addon_id == "xbmc.python":
            continue
        version = item.attrib.get("version")
        if not version:
            raise UpstreamError("required dependency lacks a minimum version")
        dependency_type = (
            "platform" if addon_id.startswith("inputstream.") else "python"
        )
        dependencies.append(addon_id)
        requirements[addon_id] = {
            "minimum_version": version,
            "type": dependency_type,
        }
    if not dependencies:
        raise UpstreamError("candidate has no qualified dependencies")
    return dependencies, requirements


def _extract_candidate(archive_path, destination):
    destination = Path(destination)
    destination.mkdir(parents=True, exist_ok=False)
    count = 0
    total = 0
    with ZipFile(archive_path) as archive:
        for item in archive.infolist():
            relative = PurePosixPath(item.filename)
            if (
                relative.is_absolute()
                or not relative.parts
                or relative.parts[0] != ADDON_ID
                or ".." in relative.parts
            ):
                raise UpstreamError("candidate archive path is unsafe")
            target = destination.joinpath(*relative.parts)
            if item.is_dir():
                target.mkdir(parents=True, exist_ok=True)
                continue
            count += 1
            total += item.file_size
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_bytes(archive.read(item))
    return {"files": count, "bytes": total}


def materialize(manifest_path, output_dir, opener=urllib.request.urlopen):
    manifest_path = Path(manifest_path)
    document = load_manifest(manifest_path)
    current = _youtube_entry(document)
    directory_url = current["url"].rsplit("/", 1)[0] + "/"
    versions = discover_versions(_read_https(directory_url, opener=opener))
    latest = versions[-1]
    if _version_key(latest) < _version_key(current["version"]):
        raise UpstreamError("official Kodi index regressed below qualified version")
    archive_url = urllib.parse.urljoin(directory_url, f"{ADDON_ID}-{latest}.zip")
    payload = _read_https(archive_url, opener=opener)
    digest = _sha256_bytes(payload)

    output_dir = Path(output_dir)
    if output_dir.exists():
        raise UpstreamError("candidate output already exists")
    output_dir.mkdir(parents=True, mode=0o700)
    archive_path = output_dir / "artifact" / (f"{ADDON_ID}-{latest}.zip")
    archive_path.parent.mkdir()
    archive_path.write_bytes(payload)

    candidate_entry = {
        **current,
        "version": latest,
        "url": archive_url,
        "sha256": digest,
        "source": f"https://github.com/anxdpanic/plugin.video.youtube/tree/v{latest}",
    }
    validate_archive(archive_path, candidate_entry)
    with ZipFile(archive_path) as archive:
        addon_xml = archive.read(ADDON_ID + "/addon.xml")
    dependencies, requirements = _requirements(addon_xml)
    candidate_entry["dependencies"] = dependencies
    candidate_entry["dependency_requirements"] = requirements

    action = "noop" if candidate_entry == current else "review"
    candidate_manifest = {
        **document,
        "addons": [
            candidate_entry if item["id"] == ADDON_ID else item
            for item in document["addons"]
        ],
    }
    extracted = _extract_candidate(archive_path, output_dir / "expanded")
    descriptor = {
        "schema": SCHEMA,
        "action": action,
        "addon_id": ADDON_ID,
        "base_manifest_sha256": _sha256_path(manifest_path),
        "candidate_id": digest,
        "qualified_version": current["version"],
        "candidate_version": latest,
        "archive": archive_path.relative_to(output_dir).as_posix(),
        "archive_sha256": digest,
        "expanded": extracted,
        "candidate_manifest": candidate_manifest,
    }
    (output_dir / "candidate.json").write_text(_canonical(descriptor), encoding="utf-8")
    return descriptor


def apply_candidate(candidate_path, manifest_path):
    candidate_path = Path(candidate_path)
    candidate = json.loads(candidate_path.read_text(encoding="utf-8"))
    expected = {
        "schema",
        "action",
        "addon_id",
        "base_manifest_sha256",
        "candidate_id",
        "qualified_version",
        "candidate_version",
        "archive",
        "archive_sha256",
        "expanded",
        "candidate_manifest",
    }
    if set(candidate) != expected or candidate["schema"] != SCHEMA:
        raise UpstreamError("candidate descriptor schema differs")
    if candidate["action"] != "review" or candidate["addon_id"] != ADDON_ID:
        raise UpstreamError("candidate does not require a manifest review")
    manifest_path = Path(manifest_path)
    if _sha256_path(manifest_path) != candidate["base_manifest_sha256"]:
        raise UpstreamError("base manifest changed after candidate discovery")
    archive = candidate_path.parent / candidate["archive"]
    if _sha256_path(archive) != candidate["archive_sha256"]:
        raise UpstreamError("candidate archive digest differs")
    document = candidate["candidate_manifest"]
    with tempfile.NamedTemporaryFile(
        mode="w", encoding="utf-8", dir=manifest_path.parent, delete=False
    ) as temporary:
        temporary.write(json.dumps(document, indent=2, ensure_ascii=False) + "\n")
        temporary_path = Path(temporary.name)
    try:
        load_manifest(temporary_path)
        temporary_path.replace(manifest_path)
    finally:
        temporary_path.unlink(missing_ok=True)
    return document


def _markdown(descriptor):
    return "\n".join(
        [
            "# Official Kodi YouTube upstream",
            "",
            "- action: `{}`".format(descriptor["action"]),
            "- qualified version: `{}`".format(descriptor["qualified_version"]),
            "- candidate version: `{}`".format(descriptor["candidate_version"]),
            "- candidate ID: `{}`".format(descriptor["candidate_id"]),
            "- expanded files: `{}`".format(descriptor["expanded"]["files"]),
            "- expanded bytes: `{}`".format(descriptor["expanded"]["bytes"]),
            "",
            (
                "No candidate code was executed. A changed candidate requires malware "
                "scan, pull-request review and BlueStacks/X88 qualification."
            ),
            "",
        ]
    )


def main():
    parser = argparse.ArgumentParser()
    commands = parser.add_subparsers(dest="command", required=True)
    discover = commands.add_parser("discover")
    discover.add_argument("--manifest", default="manifests/kodi-default-addons.json")
    discover.add_argument("--output", required=True)
    discover.add_argument("--report", required=True)
    discover.add_argument("--markdown", required=True)
    apply = commands.add_parser("apply")
    apply.add_argument("--candidate", required=True)
    apply.add_argument("--manifest", default="manifests/kodi-default-addons.json")
    args = parser.parse_args()
    try:
        if args.command == "discover":
            descriptor = materialize(args.manifest, args.output)
            Path(args.report).write_text(_canonical(descriptor), encoding="utf-8")
            Path(args.markdown).write_text(_markdown(descriptor), encoding="utf-8")
            print(_canonical(descriptor), end="")
        else:
            apply_candidate(args.candidate, args.manifest)
            print('{"result":"applied"}')
        return 0
    except (OSError, ValueError, ElementTree.ParseError) as error:
        print(json.dumps({"result": "failed", "error_type": type(error).__name__}))
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
