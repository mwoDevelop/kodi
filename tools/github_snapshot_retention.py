#!/usr/bin/env python3
"""Conservative, operator-approved cleanup of archived Actions transport copies."""

from __future__ import annotations

import argparse
import datetime as dt
import hashlib
import json
import os
from pathlib import Path
import re
import stat
import subprocess
import sys
import tempfile
import zipfile

if __package__ in {None, ""}:
    sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from tools import device_attestation, qualification_attestation, snapshot_bundle

REPO = "mwoDevelop/kodi"
ROOT = Path(__file__).resolve().parents[1]
BACKUPS = ROOT / ".kodi-private/actions-artifact-backups"
MIN_AGE = dt.timedelta(days=30)
MAX_BYTES = 256 * 1024 * 1024
FILES = {"snapshot.tar", "security-report.json"}
CONSUMERS = {"certify-testing.yml", "certify-umbrella-hermetic.yml"}


class RetentionError(RuntimeError):
    pass


class NotFound(RetentionError):
    pass


def timestamp(value):
    result = dt.datetime.fromisoformat(value.replace("Z", "+00:00"))
    if result.tzinfo is None:
        raise RetentionError("timestamp lacks timezone")
    return result


def digest(path):
    with Path(path).open("rb") as stream:
        return hashlib.file_digest(stream, "sha256").hexdigest()


def save_once(path, payload):
    """Never replace an earlier recovery copy; persist bytes before any deletion."""
    if path.exists():
        if path.is_symlink() or path.read_bytes() != payload:
            raise RetentionError("existing recovery evidence differs")
        return
    with path.open("xb") as stream:
        os.chmod(path, 0o600)
        stream.write(payload)
        stream.flush()
        os.fsync(stream.fileno())


def persist_directory(path):
    descriptor = os.open(path, os.O_RDONLY | os.O_DIRECTORY)
    try:
        os.fsync(descriptor)
    finally:
        os.close(descriptor)


def document_digest(value):
    return hashlib.sha256(snapshot_bundle.canonical_json(value)).hexdigest()


class GitHub:
    def api(self, endpoint, method="GET"):
        result = subprocess.run(
            ["gh", "api", f"repos/{REPO}/{endpoint}", "--method", method],
            capture_output=True, timeout=60, check=False,
        )
        if result.returncode:
            try:
                if str(json.loads(result.stdout).get("status")) == "404":
                    raise NotFound("GitHub object not found")
            except (ValueError, AttributeError):
                pass
            # Do not expose CLI errors, auth headers or redirect URLs.
            raise RetentionError("GitHub API request failed")
        return json.loads(result.stdout) if result.stdout else None

    def pages(self, endpoint, key=None):
        rows = []
        for page in range(1, 101):
            sep = "&" if "?" in endpoint else "?"
            value = self.api(f"{endpoint}{sep}per_page=100&page={page}")
            batch = value[key] if key else value
            rows.extend(batch)
            if len(batch) < 100:
                return rows
        raise RetentionError("pagination limit reached; incomplete inventory")

    def download(self, endpoint, target):
        # Exact fixed API paths only; gh handles redirects without logging secrets.
        with Path(target).open("xb") as stream:
            stream.flush()
            os.chmod(target, 0o600)
            result = subprocess.run(
                ["gh", "api", f"repos/{REPO}/{endpoint}", "-H",
                 "Accept: " + ("application/octet-stream" if endpoint.startswith("releases/assets/")
                                else "application/vnd.github+json")],
                stdout=stream, stderr=subprocess.PIPE, timeout=120, check=False,
            )
            stream.flush()
            os.fsync(stream.fileno())
        if result.returncode or Path(target).stat().st_size > MAX_BYTES:
            Path(target).unlink(missing_ok=True)
            raise RetentionError("archive download failed or exceeds size limit")


def old_success(run, now, workflow=None):
    if (run.get("status") != "completed" or run.get("conclusion") != "success"
            or now - timestamp(run["updated_at"]) <= MIN_AGE
            or (workflow and run.get("path") != f".github/workflows/{workflow}")):
        raise RetentionError("source/consumer is not an old successful exact workflow")


def require_no_active_consumers(api):
    for status in ("queued", "in_progress", "waiting", "requested", "pending"):
        runs = api.pages(f"actions/runs?status={status}", "workflow_runs")
        if any(Path(r.get("path", "")).name in CONSUMERS for r in runs):
            raise RetentionError("a certification consumer is active")


def missing_snapshot_is_noop(source, jobs):
    """Absence is safe only when the publication explicitly skipped its writer."""
    writers = [job for job in jobs if job.get("name") == "snapshot-writer"]
    builds = [job for job in jobs if job.get("name") == "build"]
    if (source.get("status") == "completed" and source.get("conclusion") == "success"
            and source.get("path") == ".github/workflows/publish-testing.yml"
            and source.get("head_branch") == "main"
            and len(builds) == 1 and builds[0].get("conclusion") == "success"
            and len(writers) == 1 and writers[0].get("conclusion") == "skipped"):
        steps = builds[0].get("steps", [])
        for name in ("Create immutable snapshot bundle", "Upload snapshot for the isolated writer"):
            matches = [s for s in steps if s.get("name") == name]
            if len(matches) != 1 or matches[0].get("conclusion") != "skipped":
                break
        else:
            return True
    raise RetentionError(
        "snapshot artifact missing after publication or publication evidence incomplete; "
        "use workflow_dispatch with the exact snapshot_id from its release/cleanup plan"
    )


def unpack_backup(archive, directory):
    with zipfile.ZipFile(archive) as bundle:
        members = bundle.infolist()
        if ({m.filename for m in members} != FILES or len(members) != 2
                or sum(m.file_size for m in members) > MAX_BYTES
                or any(stat.S_ISLNK(m.external_attr >> 16) for m in members)):
            raise RetentionError("unexpected transport archive members/size/type")
        for member in members:
            target = directory / member.filename
            payload = bundle.read(member)
            save_once(target, payload)


def prove(api, artifact_id, now, backups=BACKUPS):
    if type(artifact_id) is not int or artifact_id <= 0:
        raise RetentionError("invalid exact artifact ID")
    artifact = api.api(f"actions/artifacts/{artifact_id}")
    if (artifact.get("id") != artifact_id or artifact.get("name") != "testing-snapshot"
            or artifact.get("expired") is not False
            or now - timestamp(artifact["created_at"]) <= MIN_AGE
            or not 0 < artifact["size_in_bytes"] <= MAX_BYTES):
        raise RetentionError("artifact is protected by scope/age/size policy")
    source = api.api(f"actions/runs/{artifact['workflow_run']['id']}")
    old_success(source, now, "publish-testing.yml")
    if source.get("head_branch") != "main":
        raise RetentionError("source is not main")
    jobs = api.pages(f"actions/runs/{source['id']}/jobs?filter=latest", "jobs")
    writers = [j for j in jobs if j.get("name") == "snapshot-writer"]
    if len(writers) != 1 or writers[0].get("conclusion") != "success":
        raise RetentionError("successful snapshot writer not confirmed")
    related = api.pages(f"actions/runs?head_sha={source['head_sha']}", "workflow_runs")
    for run in related:
        if Path(run.get("path", "")).name in CONSUMERS:
            old_success(run, now)
    directory = backups / str(artifact_id)
    directory.mkdir(parents=True, exist_ok=True, mode=0o700)
    if directory.is_symlink():
        raise RetentionError("backup directory is a symlink")
    directory.chmod(0o700)
    archive = directory / "transport.zip"
    if not archive.exists():
        api.download(f"actions/artifacts/{artifact_id}/zip", archive)
    if archive.is_symlink() or archive.stat().st_size != artifact["size_in_bytes"]:
        raise RetentionError("backup is not the exact artifact size")
    archive_digest = digest(archive)
    if artifact.get("digest") and artifact["digest"] != "sha256:" + archive_digest:
        raise RetentionError("artifact digest differs")
    unpack_backup(archive, directory)
    snapshot = directory / "snapshot.tar"
    metadata = snapshot_bundle.verify_bundle(snapshot)
    if metadata["repository_commit"] != source["head_sha"]:
        raise RetentionError("snapshot commit differs from publication")
    tag = "testing-snapshot-" + metadata["snapshot_id"]
    release = api.api(f"releases/tags/{tag}")
    if release["tag_name"] != tag or release.get("draft"):
        raise RetentionError("release is absent/draft/different")
    assets = release["assets"]
    files = {}
    for name in sorted(FILES):
        found = [a for a in assets if a["name"] == name]
        if len(found) != 1:
            raise RetentionError("release does not contain both unique backup files")
        asset = found[0]
        with tempfile.TemporaryDirectory() as temporary:
            destination = Path(temporary) / name
            api.download(f"releases/assets/{asset['id']}", destination)
            if digest(destination) != digest(directory / name):
                raise RetentionError("release file is not byte-identical to Actions backup")
            files[name] = {"asset_id": asset["id"], "sha256": digest(destination)}
    attestations = [a for a in assets if re.fullmatch(
        r"(?:device|qualification)-attestation(?:-[a-f0-9]{64})?\.json", a["name"])]
    valid = None
    for asset in attestations:
        with tempfile.TemporaryDirectory() as temporary:
            downloaded = Path(temporary) / "attestation.json"
            api.download(f"releases/assets/{asset['id']}", downloaded)
            destination = directory / asset["name"]
            save_once(destination, downloaded.read_bytes())
        doc = json.loads(destination.read_text())
        verifier = (qualification_attestation if "qualification_type" in doc
                    else device_attestation)
        try:
            # Archive qualification, not a renewal of release approval.
            doc = verifier.verify(destination, snapshot, now=timestamp(doc["issued_at"]))
            run = api.api(f"actions/runs/{doc['workflow_run_id']}")
            old_success(run, now, Path(doc["workflow"].split("@", 1)[0]).name)
            if run["run_attempt"] != doc["workflow_run_attempt"]:
                continue
        except (ValueError, KeyError, RetentionError):
            continue
        valid = {"asset_id": asset["id"], "sha256": digest(destination),
                 "run_id": run["id"], "run_attempt": run["run_attempt"]}
        break
    if not valid:
        raise RetentionError("no verified historical certification; preserve snapshot")
    result = {"artifact_id": artifact_id, "source_run_id": source["id"],
              "source_run_attempt": source["run_attempt"], "source_sha": source["head_sha"],
              "size_in_bytes": artifact["size_in_bytes"], "zip_sha256": archive_digest,
              "snapshot_id": metadata["snapshot_id"], "release_id": release["id"],
              "files": files, "certification": valid}
    receipt = directory / "evidence.json"
    save_once(receipt, (json.dumps(result, indent=2) + "\n").encode())
    for path in (directory, backups, backups.parent):
        persist_directory(path)
    return result


def confirm_deleted(api, row, backups):
    try:
        api.api(f"actions/artifacts/{row['artifact_id']}")
    except NotFound:
        pass
    else:
        raise RetentionError("artifact deletion has not been observed")
    release = api.api("releases/tags/testing-snapshot-" + row["snapshot_id"])
    if release["id"] != row["release_id"]:
        raise RetentionError("release identity changed after deletion; backup retained")
    for name, proof in row["files"].items():
        found = [a for a in release["assets"] if a["name"] == name]
        if len(found) != 1 or found[0]["id"] != proof["asset_id"]:
            raise RetentionError("release asset changed after deletion; backup retained")
        with tempfile.TemporaryDirectory() as temporary:
            destination = Path(temporary) / name
            api.download(f"releases/assets/{proof['asset_id']}", destination)
            if (digest(destination) != proof["sha256"] or
                    digest(backups / str(row["artifact_id"]) / name) != proof["sha256"]):
                raise RetentionError("post-delete release/backup digest differs")


def apply_plan(api, plan, approval, now, backups=BACKUPS):
    if (approval != document_digest(plan) or plan.get("schema") != 1
            or plan.get("repository") != REPO
            or not dt.timedelta(0) <= now - timestamp(plan["created_at"]) <= dt.timedelta(days=1)):
        raise RetentionError("plan approval/scope/age invalid")
    rows = plan["artifacts"]
    if len(rows) > 20 or len({row["artifact_id"] for row in rows}) != len(rows):
        raise RetentionError("plan is not a bounded unique batch")
    deleted = []
    for row in rows:
        require_no_active_consumers(api)
        if prove(api, row["artifact_id"], now, backups) != row:
            raise RetentionError("live evidence changed since plan")
        require_no_active_consumers(api)
        # The durable backup was read and compared to the current release above.
        api.api(f"actions/artifacts/{row['artifact_id']}", method="DELETE")
        deleted.append(row["artifact_id"])
        print(json.dumps({"deleted_artifact_id": row["artifact_id"],
                          "retained_backup": str(backups / str(row["artifact_id"])),
                          "snapshot_id": row["snapshot_id"]}), flush=True)
        confirm_deleted(api, row, backups)
        save_once(backups / str(row["artifact_id"]) / "deleted.json",
                  json.dumps({"confirmed_at": now.isoformat(), "artifact_id": row["artifact_id"]}).encode())
        persist_directory(backups / str(row["artifact_id"]))
    return deleted


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    sub = parser.add_subparsers(dest="command", required=True)
    sub.add_parser("inventory")
    plan_parser = sub.add_parser("plan")
    plan_parser.add_argument("--artifact-id", type=int, action="append", required=True)
    plan_parser.add_argument("--output", type=Path, required=True)
    apply_parser = sub.add_parser("apply")
    apply_parser.add_argument("--plan", type=Path, required=True)
    apply_parser.add_argument("--approve-sha256", required=True)
    noop_parser = sub.add_parser("check-missing")
    noop_parser.add_argument("--run-id", type=int, required=True)
    args = parser.parse_args()
    api = GitHub()
    now = dt.datetime.now(dt.timezone.utc)
    if args.command == "inventory":
        values = api.pages("actions/artifacts", "artifacts")
        rows = [{"id": a["id"], "created_at": a["created_at"],
                 "size_in_bytes": a["size_in_bytes"], "run_id": a["workflow_run"]["id"]}
                for a in values if a["name"] == "testing-snapshot" and not a["expired"]
                and now - timestamp(a["created_at"]) > MIN_AGE]
        print(json.dumps({"age_candidates_only": rows}, indent=2))
    elif args.command == "check-missing":
        jobs = api.pages(f"actions/runs/{args.run_id}/jobs?filter=latest", "jobs")
        source = api.api(f"actions/runs/{args.run_id}")
        missing_snapshot_is_noop(source, jobs)
        print("confirmed publication no-op")
    elif args.command == "plan":
        if len(args.artifact_id) > 20 or len(set(args.artifact_id)) != len(args.artifact_id):
            raise RetentionError("maximum 20 unique artifact IDs per batch")
        require_no_active_consumers(api)
        rows, skipped = [], []
        for artifact_id in args.artifact_id:
            try:
                rows.append(prove(api, artifact_id, now))
            except (RetentionError, ValueError) as error:
                skipped.append({"id": artifact_id, "reason": str(error)})
        plan = {"schema": 1, "repository": REPO, "created_at": now.isoformat(),
                "artifacts": rows, "protected": skipped}
        args.output.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
        with args.output.open("x") as stream:
            os.chmod(args.output, 0o600)
            json.dump(plan, stream, indent=2)
        print(json.dumps({"plan": str(args.output), "approve_sha256": document_digest(plan),
                          "eligible": len(rows), "protected": skipped,
                          "reclaimable_bytes": sum(r["size_in_bytes"] for r in rows)}))
    else:
        plan = json.loads(args.plan.read_text())
        deleted = apply_plan(api, plan, args.approve_sha256, now)
        print(json.dumps({"deleted": deleted}))


if __name__ == "__main__":
    try:
        main()
    except RetentionError as error:
        raise SystemExit(str(error)) from None
