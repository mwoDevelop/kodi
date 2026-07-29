import json

from tools.compose_stable_snapshot import compose
from tools.snapshot_bundle import create_bundle


def _index(repository_id, component_version):
    return (
        '<?xml version="1.0" encoding="UTF-8"?>\n'
        "<addons>"
        '<addon id="%s" name="%s" version="1.0.0" />'
        '<addon id="plugin.video.example" name="Example" version="%s" />'
        "</addons>\n"
    ) % (repository_id, repository_id, component_version)


def _dist(path, testing_version, stable_version):
    for channel, repository, version in (
        ("testing", "repository.mwodevelop.testing", testing_version),
        ("stable", "repository.mwodevelop", stable_version),
    ):
        root = path / channel / "omega"
        root.mkdir(parents=True)
        (root / "addons.xml").write_text(
            _index(repository, version), encoding="utf-8"
        )
        package = root / "plugin.video.example/example.zip"
        package.parent.mkdir()
        package.write_bytes(("%s-%s" % (channel, version)).encode())
    (path / "repo").mkdir()
    (path / "repo/index.html").write_text("repo")
    (path / "repo/repository.mwodevelop-1.0.0.zip").write_bytes(b"repo")
    (path / "repository.mwodevelop-1.0.0.zip").write_bytes(b"repo")
    (path / "repository.mwodevelop.testing-1.0.0.zip").write_bytes(b"testing")
    provenance = {
        "schema": 2,
        "channels": {
            "testing": {"marker": testing_version},
            "stable": {"marker": stable_version},
        },
    }
    (path / "build-provenance.json").write_text(json.dumps(provenance))
    (path / "index.html").write_text("old")
    (path / "artifact-manifest.sha256").write_text("manifest\n")


def _snapshot(tmp_path, name, payload, promotion, commit):
    lock = tmp_path / ("%s-testing.json" % name)
    lock.write_text(
        json.dumps({"schema": 1, "channel": "testing", "components": {}})
    )
    bundle = tmp_path / ("%s.tar" % name)
    create_bundle(
        payload,
        lock,
        commit,
        bundle,
        promotion_dist=promotion,
    )
    return bundle


def test_composer_preserves_newer_testing_and_exact_promoted_stable(tmp_path):
    current = tmp_path / "current"
    promoted = tmp_path / "promoted"
    _dist(current, "2.0.0", "1.0.0")
    _dist(promoted, "1.0.0", "1.0.0")
    current_snapshot = _snapshot(
        tmp_path, "current", current, current, "a" * 40
    )
    promoted_snapshot = _snapshot(
        tmp_path, "promoted", promoted, promoted, "b" * 40
    )

    output = tmp_path / "output"
    result = compose(current_snapshot, promoted_snapshot, output)

    assert "2.0.0" in (output / "testing/omega/addons.xml").read_text()
    assert "1.0.0" in (output / "stable/omega/addons.xml").read_text()
    assert (output / "stable/omega/plugin.video.example/example.zip").read_bytes() == (
        promoted / "stable/omega/plugin.video.example/example.zip"
    ).read_bytes()
    provenance = json.loads((output / "build-provenance.json").read_text())
    assert provenance["channels"]["testing"]["marker"] == "2.0.0"
    assert provenance["channels"]["stable"]["marker"] == "1.0.0"
    assert result["current_testing_snapshot_id"] != result[
        "promoted_stable_snapshot_id"
    ]
