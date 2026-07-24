import hashlib
import json
from pathlib import Path
from xml.etree import ElementTree
from zipfile import ZipFile

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


def test_testing_index_and_dependency_closure(tmp_path):
    output = build(tmp_path / "repo")
    index = ElementTree.parse(output / "testing/omega/addons.xml").getroot()
    ids = {addon.attrib["id"] for addon in index}
    assert ids == {
        "plugin.video.umbrella",
        "repository.mwodevelop.testing",
        "script.module.mwoscrapers",
    }
    umbrella = index.find("./addon[@id='plugin.video.umbrella']")
    assert umbrella.find("./requires/import[@addon='script.module.mwoscrapers']") is not None


def test_zips_have_single_safe_root(tmp_path):
    output = build(tmp_path / "repo")
    for path in output.rglob("*.zip"):
        with ZipFile(path) as archive:
            names = archive.namelist()
            assert names
            roots = {name.split("/", 1)[0] for name in names}
            assert len(roots) == 1
            assert all(".." not in Path(name).parts for name in names)


def test_provenance_matches_submodule_locks(tmp_path):
    output = build(tmp_path / "repo")
    provenance = json.loads((output / "build-provenance.json").read_text())
    components = json.loads(Path("manifests/components.json").read_text())["components"]
    for addon_id, data in provenance["components"].items():
        assert data["commit"] == components[addon_id]["commit"]


def test_metadata_assets_are_published_next_to_zip(tmp_path):
    output = build(tmp_path / "repo")
    umbrella = output / "testing/omega/plugin.video.umbrella"
    assert (umbrella / "icon.png").is_file()
    assert (umbrella / "fanart.jpg").is_file()
