import datetime as dt

from tools.upstream_watchdog import evaluate, load_manifest


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
    assert len(loaded["workflows"]) == 4
