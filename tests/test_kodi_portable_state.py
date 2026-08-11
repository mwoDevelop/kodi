import json
import zipfile
from pathlib import Path

import pytest

from tools.kodi_portable_state import (
    ARTWORK_URI,
    BACKUP_NAME,
    JOURNAL_NAME,
    STATE_NAME,
    apply_bundle,
    build_bundle,
    canonical_json,
    digest,
    profile_summary,
    recover,
    validate_bundle,
)
from tools.kodi_portable_state_rollout import _current_bundle


JPEG = b"\xff\xd8\xff\xe0" + b"portable-artwork"


def write_profile(root, names=("Bluey",)):
    root.mkdir(parents=True, exist_ok=True)
    image_hash = digest(JPEG)
    artwork = root / "favourite-artwork"
    artwork.mkdir()
    (artwork / (image_hash + ".jpg")).write_bytes(JPEG)
    items = []
    for name in names:
        items.append(
            (
                '    <favourite name="%s" thumb="%s%s.jpg">'
                "ActivateWindow(10025,&quot;plugin://"
                "plugin.video.watchnixtoons2.mwodevelop/"
                "?action=actionEpisodesMenu&quot;,return)</favourite>"
            )
            % (name, ARTWORK_URI, image_hash)
        )
    (root / "favourites.xml").write_text(
        "<favourites>\n%s\n</favourites>\n" % "\n".join(items),
        encoding="utf-8",
    )
    return image_hash


def test_bundle_is_deterministic_exact_and_idempotent(tmp_path):
    source = tmp_path / "source"
    image_hash = write_profile(source, ("Bluey", "Stitch!"))
    first = tmp_path / "first.zip"
    second = tmp_path / "second.zip"

    first_manifest = build_bundle(source, first)
    second_manifest = build_bundle(source, second)

    assert first.read_bytes() == second.read_bytes()
    assert first_manifest == second_manifest == validate_bundle(first)
    with zipfile.ZipFile(first) as archive:
        assert set(archive.namelist()) == {
            "manifest.json",
            "payload/favourites.xml",
            "payload/favourite-artwork/%s.jpg" % image_hash,
        }

    target = tmp_path / "target"
    write_profile(target, ("Old",))
    result = apply_bundle(target, first)
    repeated = apply_bundle(target, first)

    assert result["status"] == "APPLIED"
    assert repeated["status"] == "NO_CHANGE"
    assert profile_summary(target)["favourites"] == 2
    assert profile_summary(target)["portable"] == 2
    assert (target / STATE_NAME).is_file()
    assert not (target / JOURNAL_NAME).exists()
    assert not (target / BACKUP_NAME).exists()
    parsed = (target / "favourites.xml").read_text(encoding="utf-8")
    (target / "favourites.xml").write_text(
        parsed.replace("<favourites>\n", "<favourites>").replace(
            "\n</favourites>", "</favourites>"
        ),
        encoding="utf-8",
    )
    assert apply_bundle(target, first)["status"] == "NO_CHANGE"


def test_bundle_rejects_missing_or_extra_artwork(tmp_path):
    source = tmp_path / "source"
    write_profile(source)
    bundle = tmp_path / "bundle.zip"
    build_bundle(source, bundle)

    with zipfile.ZipFile(bundle, "a") as archive:
        archive.writestr("payload/favourite-artwork/unmanaged.jpg", b"bad")

    with pytest.raises(ValueError, match="inventory mismatch"):
        validate_bundle(bundle)


def test_bundle_preserves_refresh_manifest_and_enforces_exact_directory(
    tmp_path,
):
    source = tmp_path / "source"
    image_hash = write_profile(source)
    (source / "favourite-artwork/manifest.json").write_text(
        json.dumps(
            {
                "schema": 1,
                "entries": {
                    "favourite": {
                        "file": image_hash + ".jpg",
                        "sha256": image_hash,
                        "source_url": (
                            "https://images.wcostream.com/catimg/1.jpg"
                        ),
                    }
                },
            }
        ),
        encoding="utf-8",
    )
    bundle = tmp_path / "bundle.zip"

    build_bundle(source, bundle)
    target = tmp_path / "target"
    write_profile(target)
    (target / "favourite-artwork/stale.txt").write_text(
        "stale", encoding="utf-8"
    )

    result = apply_bundle(target, bundle)

    assert result["status"] == "APPLIED"
    assert {
        path.name for path in (target / "favourite-artwork").iterdir()
    } == {image_hash + ".jpg", "manifest.json"}
    (target / "favourite-artwork/manifest.json").write_text(
        json.dumps({"schema": 1, "entries": {}, "device_local": True}),
        encoding="utf-8",
    )
    assert apply_bundle(target, bundle)["status"] == "NO_CHANGE"


def test_apply_failure_recovers_previous_profile(tmp_path, monkeypatch):
    source = tmp_path / "source"
    write_profile(source, ("New",))
    bundle = tmp_path / "bundle.zip"
    build_bundle(source, bundle)
    target = tmp_path / "target"
    write_profile(target, ("Old",))
    original = (target / "favourites.xml").read_bytes()

    real_replace = __import__("os").replace

    def failing_replace(source_path, target_path):
        if str(target_path).endswith("/favourites.xml") and str(
            source_path
        ).endswith("/.mwodevelop-portable-state-stage/favourites.xml"):
            raise RuntimeError("injected replacement failure")
        return real_replace(source_path, target_path)

    monkeypatch.setattr("tools.kodi_portable_state.os.replace", failing_replace)

    with pytest.raises(RuntimeError, match="injected"):
        apply_bundle(target, bundle)

    assert (target / "favourites.xml").read_bytes() == original
    assert not (target / JOURNAL_NAME).exists()


def test_recover_rejects_untrusted_journal(tmp_path):
    (tmp_path / JOURNAL_NAME).write_bytes(
        canonical_json({"schema": 99}) + b"\n"
    )

    with pytest.raises(ValueError, match="journal"):
        recover(tmp_path)


def test_current_bundle_pointer_is_content_addressed_and_path_safe(tmp_path):
    source = tmp_path / "source"
    write_profile(source)
    private = tmp_path / ".kodi-private/portable-state"
    private.mkdir(parents=True)
    bundle = private / "bundle.zip"
    manifest = build_bundle(source, bundle)
    pointer = private / "current.json"
    pointer.write_text(
        json.dumps(
            {
                "schema": 1,
                "bundle_id": manifest["bundle_id"],
                "filename": bundle.name,
            }
        )
    )

    selected, observed = _current_bundle(tmp_path)

    assert selected == bundle
    assert observed == manifest
    pointer.write_text(
        json.dumps(
            {
                "schema": 1,
                "bundle_id": manifest["bundle_id"],
                "filename": "../bundle.zip",
            }
        )
    )
    with pytest.raises(RuntimeError, match="filename"):
        _current_bundle(tmp_path)
