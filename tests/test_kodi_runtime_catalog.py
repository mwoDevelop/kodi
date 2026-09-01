import io
import json
import tarfile
from pathlib import Path

import pytest

from tools import kodi_runtime_catalog as subject
from tools.kodi_addon_runtime_compatibility import (
    catalog_digest,
    load_catalog,
)

ROOT = Path(__file__).resolve().parents[1]
CATALOG_PATH = ROOT / "manifests/kodi-runtime-capabilities.json"


def source_archive(*, unsafe_path=None, unknown_variable=False):
    payload = io.BytesIO()
    with tarfile.open(fileobj=payload, mode="w:gz") as archive:
        files = {
            "source/version.txt": (
                b"VERSION_MAJOR 22\nVERSION_MINOR 0\nADDON_API 22.0.0\n"
            ),
            "source/xbmc/interfaces/json-rpc/schema/version.txt": (
                b"JSONRPC_VERSION 14.0.0\n"
            ),
            "source/xbmc/addons/kodi-dev-kit/include/kodi/versions.h": (
                b'#define ADDON_TEST_VERSION "2.0.0"\n'
            ),
        }
        for index in range(20):
            addon_id = "xbmc.fixture%02d" % index
            version = (
                "@UNKNOWN_VERSION@"
                if unknown_variable and index == 0
                else "@ADDON_TEST_VERSION@"
            )
            files[
                "source/addons/%s/addon.xml.in" % addon_id
            ] = (
                '<addon id="%s" version="%s">'
                '<backwards-compatibility abi="1.0.0"/>'
                "</addon>"
            ) % (addon_id, version)
        if unsafe_path:
            files[unsafe_path] = b"unsafe"
        for name, value in files.items():
            value = value.encode("utf-8") if isinstance(value, str) else value
            member = tarfile.TarInfo(name)
            member.size = len(value)
            archive.addfile(member, io.BytesIO(value))
    return payload.getvalue()


def test_official_catalog_is_valid_and_complete():
    catalog = load_catalog(CATALOG_PATH)
    assert set(catalog["releases"]) == {"21.2", "21.3"}
    assert {
        len(entry["capabilities"])
        for entry in catalog["releases"].values()
    } == {26}


def test_source_archive_materializes_allowlisted_variables():
    entry = subject._entry(
        {"tag_name": "22.0-Fixture"},
        "f" * 40,
        source_archive(),
    )
    assert entry["version"] == "22.0"
    assert len(entry["capabilities"]) == 20
    assert entry["capabilities"]["xbmc.fixture00"] == {
        "min_compatible": "1.0.0",
        "provided": "2.0.0",
        "addon_xml_sha256": entry["capabilities"]["xbmc.fixture00"][
            "addon_xml_sha256"
        ],
    }


def test_source_archive_rejects_unknown_variables_and_unsafe_paths():
    with pytest.raises(ValueError, match="unknown replacement"):
        subject._entry(
            {"tag_name": "22.0-Fixture"},
            "f" * 40,
            source_archive(unknown_variable=True),
        )
    with pytest.raises(ValueError, match="unsafe"):
        subject._entry(
            {"tag_name": "22.0-Fixture"},
            "f" * 40,
            source_archive(unsafe_path="source/../escape"),
        )


def test_discover_metadata_noop_does_not_download(monkeypatch):
    catalog = load_catalog(CATALOG_PATH)
    entry = catalog["releases"]["21.3"]
    monkeypatch.setattr(
        subject,
        "_release_metadata",
        lambda tag=None, token=None: {
            "tag_name": entry["tag"],
            "draft": False,
            "prerelease": False,
        },
    )
    monkeypatch.setattr(
        subject, "_resolve_tag", lambda tag, token=None: entry["commit"]
    )

    def forbidden_fetch(*_args, **_kwargs):
        raise AssertionError("archive fetched during metadata no-op")

    result = subject.discover(catalog, fetch=forbidden_fetch)
    assert result["action"] == "NO_CHANGE"
    assert result["candidate_id"] == catalog_digest(catalog)


def test_candidate_is_append_only_and_bound_to_base():
    catalog = load_catalog(CATALOG_PATH)
    result = {
        "action": "REVIEW",
        "version": "22.0",
        "tag": "22.0-Fixture",
        "commit": "f" * 40,
        "candidate_id": "0" * 64,
        "catalog": json.loads(json.dumps(catalog)),
    }
    entry = json.loads(json.dumps(catalog["releases"]["21.3"]))
    entry.update(
        {
            "version": "22.0",
            "tag": result["tag"],
            "commit": result["commit"],
            "source_archive_sha256": "e" * 64,
            "source_files_sha256": "d" * 64,
        }
    )
    from tools.kodi_addon_runtime_compatibility import release_digest

    entry["entry_sha256"] = release_digest(entry)
    result["catalog"]["releases"]["22.0"] = entry
    result["candidate_id"] = catalog_digest(result["catalog"])
    candidate = subject.candidate_document(result, catalog, "base")
    subject.verify_candidate(candidate, catalog, "base")

    changed = json.loads(json.dumps(candidate))
    changed["catalog"]["releases"]["21.3"]["tag"] = "moved"
    with pytest.raises(ValueError):
        subject.verify_candidate(changed, catalog, "base")
    with pytest.raises(ValueError, match="base differs"):
        subject.verify_candidate(candidate, catalog, "other")
