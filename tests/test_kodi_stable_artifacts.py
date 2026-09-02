import hashlib
import io
import json
import stat
import zipfile

from tools import kodi_stable_artifacts


class Response(io.BytesIO):
    def __init__(self, payload, url):
        super().__init__(payload)
        self.url = url

    def geturl(self):
        return self.url

    def __enter__(self):
        return self

    def __exit__(self, *_args):
        self.close()


def addon_zip(addon_id, version):
    output = io.BytesIO()
    with zipfile.ZipFile(output, "w") as archive:
        archive.writestr(
            addon_id + "/addon.xml",
            '<addon id="%s" version="%s" />' % (addon_id, version),
        )
    return output.getvalue()


def test_prepare_fetches_content_addressed_public_stable(tmp_path, monkeypatch):
    addon = addon_zip("service.test", "1.2.3")
    repository = addon_zip("repository.mwodevelop", "1.0.0")
    addon_sha = hashlib.sha256(addon).hexdigest()
    repository_sha = hashlib.sha256(repository).hexdigest()
    relative = "stable/omega/service.test/service.test-1.2.3.zip"
    manifest = (
        "%s  %s\n%s  repository.mwodevelop-1.0.0.zip\n"
        % (addon_sha, relative, repository_sha)
    ).encode()
    payloads = {
        kodi_stable_artifacts.PUBLIC + "/artifact-manifest.sha256": manifest,
        kodi_stable_artifacts.PUBLIC + "/" + relative: addon,
        kodi_stable_artifacts.PUBLIC + "/repository.mwodevelop-1.0.0.zip": repository,
    }

    def opener(url, timeout=0):
        assert timeout > 0
        return Response(payloads[url], url)

    lock = tmp_path / "manifests/locks"
    lock.mkdir(parents=True)
    (lock / "stable.json").write_text(
        json.dumps(
            {
                "schema": 2,
                "channel": "stable",
                "components": {
                    "service.test": {
                        "version": "1.2.3",
                        "zip_sha256": addon_sha,
                    }
                },
            }
        )
    )

    result = kodi_stable_artifacts.prepare(tmp_path, opener=opener)

    assert result["addons"]["service.test"]["sha256"] == addon_sha
    assert result["repository"]["sha256"] == repository_sha
    assert stat.S_IMODE(result["repository"]["path"].stat().st_mode) == 0o600


def test_prepare_fetches_content_addressed_public_testing(tmp_path):
    addon = addon_zip("service.test", "2.0.0")
    repository = addon_zip("repository.mwodevelop.testing", "1.0.0")
    addon_sha = hashlib.sha256(addon).hexdigest()
    repository_sha = hashlib.sha256(repository).hexdigest()
    relative = "testing/omega/service.test/service.test-2.0.0.zip"
    manifest = (
        "%s  %s\n%s  repository.mwodevelop.testing-1.0.0.zip\n"
        % (addon_sha, relative, repository_sha)
    ).encode()
    payloads = {
        kodi_stable_artifacts.PUBLIC + "/artifact-manifest.sha256": manifest,
        kodi_stable_artifacts.PUBLIC + "/" + relative: addon,
        kodi_stable_artifacts.PUBLIC
        + "/repository.mwodevelop.testing-1.0.0.zip": repository,
    }

    def opener(url, timeout=0):
        assert timeout > 0
        return Response(payloads[url], url)

    lock = tmp_path / "manifests/locks"
    lock.mkdir(parents=True)
    (lock / "testing.json").write_text(
        json.dumps(
            {
                "schema": 1,
                "channel": "testing",
                "components": {
                    "service.test": {
                        "version": "2.0.0",
                        "zip_sha256": addon_sha,
                    }
                },
            }
        )
    )

    result = kodi_stable_artifacts.prepare(
        tmp_path, opener=opener, channel="testing"
    )

    assert result["channel"] == "testing"
    assert result["repository_id"] == "repository.mwodevelop.testing"
    assert result["addons"]["service.test"]["sha256"] == addon_sha
    assert result["repository"]["sha256"] == repository_sha


def test_prepare_repository_does_not_download_channel_addons(tmp_path):
    addon = addon_zip("service.test", "1.2.3")
    repository = addon_zip("repository.mwodevelop", "1.0.0")
    addon_sha = hashlib.sha256(addon).hexdigest()
    repository_sha = hashlib.sha256(repository).hexdigest()
    relative = "stable/omega/service.test/service.test-1.2.3.zip"
    manifest = (
        "%s  %s\n%s  repository.mwodevelop-1.0.0.zip\n"
        % (addon_sha, relative, repository_sha)
    ).encode()
    payloads = {
        kodi_stable_artifacts.PUBLIC + "/artifact-manifest.sha256": manifest,
        kodi_stable_artifacts.PUBLIC + "/repository.mwodevelop-1.0.0.zip": repository,
    }
    fetched = []

    def opener(url, timeout=0):
        assert timeout > 0
        fetched.append(url)
        return Response(payloads[url], url)

    lock = tmp_path / "manifests/locks"
    lock.mkdir(parents=True)
    (lock / "stable.json").write_text(
        json.dumps(
            {
                "schema": 2,
                "channel": "stable",
                "components": {
                    "service.test": {
                        "version": "1.2.3",
                        "zip_sha256": addon_sha,
                    }
                },
            }
        )
    )

    result = kodi_stable_artifacts.prepare_repository(
        tmp_path, opener=opener, channel="stable"
    )

    assert result["repository"]["sha256"] == repository_sha
    assert kodi_stable_artifacts.PUBLIC + "/" + relative not in fetched
