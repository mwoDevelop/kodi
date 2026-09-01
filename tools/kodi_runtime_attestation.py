#!/usr/bin/env python3
"""Attest packaged Kodi system capabilities against the trusted catalog."""

from __future__ import annotations

import argparse
import hashlib
import json
import posixpath
import re
import stat
import tempfile
from pathlib import Path, PurePosixPath
from zipfile import BadZipFile, ZipFile

from tools.kodi_addon_runtime_compatibility import (
    _safe_xml,
    canonical_json,
    catalog_digest,
    load_catalog,
    runtime_release,
    sha256_file,
)

APK_MANIFEST = re.compile(
    r"^assets/addons/([A-Za-z0-9][A-Za-z0-9._-]{0,127})/addon\.xml$"
)
REMOTE_APK = re.compile(r"^/[A-Za-z0-9._/+@=~-]+/base\.apk$")
SHA256 = re.compile(r"^[0-9a-f]{64}$")
MAX_MANIFESTS = 128
MAX_MANIFEST_SIZE = 2 * 1024 * 1024


def _capability(addon_id, payload):
    root = _safe_xml(payload)
    backwards = root.find("./backwards-compatibility")
    if backwards is None:
        return None
    if root.attrib.get("id") != addon_id:
        raise ValueError("packaged Kodi capability id differs from its path")
    minimum = backwards.attrib.get("abi", "") or "0.0.0"
    provided = root.attrib.get("version", "")
    if not provided:
        raise ValueError("packaged Kodi capability version is missing")
    return {
        "min_compatible": minimum,
        "provided": provided,
        "addon_xml_sha256": hashlib.sha256(payload).hexdigest(),
    }


def capabilities_from_apk(path):
    result = {}
    try:
        with ZipFile(path) as archive:
            for member in archive.infolist():
                match = APK_MANIFEST.fullmatch(member.filename)
                if match is None:
                    continue
                if member.is_dir() or member.file_size > MAX_MANIFEST_SIZE:
                    raise ValueError("packaged Kodi capability XML is invalid")
                addon_id = match.group(1)
                if addon_id in result:
                    raise ValueError("packaged Kodi capability is duplicated")
                capability = _capability(addon_id, archive.read(member))
                if capability is not None:
                    result[addon_id] = capability
                if len(result) > MAX_MANIFESTS:
                    raise ValueError("packaged Kodi capability count exceeds policy")
    except BadZipFile as error:
        raise ValueError("Kodi APK is not a valid ZIP archive") from error
    if len(result) < 20:
        raise ValueError("packaged Kodi capability set is incomplete")
    return dict(sorted(result.items()))


def capabilities_from_directory(path):
    root = Path(path)
    if root.is_symlink() or not root.is_dir():
        raise ValueError("Kodi system add-on root is invalid")
    result = {}
    for addon in sorted(root.iterdir()):
        if addon.is_symlink() or not addon.is_dir():
            continue
        manifest = addon / "addon.xml"
        if not manifest.exists():
            continue
        if manifest.is_symlink() or not manifest.is_file():
            raise ValueError("Kodi system capability manifest is unsafe")
        if manifest.stat().st_size > MAX_MANIFEST_SIZE:
            raise ValueError("Kodi system capability XML exceeds policy")
        capability = _capability(addon.name, manifest.read_bytes())
        if capability is not None:
            result[addon.name] = capability
        if len(result) > MAX_MANIFESTS:
            raise ValueError("Kodi system capability count exceeds policy")
    if len(result) < 20:
        raise ValueError("Kodi system capability set is incomplete")
    return dict(sorted(result.items()))


def capabilities_from_sftp(sftp, root):
    if not isinstance(root, str) or not root.startswith("/") or ".." in PurePosixPath(root).parts:
        raise ValueError("remote Kodi system add-on root is unsafe")
    result = {}
    for addon in sftp.listdir_attr(root):
        if (
            not re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9._-]{0,127}", addon.filename)
            or stat.S_ISLNK(addon.st_mode)
            or not stat.S_ISDIR(addon.st_mode)
        ):
            continue
        manifest = posixpath.join(root, addon.filename, "addon.xml")
        try:
            metadata = sftp.lstat(manifest)
        except OSError:
            continue
        if (
            stat.S_ISLNK(metadata.st_mode)
            or not stat.S_ISREG(metadata.st_mode)
            or metadata.st_size > MAX_MANIFEST_SIZE
        ):
            raise ValueError("remote Kodi system capability manifest is unsafe")
        with sftp.open(manifest, "rb") as handle:
            payload = handle.read(MAX_MANIFEST_SIZE + 1)
        if len(payload) != metadata.st_size:
            raise ValueError("remote Kodi system capability changed during read")
        capability = _capability(addon.filename, payload)
        if capability is not None:
            result[addon.filename] = capability
        if len(result) > MAX_MANIFESTS:
            raise ValueError("remote Kodi system capability count exceeds policy")
    if len(result) < 20:
        raise ValueError("remote Kodi system capability set is incomplete")
    return dict(sorted(result.items()))


def attest_capabilities(capabilities, kodi_version, catalog):
    release = runtime_release(kodi_version)
    if release is None or release not in catalog["releases"]:
        raise RuntimeError("Kodi runtime attestation failed: RUNTIME_CATALOG_MISS")
    expected = catalog["releases"][release]["capabilities"]
    missing = sorted(set(expected) - set(capabilities))
    unexpected = sorted(set(capabilities) - set(expected))
    different = sorted(
        addon_id
        for addon_id in set(expected).intersection(capabilities)
        if capabilities[addon_id] != expected[addon_id]
    )
    report = {
        "schema": 1,
        "status": (
            "ATTESTATION_PASS"
            # Official packages may add platform-specific capabilities (for
            # example game.libretro in Flatpak). They cannot weaken or replace
            # the catalogued core set, and the evaluator never consumes an
            # unqualified extension merely because it was observed here.
            if not missing and not different
            else "DISTRIBUTION_MISMATCH"
        ),
        "catalog_release": release,
        "catalog_sha256": catalog_digest(catalog),
        "capabilities_sha256": hashlib.sha256(
            canonical_json(capabilities)
        ).hexdigest(),
        "capability_count": len(capabilities),
        "missing": missing,
        "unexpected": unexpected,
        "different": different,
    }
    return report


def assert_apk_attested(path, kodi_version, catalog):
    report = attest_capabilities(
        capabilities_from_apk(path), kodi_version, catalog
    )
    if report["status"] != "ATTESTATION_PASS":
        raise RuntimeError(
            "Kodi runtime attestation failed: DISTRIBUTION_MISMATCH"
        )
    return report


def assert_directory_attested(path, kodi_version, catalog):
    report = attest_capabilities(
        capabilities_from_directory(path), kodi_version, catalog
    )
    if report["status"] != "ATTESTATION_PASS":
        raise RuntimeError(
            "Kodi runtime attestation failed: DISTRIBUTION_MISMATCH"
        )
    return report


def attest_flatpak_runtime(
    transport,
    connect_sftp,
    app_id,
    kodi_version,
    catalog,
):
    from tools.kodi_transports import ReadOnlyCommand

    locations = []
    for scope in ("user", "system"):
        result = transport.execute_read_only(
            ReadOnlyCommand(
                ("flatpak", "info", "--%s" % scope, "--show-location", app_id),
                allowed_returncodes=(0, 1),
            )
        )
        if result.returncode == 0:
            location = result.stdout.strip()
            if (
                not location.startswith("/")
                or "\n" in location
                or "\r" in location
                or ".." in PurePosixPath(location).parts
            ):
                raise RuntimeError("Flatpak Kodi installation location is invalid")
            locations.append(location)
    if len(locations) != 1:
        raise RuntimeError("Flatpak Kodi installation location is ambiguous")
    addon_root = posixpath.join(
        locations[0], "files", "share", "kodi", "addons"
    )
    client, sftp = connect_sftp(transport)
    try:
        capabilities = capabilities_from_sftp(sftp, addon_root)
    finally:
        sftp.close()
        client.close()
    report = attest_capabilities(capabilities, kodi_version, catalog)
    if report["status"] != "ATTESTATION_PASS":
        raise RuntimeError(
            "Kodi runtime attestation failed: DISTRIBUTION_MISMATCH"
        )
    return report


def _single_base_apk(adb_command, adb, port, serial):
    result = adb_command(
        adb,
        port,
        serial,
        "shell",
        "pm path org.xbmc.kodi",
        text=True,
        timeout=30,
    )
    paths = []
    for line in (result.stdout or "").splitlines():
        prefix, separator, value = line.strip().partition(":")
        if prefix == "package" and separator and value.endswith("/base.apk"):
            paths.append(value)
    if len(paths) != 1 or not REMOTE_APK.fullmatch(paths[0]):
        raise RuntimeError("Kodi base APK identity is ambiguous")
    return paths[0]


def attest_android_runtime(
    adb_command,
    adb,
    port,
    serial,
    kodi_version,
    catalog,
    cache_root=None,
):
    remote = _single_base_apk(adb_command, adb, port, serial)
    checksum = adb_command(
        adb,
        port,
        serial,
        "shell",
        "sha256sum '%s'" % remote,
        text=True,
        timeout=60,
    )
    apk_sha256 = (checksum.stdout or "").strip().split(None, 1)[0]
    if not SHA256.fullmatch(apk_sha256):
        raise RuntimeError("Kodi base APK digest is invalid")
    release = runtime_release(kodi_version)
    catalog_sha256 = catalog_digest(catalog)
    cache = None
    if cache_root is not None:
        cache_root = Path(cache_root)
        cache_root.mkdir(parents=True, exist_ok=True, mode=0o700)
        cache = cache_root / (apk_sha256 + ".json")
        if cache.exists() and cache.is_file() and not cache.is_symlink():
            document = json.loads(cache.read_text(encoding="utf-8"))
            if (
                document.get("status") == "ATTESTATION_PASS"
                and document.get("catalog_release") == release
                and document.get("catalog_sha256") == catalog_sha256
                and document.get("apk_sha256") == apk_sha256
            ):
                return document
    with tempfile.TemporaryDirectory(prefix="kodi-runtime-apk-") as temporary:
        local = Path(temporary) / "base.apk"
        adb_command(
            adb,
            port,
            serial,
            "pull",
            remote,
            str(local),
            timeout=180,
        )
        if sha256_file(local) != apk_sha256:
            raise RuntimeError("pulled Kodi base APK digest differs")
        report = {
            **assert_apk_attested(local, kodi_version, catalog),
            "apk_sha256": apk_sha256,
        }
    if cache is not None:
        temporary = cache.with_suffix(".tmp")
        temporary.write_text(
            json.dumps(report, indent=2, sort_keys=True) + "\n",
            encoding="utf-8",
        )
        temporary.replace(cache)
    return report


def main(argv=None):
    parser = argparse.ArgumentParser()
    parser.add_argument("--catalog", default="manifests/kodi-runtime-capabilities.json")
    parser.add_argument("--kodi-version", required=True)
    source = parser.add_mutually_exclusive_group(required=True)
    source.add_argument("--apk")
    source.add_argument("--addon-root")
    args = parser.parse_args(argv)
    catalog = load_catalog(args.catalog)
    report = (
        assert_apk_attested(args.apk, args.kodi_version, catalog)
        if args.apk
        else assert_directory_attested(args.addon_root, args.kodi_version, catalog)
    )
    print(json.dumps(report, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
