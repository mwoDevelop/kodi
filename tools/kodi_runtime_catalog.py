#!/usr/bin/env python3
"""Generate an append-only Kodi runtime capability catalog from official tags."""

from __future__ import annotations

import argparse
import hashlib
import io
import json
import os
import re
import sys
import tarfile
import tempfile
import urllib.error
import urllib.parse
import urllib.request
from pathlib import Path, PurePosixPath

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from tools.kodi_addon_runtime_compatibility import (
    CATALOG_SCHEMA,
    KodiVersion,
    _safe_xml,
    canonical_json,
    catalog_digest,
    release_digest,
    validate_catalog,
)

REPOSITORY = "xbmc/xbmc"
API_ORIGIN = "https://api.github.com"
CODELOAD_ORIGIN = "https://codeload.github.com"
MAX_DOWNLOAD = 256 * 1024 * 1024
MAX_ARCHIVE_FILES = 200_000
MAX_ARCHIVE_UNCOMPRESSED = 4 * 1024 * 1024 * 1024
MAX_SELECTED_FILES = 512
MAX_SELECTED_BYTES = 8 * 1024 * 1024
MAX_SOURCE_FILE = 2 * 1024 * 1024
TAG = re.compile(r"^[A-Za-z0-9._-]{1,128}$")
COMMIT = re.compile(r"^[0-9a-f]{40}$")
VARIABLE = re.compile(rb"@([A-Z][A-Z0-9_]*)@")
DEFINE = re.compile(
    rb'^\s*#define\s+([A-Z][A-Z0-9_]*)\s+"([^"\r\n]+)"\s*$',
    re.MULTILINE,
)


def _request(url, *, token=None, accept="application/vnd.github+json"):
    parsed = urllib.parse.urlparse(url)
    if parsed.scheme != "https" or parsed.netloc not in {
        "api.github.com",
        "codeload.github.com",
    }:
        raise ValueError("Kodi runtime source URL is not allowlisted")
    headers = {
        "Accept": accept,
        "User-Agent": "mwoDevelop-kodi-runtime-catalog/1",
        "X-GitHub-Api-Version": "2022-11-28",
    }
    if token:
        headers["Authorization"] = "Bearer " + token
    request = urllib.request.Request(url, headers=headers)
    try:
        response = urllib.request.urlopen(request, timeout=30)
    except (urllib.error.URLError, TimeoutError) as error:
        raise RuntimeError("Kodi runtime source request failed") from error
    final = urllib.parse.urlparse(response.geturl())
    if final.scheme != "https" or final.netloc not in {
        "api.github.com",
        "codeload.github.com",
    }:
        response.close()
        raise ValueError("Kodi runtime source redirect is not allowlisted")
    length = response.headers.get("Content-Length")
    if length and int(length) > MAX_DOWNLOAD:
        response.close()
        raise ValueError("Kodi runtime source download exceeds size policy")
    payload = bytearray()
    with response:
        while True:
            block = response.read(1024 * 1024)
            if not block:
                break
            payload.extend(block)
            if len(payload) > MAX_DOWNLOAD:
                raise ValueError(
                    "Kodi runtime source download exceeds size policy"
                )
    return bytes(payload)


def _json_request(path, token=None):
    try:
        document = json.loads(
            _request(API_ORIGIN + path, token=token).decode("utf-8")
        )
    except (UnicodeDecodeError, json.JSONDecodeError) as error:
        raise ValueError("Kodi runtime source metadata is invalid") from error
    if not isinstance(document, dict):
        raise ValueError("Kodi runtime source metadata is invalid")
    return document


def _release_metadata(tag=None, token=None):
    if tag is not None:
        if not TAG.fullmatch(tag):
            raise ValueError("Kodi release tag is invalid")
        path = "/repos/%s/releases/tags/%s" % (
            REPOSITORY,
            urllib.parse.quote(tag, safe=""),
        )
    else:
        path = "/repos/%s/releases/latest" % REPOSITORY
    release = _json_request(path, token=token)
    required = {
        "id": int,
        "tag_name": str,
        "draft": bool,
        "prerelease": bool,
    }
    if any(not isinstance(release.get(key), kind) for key, kind in required.items()):
        raise ValueError("Kodi release metadata is incomplete")
    if release["draft"] or release["prerelease"]:
        raise ValueError("Kodi prerelease is outside stable catalog scope")
    if not TAG.fullmatch(release["tag_name"]):
        raise ValueError("Kodi release metadata has an invalid tag")
    repository = release.get("html_url", "")
    if not isinstance(repository, str) or not repository.startswith(
        "https://github.com/xbmc/xbmc/releases/"
    ):
        raise ValueError("Kodi release repository identity differs")
    return release


def _resolve_tag(tag, token=None):
    ref = _json_request(
        "/repos/%s/git/ref/tags/%s"
        % (REPOSITORY, urllib.parse.quote(tag, safe="")),
        token=token,
    )
    item = ref.get("object")
    for _attempt in range(4):
        if not isinstance(item, dict):
            break
        kind = item.get("type")
        sha = item.get("sha")
        if not isinstance(sha, str) or not COMMIT.fullmatch(sha):
            break
        if kind == "commit":
            return sha
        if kind != "tag":
            break
        item = _json_request(
            "/repos/%s/git/tags/%s" % (REPOSITORY, sha), token=token
        ).get("object")
    raise ValueError("Kodi release tag does not resolve to one commit")


def _empty_catalog():
    return {
        "schema": CATALOG_SCHEMA,
        "source_repository": REPOSITORY,
        "releases": {},
    }


def _read_catalog(path):
    path = Path(path)
    if not path.exists():
        return _empty_catalog()
    document = json.loads(path.read_text(encoding="utf-8"))
    if not document.get("releases"):
        if document != _empty_catalog():
            raise ValueError("empty Kodi runtime catalog fields differ")
        return document
    return validate_catalog(document)


def _selected_archive_files(payload):
    selected = {}
    names = set()
    folded = set()
    total = 0
    try:
        archive = tarfile.open(fileobj=io.BytesIO(payload), mode="r:gz")
    except tarfile.TarError as error:
        raise ValueError("Kodi runtime source archive is invalid") from error
    with archive:
        members = archive.getmembers()
        if not members or len(members) > MAX_ARCHIVE_FILES:
            raise ValueError("Kodi runtime source archive file count differs")
        for member in members:
            path = PurePosixPath(member.name)
            if path.is_absolute() or not path.parts or ".." in path.parts:
                raise ValueError("Kodi runtime source archive path is unsafe")
            normalized = path.as_posix().rstrip("/")
            folded_name = normalized.casefold()
            if normalized in names or folded_name in folded:
                raise ValueError("Kodi runtime source archive has duplicate paths")
            names.add(normalized)
            folded.add(folded_name)
            if member.size < 0:
                raise ValueError("Kodi runtime source archive size is invalid")
            total += member.size
            if total > MAX_ARCHIVE_UNCOMPRESSED:
                raise ValueError("Kodi runtime source archive expands too far")
            relative = PurePosixPath(*path.parts[1:])
            keep = relative.as_posix() in {
                "version.txt",
                "xbmc/addons/kodi-dev-kit/include/kodi/versions.h",
                "xbmc/interfaces/json-rpc/schema/version.txt",
            } or (
                len(relative.parts) == 3
                and relative.parts[0] == "addons"
                and relative.name in {"addon.xml", "addon.xml.in"}
            )
            if not keep:
                continue
            if not member.isfile() or member.issym() or member.islnk():
                raise ValueError("Kodi runtime selected source is not regular")
            if member.size > MAX_SOURCE_FILE:
                raise ValueError("Kodi runtime selected source exceeds size policy")
            handle = archive.extractfile(member)
            if handle is None:
                raise ValueError("Kodi runtime selected source cannot be read")
            value = handle.read(MAX_SOURCE_FILE + 1)
            if len(value) != member.size or len(value) > MAX_SOURCE_FILE:
                raise ValueError("Kodi runtime selected source size differs")
            key = relative.as_posix()
            if key in selected:
                raise ValueError("Kodi runtime selected source is duplicated")
            selected[key] = value
            if len(selected) > MAX_SELECTED_FILES or sum(
                len(item) for item in selected.values()
            ) > MAX_SELECTED_BYTES:
                raise ValueError("Kodi runtime selected sources exceed policy")
    required = {
        "version.txt",
        "xbmc/addons/kodi-dev-kit/include/kodi/versions.h",
        "xbmc/interfaces/json-rpc/schema/version.txt",
    }
    if not required.issubset(selected):
        raise ValueError("Kodi runtime source metadata files are missing")
    return selected


def _variables(selected):
    values = {}
    try:
        version_lines = selected["version.txt"].decode("utf-8").splitlines()
    except UnicodeDecodeError as error:
        raise ValueError("Kodi version.txt is invalid") from error
    for line in version_lines:
        key, separator, value = line.partition(" ")
        if separator and re.fullmatch(r"[A-Z][A-Z0-9_]*", key) and value:
            values[key] = value.strip()
            values["APP_" + key] = value.strip()
    for key, value in DEFINE.findall(
        selected["xbmc/addons/kodi-dev-kit/include/kodi/versions.h"]
    ):
        values[key.decode("ascii")] = value.decode("ascii")
    try:
        json_key, json_version = selected[
            "xbmc/interfaces/json-rpc/schema/version.txt"
        ].decode("ascii").strip().split()
    except (UnicodeDecodeError, ValueError) as error:
        raise ValueError("Kodi JSON-RPC version source is invalid") from error
    if json_key != "JSONRPC_VERSION":
        raise ValueError("Kodi JSON-RPC version source differs")
    values[json_key] = json_version
    for key, value in values.items():
        if (
            not re.fullmatch(r"[A-Z][A-Z0-9_]*", key)
            or not isinstance(value, str)
            or not value
            or len(value) > 256
            or any(ord(character) < 0x20 or ord(character) > 0x7E for character in value)
            or any(character in value for character in '<>&"\'')
        ):
            raise ValueError("Kodi source replacement variable is invalid")
    return values


def _materialize(payload, variables):
    def replace(match):
        key = match.group(1).decode("ascii")
        if key not in variables:
            raise ValueError("Kodi source contains an unknown replacement variable")
        return variables[key].encode("ascii")

    result = VARIABLE.sub(replace, payload)
    if VARIABLE.search(result):
        raise ValueError("Kodi source replacement variable remains unresolved")
    return result


def _capabilities(selected):
    variables = _variables(selected)
    capabilities = {}
    materialized_hashes = {}
    addon_directories = {}
    for path, payload in sorted(selected.items()):
        parts = PurePosixPath(path).parts
        if len(parts) != 3 or parts[0] != "addons" or parts[2] not in {
            "addon.xml",
            "addon.xml.in",
        }:
            continue
        directory = parts[1]
        previous = addon_directories.get(directory)
        if previous is not None:
            if previous.endswith("addon.xml"):
                continue
            if path.endswith("addon.xml"):
                addon_directories[directory] = path
                continue
            raise ValueError("Kodi source add-on manifest is ambiguous")
        addon_directories[directory] = path
    for directory, path in sorted(addon_directories.items()):
        payload = selected[path]
        materialized = _materialize(payload, variables) if path.endswith(".in") else payload
        root = _safe_xml(materialized)
        addon_id = root.attrib.get("id", "")
        if addon_id != directory:
            raise ValueError("Kodi source add-on directory and id differ")
        backwards = root.find("./backwards-compatibility")
        if backwards is None:
            continue
        minimum = backwards.attrib.get("abi", "") or "0.0.0"
        provided = root.attrib.get("version", "")
        try:
            if KodiVersion(minimum) > KodiVersion(provided):
                raise ValueError("Kodi source capability interval is empty")
        except ValueError as error:
            raise ValueError("Kodi source capability version is invalid") from error
        digest = hashlib.sha256(materialized).hexdigest()
        if addon_id in capabilities:
            raise ValueError("Kodi source capability is duplicated")
        capabilities[addon_id] = {
            "min_compatible": minimum,
            "provided": provided,
            "addon_xml_sha256": digest,
        }
        materialized_hashes[path] = digest
    if len(capabilities) < 20:
        raise ValueError("Kodi source capability set is unexpectedly incomplete")
    return dict(sorted(capabilities.items())), materialized_hashes, variables


def _release_version(variables):
    major = variables.get("VERSION_MAJOR")
    minor = variables.get("VERSION_MINOR")
    if not major or not minor or not major.isdigit() or not minor.isdigit():
        raise ValueError("Kodi source version is invalid")
    return "%s.%s" % (int(major), int(minor))


def _entry(release, commit, archive):
    selected = _selected_archive_files(archive)
    capabilities, _materialized_hashes, variables = _capabilities(selected)
    version = _release_version(variables)
    if not release["tag_name"].startswith(version):
        raise ValueError("Kodi release tag and source version differ")
    source_files = {
        path: hashlib.sha256(payload).hexdigest()
        for path, payload in sorted(selected.items())
    }
    entry = {
        "version": version,
        "tag": release["tag_name"],
        "commit": commit,
        "prerelease": False,
        "source_archive_sha256": hashlib.sha256(archive).hexdigest(),
        "source_files_sha256": hashlib.sha256(
            canonical_json(source_files)
        ).hexdigest(),
        "capabilities": capabilities,
    }
    entry["entry_sha256"] = release_digest(entry)
    return entry


def discover(catalog, *, tag=None, token=None, fetch=_request):
    release = _release_metadata(tag=tag, token=token)
    commit = _resolve_tag(release["tag_name"], token=token)
    tag_version = re.match(r"^(\d+)\.(\d+)", release["tag_name"])
    if tag_version is None:
        raise ValueError("Kodi stable release tag has no normalized version")
    version = "%s.%s" % tag_version.groups()
    existing = catalog["releases"].get(version)
    if existing is not None:
        if existing["tag"] == release["tag_name"] and existing["commit"] == commit:
            return {
                "action": "NO_CHANGE",
                "version": version,
                "tag": release["tag_name"],
                "commit": commit,
                "catalog": catalog,
                "candidate_id": catalog_digest(catalog),
            }
        return {
            "action": "REJECTED",
            "reason": "TAG_DRIFT",
            "version": version,
            "tag": release["tag_name"],
            "commit": commit,
            "catalog": catalog,
            "candidate_id": catalog_digest(catalog),
        }
    archive = fetch(
        "%s/%s/tar.gz/%s" % (CODELOAD_ORIGIN, REPOSITORY, commit),
        token=token,
        accept="application/octet-stream",
    )
    entry = _entry(release, commit, archive)
    if entry["version"] != version:
        raise ValueError("Kodi release normalized version differs")
    candidate = {
        **catalog,
        "releases": {**catalog["releases"], version: entry},
    }
    validate_catalog(candidate)
    return {
        "action": "REVIEW",
        "version": version,
        "tag": release["tag_name"],
        "commit": commit,
        "catalog": candidate,
        "candidate_id": catalog_digest(candidate),
    }


def candidate_document(result, base_catalog, base_sha):
    return {
        "schema": 1,
        "action": result["action"],
        "base_sha": base_sha,
        "base_catalog_sha256": catalog_digest(base_catalog),
        "candidate_id": result["candidate_id"],
        "version": result["version"],
        "tag": result["tag"],
        "commit": result["commit"],
        "catalog": result["catalog"],
    }


def verify_candidate(document, current_catalog, base_sha):
    expected = {
        "schema",
        "action",
        "base_sha",
        "base_catalog_sha256",
        "candidate_id",
        "version",
        "tag",
        "commit",
        "catalog",
    }
    if not isinstance(document, dict) or set(document) != expected:
        raise ValueError("Kodi runtime candidate fields differ")
    if (
        document["schema"] != 1
        or document["action"] not in {"NO_CHANGE", "REVIEW"}
        or document["base_sha"] != base_sha
        or document["base_catalog_sha256"] != catalog_digest(current_catalog)
    ):
        raise ValueError("Kodi runtime candidate base differs")
    candidate = validate_catalog(document["catalog"])
    if document["candidate_id"] != catalog_digest(candidate):
        raise ValueError("Kodi runtime candidate digest differs")
    current_keys = set(current_catalog["releases"])
    candidate_keys = set(candidate["releases"])
    if not current_keys.issubset(candidate_keys):
        raise ValueError("Kodi runtime candidate removed a release")
    for key in current_keys:
        if current_catalog["releases"][key] != candidate["releases"][key]:
            raise ValueError("Kodi runtime candidate changed an existing release")
    added = candidate_keys - current_keys
    if document["action"] == "NO_CHANGE":
        if added or candidate != current_catalog:
            raise ValueError("Kodi runtime no-op candidate contains changes")
    elif added != {document["version"]}:
        raise ValueError("Kodi runtime candidate scope differs")
    entry = candidate["releases"][document["version"]]
    if entry["tag"] != document["tag"] or entry["commit"] != document["commit"]:
        raise ValueError("Kodi runtime candidate identity differs")
    return candidate


def _write_json(path, document):
    target = Path(path)
    target.parent.mkdir(parents=True, exist_ok=True)
    payload = (
        json.dumps(document, indent=2, sort_keys=True) + "\n"
    ).encode("utf-8")
    descriptor, temporary_name = tempfile.mkstemp(
        prefix=".%s." % target.name,
        suffix=".tmp",
        dir=str(target.parent),
    )
    temporary = Path(temporary_name)
    try:
        with os.fdopen(descriptor, "wb") as handle:
            handle.write(payload)
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(temporary, target)
        directory = os.open(target.parent, os.O_RDONLY)
        try:
            os.fsync(directory)
        finally:
            os.close(directory)
    except BaseException:
        temporary.unlink(missing_ok=True)
        raise


def main(argv=None):
    parser = argparse.ArgumentParser()
    commands = parser.add_subparsers(dest="command", required=True)

    discover_parser = commands.add_parser("discover")
    discover_parser.add_argument(
        "--catalog", default="manifests/kodi-runtime-capabilities.json"
    )
    discover_parser.add_argument("--candidate", required=True)
    discover_parser.add_argument("--report", required=True)
    discover_parser.add_argument("--release-tag")
    discover_parser.add_argument("--base-sha", default="local")

    verify_parser = commands.add_parser("verify")
    verify_parser.add_argument(
        "--catalog", default="manifests/kodi-runtime-capabilities.json"
    )
    verify_parser.add_argument("--candidate", required=True)
    verify_parser.add_argument("--base-sha", required=True)

    apply_parser = commands.add_parser("apply")
    apply_parser.add_argument(
        "--catalog", default="manifests/kodi-runtime-capabilities.json"
    )
    apply_parser.add_argument("--candidate", required=True)
    apply_parser.add_argument("--base-sha", required=True)

    args = parser.parse_args(argv)
    catalog = _read_catalog(args.catalog)
    if args.command == "discover":
        result = discover(
            catalog,
            tag=args.release_tag,
            token=os.environ.get("GITHUB_TOKEN"),
        )
        if result["action"] == "REJECTED":
            report = {key: value for key, value in result.items() if key != "catalog"}
            _write_json(args.report, report)
            raise SystemExit(2)
        candidate = candidate_document(result, catalog, args.base_sha)
        _write_json(args.candidate, candidate)
        _write_json(
            args.report,
            {key: value for key, value in result.items() if key != "catalog"},
        )
        print(result["action"])
        return 0
    document = json.loads(Path(args.candidate).read_text(encoding="utf-8"))
    verified = verify_candidate(document, catalog, args.base_sha)
    if args.command == "apply":
        if document["action"] != "REVIEW":
            raise ValueError("Kodi runtime apply requires a review candidate")
        _write_json(args.catalog, verified)
    print(document["action"])
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
