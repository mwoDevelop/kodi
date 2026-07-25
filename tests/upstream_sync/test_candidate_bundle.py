import json

import pytest

from tools.upstream_sync.candidate_bundle import (
    build_bundle,
    canonical_json,
    sha256_bytes,
    verify_bundle,
)


def candidate_inputs():
    return {
        "component": "umbrella",
        "downstream_base": "a" * 40,
        "upstream_identity": {"commit": "b" * 40},
        "manifest_sha256": "c" * 64,
        "adapter_version": 1,
        "transform_sha256": "d" * 64,
        "version_policy": "umbrella_downstream",
    }


def test_bundle_is_reproducible_and_verifiable(tmp_path):
    tree = tmp_path / "tree"
    tree.mkdir()
    (tree / "addon.xml").write_text("<addon/>\n", encoding="utf-8")
    (tree / "lib").mkdir()
    (tree / "lib/module.py").write_text("VALUE = 1\n", encoding="utf-8")

    first = build_bundle(tree, tmp_path / "first", candidate_inputs())
    second = build_bundle(tree, tmp_path / "second", candidate_inputs())

    assert first["candidate_id"] == second["candidate_id"]
    assert verify_bundle(tmp_path / "first") == first


def test_candidate_id_includes_downstream_base(tmp_path):
    tree = tmp_path / "tree"
    tree.mkdir()
    (tree / "addon.xml").write_text("<addon/>\n", encoding="utf-8")
    first = build_bundle(tree, tmp_path / "first", candidate_inputs())
    changed = candidate_inputs()
    changed["downstream_base"] = "e" * 40
    second = build_bundle(tree, tmp_path / "second", changed)
    assert first["candidate_id"] != second["candidate_id"]


def test_verifier_detects_tree_tampering(tmp_path):
    tree = tmp_path / "tree"
    tree.mkdir()
    (tree / "addon.xml").write_text("<addon/>\n", encoding="utf-8")
    build_bundle(tree, tmp_path / "bundle", candidate_inputs())
    (tmp_path / "bundle/tree/addon.xml").write_text("<changed/>\n", encoding="utf-8")

    with pytest.raises(ValueError, match="inventory"):
        verify_bundle(tmp_path / "bundle")


def test_symlink_is_rejected(tmp_path):
    tree = tmp_path / "tree"
    tree.mkdir()
    (tree / "target").write_text("safe", encoding="utf-8")
    (tree / "link").symlink_to("target")

    with pytest.raises(ValueError, match="symlink"):
        build_bundle(tree, tmp_path / "bundle", candidate_inputs())


def test_candidate_document_is_canonical():
    left = canonical_json({"b": 2, "a": 1})
    right = canonical_json({"a": 1, "b": 2})
    assert left == right
    assert sha256_bytes(left) == sha256_bytes(right)


def test_candidate_digest_rejects_document_tampering(tmp_path):
    tree = tmp_path / "tree"
    tree.mkdir()
    (tree / "addon.xml").write_text("<addon/>\n", encoding="utf-8")
    build_bundle(tree, tmp_path / "bundle", candidate_inputs())
    path = tmp_path / "bundle/candidate.json"
    payload = json.loads(path.read_text(encoding="utf-8"))
    payload["inputs"]["component"] = "other"
    path.write_text(json.dumps(payload), encoding="utf-8")

    with pytest.raises(ValueError, match="document digest"):
        verify_bundle(tmp_path / "bundle")
