"""Content-addressed handoff between unprivileged preparation and writer jobs."""

import hashlib
import json
import os
import shutil
from pathlib import Path, PurePosixPath


SCHEMA = 1
MAX_FILE_SIZE = 64 * 1024 * 1024
MAX_FILES = 20000


def canonical_json(payload):
    return (
        json.dumps(payload, ensure_ascii=False, separators=(",", ":"), sort_keys=True)
        + "\n"
    ).encode("utf-8")


def sha256_bytes(payload):
    return hashlib.sha256(payload).hexdigest()


def sha256_file(path):
    digest = hashlib.sha256()
    with Path(path).open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _safe_relative(value):
    path = PurePosixPath(value)
    if path.is_absolute() or not value or ".." in path.parts:
        raise ValueError("unsafe candidate path: %r" % value)
    return path.as_posix()


def inventory_tree(tree):
    tree = Path(tree)
    result = {}
    paths = sorted(path for path in tree.rglob("*") if path.is_file() or path.is_symlink())
    if len(paths) > MAX_FILES:
        raise ValueError("candidate contains too many files")
    for path in paths:
        relative = _safe_relative(path.relative_to(tree).as_posix())
        if path.is_symlink():
            raise ValueError("candidate symlink is forbidden: %s" % relative)
        size = path.stat().st_size
        if size > MAX_FILE_SIZE:
            raise ValueError("candidate file is too large: %s" % relative)
        result[relative] = {
            "sha256": sha256_file(path),
            "size": size,
            "executable": bool(path.stat().st_mode & 0o111),
        }
    return result


def candidate_document(inputs, files):
    required = (
        "component",
        "downstream_base",
        "upstream_identity",
        "manifest_sha256",
        "adapter_version",
        "transform_sha256",
        "version_policy",
    )
    missing = [key for key in required if key not in inputs]
    if missing:
        raise ValueError("candidate inputs missing: %s" % ", ".join(missing))
    body = {
        "schema": SCHEMA,
        "inputs": inputs,
        "files": files,
    }
    candidate_id = sha256_bytes(canonical_json(body))
    return {**body, "candidate_id": candidate_id}


def build_bundle(tree, output, inputs):
    tree = Path(tree).resolve()
    output = Path(output).resolve()
    if output.exists():
        raise ValueError("candidate output already exists")
    files = inventory_tree(tree)
    document = candidate_document(inputs, files)
    (output / "tree").mkdir(parents=True)
    for relative in files:
        source = tree / relative
        target = output / "tree" / relative
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(source, target)
        os.chmod(target, 0o755 if files[relative]["executable"] else 0o644)
    payload = canonical_json(document)
    (output / "candidate.json").write_bytes(payload)
    (output / "candidate.json.sha256").write_text(
        sha256_bytes(payload) + "\n", encoding="ascii"
    )
    (output / "files.sha256").write_text(
        "".join(
            "%s  %s\n" % (item["sha256"], relative)
            for relative, item in sorted(files.items())
        ),
        encoding="utf-8",
    )
    return document


def verify_bundle(bundle):
    bundle = Path(bundle).resolve()
    payload = (bundle / "candidate.json").read_bytes()
    expected_document = (bundle / "candidate.json.sha256").read_text(
        encoding="ascii"
    ).strip()
    if sha256_bytes(payload) != expected_document:
        raise ValueError("candidate document digest mismatch")
    document = json.loads(payload)
    if document.get("schema") != SCHEMA:
        raise ValueError("unsupported candidate bundle schema")
    candidate_id = document.pop("candidate_id", None)
    if candidate_id != sha256_bytes(canonical_json(document)):
        raise ValueError("candidate ID mismatch")
    document["candidate_id"] = candidate_id
    actual = inventory_tree(bundle / "tree")
    if actual != document.get("files"):
        raise ValueError("candidate tree inventory mismatch")
    expected_lines = "".join(
        "%s  %s\n" % (item["sha256"], relative)
        for relative, item in sorted(actual.items())
    )
    if (bundle / "files.sha256").read_text(encoding="utf-8") != expected_lines:
        raise ValueError("candidate files manifest mismatch")
    return document
