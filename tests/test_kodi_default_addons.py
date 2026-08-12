import hashlib
import io
from pathlib import Path
from zipfile import ZipFile

import pytest

from tools import kodi_default_addons as defaults


MANIFEST = Path("manifests/kodi-default-addons.json")


def archive(addon_id, version):
    output = io.BytesIO()
    with ZipFile(output, "w") as zipped:
        zipped.writestr(
            addon_id + "/addon.xml",
            '<addon id="%s" version="%s"/>' % (addon_id, version),
        )
    return output.getvalue()


def test_versioned_default_manifest_is_valid():
    document = defaults.load_manifest(MANIFEST)
    assert [item["id"] for item in document["addons"]] == [
        "repository.rapideo_pl",
        "script.module.xbmcswift2",
        "service.subtitles.opensubtitles",
        "plugin.video.rapideo_pl",
    ]
    assert all(item["url"].startswith("https://") for item in document["addons"])


def test_fetch_artifact_verifies_digest_and_identity(tmp_path):
    payload = archive("repository.example", "1.2.3")
    addon = {
        "id": "repository.example",
        "version": "1.2.3",
        "sha256": hashlib.sha256(payload).hexdigest(),
        "url": "https://example.invalid/repository.zip",
    }

    class Response(io.BytesIO):
        def __enter__(self):
            return self

        def __exit__(self, *_args):
            self.close()

    path = defaults.fetch_artifact(
        addon, tmp_path, opener=lambda *_args, **_kwargs: Response(payload)
    )

    assert path.read_bytes() == payload


def test_fetch_artifact_rejects_digest_mismatch(tmp_path):
    payload = archive("repository.example", "1.2.3")
    addon = {
        "id": "repository.example",
        "version": "1.2.3",
        "sha256": "0" * 64,
        "url": "https://example.invalid/repository.zip",
    }

    class Response(io.BytesIO):
        def __enter__(self):
            return self

        def __exit__(self, *_args):
            self.close()

    with pytest.raises(ValueError, match="digest differs"):
        defaults.fetch_artifact(
            addon, tmp_path, opener=lambda *_args, **_kwargs: Response(payload)
        )


def test_official_dependency_repair_checks_archive_bytes(monkeypatch, tmp_path):
    dependency = {
        "id": "script.module.urllib3",
        "version": "2.2.3",
        "sha256": "a" * 64,
        "url": (
            "https://mirrors.kodi.tv/addons/omega/"
            "script.module.urllib3/script.module.urllib3-2.2.3.zip"
        ),
    }
    artifact = tmp_path / "urllib3.zip"
    artifact.write_bytes(b"candidate")
    applied = []
    monkeypatch.setattr(defaults, "fetch_artifact", lambda *_args: artifact)
    monkeypatch.setattr(
        defaults,
        "addon_details",
        lambda *_args: {"enabled": True, "version": "2.2.3"},
    )
    monkeypatch.setattr(
        defaults,
        "installed_archive_matches",
        lambda *_args: False,
    )
    monkeypatch.setattr(
        defaults,
        "rollout",
        lambda *_args, **_kwargs: applied.append(_args[4]) or {},
    )

    actions = defaults.reconcile_official_dependencies(
        "adb", 5038, "serial", [dependency], tmp_path, 180
    )

    assert applied == ["script.module.urllib3"]
    assert actions == [
        {
            "addon": "script.module.urllib3",
            "action": "repaired",
            "version": "2.2.3",
        }
    ]


def test_reconcile_repairs_only_a_database_absent_orphan(
    monkeypatch, tmp_path
):
    addon = {
        "id": "repository.rapideo_pl",
        "version": "1.0.4",
        "kind": "repository",
        "url": "https://example.invalid/repository.zip",
        "sha256": "0" * 64,
        "source": "https://example.invalid/source",
        "license": "GPL-2.0-only",
    }
    current = {}
    repair_flags = []

    monkeypatch.setattr(
        defaults, "fetch_artifact", lambda *_args: tmp_path / "addon.zip"
    )
    monkeypatch.setattr(
        defaults,
        "addon_details",
        lambda *_args: current.get(addon["id"]),
    )

    def apply(*_args, **kwargs):
        repair = kwargs.get("repair_orphan", False)
        repair_flags.append(repair)
        if not repair:
            raise RuntimeError(
                "Kodi candidate apply failed: PermissionError at "
                "backup-installed-addon"
            )
        current[addon["id"]] = {
            "enabled": True,
            "version": addon["version"],
        }
        return {"repaired_orphan": True}

    monkeypatch.setattr(defaults, "rollout", apply)
    monkeypatch.setattr(
        defaults,
        "AdbEventClient",
        lambda *_args: type(
            "Events", (), {"execute_builtin": lambda *_args: None}
        )(),
    )
    monkeypatch.setattr(defaults.time, "sleep", lambda *_args: None)

    result = defaults.reconcile_android(
        "adb",
        5038,
        "serial",
        {"addons": [addon]},
        tmp_path,
        assign_origins=False,
    )

    assert repair_flags == [False, True]
    assert result["actions"][0]["repaired_orphan"] is True
