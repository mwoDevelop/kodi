#!/usr/bin/env python3
"""Build/reuse exact QNAP approvals and attach one immutable lock candidate."""

from __future__ import annotations

import argparse
import hashlib
import json
import shutil
import subprocess
import tempfile
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from tools import qnap_images, qnap_lock


def _run(argv, repository=ROOT):
    return subprocess.run(
        [str(item) for item in argv],
        cwd=repository,
        check=True,
        capture_output=True,
        text=True,
    ).stdout.strip()


def _prior_lock(repository):
    path = Path(repository) / "manifests/locks/qnap-stable.json"
    return qnap_lock.load_lock(path) if path.is_file() else None


def _reuse_approval(name, service, prior, input_sha256, commit):
    if not prior:
        return None
    item = prior["services"].get(name)
    if not item or (
        item["source_commit"] != commit
        or item["input_sha256"] != input_sha256
        or item["source_repository"] != service.github_repository
        or item["platforms"] != list(service.platforms)
    ):
        return None
    return {"schema": 1, "service": name, **item}


def _download_approval(service, run_id, destination):
    destination.mkdir(parents=True, exist_ok=False, mode=0o700)
    destination.chmod(0o700)
    artifacts = json.loads(
        _run(
            (
                "gh",
                "api",
                "repos/%s/actions/runs/%s/artifacts?per_page=100"
                % (service.github_repository, run_id),
            )
        )
    ).get("artifacts", [])
    approval_artifacts = [
        item["name"]
        for item in artifacts
        if (
            isinstance(item, dict)
            and isinstance(item.get("name"), str)
            and item["name"].startswith("qnap-image-approval-")
            and not item.get("expired", False)
        )
    ]
    if len(approval_artifacts) != 1:
        raise RuntimeError(
            "workflow did not publish exactly one QNAP approval artifact"
        )
    _run(
        (
            "gh",
            "run",
            "download",
            run_id,
            "--repo",
            service.github_repository,
            "--name",
            approval_artifacts[0],
            "--dir",
            destination,
        )
    )
    matches = list(destination.rglob("qnap-image-approval.json"))
    if len(matches) != 1 or matches[0].is_symlink():
        raise RuntimeError("workflow did not publish exactly one QNAP approval")
    return matches[0]


def prepare(repository=ROOT):
    repository = Path(repository).resolve()
    services = qnap_images.services()
    prior = _prior_lock(repository)
    private = repository / ".kodi-private/kodi-ops/qnap-candidates"
    private.mkdir(parents=True, exist_ok=True, mode=0o700)
    private.chmod(0o700)
    approval_paths = []
    build_runs = {}
    with tempfile.TemporaryDirectory(prefix="candidate-", dir=private) as temporary:
        temporary = Path(temporary)
        for name, service in services.items():
            identity = qnap_images.source_identity(service, require_clean=True)
            input_sha = qnap_images.source_input_sha256(service, identity["commit"])
            reused = _reuse_approval(
                name, service, prior, input_sha, identity["commit"]
            )
            approval = temporary / (name + ".json")
            if reused is not None:
                approval.write_text(
                    json.dumps(reused, indent=2, sort_keys=True) + "\n",
                    encoding="utf-8",
                )
                approval.chmod(0o600)
                build_runs[name] = "reused"
            else:
                built = qnap_images.build_with_actions(service)
                source = _download_approval(
                    service,
                    built["workflow_run_id"],
                    temporary / (name + "-artifact"),
                )
                shutil.copyfile(source, approval)
                approval.chmod(0o600)
                build_runs[name] = built["workflow_run_id"]
            approval_paths.append(approval)
        document = qnap_lock.compose_lock(approval_paths)
        output = private / ("qnap-candidate-%s.json" % document["candidate_id"])
        if output.is_file():
            existing = json.loads(output.read_text(encoding="utf-8"))
            if existing != document:
                raise RuntimeError("QNAP candidate ID collides with different bytes")
        else:
            qnap_lock.write_lock(output, document)
            output.chmod(0o600)
    return {
        "candidate_id": document["candidate_id"],
        "path": output,
        "sha256": hashlib.sha256(output.read_bytes()).hexdigest(),
        "build_runs": build_runs,
    }


def upload(snapshot_tag, candidate, repository=ROOT):
    name = "qnap-candidate-%s.json" % candidate["candidate_id"]
    view = json.loads(
        _run(
            (
                "gh",
                "release",
                "view",
                snapshot_tag,
                "--repo",
                "mwoDevelop/kodi",
                "--json",
                "assets",
            ),
            repository,
        )
    )
    if name in {item["name"] for item in view["assets"]}:
        with tempfile.TemporaryDirectory(
            prefix="verify-upload-", dir=candidate["path"].parent
        ) as temporary:
            _run(
                (
                    "gh",
                    "release",
                    "download",
                    snapshot_tag,
                    "--repo",
                    "mwoDevelop/kodi",
                    "--pattern",
                    name,
                    "--dir",
                    temporary,
                ),
                repository,
            )
            remote = Path(temporary) / name
            if (
                not remote.is_file()
                or hashlib.sha256(remote.read_bytes()).hexdigest()
                != candidate["sha256"]
            ):
                raise RuntimeError("immutable QNAP candidate asset differs")
        return {**candidate, "asset": name, "snapshot_tag": snapshot_tag}
    _run(
        (
            "gh",
            "release",
            "upload",
            snapshot_tag,
            str(candidate["path"]),
            "--repo",
            "mwoDevelop/kodi",
        ),
        repository,
    )
    return {**candidate, "asset": name, "snapshot_tag": snapshot_tag}


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--snapshot-tag", required=True)
    args = parser.parse_args()
    result = upload(args.snapshot_tag, prepare(ROOT), ROOT)
    print(
        json.dumps(
            {
                "schema": 1,
                "candidate_id": result["candidate_id"],
                "sha256": result["sha256"],
                "asset": result["asset"],
                "build_runs": result["build_runs"],
            },
            indent=2,
            sort_keys=True,
        )
    )


if __name__ == "__main__":
    main()
