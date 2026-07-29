#!/usr/bin/env python3
"""Create and verify an immutable, content-addressed Kodi testing snapshot."""

import argparse
import hashlib
import io
import json
import re
import tarfile
from pathlib import Path, PurePosixPath


SCHEMA = 2
GENERATOR_VERSION = 2
SHA256 = re.compile(r"^[0-9a-f]{64}$")


def canonical_json(value):
    return json.dumps(
        value, sort_keys=True, separators=(",", ":"), ensure_ascii=False
    ).encode("utf-8")


def digest(payload):
    return hashlib.sha256(payload).hexdigest()


def file_digest(path):
    return digest(Path(path).read_bytes())


def snapshot_document(dist, promotion_dist, testing_lock, repository_commit):
    dist = Path(dist)
    lock = json.loads(Path(testing_lock).read_text(encoding="utf-8"))
    if lock.get("schema") != 1 or lock.get("channel") != "testing":
        raise ValueError("invalid testing lock")
    if not re.fullmatch(r"[0-9a-f]{40}", repository_commit):
        raise ValueError("repository commit must be an exact 40-character SHA")
    identity = {
        "schema": SCHEMA,
        "generator_version": GENERATOR_VERSION,
        "repository_commit": repository_commit,
        "testing_lock_sha256": digest(canonical_json(lock)),
        "testing_index_sha256": file_digest(
            dist / "testing" / "omega" / "addons.xml"
        ),
        "artifact_manifest_sha256": file_digest(
            dist / "artifact-manifest.sha256"
        ),
        "promotion_artifact_manifest_sha256": file_digest(
            Path(promotion_dist) / "artifact-manifest.sha256"
        ),
    }
    return {**identity, "snapshot_id": digest(canonical_json(identity))}


def _inventory(dist):
    result = {}
    for path in sorted(Path(dist).rglob("*")):
        if path.is_symlink():
            raise ValueError("snapshot payload cannot contain symlinks")
        if path.is_file():
            relative = PurePosixPath(path.relative_to(dist).as_posix())
            if relative.is_absolute() or ".." in relative.parts:
                raise ValueError("unsafe snapshot path")
            result[relative.as_posix()] = {
                "sha256": file_digest(path),
                "size": path.stat().st_size,
            }
    return result


def create_bundle(dist, testing_lock, repository_commit, output, promotion_dist=None):
    output = Path(output)
    if output.exists():
        raise ValueError("snapshot output already exists")
    promotion_dist = Path(promotion_dist or dist)
    document = snapshot_document(
        dist, promotion_dist, testing_lock, repository_commit
    )
    metadata = {
        **document,
        "files": _inventory(dist),
        "promotion_files": _inventory(promotion_dist),
        "testing_lock": json.loads(Path(testing_lock).read_text(encoding="utf-8")),
    }
    payload = canonical_json(metadata)
    with output.open("wb") as raw:
        with tarfile.open(fileobj=raw, mode="w", format=tarfile.PAX_FORMAT) as archive:
            info = tarfile.TarInfo("snapshot.json")
            info.size = len(payload)
            info.mode = 0o644
            info.mtime = 0
            archive.addfile(info, io.BytesIO(payload))
            for relative in sorted(metadata["files"]):
                source = Path(dist) / relative
                info = tarfile.TarInfo("payload/" + relative)
                info.size = source.stat().st_size
                info.mode = 0o644
                info.mtime = 0
                with source.open("rb") as handle:
                    archive.addfile(info, handle)
            for relative in sorted(metadata["promotion_files"]):
                source = promotion_dist / relative
                info = tarfile.TarInfo("promotion/" + relative)
                info.size = source.stat().st_size
                info.mode = 0o644
                info.mtime = 0
                with source.open("rb") as handle:
                    archive.addfile(info, handle)
    return metadata


def verify_bundle(bundle):
    seen = {}
    promotion_seen = {}
    metadata = None
    with tarfile.open(bundle, mode="r:") as archive:
        for member in archive:
            path = PurePosixPath(member.name)
            if path.is_absolute() or ".." in path.parts or not member.isfile():
                raise ValueError("unsafe snapshot member: %s" % member.name)
            handle = archive.extractfile(member)
            payload = handle.read() if handle else b""
            if member.name == "snapshot.json":
                metadata = json.loads(payload)
            elif member.name.startswith("payload/"):
                seen[member.name[len("payload/") :]] = {
                    "sha256": digest(payload),
                    "size": len(payload),
                }
            elif member.name.startswith("promotion/"):
                promotion_seen[member.name[len("promotion/") :]] = {
                    "sha256": digest(payload),
                    "size": len(payload),
                }
            else:
                raise ValueError("unexpected snapshot member: %s" % member.name)
    if not metadata or metadata.get("schema") != SCHEMA:
        raise ValueError("snapshot metadata is missing or unsupported")
    if metadata.get("files") != seen:
        raise ValueError("snapshot payload inventory mismatch")
    if metadata.get("promotion_files") != promotion_seen:
        raise ValueError("snapshot promotion inventory mismatch")
    lock = metadata.get("testing_lock")
    if (
        not isinstance(lock, dict)
        or lock.get("schema") != 1
        or lock.get("channel") != "testing"
        or digest(canonical_json(lock)) != metadata.get("testing_lock_sha256")
    ):
        raise ValueError("snapshot testing lock mismatch")
    identity = {
        key: metadata[key]
        for key in (
            "schema",
            "generator_version",
            "repository_commit",
            "testing_lock_sha256",
            "testing_index_sha256",
            "artifact_manifest_sha256",
            "promotion_artifact_manifest_sha256",
        )
    }
    if any(
        not SHA256.fullmatch(identity[key])
        for key in (
            "testing_lock_sha256",
            "testing_index_sha256",
            "artifact_manifest_sha256",
            "promotion_artifact_manifest_sha256",
        )
    ):
        raise ValueError("snapshot identity contains an invalid digest")
    expected = digest(canonical_json(identity))
    if metadata.get("snapshot_id") != expected:
        raise ValueError("snapshot ID mismatch")
    return metadata


def extract_section(bundle, section, output):
    metadata = verify_bundle(bundle)
    field = "promotion_files" if section == "promotion" else "files"
    prefix = "promotion/" if section == "promotion" else "payload/"
    output = Path(output)
    if output.exists():
        raise ValueError("snapshot extraction output already exists")
    output.mkdir(parents=True)
    with tarfile.open(bundle, mode="r:") as archive:
        for member in archive:
            if not member.name.startswith(prefix):
                continue
            relative = member.name[len(prefix) :]
            if relative not in metadata[field]:
                raise ValueError("snapshot contains an undeclared file")
            target = output.joinpath(*PurePosixPath(relative).parts)
            target.parent.mkdir(parents=True, exist_ok=True)
            handle = archive.extractfile(member)
            target.write_bytes(handle.read() if handle else b"")
    if _inventory(output) != metadata[field]:
        raise ValueError("extracted snapshot inventory mismatch")
    return metadata


def main():
    parser = argparse.ArgumentParser()
    commands = parser.add_subparsers(dest="command", required=True)
    create = commands.add_parser("create")
    create.add_argument("--dist", required=True)
    create.add_argument("--testing-lock", required=True)
    create.add_argument("--repository-commit", required=True)
    create.add_argument("--promotion-dist")
    create.add_argument("--output", required=True)
    verify = commands.add_parser("verify")
    verify.add_argument("bundle")
    extract = commands.add_parser("extract")
    extract.add_argument("bundle")
    extract.add_argument("--section", choices=("payload", "promotion"), required=True)
    extract.add_argument("--output", required=True)
    args = parser.parse_args()
    if args.command == "create":
        metadata = create_bundle(
            args.dist,
            args.testing_lock,
            args.repository_commit,
            args.output,
            promotion_dist=args.promotion_dist,
        )
    elif args.command == "verify":
        metadata = verify_bundle(args.bundle)
    else:
        metadata = extract_section(args.bundle, args.section, args.output)
    print(json.dumps(metadata, indent=2, sort_keys=True))


if __name__ == "__main__":
    main()
