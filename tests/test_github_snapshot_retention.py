import datetime as dt
import io
import json
from pathlib import Path
import zipfile

import pytest

from tools import github_snapshot_retention as retention
from tools.qualification_attestation import create
from tools.snapshot_bundle import create_bundle


NOW = dt.datetime(2026, 9, 8, tzinfo=dt.timezone.utc)
OLD = "2026-07-01T00:00:00Z"


class FakeGitHub:
    def __init__(self, tmp_path):
        dist = tmp_path / "dist"
        (dist / "testing/omega").mkdir(parents=True)
        (dist / "testing/omega/addons.xml").write_text("<addons/>")
        (dist / "artifact-manifest.sha256").write_text("manifest\n")
        lock = tmp_path / "lock.json"
        lock.write_text(json.dumps({"schema": 1, "channel": "testing", "components": {}}))
        snapshot = tmp_path / "snapshot.tar"
        meta = create_bundle(dist, lock, "a" * 40, snapshot)
        report = tmp_path / "report.json"
        report.write_text(json.dumps({
            "schema": 1, "qualification_type": "hermetic_ci",
            "component": "plugin.video.umbrella", "result": "passed",
            "checks": [{"name": "regression", "result": "passed", "evidence_sha256": "b" * 64}],
        }))
        attestation = tmp_path / "qualification.json"
        create(snapshot, report, retention.REPO, "a" * 40, "22", 1, "ab" * 32,
               OLD, "2026-07-02T00:00:00Z", attestation)
        payload = io.BytesIO()
        with zipfile.ZipFile(payload, "w") as archive:
            archive.writestr("snapshot.tar", snapshot.read_bytes())
            archive.writestr("security-report.json", b'{"status":"passed"}')
        archive_path = tmp_path / "original.zip"
        archive_path.write_bytes(payload.getvalue())
        self.artifact = {
            "id": 10, "name": "testing-snapshot", "expired": False, "created_at": OLD,
            "size_in_bytes": len(payload.getvalue()), "workflow_run": {"id": 20},
            "digest": "sha256:" + retention.digest(archive_path),
        }
        self.source = {"id": 20, "status": "completed", "conclusion": "success",
                       "updated_at": OLD, "path": ".github/workflows/publish-testing.yml",
                       "head_branch": "main", "head_sha": "a" * 40, "run_attempt": 1}
        self.certification = {**self.source, "id": 22,
                              "path": ".github/workflows/certify-umbrella-hermetic.yml"}
        self.jobs = [{"name": "snapshot-writer", "conclusion": "success"}]
        self.related = []
        self.active = []
        self.release = {
            "id": 30, "tag_name": "testing-snapshot-" + meta["snapshot_id"],
            "draft": False, "immutable": False,
            "assets": [{"id": 31, "name": "snapshot.tar"},
                       {"id": 32, "name": "security-report.json"},
                       {"id": 33, "name": "qualification-attestation.json"}],
        }
        self.downloads = {
            "actions/artifacts/10/zip": payload.getvalue(),
            "releases/assets/31": snapshot.read_bytes(),
            "releases/assets/32": b'{"status":"passed"}',
            "releases/assets/33": attestation.read_bytes(),
        }
        self.deleted = []

    def api(self, endpoint, method="GET"):
        if method == "DELETE":
            self.deleted.append(endpoint)
            return None
        if endpoint in self.deleted:
            raise retention.NotFound("deleted")
        if endpoint.startswith("releases/tags/"):
            return self.release
        return {"actions/artifacts/10": self.artifact, "actions/runs/20": self.source,
                "actions/runs/22": self.certification}[endpoint]

    def pages(self, endpoint, key=None):
        if "status=" in endpoint:
            return self.active
        if "/jobs?" in endpoint:
            return self.jobs
        return self.related

    def download(self, endpoint, path):
        path.write_bytes(self.downloads[endpoint])


def plan(api, backups):
    return {"schema": 1, "repository": retention.REPO, "created_at": NOW.isoformat(),
            "artifacts": [retention.prove(api, 10, NOW, backups)], "protected": []}


def test_plan_and_apply_retains_verified_backup_and_uses_exact_id(tmp_path):
    api = FakeGitHub(tmp_path)
    backups = tmp_path / "backups"
    doc = plan(api, backups)
    assert api.deleted == []
    assert retention.digest(backups / "10/transport.zip") == doc["artifacts"][0]["zip_sha256"]
    assert (backups / "10/evidence.json").exists()
    assert retention.apply_plan(api, doc, retention.document_digest(doc), NOW, backups) == [10]
    assert api.deleted == ["actions/artifacts/10"]
    assert (backups / "10/snapshot.tar").exists()


@pytest.mark.parametrize("change", ["age", "failed", "wrong_branch", "wrong_path",
                                   "failed_consumer", "active_consumer", "changed_report",
                                   "no_attestation", "changed_archive", "different_commit"])
def test_fail_closed_protections(tmp_path, change):
    api = FakeGitHub(tmp_path)
    if change == "age":
        api.source["updated_at"] = NOW.isoformat()
    elif change == "failed":
        api.source["conclusion"] = "failure"
    elif change == "wrong_branch":
        api.source["head_branch"] = "untrusted"
    elif change == "wrong_path":
        api.source["path"] = ".github/workflows/other.yml"
    elif change in {"failed_consumer", "active_consumer"}:
        api.related = [{**api.certification,
                        "conclusion": "failure" if change == "failed_consumer" else None}]
    elif change == "changed_report":
        api.downloads["releases/assets/32"] = b"changed"
    elif change == "no_attestation":
        api.release["assets"].pop()
    elif change == "changed_archive":
        api.artifact["digest"] = "sha256:" + "f" * 64
    elif change == "different_commit":
        api.source["head_sha"] = "b" * 40
    with pytest.raises((retention.RetentionError, ValueError)):
        plan(api, tmp_path / "backups")
    assert api.deleted == []


@pytest.mark.parametrize("change", ["approval", "old_plan", "source_rerun", "release_swap",
                                   "active", "corrupt_backup", "duplicate"])
def test_apply_rechecks_plan_and_live_evidence(tmp_path, change):
    api = FakeGitHub(tmp_path)
    backups = tmp_path / "backups"
    doc = plan(api, backups)
    now = NOW
    if change == "old_plan":
        now += dt.timedelta(days=2)
    elif change == "source_rerun":
        api.source["run_attempt"] = 2
    elif change == "release_swap":
        api.downloads["releases/assets/31"] = b"different snapshot"
    elif change == "active":
        api.active = [api.certification]
    elif change == "corrupt_backup":
        (backups / "10/transport.zip").write_bytes(b"corrupt")
    elif change == "duplicate":
        doc["artifacts"] *= 2
    approval = "wrong" if change == "approval" else retention.document_digest(doc)
    with pytest.raises(retention.RetentionError):
        retention.apply_plan(api, doc, approval, now, backups)
    assert api.deleted == []


@pytest.mark.parametrize("names", [["../snapshot.tar", "security-report.json"],
                                   ["snapshot.tar", "snapshot.tar", "security-report.json"]])
def test_archive_paths_and_duplicate_members_rejected(tmp_path, names):
    path = tmp_path / "unsafe.zip"
    with zipfile.ZipFile(path, "w") as archive:
        for name in names:
            archive.writestr(name, b"test")
    with pytest.raises(retention.RetentionError):
        retention.unpack_backup(path, tmp_path)


def test_missing_artifact_is_only_noop_for_confirmed_skipped_writer():
    source = {"status": "completed", "conclusion": "success", "head_branch": "main",
              "path": ".github/workflows/publish-testing.yml"}
    jobs = [{"name": "snapshot-writer", "conclusion": "skipped"},
            {"name": "build", "conclusion": "success", "steps": [
                {"name": "Create immutable snapshot bundle", "conclusion": "skipped"},
                {"name": "Upload snapshot for the isolated writer", "conclusion": "skipped"}]}]
    assert retention.missing_snapshot_is_noop(source, jobs)
    for change in [{"conclusion": "failure"}, {"status": "in_progress"}, {"head_branch": "other"}]:
        with pytest.raises(retention.RetentionError):
            retention.missing_snapshot_is_noop({**source, **change}, jobs)
    for jobs in [[], [{"name": "snapshot-writer", "conclusion": "success"}],
                 [{"name": "snapshot-writer", "conclusion": "failure"}],
                 [{"name": "snapshot-writer", "conclusion": "skipped"}]]:
        with pytest.raises(retention.RetentionError, match="workflow_dispatch"):
            retention.missing_snapshot_is_noop(source, jobs)


def test_workflow_checks_missing_artifact_before_noop():
    workflow = (Path(__file__).parents[1] / ".github/workflows/certify-umbrella-hermetic.yml").read_text()
    block = workflow.split('if [ "$count" -eq 0 ]; then', 1)[1].split("fi", 1)[0]
    assert block.index("github_snapshot_retention.py check-missing") < block.index("available=false")
    assert "retention-days: 90" in (Path(__file__).parents[1] / ".github/workflows/publish-testing.yml").read_text()


def test_post_delete_readback_requires_absence_and_unchanged_release(tmp_path):
    api = FakeGitHub(tmp_path)
    backups = tmp_path / "backups"
    row = plan(api, backups)["artifacts"][0]
    with pytest.raises(retention.RetentionError, match="has not been observed"):
        retention.confirm_deleted(api, row, backups)
    api.deleted = ["actions/artifacts/10"]
    api.downloads["releases/assets/32"] = b"changed"
    with pytest.raises(retention.RetentionError, match="digest differs"):
        retention.confirm_deleted(api, row, backups)
    assert (backups / "10/security-report.json").read_bytes() == b'{"status":"passed"}'
