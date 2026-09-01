import hashlib
from pathlib import Path
from zipfile import ZipFile

import pytest

from tools.kodi_addon_runtime_compatibility import release_digest
from tools.kodi_runtime_attestation import (
    assert_apk_attested,
    assert_directory_attested,
    attest_capabilities,
    capabilities_from_apk,
)


def manifest(addon_id, minimum="1.0.0", provided="2.0.0"):
    return (
        '<addon id="%s" version="%s">'
        '<backwards-compatibility abi="%s"/>'
        "</addon>"
    ) % (addon_id, provided, minimum)


def fixture(tmp_path):
    payloads = {
        "xbmc.fixture%02d" % index: manifest("xbmc.fixture%02d" % index).encode()
        for index in range(20)
    }
    capabilities = {
        addon_id: {
            "min_compatible": "1.0.0",
            "provided": "2.0.0",
            "addon_xml_sha256": hashlib.sha256(payload).hexdigest(),
        }
        for addon_id, payload in payloads.items()
    }
    entry = {
        "version": "22.0",
        "tag": "22.0-Fixture",
        "commit": "f" * 40,
        "prerelease": False,
        "source_archive_sha256": "e" * 64,
        "source_files_sha256": "d" * 64,
        "capabilities": capabilities,
    }
    entry["entry_sha256"] = release_digest(entry)
    catalog = {
        "schema": 1,
        "source_repository": "xbmc/xbmc",
        "releases": {"22.0": entry},
    }
    addon_root = tmp_path / "addons"
    apk = tmp_path / "kodi.apk"
    with ZipFile(apk, "w") as archive:
        for addon_id, payload in payloads.items():
            archive.writestr("assets/addons/%s/addon.xml" % addon_id, payload)
            directory = addon_root / addon_id
            directory.mkdir(parents=True)
            (directory / "addon.xml").write_bytes(payload)
    return catalog, apk, addon_root


def test_apk_and_directory_attestation_pass(tmp_path):
    catalog, apk, addon_root = fixture(tmp_path)
    assert assert_apk_attested(apk, "22.0.1", catalog)["status"] == "ATTESTATION_PASS"
    assert (
        assert_directory_attested(addon_root, "22.0", catalog)["status"]
        == "ATTESTATION_PASS"
    )


def test_distribution_mismatch_is_explicit(tmp_path):
    catalog, apk, _addon_root = fixture(tmp_path)
    capabilities = capabilities_from_apk(apk)
    capabilities["xbmc.fixture00"]["provided"] = "3.0.0"
    report = attest_capabilities(capabilities, "22.0", catalog)
    assert report["status"] == "DISTRIBUTION_MISMATCH"
    assert report["different"] == ["xbmc.fixture00"]


def test_additional_distribution_capability_is_reported_but_not_trusted(tmp_path):
    catalog, apk, _addon_root = fixture(tmp_path)
    capabilities = capabilities_from_apk(apk)
    capabilities["game.libretro"] = {
        "min_compatible": "1.0.0",
        "provided": "2.0.0",
        "addon_xml_sha256": "a" * 64,
    }
    report = attest_capabilities(capabilities, "22.0", catalog)
    assert report["status"] == "ATTESTATION_PASS"
    assert report["unexpected"] == ["game.libretro"]


def test_unknown_runtime_and_incomplete_package_fail_closed(tmp_path):
    catalog, apk, _addon_root = fixture(tmp_path)
    with pytest.raises(RuntimeError, match="RUNTIME_CATALOG_MISS"):
        attest_capabilities(capabilities_from_apk(apk), "23.0", catalog)
    empty = tmp_path / "empty.apk"
    with ZipFile(empty, "w") as archive:
        archive.writestr(
            "assets/addons/xbmc.python/addon.xml",
            manifest("xbmc.python").encode(),
        )
    with pytest.raises(ValueError, match="incomplete"):
        capabilities_from_apk(empty)
