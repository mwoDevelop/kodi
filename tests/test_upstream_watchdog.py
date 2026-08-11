import datetime as dt
import re
from pathlib import Path

from tools.upstream_watchdog import evaluate, load_manifest


SCHEDULED_WORKFLOWS = {
    ("mwoDevelop/kodi", "reconcile-upstreams.yml"): (
        Path(".github/workflows/reconcile-upstreams.yml"),
        "20 4 * * *",
    ),
    (
        "mwoDevelop/script.module.mwoscrapers",
        "check-provider-upstreams.yml",
    ): (
        Path("mwoscrapers/.github/workflows/check-provider-upstreams.yml"),
        "23 4 * * *",
    ),
    (
        "mwoDevelop/script.module.mwoscrapers",
        "discover-provider-upstreams.yml",
    ): (
        Path("mwoscrapers/.github/workflows/discover-provider-upstreams.yml"),
        "41 4 * * *",
    ),
    ("mwoDevelop/umbrellaplug.github.io", "propose-upstream-update.yml"): (
        Path("umbrella/.github/workflows/propose-upstream-update.yml"),
        "50 4 * * *",
    ),
    (
        "mwoDevelop/ch.repo",
        "mwodevelop-watchnixtoons2-update.yml",
    ): (
        Path(
            "watchnixtoons2/.github/workflows/"
            "mwodevelop-watchnixtoons2-update.yml"
        ),
        "35 4 * * *",
    ),
}


def _manifest():
    return {
        "schema": 1,
        "max_age_hours": 36,
        "workflows": [
            {"repository": "owner/repo", "workflow": "sync.yml"},
        ],
    }


def test_watchdog_accepts_recent_success_and_active_run():
    now = dt.datetime(2026, 7, 29, 12, tzinfo=dt.timezone.utc)

    def fetch(_repository, _workflow, token=None):
        assert token == "token"
        return [
            {
                "id": 42,
                "status": "completed",
                "conclusion": "success",
                "updated_at": "2026-07-29T11:00:00Z",
            }
        ]

    report = evaluate(_manifest(), fetcher=fetch, now=now, token="token")

    assert report["healthy"] is True
    assert report["workflows"][0]["age_seconds"] == 3600


def test_watchdog_rejects_failure_and_stale_success():
    now = dt.datetime(2026, 7, 29, 12, tzinfo=dt.timezone.utc)
    values = iter(
        [
            {
                "id": 1,
                "status": "completed",
                "conclusion": "failure",
                "updated_at": "2026-07-29T11:00:00Z",
            },
            {
                "id": 2,
                "status": "completed",
                "conclusion": "success",
                "updated_at": "2026-07-27T11:00:00Z",
            },
        ]
    )
    manifest = _manifest()
    manifest["workflows"].append(
        {"repository": "owner/other", "workflow": "sync.yml"}
    )

    report = evaluate(
        manifest,
        fetcher=lambda *_args, **_kwargs: [next(values)],
        now=now,
    )

    assert report["healthy"] is False
    assert [item["healthy"] for item in report["workflows"]] == [False, False]


def test_versioned_manifest_is_valid():
    loaded = load_manifest("manifests/upstream-watchdog.json")
    assert len(loaded["workflows"]) == 5
    assert {
        (item["repository"], item["workflow"])
        for item in loaded["workflows"]
    } == set(SCHEDULED_WORKFLOWS)


def test_scheduled_process_catalog_matches_workflows():
    catalogue = Path("docs/scheduled-processes.md").read_text(
        encoding="utf-8"
    )
    for (_repository, workflow), (path, cron) in SCHEDULED_WORKFLOWS.items():
        source = path.read_text(encoding="utf-8")
        assert re.search(
            r'^\s*-\s+cron:\s*["\']%s["\']\s*$' % re.escape(cron),
            source,
            flags=re.MULTILINE,
        )
        minute, hour, _day, _month, _weekday = cron.split()
        assert workflow in catalogue
        assert "%s:%s codziennie" % (
            hour.zfill(2),
            minute.zfill(2),
        ) in catalogue
