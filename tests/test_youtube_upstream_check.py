import hashlib
import io
import json
from zipfile import ZipFile

import pytest

from tools import youtube_upstream_check as upstream


def _zip(version="7.4.4", requests="2.27.1"):
    value = io.BytesIO()
    addon = f"""<addon id="plugin.video.youtube" version="{version}">
      <requires>
        <import addon="xbmc.python" version="3.0.0" />
        <import addon="script.module.requests" version="{requests}" />
        <import addon="inputstream.adaptive" version="19.0.0" />
        <import addon="script.module.pysocks" optional="true" />
      </requires>
    </addon>"""
    with ZipFile(value, "w") as archive:
        archive.writestr("plugin.video.youtube/addon.xml", addon)
        archive.writestr("plugin.video.youtube/resources/lib/default.py", "pass\n")
    return value.getvalue()


class _Response:
    def __init__(self, payload, url):
        self.payload = payload
        self.url = url

    def __enter__(self):
        return self

    def __exit__(self, *_args):
        return None

    def read(self, limit):
        return self.payload[:limit]

    def geturl(self):
        return self.url


def _manifest(tmp_path, version="7.4.4", payload=None):
    payload = payload or _zip(version)
    document = {
        "schema": 1,
        "policy": "official-external",
        "addons": [
            {
                "id": "plugin.video.youtube",
                "version": version,
                "kind": "plugin",
                "url": f"https://mirrors.kodi.tv/addons/omega/plugin.video.youtube/plugin.video.youtube-{version}.zip",
                "sha256": hashlib.sha256(payload).hexdigest(),
                "source": f"https://github.com/anxdpanic/plugin.video.youtube/tree/v{version}",
                "license": "GPL-2.0-only",
                "origin": "repository.xbmc.org",
                "install_mode": "kodi-native-official",
                "dependencies": ["script.module.requests", "inputstream.adaptive"],
                "dependency_requirements": {
                    "script.module.requests": {
                        "minimum_version": "2.27.1",
                        "type": "python",
                    },
                    "inputstream.adaptive": {
                        "minimum_version": "19.0.0",
                        "type": "platform",
                    },
                },
            }
        ],
    }
    path = tmp_path / "manifest.json"
    path.write_text(json.dumps(document))
    return path


def test_discover_versions_selects_semantic_latest():
    assert upstream.discover_versions(
        b'<a href="plugin.video.youtube-7.4.4.zip">a</a>'
        b'<a href="plugin.video.youtube-7.10.0.zip">b</a>'
    ) == ["7.4.4", "7.10.0"]


def test_materialize_noop_keeps_zip_and_expanded_tree(tmp_path):
    payload = _zip()
    manifest = _manifest(tmp_path, payload=payload)

    def opener(url, timeout):
        assert timeout == 30
        body = (
            b'<a href="plugin.video.youtube-7.4.4.zip">zip</a>'
            if url.endswith("/")
            else payload
        )
        return _Response(body, url)

    candidate = upstream.materialize(manifest, tmp_path / "candidate", opener)

    assert candidate["action"] == "noop"
    assert candidate["candidate_id"] == hashlib.sha256(payload).hexdigest()
    assert candidate["expanded"]["files"] == 2
    assert (tmp_path / "candidate/artifact/plugin.video.youtube-7.4.4.zip").is_file()
    assert (tmp_path / "candidate/expanded/plugin.video.youtube/addon.xml").is_file()


def test_changed_candidate_is_atomic_and_updates_dependency_policy(tmp_path):
    current = _zip("7.4.4")
    payload = _zip("7.5.0", requests="2.32.0")
    manifest = _manifest(tmp_path, payload=current)

    def opener(url, timeout):
        body = (
            b'<a href="plugin.video.youtube-7.4.4.zip">old</a>'
            b'<a href="plugin.video.youtube-7.5.0.zip">new</a>'
            if url.endswith("/")
            else payload
        )
        return _Response(body, url)

    candidate_dir = tmp_path / "candidate"
    candidate = upstream.materialize(manifest, candidate_dir, opener)
    assert candidate["action"] == "review"
    assert (
        candidate["candidate_manifest"]["addons"][0]["dependency_requirements"][
            "script.module.requests"
        ]["minimum_version"]
        == "2.32.0"
    )

    upstream.apply_candidate(candidate_dir / "candidate.json", manifest)
    applied = json.loads(manifest.read_text())
    assert applied["addons"][0]["version"] == "7.5.0"


def test_apply_rejects_base_manifest_drift(tmp_path):
    current = _zip("7.4.4")
    payload = _zip("7.5.0")
    manifest = _manifest(tmp_path, payload=current)

    def opener(url, timeout):
        return _Response(
            b'<a href="plugin.video.youtube-7.5.0.zip">new</a>'
            if url.endswith("/")
            else payload,
            url,
        )

    candidate_dir = tmp_path / "candidate"
    upstream.materialize(manifest, candidate_dir, opener)
    manifest.write_text(manifest.read_text() + "\n")
    with pytest.raises(upstream.UpstreamError, match="base manifest changed"):
        upstream.apply_candidate(candidate_dir / "candidate.json", manifest)
