#!/usr/bin/env python3
"""Prepare and apply a typed testing-lock candidate from product branches."""

import argparse
import hashlib
import json
import subprocess
import sys
import tempfile
from pathlib import Path, PurePosixPath

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from tools import build_repo
from tools.kodi_addon_runtime_compatibility import inspect_archive
from tools.upstream_sync.versioning import require_strictly_newer


TESTING_LOCK = Path("manifests/locks/testing.json")
STABLE_LOCK = Path("manifests/locks/stable.json")
SCHEMA = 1


def canonical_json(value):
    return json.dumps(
        value, sort_keys=True, separators=(",", ":"), ensure_ascii=False
    ).encode("utf-8")


def digest(value):
    payload = value if isinstance(value, bytes) else canonical_json(value)
    return hashlib.sha256(payload).hexdigest()


def load(path):
    return json.loads(Path(path).read_text(encoding="utf-8"))


def git(*args, cwd=ROOT):
    return subprocess.check_output(["git", "-C", str(cwd), *args], text=True).strip()


def _artifact(component, addon_id, commit, output):
    files = build_repo.component_files(component, commit)
    by_name = {
        PurePosixPath(relative).as_posix(): payload for payload, relative in files
    }
    addon, parsed_id, version = build_repo.parse_addon_payload(by_name["addon.xml"])
    if parsed_id != addon_id:
        raise ValueError("component ID drift: %s" % addon_id)
    target = Path(output) / ("%s-%s.zip" % (addon_id, version))
    build_repo.write_deterministic_zip(target, addon_id, files)
    inspect_archive(target, expected_id=addon_id, expected_version=version)
    return {
        "commit": commit,
        "version": version,
        "zip_sha256": build_repo.sha256(target),
    }


def component_repository_targets(root, components, upstreams):
    targets = {}
    for config in upstreams.values():
        target = config["target"]
        targets[target["repository"]] = (
            root / config["local_path"],
            target["branch"],
        )
    for component in components.values():
        repository = component["repository"]
        if repository in targets:
            continue
        source = PurePosixPath(component["source"])
        if source.is_absolute() or ".." in source.parts or not source.parts:
            raise ValueError("component source must be a confined relative path")
        targets[repository] = (
            root / source.parts[0],
            component.get("branch", "main"),
        )
    return targets


def prepare(output, root=ROOT, component_id=None):
    root = Path(root).resolve()
    output = Path(output)
    if output.exists():
        raise ValueError("candidate output already exists")
    components = load(root / "manifests/components.json")["components"]
    if component_id is not None and component_id not in components:
        raise ValueError("unknown requested component: %s" % component_id)
    upstreams = load(root / "manifests/upstreams.json")["components"]
    testing = load(root / TESTING_LOCK)
    stable = load(root / STABLE_LOCK)
    proposed = json.loads(json.dumps(testing))
    repository_targets = component_repository_targets(
        root, components, upstreams
    )
    if component_id is not None:
        selected_repository = components[component_id]["repository"]
        repository_targets = {
            selected_repository: repository_targets[selected_repository]
        }
    changed = []
    target_heads = {}
    with tempfile.TemporaryDirectory(prefix="testing-lock-") as temporary:
        for repository, (checkout, branch) in sorted(repository_targets.items()):
            subprocess.run(
                ["git", "-C", str(checkout), "fetch", "--no-tags", "origin", branch],
                check=True,
            )
            head = git("rev-parse", "FETCH_HEAD", cwd=checkout)
            target_heads[repository] = head
            repository_components = [
                (addon_id, component)
                for addon_id, component in components.items()
                if component["repository"] == repository
                and (component_id is None or addon_id == component_id)
            ]
            artifacts = {}
            for addon_id, component in repository_components:
                artifact = _artifact(component, addon_id, head, temporary)
                current = testing["components"][addon_id]
                if artifact["zip_sha256"] != current["zip_sha256"]:
                    require_strictly_newer(
                        artifact["version"],
                        current["version"],
                        stable["components"][addon_id]["version"],
                    )
                    changed.append(addon_id)
                artifacts[addon_id] = artifact
            if any(addon_id in changed for addon_id, _ in repository_components):
                for addon_id, _component in repository_components:
                    pin = dict(artifacts[addon_id])
                    if "provider_api" in testing["components"][addon_id]:
                        pin["provider_api"] = testing["components"][addon_id][
                            "provider_api"
                        ]
                    proposed["components"][addon_id] = pin
    action = "propose" if changed else "noop"
    base_commit = git("rev-parse", "HEAD", cwd=root)
    identity = {
        "schema": SCHEMA,
        "action": action,
        "mutation_kind": "testing_lock_candidate",
        "requested_component": component_id,
        "base_commit": base_commit,
        "current_lock_sha256": digest(testing),
        "proposed_lock_sha256": digest(proposed),
        "changed_components": sorted(changed),
        "target_heads": target_heads,
    }
    candidate = {**identity, "candidate_id": digest(identity)}
    output.mkdir(parents=True)
    (output / "candidate.json").write_bytes(canonical_json(candidate))
    (output / "testing-lock.json").write_text(
        json.dumps(proposed, indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )
    return candidate


def apply(bundle, checkout):
    bundle = Path(bundle).resolve()
    checkout = Path(checkout).resolve()
    candidate = load(bundle / "candidate.json")
    proposed = load(bundle / "testing-lock.json")
    identity = {
        key: candidate[key]
        for key in (
            "schema",
            "action",
            "mutation_kind",
            "requested_component",
            "base_commit",
            "current_lock_sha256",
            "proposed_lock_sha256",
            "changed_components",
            "target_heads",
        )
    }
    if candidate.get("candidate_id") != digest(identity):
        raise ValueError("testing-lock candidate identity mismatch")
    if candidate["action"] != "propose":
        raise ValueError("testing-lock candidate is a no-op")
    if candidate["mutation_kind"] != "testing_lock_candidate":
        raise ValueError("unexpected mutation kind")
    if git("rev-parse", "HEAD", cwd=checkout) != candidate["base_commit"]:
        raise ValueError("testing-lock base drift")
    current = load(checkout / TESTING_LOCK)
    if digest(current) != candidate["current_lock_sha256"]:
        raise ValueError("testing lock changed after prepare")
    if digest(proposed) != candidate["proposed_lock_sha256"]:
        raise ValueError("proposed testing lock digest mismatch")
    (checkout / TESTING_LOCK).write_text(
        json.dumps(proposed, indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )
    return candidate


def main():
    parser = argparse.ArgumentParser()
    commands = parser.add_subparsers(dest="command", required=True)
    prepare_parser = commands.add_parser("prepare")
    prepare_parser.add_argument("--output", required=True)
    prepare_parser.add_argument("--component")
    apply_parser = commands.add_parser("apply")
    apply_parser.add_argument("--bundle", required=True)
    apply_parser.add_argument("--checkout", default=".")
    args = parser.parse_args()
    result = (
        prepare(args.output, component_id=args.component)
        if args.command == "prepare"
        else apply(args.bundle, args.checkout)
    )
    print(json.dumps(result, indent=2, sort_keys=True))


if __name__ == "__main__":
    main()
