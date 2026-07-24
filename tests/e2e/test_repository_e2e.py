import contextlib
import functools
import http.server
import importlib
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
    with repository_server(output) as base:
        index_payload = urlopen(base + "testing/omega/addons.xml", timeout=5).read()
        index = ElementTree.fromstring(index_payload)
        for addon_id in ("script.module.mwoscrapers", "plugin.video.umbrella"):
            addon = index.find("./addon[@id='%s']" % addon_id)
            version = addon.attrib["version"]
            relative = "testing/omega/%s/%s-%s.zip" % (addon_id, addon_id, version)
            package = tmp_path / ("%s.zip" % addon_id)
            package.write_bytes(urlopen(base + relative, timeout=5).read())
            with ZipFile(package) as archive:
                archive.extractall(profile)

    sys.path.insert(0, str(profile / "script.module.mwoscrapers" / "lib"))
    try:
        module = importlib.import_module("mwoscrapers")
        providers = module.sources(ret_all=True)
        assert [name for name, _ in providers] == ["torrentio", "comet"]
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
