import datetime as dt
import json
import re
from pathlib import Path

from tools import upstream_watchdog
from tools.control_plane_catalog import (
    compare_watchdog,
    load_schedules,
    load_severity_policy,
    load_status_sources,
)
from tools.upstream_watchdog import evaluate, fetch_runs, load_manifest, validate_status

SCHEDULED_WORKFLOWS = {
    ("mwoDevelop/kodi", "reconcile-upstreams.yml"): (
        Path(".github/workflows/reconcile-upstreams.yml"),
        "20 4 * * *",
        "04:20 codziennie",
    ),
    ("mwoDevelop/kodi", "approve-umbrella-update.yml"): (
        Path(".github/workflows/approve-umbrella-update.yml"),
        "*/15 * * * *",
        "co 15 minut",
    ),
    ("mwoDevelop/kodi", "approve-umbrella-promotion.yml"): (
        Path(".github/workflows/approve-umbrella-promotion.yml"),
        "7,37 * * * *",
        "co 30 minut",
    ),
    ("mwoDevelop/kodi", "publish-pages.yml"): (
        Path(".github/workflows/publish-pages.yml"),
        "10 3 * * *",
        "03:10 codziennie",
    ),
    ("mwoDevelop/kodi", "check-youtube-upstream.yml"): (
        Path(".github/workflows/check-youtube-upstream.yml"),
        "29 4 * * *",
        "04:29 codziennie",
    ),
    (
        "mwoDevelop/script.module.mwoscrapers",
        "check-provider-upstreams.yml",
    ): (
        Path("mwoscrapers/.github/workflows/check-provider-upstreams.yml"),
        "23 4 * * *",
        "04:23 codziennie",
    ),
    (
        "mwoDevelop/script.module.mwoscrapers",
        "discover-provider-upstreams.yml",
    ): (
        Path("mwoscrapers/.github/workflows/discover-provider-upstreams.yml"),
        "41 4 * * *",
        "04:41 codziennie",
    ),
    (
        "mwoDevelop/script.module.mwoscrapers",
        "probe-provider-health.yml",
    ): (
        Path("mwoscrapers/.github/workflows/probe-provider-health.yml"),
        "3 5 * * *",
        "05:03 codziennie",
    ),
    ("mwoDevelop/umbrellaplug.github.io", "propose-upstream-update.yml"): (
        Path("umbrella/.github/workflows/propose-upstream-update.yml"),
        "50 4 * * *",
        "04:50 codziennie",
    ),
    ("mwoDevelop/umbrellaplug.github.io", "approve-upstream-update.yml"): (
        Path("umbrella/.github/workflows/approve-upstream-update.yml"),
        "2,17,32,47 * * * *",
        "co 15 minut",
    ),
    (
        "mwoDevelop/ch.repo",
        "mwodevelop-watchnixtoons2-update.yml",
    ): (
        Path("watchnixtoons2/.github/workflows/mwodevelop-watchnixtoons2-update.yml"),
        "35 4 * * *",
        "04:35 codziennie",
    ),
}


def _manifest():
    return {
        "schema": 2,
        "workflows": [
            {
                "repository": "owner/repo",
                "workflow": "sync.yml",
                "max_age_seconds": 129600,
            },
        ],
    }


def test_watchdog_accepts_recent_success_and_active_run():
    now = dt.datetime(2026, 7, 29, 12, tzinfo=dt.timezone.utc)

    def fetch(_repository, _workflow, token=None):
        assert token == "token"
        return [
            {
                "id": 42,
                "event": "schedule",
                "status": "completed",
                "conclusion": "success",
                "updated_at": "2026-07-29T11:00:00Z",
            }
        ]

    report = evaluate(_manifest(), fetcher=fetch, now=now, token="token")

    assert report["healthy"] is True
    assert report["observer_ready"] is True
    assert report["collection_state"] == "READY"
    assert report["monitored_state"] == "HEALTHY"
    assert report["workflows"][0]["age_seconds"] == 3600


def test_watchdog_fetches_schedule_and_manual_remediation_runs(monkeypatch):
    observed = {}

    class Response:
        def __enter__(self):
            return self

        def __exit__(self, *_args):
            return None

        def read(self):
            return b'{"workflow_runs":[]}'

    def open_request(request, timeout):
        observed["url"] = request.full_url
        observed["timeout"] = timeout
        return Response()

    monkeypatch.setattr(upstream_watchdog, "urlopen", open_request)
    assert fetch_runs("owner/repo", "sync.yml") == []
    assert "event=" not in observed["url"]
    assert "per_page=20" in observed["url"]
    assert observed["timeout"] == 20


def test_watchdog_rejects_failure_and_stale_success():
    now = dt.datetime(2026, 7, 29, 12, tzinfo=dt.timezone.utc)
    values = iter(
        [
            {
                "id": 1,
                "event": "schedule",
                "status": "completed",
                "conclusion": "failure",
                "updated_at": "2026-07-29T11:00:00Z",
            },
            {
                "id": 2,
                "event": "schedule",
                "status": "completed",
                "conclusion": "success",
                "updated_at": "2026-07-27T11:00:00Z",
            },
        ]
    )
    manifest = _manifest()
    manifest["workflows"].append(
        {
            "repository": "owner/other",
            "workflow": "sync.yml",
            "max_age_seconds": 129600,
        }
    )

    report = evaluate(
        manifest,
        fetcher=lambda *_args, **_kwargs: [next(values)],
        now=now,
    )

    assert report["healthy"] is False
    assert report["observer_ready"] is True
    assert report["collection_state"] == "READY"
    assert report["monitored_state"] == "FAILED"
    assert [item["healthy"] for item in report["workflows"]] == [False, False]


def test_watchdog_accepts_newer_manual_success_without_hiding_scheduler():
    now = dt.datetime(2026, 8, 22, 8, tzinfo=dt.timezone.utc)

    def fetch(_repository, _workflow, token=None):
        return [
            {
                "id": 2,
                "event": "workflow_dispatch",
                "status": "completed",
                "conclusion": "success",
                "updated_at": "2026-08-22T07:30:00Z",
            },
            {
                "id": 1,
                "event": "schedule",
                "status": "completed",
                "conclusion": "failure",
                "updated_at": "2026-08-22T05:05:00Z",
            },
        ]

    report = evaluate(_manifest(), fetcher=fetch, now=now)

    assert report["healthy"] is True
    item = report["workflows"][0]
    assert item["run_id"] == 2
    assert item["run_event"] == "workflow_dispatch"
    assert item["latest_scheduled_run"]["id"] == 1


def test_watchdog_manual_run_cannot_replace_missing_scheduler():
    now = dt.datetime(2026, 8, 22, 8, tzinfo=dt.timezone.utc)

    def fetch(_repository, _workflow, token=None):
        return [
            {
                "id": 2,
                "event": "workflow_dispatch",
                "status": "completed",
                "conclusion": "success",
                "updated_at": "2026-08-22T07:30:00Z",
            }
        ]

    report = evaluate(_manifest(), fetcher=fetch, now=now)

    assert report["healthy"] is False
    assert report["workflows"][0]["status"] == "missing"


def test_watchdog_ignores_cancelled_manual_run_after_successful_schedule():
    now = dt.datetime(2026, 8, 22, 8, tzinfo=dt.timezone.utc)

    def fetch(_repository, _workflow, token=None):
        return [
            {
                "id": 2,
                "event": "workflow_dispatch",
                "status": "completed",
                "conclusion": "cancelled",
                "updated_at": "2026-08-22T07:30:00Z",
            },
            {
                "id": 1,
                "event": "schedule",
                "status": "completed",
                "conclusion": "success",
                "updated_at": "2026-08-22T05:05:00Z",
            },
        ]

    report = evaluate(_manifest(), fetcher=fetch, now=now)

    assert report["healthy"] is True
    assert report["workflows"][0]["run_id"] == 1
    assert report["workflows"][0]["run_event"] == "schedule"


def test_watchdog_publishes_complete_fail_closed_report_on_api_error():
    manifest = _manifest()
    manifest["workflows"].append(
        {
            "repository": "owner/other",
            "workflow": "other.yml",
            "max_age_seconds": 129600,
        }
    )

    def fetch(repository, _workflow, token=None):
        if repository == "owner/repo":
            raise OSError("rate limited response with sensitive detail")
        return []

    report = evaluate(manifest, fetcher=fetch)

    assert report["healthy"] is False
    assert report["observer_ready"] is False
    assert report["collection_state"] == "PARTIAL"
    assert report["monitored_state"] == "UNKNOWN"
    assert len(report["workflows"]) == 2
    assert report["workflows"][0] == {
        **manifest["workflows"][0],
        "status": "api_error",
        "healthy": False,
        "monitored_state": "UNKNOWN",
    }
    assert report["workflows"][1]["status"] == "missing"
    assert "sensitive" not in json.dumps(report)


def test_watchdog_health_validates_observer_not_monitored_result():
    now = dt.datetime(2026, 8, 26, 10, tzinfo=dt.timezone.utc)
    report = {
        "schema": 2,
        "checked_at": "2026-08-26T09:59:00+00:00",
        "observer_ready": True,
        "collection_state": "READY",
        "monitored_state": "FAILED",
        "healthy": False,
        "workflows": [
            {
                **_manifest()["workflows"][0],
                "status": "completed",
                "healthy": False,
                "monitored_state": "FAILED",
            }
        ],
    }

    assert validate_status(report, _manifest(), now=now)

    report["observer_ready"] = False
    report["collection_state"] = "PARTIAL"
    report["monitored_state"] = "UNKNOWN"
    assert not validate_status(report, _manifest(), now=now)


def test_watchdog_health_rejects_stale_future_and_incomplete_reports():
    now = dt.datetime(2026, 8, 26, 10, tzinfo=dt.timezone.utc)
    report = evaluate(
        _manifest(),
        fetcher=lambda *_args, **_kwargs: [
            {
                "id": 1,
                "event": "schedule",
                "status": "completed",
                "conclusion": "success",
                "updated_at": "2026-08-26T09:59:00Z",
            }
        ],
        now=now,
    )
    assert validate_status(report, _manifest(), now=now)

    report["checked_at"] = "2026-08-25T00:00:00Z"
    assert not validate_status(report, _manifest(), now=now)
    report["checked_at"] = "2026-08-26T10:06:00Z"
    assert not validate_status(report, _manifest(), now=now)
    report["checked_at"] = "2026-08-26T09:59:00Z"
    report["workflows"] = []
    assert not validate_status(report, _manifest(), now=now)


def test_versioned_manifest_is_valid():
    loaded = load_manifest("manifests/upstream-watchdog.json")
    assert len(loaded["workflows"]) == 11
    assert {
        (item["repository"], item["workflow"]) for item in loaded["workflows"]
    } == set(SCHEDULED_WORKFLOWS)


def test_control_plane_catalogs_are_valid_and_watchdog_thresholds_match():
    schedules = load_schedules("manifests/control-plane-schedules.json")
    sources = load_status_sources("manifests/control-plane-status-sources.json")
    severity = load_severity_policy("manifests/control-plane-severity-policy.json")
    compare_watchdog(schedules, "manifests/upstream-watchdog.json")

    github_jobs = [
        item for item in schedules["jobs"] if item["kind"] == "github_actions"
    ]
    assert len(github_jobs) == 11
    assert len(sources["sources"]) == 6
    assert len(severity["rules"]) == 7
    assert {(item["repository"], item["workflow"]) for item in github_jobs} == set(
        SCHEDULED_WORKFLOWS
    )


def test_scheduled_process_catalog_matches_workflows():
    catalogue = Path("docs/scheduled-processes.md").read_text(encoding="utf-8")
    for (_repository, workflow), (path, cron, marker) in SCHEDULED_WORKFLOWS.items():
        source = path.read_text(encoding="utf-8")
        assert re.search(
            rf'^\s*-\s+cron:\s*["\']{re.escape(cron)}["\']\s*$',
            source,
            flags=re.MULTILINE,
        )
        assert workflow in catalogue
        assert marker in catalogue

    schedules = load_schedules("manifests/control-plane-schedules.json")
    indexed = {
        (item["repository"], item["workflow"]): item
        for item in schedules["jobs"]
        if item["kind"] == "github_actions"
    }
    for identity, (_path, cron, _marker) in SCHEDULED_WORKFLOWS.items():
        assert cron in indexed[identity]["cron"]
        source = SCHEDULED_WORKFLOWS[identity][0].read_text(encoding="utf-8")
        configured = set(
            re.findall(r'^\s*-\s+cron:\s*["\']([^"\']+)["\']\s*$', source, re.MULTILINE)
        )
        assert configured == set(indexed[identity]["cron"])


def test_youtube_upstream_scans_zip_and_expanded_tree_before_review_pr():
    workflow = Path(".github/workflows/check-youtube-upstream.yml").read_text(
        encoding="utf-8"
    )
    assert "candidate-path: youtube-upstream-candidate" in workflow
    assert "baseline: security/youtube-7.4.4-baseline.json" in workflow
    assert "tools/upstream_security_scan.py verify" in workflow
    assert workflow.count("tools/upstream_security_scan.py verify") == 2
    assert "tools/youtube_upstream_check.py apply" in workflow
    assert "automation/youtube-upstream" in workflow
    assert "gh pr create" in workflow
    assert "gh pr merge" not in workflow
    assert "pull_request:" in workflow
    assert "github.event_name != 'pull_request'" in workflow


def test_youtube_security_baseline_is_exact_file_bound():
    baseline = json.loads(
        Path("security/youtube-7.4.4-baseline.json").read_text(encoding="utf-8")
    )
    assert baseline["schema"] == 1
    assert len(baseline["findings"]) == 4
    assert all(
        set(item) == {"engine", "path", "rule", "sha256"}
        and item["engine"] == "gitleaks"
        and item["path"].startswith("expanded/plugin.video.youtube/")
        and len(item["sha256"]) == 64
        for item in baseline["findings"]
    )
