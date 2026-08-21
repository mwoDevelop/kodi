"""Exact-SHA GitHub workflow and reviewed promotion operations."""

from __future__ import annotations

import base64
import datetime as dt
import hashlib
import json
import subprocess
import time
from pathlib import Path

from tools.device_attestation import verify as verify_attestation
from tools.qnap_lock import load_lock as load_qnap_lock
from tools.snapshot_bundle import verify_bundle


class GitHubError(RuntimeError):
    pass


class GitHubClient:
    PUBLICATION_WORKFLOWS = (
        "publish-testing.yml",
        "publish-pages.yml",
        "deploy-stable.yml",
    )

    def __init__(self, repository: Path, slug="mwoDevelop/kodi"):
        self.repository = Path(repository).resolve()
        self.slug = slug

    def _run(self, argv, *, check=True):
        result = subprocess.run(
            [str(item) for item in argv],
            cwd=self.repository,
            check=check,
            capture_output=True,
            text=True,
        )
        return result

    def gh(self, *args):
        return self._run(("gh", *args)).stdout.strip()

    def gh_json(self, *args):
        output = self.gh(*args)
        return json.loads(output) if output else None

    def exact_main_preflight(self, commit):
        self._run(("git", "fetch", "origin", "main"))
        head = self._run(("git", "rev-parse", "HEAD")).stdout.strip()
        remote = self._run(("git", "rev-parse", "origin/main")).stdout.strip()
        branch = self._run(("git", "branch", "--show-current")).stdout.strip()
        dirty = self._run(
            ("git", "status", "--porcelain", "--untracked-files=all")
        ).stdout.strip()
        if head != commit or remote != commit or branch != "main":
            raise GitHubError("release requires the exact pushed origin/main head")
        if dirty:
            raise GitHubError("release requires a clean worktree")
        self.gh("auth", "status")
        return {"commit": commit, "branch": branch, "clean": True}

    def wait_publication_queue_idle(
        self, *, quiet_polls=3, poll_seconds=5, max_polls=360
    ):
        """Wait for the shared kodi-pages concurrency group to become stable-idle.

        GitHub retains only one pending run per concurrency group.  A delayed
        workflow_run event can therefore replace a manual pending dispatch even
        when cancel-in-progress is false.  Requiring consecutive idle polls
        closes that race without weakening the single-writer contract.
        """
        idle_polls = 0
        active_states = {"queued", "pending", "in_progress", "waiting", "requested"}
        for _attempt in range(max_polls):
            active = []
            for workflow in self.PUBLICATION_WORKFLOWS:
                rows = self.gh_json(
                    "run",
                    "list",
                    "--repo",
                    self.slug,
                    "--workflow",
                    workflow,
                    "--branch",
                    "main",
                    "--limit",
                    "10",
                    "--json",
                    "databaseId,status,url",
                )
                active.extend(
                    item for item in rows if item.get("status") in active_states
                )
            if active:
                idle_polls = 0
            else:
                idle_polls += 1
                if idle_polls >= quiet_polls:
                    return
            time.sleep(poll_seconds)
        raise GitHubError("kodi-pages publication queue did not become idle")

    def dispatch(self, workflow, commit, fields=None):
        if workflow in self.PUBLICATION_WORKFLOWS:
            self.wait_publication_queue_idle()
        started = dt.datetime.now(dt.timezone.utc) - dt.timedelta(seconds=5)
        command = [
            "workflow",
            "run",
            workflow,
            "--repo",
            self.slug,
            "--ref",
            "main",
        ]
        for key, value in sorted((fields or {}).items()):
            command.extend(("--field", f"{key}={value}"))
        self.gh(*command)
        for _attempt in range(60):
            runs = self.gh_json(
                "run",
                "list",
                "--repo",
                self.slug,
                "--workflow",
                workflow,
                "--event",
                "workflow_dispatch",
                "--branch",
                "main",
                "--limit",
                "20",
                "--json",
                "databaseId,headSha,createdAt,status,conclusion,url",
            )
            matches = [
                item
                for item in runs
                if item.get("headSha") == commit
                and dt.datetime.fromisoformat(item["createdAt"].replace("Z", "+00:00"))
                >= started
            ]
            if matches:
                return max(matches, key=lambda item: item["databaseId"])
            time.sleep(2)
        raise GitHubError("dispatched workflow run did not appear")

    def watch(self, run):
        self._run(
            (
                "gh",
                "run",
                "watch",
                str(run["databaseId"]),
                "--repo",
                self.slug,
                "--exit-status",
                "--interval",
                "5",
            )
        )
        return {"run_id": str(run["databaseId"]), "url": run["url"]}

    def verify_run(self, run_id, expected_commit):
        if not str(run_id or "").isdigit():
            raise GitHubError("persisted workflow run ID is invalid")
        run = self.gh_json(
            "run",
            "view",
            str(run_id),
            "--repo",
            self.slug,
            "--json",
            "databaseId,headSha,status,conclusion,url",
        )
        if (
            not isinstance(run, dict)
            or run.get("headSha") != expected_commit
            or run.get("status") != "completed"
            or run.get("conclusion") != "success"
        ):
            raise GitHubError("persisted exact-SHA workflow run is not successful")
        return {"run_id": str(run["databaseId"]), "url": run["url"]}

    def _release_cache(self, tag):
        path = self.repository / ".kodi-private/kodi-ops/github" / tag
        path.mkdir(parents=True, exist_ok=True, mode=0o700)
        path.chmod(0o700)
        return path

    def snapshot_for_commit(self, commit):
        releases = self.gh_json(
            "release",
            "list",
            "--repo",
            self.slug,
            "--limit",
            "100",
            "--json",
            "tagName,createdAt",
        )
        candidates = sorted(
            (
                item
                for item in releases
                if item["tagName"].startswith("testing-snapshot-")
            ),
            key=lambda item: item["createdAt"],
            reverse=True,
        )
        for release in candidates:
            tag = release["tagName"]
            cache = self._release_cache(tag)
            snapshot = cache / "snapshot.tar"
            if not snapshot.is_file():
                self.gh(
                    "release",
                    "download",
                    tag,
                    "--repo",
                    self.slug,
                    "--pattern",
                    "snapshot.tar",
                    "--dir",
                    str(cache),
                )
                snapshot.chmod(0o600)
            metadata = verify_bundle(snapshot)
            if metadata["repository_commit"] == commit:
                return {
                    "snapshot_id": metadata["snapshot_id"],
                    "path": snapshot,
                    "tag": tag,
                }
        raise GitHubError("no immutable testing snapshot matches release commit")

    def attestation_for_snapshot(self, snapshot):
        view = self.gh_json(
            "release",
            "view",
            snapshot["tag"],
            "--repo",
            self.slug,
            "--json",
            "assets",
        )
        names = sorted(
            item["name"]
            for item in view["assets"]
            if item["name"].startswith("device-attestation-")
            and item["name"].endswith(".json")
        )
        valid = []
        cache = self._release_cache(snapshot["tag"])
        for name in names:
            path = cache / name
            if not path.is_file():
                self.gh(
                    "release",
                    "download",
                    snapshot["tag"],
                    "--repo",
                    self.slug,
                    "--pattern",
                    name,
                    "--dir",
                    str(cache),
                )
                path.chmod(0o600)
            try:
                document = verify_attestation(path, snapshot["path"])
            except ValueError:
                continue
            valid.append((document["issued_at"], document, path))
        if not valid:
            raise GitHubError("snapshot has no currently valid device attestation")
        _issued, document, path = max(valid, key=lambda item: item[0])
        return {
            "attestation_id": document["attestation_id"],
            "attestation_sha256": hashlib.sha256(path.read_bytes()).hexdigest(),
            "path": path,
        }

    def qnap_for_snapshot(self, snapshot, candidate_id=None, expected_sha256=None):
        view = self.gh_json(
            "release",
            "view",
            snapshot["tag"],
            "--repo",
            self.slug,
            "--json",
            "assets",
        )
        expected_name = f"qnap-candidate-{candidate_id}.json" if candidate_id else None
        names = [
            item["name"]
            for item in view["assets"]
            if item["name"].startswith("qnap-candidate-")
            and item["name"].endswith(".json")
            and (expected_name is None or item["name"] == expected_name)
        ]
        if len(names) != 1:
            raise GitHubError(
                "snapshot does not contain exactly one selected QNAP candidate"
            )
        cache = self._release_cache(snapshot["tag"])
        path = cache / names[0]
        if not path.is_file():
            self.gh(
                "release",
                "download",
                snapshot["tag"],
                "--repo",
                self.slug,
                "--pattern",
                names[0],
                "--dir",
                str(cache),
            )
            path.chmod(0o600)
        observed_sha = hashlib.sha256(path.read_bytes()).hexdigest()
        if expected_sha256 and observed_sha != expected_sha256:
            raise GitHubError("QNAP candidate asset digest differs")
        document = load_qnap_lock(path)
        if candidate_id and document["candidate_id"] != candidate_id:
            raise GitHubError("QNAP candidate asset identity differs")
        return {
            "candidate_id": document["candidate_id"],
            "qnap_candidate_sha256": observed_sha,
            "path": path,
        }

    def promotion_pr(self, snapshot_id):
        branch = f"automation/promote-stable-{snapshot_id[:12]}"
        rows = self.gh_json(
            "pr",
            "list",
            "--repo",
            self.slug,
            "--head",
            branch,
            "--base",
            "main",
            "--state",
            "all",
            "--limit",
            "5",
            "--json",
            "number,state,headRefOid,mergeCommit,url,statusCheckRollup",
        )
        if len(rows) != 1:
            raise GitHubError("promotion PR was not found exactly once")
        return rows[0]

    @staticmethod
    def require_merged_pr(pr):
        if pr["state"] != "MERGED":
            return None
        checks = pr.get("statusCheckRollup") or []
        failures = [
            item
            for item in checks
            if item.get("conclusion") not in {"SUCCESS", "NEUTRAL", "SKIPPED"}
        ]
        if failures:
            raise GitHubError("promotion PR has unsuccessful required checks")
        merge = pr.get("mergeCommit") or {}
        sha = merge.get("oid")
        if not sha or len(sha) != 40:
            raise GitHubError("merged promotion PR has no exact merge commit")
        return sha

    def validate_promotion_files(self, pr_number):
        view = self.gh_json(
            "pr",
            "view",
            str(pr_number),
            "--repo",
            self.slug,
            "--json",
            "files",
        )
        names = {item["path"] for item in view["files"]}
        allowed = {
            "manifests/locks/stable.json",
            "manifests/locks/qnap-stable.json",
        }
        if "manifests/locks/stable.json" not in names or not names.issubset(allowed):
            raise GitHubError("promotion PR changed files outside approved locks")
        return sorted(names)

    def validate_promotion_content(self, pr, snapshot, attestation, qnap):
        head = pr.get("headRefOid")
        if not isinstance(head, str) or len(head) != 40:
            raise GitHubError("promotion PR has no exact head commit")

        def content(path):
            result = self.gh_json(
                "api",
                f"repos/{self.slug}/contents/{path}?ref={head}",
            )
            if not isinstance(result, dict) or result.get("encoding") != "base64":
                raise GitHubError("promotion PR content could not be verified")
            try:
                encoded = "".join(result["content"].split())
                return base64.b64decode(encoded, validate=True)
            except (KeyError, ValueError) as error:
                raise GitHubError("promotion PR content is invalid") from error

        try:
            stable = json.loads(content("manifests/locks/stable.json").decode("utf-8"))
        except (UnicodeDecodeError, json.JSONDecodeError) as error:
            raise GitHubError("promotion stable lock is invalid") from error
        expected = {
            "source_snapshot_id": snapshot["snapshot_id"],
            "attestation_id": attestation["attestation_id"],
            "attestation_sha256": attestation["attestation_sha256"],
        }
        if (
            stable.get("schema") != 2
            or stable.get("channel") != "stable"
            or any(stable.get(key) != value for key, value in expected.items())
        ):
            raise GitHubError("promotion stable lock differs from certified candidate")
        qnap_payload = content("manifests/locks/qnap-stable.json")
        if hashlib.sha256(qnap_payload).hexdigest() != qnap["qnap_candidate_sha256"]:
            raise GitHubError("promotion QNAP lock differs from approved candidate")
        try:
            qnap_document = json.loads(qnap_payload.decode("utf-8"))
        except (UnicodeDecodeError, json.JSONDecodeError) as error:
            raise GitHubError("promotion QNAP lock is invalid") from error
        if qnap_document.get("candidate_id") != qnap["candidate_id"]:
            raise GitHubError("promotion QNAP candidate identity differs")
        return {
            "head_commit": head,
            "files": self.validate_promotion_files(pr["number"]),
        }

    def wait_deploy(self, merge_commit):
        redispatched = False
        for _attempt in range(90):
            rows = self.gh_json(
                "run",
                "list",
                "--repo",
                self.slug,
                "--workflow",
                "deploy-stable.yml",
                "--branch",
                "main",
                "--limit",
                "20",
                "--json",
                "databaseId,headSha,status,conclusion,url",
            )
            matches = [item for item in rows if item.get("headSha") == merge_commit]
            if matches:
                run = max(matches, key=lambda item: item["databaseId"])
                if run["status"] == "completed":
                    if run["conclusion"] == "success":
                        return {"run_id": str(run["databaseId"]), "url": run["url"]}
                    if run["conclusion"] == "cancelled" and not redispatched:
                        # GitHub keeps at most one pending run per concurrency
                        # group. A later Pages writer can therefore replace a
                        # pending stable deployment even when
                        # cancel-in-progress is false. Retry exactly once, but
                        # only while this merge commit is still origin/main.
                        self._run(("git", "fetch", "origin", "main"))
                        remote = self._run(
                            ("git", "rev-parse", "origin/main")
                        ).stdout.strip()
                        if remote != merge_commit:
                            raise GitHubError(
                                "cancelled stable deploy is no longer current"
                            )
                        self.dispatch(
                            "deploy-stable.yml",
                            merge_commit,
                            {"dry_run": "false"},
                        )
                        redispatched = True
                        continue
                    if run["conclusion"] != "success":
                        raise GitHubError("exact stable deploy run failed")
            time.sleep(5)
        raise GitHubError("exact stable deploy run did not complete")
