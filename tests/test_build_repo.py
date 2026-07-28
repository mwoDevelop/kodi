import hashlib
import json
import re
from copy import deepcopy
from pathlib import Path
from xml.etree import ElementTree
from zipfile import ZipFile

import pytest

from tools.build_repo import build


def tree_digest(root):
    result = {}
    for path in sorted(Path(root).rglob("*")):
        if path.is_file():
            result[str(path.relative_to(root))] = hashlib.sha256(path.read_bytes()).hexdigest()
    return result


def test_two_builds_are_byte_identical(tmp_path):
    first = build(tmp_path / "first")
    second = build(tmp_path / "second")
    assert tree_digest(first) == tree_digest(second)


def test_build_rejects_filesystem_root():
    with pytest.raises(ValueError, match="unsafe output directory"):
        build(Path("/"))


def test_testing_index_and_dependency_closure(tmp_path):
    output = build(tmp_path / "repo")
    index = ElementTree.parse(output / "testing/omega/addons.xml").getroot()
    ids = {addon.attrib["id"] for addon in index}
    assert ids == {
        "plugin.video.umbrella",
        "plugin.video.watchnixtoons2.mwodevelop",
        "repository.mwodevelop.testing",
        "service.mwodevelop.profilesync",
        "script.module.mwoscrapers",
        "script.mwoscrapers",
    }
    umbrella = index.find("./addon[@id='plugin.video.umbrella']")
    assert umbrella.find("./requires/import[@addon='script.module.mwoscrapers']") is not None
    manager = index.find("./addon[@id='script.mwoscrapers']")
    assert manager.find("./requires/import[@addon='script.module.mwoscrapers']") is not None
    assert manager.find("./extension[@point='xbmc.python.script']") is not None
    watchnixtoons = index.find(
        "./addon[@id='plugin.video.watchnixtoons2.mwodevelop']"
    )
    assert watchnixtoons.attrib["version"] == "0.26.1"
    adaptive = watchnixtoons.find(
        "./requires/import[@addon='inputstream.adaptive']"
    )
    assert adaptive is not None
    assert adaptive.attrib["optional"] == "true"
    assert watchnixtoons.find("./requires/import[@addon='script.module.six']") is not None


def test_home_page_catalogs_both_channels(tmp_path):
    output = build(tmp_path / "repo")
    home = (output / "index.html").read_text(encoding="utf-8")

    assert 'href="repository.mwodevelop-1.0.0.zip"' in home
    assert 'href="repository.mwodevelop.testing-1.0.0.zip"' in home
    assert 'href="stable/omega/addons.xml"' in home
    assert 'href="testing/omega/addons.xml"' in home
    assert "Umbrella" in home
    assert "MwoScrapers" in home
    assert "MwoScrapers Manager" in home
    assert "WatchNixtoons2 (mwoDevelop)" in home
    assert "mwoDevelop Profile Sync" in home


def test_kodi_file_source_lists_stable_repository_zip(tmp_path):
    output = build(tmp_path / "repo")
    repository_zip = "repository.mwodevelop-1.0.0.zip"
    source = (output / "repo/index.html").read_text(encoding="utf-8")

    assert 'href="%s"' % repository_zip in source
    kodi_http_directory_item = re.compile(
        r'<a href="([^"]*)"[^>]*>\s*(.*?)\s*</a>(.+?)(?=<a|</tr|$)',
        re.IGNORECASE,
    )
    assert kodi_http_directory_item.findall(source) == [
        (repository_zip, repository_zip, "</td>")
    ]
    assert (output / "repo" / repository_zip).read_bytes() == (
        output / repository_zip
    ).read_bytes()


def test_zips_have_single_safe_root(tmp_path):
    output = build(tmp_path / "repo")
    for path in output.rglob("*.zip"):
        with ZipFile(path) as archive:
            names = archive.namelist()
            assert names
            roots = {name.split("/", 1)[0] for name in names}
            assert len(roots) == 1
            assert all(".." not in Path(name).parts for name in names)


def test_provenance_matches_channel_locks(tmp_path):
    output = build(tmp_path / "repo")
    provenance = json.loads((output / "build-provenance.json").read_text())
    testing = json.loads(Path("manifests/locks/testing.json").read_text())
    for addon_id, data in provenance["channels"]["testing"]["components"].items():
        pin = testing["components"][addon_id]
        assert data["commit"] == pin["commit"]
        assert data["version"] == pin["version"]
        assert data["zip_sha256"] == pin["zip_sha256"]


def test_testing_changes_cannot_mutate_stable_snapshot(tmp_path):
    current = json.loads(Path("manifests/locks/testing.json").read_text())
    stable = deepcopy(current)
    stable["channel"] = "stable"
    empty_testing = {
        "schema": 1,
        "channel": "testing",
        "components": {},
    }

    first = build(
        tmp_path / "first",
        lock_overrides={"stable": stable, "testing": current},
    )
    second = build(
        tmp_path / "second",
        lock_overrides={"stable": stable, "testing": empty_testing},
    )

    assert tree_digest(first / "stable") == tree_digest(second / "stable")
    assert tree_digest(first / "testing") != tree_digest(second / "testing")


def test_metadata_assets_are_published_next_to_zip(tmp_path):
    output = build(tmp_path / "repo")
    umbrella = output / "testing/omega/plugin.video.umbrella"
    assert (umbrella / "icon.png").is_file()
    assert (umbrella / "fanart.jpg").is_file()
    watchnixtoons = (
        output / "testing/omega/plugin.video.watchnixtoons2.mwodevelop"
    )
    assert (watchnixtoons / "icon.png").is_file()
    assert (watchnixtoons / "fanart.jpg").is_file()
