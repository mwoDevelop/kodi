import contextlib
import functools
import http.server
import importlib
import io
import sys
import threading
from pathlib import Path
from urllib.request import urlopen
from xml.etree import ElementTree
from zipfile import ZipFile

from tools.build_repo import build


@contextlib.contextmanager
def repository_server(root):
    handler = functools.partial(http.server.SimpleHTTPRequestHandler, directory=str(root))
    server = http.server.ThreadingHTTPServer(("127.0.0.1", 0), handler)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        yield "http://127.0.0.1:%d/" % server.server_port
    finally:
        server.shutdown()
        thread.join()


def test_installable_repository_and_provider_contract(tmp_path):
    output = build(tmp_path / "dist")
    profile = tmp_path / "kodi-profile" / "addons"
    profile.mkdir(parents=True)
    installed = []
    with repository_server(output) as base:
        index_payload = urlopen(base + "testing/omega/addons.xml", timeout=5).read()
        index = ElementTree.fromstring(index_payload)

        def install(addon_id):
            if addon_id in installed:
                return
            addon = index.find("./addon[@id='%s']" % addon_id)
            assert addon is not None, "repository cannot resolve %s" % addon_id
            for dependency in addon.findall("./requires/import"):
                dependency_id = dependency.attrib["addon"]
                if dependency.attrib.get("optional") == "true":
                    continue
                if index.find("./addon[@id='%s']" % dependency_id) is not None:
                    install(dependency_id)
            version = addon.attrib["version"]
            relative = "testing/omega/%s/%s-%s.zip" % (addon_id, addon_id, version)
            package = tmp_path / ("%s.zip" % addon_id)
            package.write_bytes(urlopen(base + relative, timeout=5).read())
            with ZipFile(package) as archive:
                archive.extractall(profile)
            installed.append(addon_id)

        assert not (profile / "script.module.mwoscrapers").exists()
        install("plugin.video.umbrella")

    assert installed == ["script.module.mwoscrapers", "plugin.video.umbrella"]
    sys.path.insert(0, str(profile / "script.module.mwoscrapers" / "lib"))
    try:
        module = importlib.import_module("mwoscrapers")
        assert module.PROVIDER_API_VERSION == 1
        providers = module.sources(ret_all=True)
        addon = ElementTree.parse(
            profile / "script.module.mwoscrapers" / "addon.xml"
        ).getroot()
        version = tuple(int(part) for part in addon.attrib["version"].split("."))
        expected = ["torrentio", "comet"]
        if version >= (0, 2, 0):
            expected.extend(["torz", "mediafusion", "eztv", "piratebay"])
        assert [name for name, _ in providers] == expected
    finally:
        sys.path.pop(0)
        sys.modules.pop("mwoscrapers", None)

    umbrella = profile / "plugin.video.umbrella"
    targets = [
        umbrella / "resources/lib/modules/sources.py",
        umbrella / "resources/lib/debrid/realdebrid.py",
        *sorted((umbrella / "resources/lib/downstream").glob("*.py")),
    ]
    for target in targets:
        compile(target.read_bytes(), str(target), "exec")


def test_kodi_file_source_exposes_installable_repository_zip(tmp_path):
    output = build(tmp_path / "dist")
    with repository_server(output) as base:
        listing = urlopen(base + "repo", timeout=5).read().decode("utf-8")
        repository_zip = "repository.mwodevelop-1.0.0.zip"
        assert 'href="%s"' % repository_zip in listing
        payload = urlopen(base + "repo/" + repository_zip, timeout=5).read()

    with ZipFile(io.BytesIO(payload)) as archive:
        addon = ElementTree.fromstring(
            archive.read("repository.mwodevelop/addon.xml")
        )
    assert addon.attrib["id"] == "repository.mwodevelop"
    assert addon.attrib["version"] == "1.0.0"
