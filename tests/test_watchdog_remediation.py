import datetime as dt
import json
from pathlib import Path

import pytest

from tools import qnap_images
from tools import watchdog_remediation as retry
from tools.upstream_watchdog import evaluate

NOW = dt.datetime(2026, 9, 8, 12, tzinfo=dt.timezone.utc)
KEY = ("owner/repo", "sync.yml", "main")
MANIFEST = {
    "workflows": [
        {
            "repository": KEY[0],
            "workflow": KEY[1],
            "ref": KEY[2],
            "max_age_seconds": 129600,
            "remediation_after_seconds": 90000,
            "remediation_cooldown_seconds": 900,
        }
    ]
}


def run(ident=1, ago=3600, event="schedule", conclusion="failure", branch="main"):
    return {
        "id": ident,
        "run_attempt": 1,
        "head_branch": branch,
        "event": event,
        "conclusion": conclusion,
        "status": "completed",
        "updated_at": (NOW - dt.timedelta(seconds=ago)).isoformat(),
        "check_suite_id": 20,
    }


def ledger(tmp_path, category="BILLING_BLOCKED"):
    path = tmp_path / "attempts.json"
    retry.RetryLedger.initialize(path)
    return retry.RetryLedger(path, classifier=lambda *a, **kw: category)


def evaluate_at(guard, runs, now=NOW, dispatch=None):
    return evaluate(
        MANIFEST,
        fetcher=lambda *a, **kw: runs,
        now=now,
        retry_ledger=guard,
        remediator=dispatch or (lambda *a, **kw: None),
    )


def test_billing_failed_manual_is_not_ignored_and_other_ref_success_does_not_clear(
    tmp_path,
):
    guard = ledger(tmp_path)
    runs = [
        run(3, ago=0, conclusion="success", branch="testing"),
        run(2, ago=60, event="workflow_dispatch"),
        run(1, ago=3600, conclusion="success"),
    ]
    report = evaluate_at(guard, runs)
    item = report["workflows"][0]
    assert item["failure_category"] == "BILLING_BLOCKED"
    assert item["remediation_state"] == "NOT_DUE"
    # Health selection remains independent; old successful schedule is still fresh.
    assert item["run_id"] == 1
    guard.close()


def test_retry_survives_restart_and_reserves_before_ambiguous_post(tmp_path):
    guard = ledger(tmp_path)
    calls = []
    runs = [run(ago=retry.DAY + 10)]

    def dispatch(*args, **kwargs):
        persisted = json.loads(guard.path.read_text())
        assert persisted["entries"][json.dumps(KEY)]["attempts"] == [NOW.isoformat()]
        calls.append(1)
        raise OSError("response lost")

    first = evaluate_at(guard, runs, dispatch=dispatch)
    assert first["workflows"][0]["remediation_state"] == "FAILED"
    assert first["healthy"] is False
    guard.close()
    guard = retry.RetryLedger(
        tmp_path / "attempts.json", classifier=lambda *a, **k: "BILLING_BLOCKED"
    )
    for delta in (60, 3600, retry.DAY - 1):
        report = evaluate_at(guard, runs, NOW + dt.timedelta(seconds=delta), dispatch)
        assert report["workflows"][0]["remediation_state"] == "NOT_DUE"
    assert len(calls) == 1
    assert (
        evaluate_at(guard, runs, NOW + dt.timedelta(seconds=retry.DAY))["workflows"][0][
            "remediation_state"
        ]
        == "DISPATCHED"
    )
    guard.close()


def test_new_success_clears_billing_but_does_not_erase_rolling_budget(tmp_path):
    guard = ledger(tmp_path)
    evaluate_at(guard, [run(ago=90000)])
    report = evaluate_at(
        guard,
        [run(2, ago=-60, conclusion="success"), run(ago=90000)],
        NOW + dt.timedelta(minutes=1),
    )
    assert report["workflows"][0]["failure_category"] == "NONE"
    entry = guard.entries[json.dumps(KEY)]
    assert entry["blocked_at"] is None
    assert len(entry["attempts"]) == 1
    guard.close()


def test_normal_failures_have_three_attempts_maximum_per_day(tmp_path):
    guard = ledger(tmp_path, "OTHER_FAILURE")
    for minutes in (0, 15, 30):
        item = evaluate_at(guard, [run()], NOW + dt.timedelta(minutes=minutes))[
            "workflows"
        ][0]
        assert item["remediation_state"] == "DISPATCHED"
    item = evaluate_at(guard, [run()], NOW + dt.timedelta(minutes=45))["workflows"][0]
    assert item["remediation_state"] == "RETRY_BUDGET_EXHAUSTED"
    assert not item["healthy"]
    guard.close()


def test_unavailable_annotations_preserve_block_and_do_not_postpone_deadline(tmp_path):
    guard = ledger(tmp_path)
    evaluate_at(guard, [run(ago=90000)])

    def unavailable(*a, **kw):
        raise OSError("forbidden")

    guard.classifier = unavailable
    runs = [run(2, ago=30, event="workflow_dispatch"), run(ago=90000)]
    item = evaluate_at(guard, runs)["workflows"][0]
    assert item["failure_observation"] == "UNAVAILABLE"
    assert item["failure_category"] == "BILLING_BLOCKED"
    # Do not replace persisted attempt with observation time on each poll.
    assert guard.entries[json.dumps(KEY)]["attempts"] == [NOW.isoformat()]
    item = evaluate_at(guard, runs, NOW + dt.timedelta(days=1))["workflows"][0]
    assert item["remediation_state"] == "DISPATCHED"
    guard.close()


def test_unknown_cause_uses_daily_cooldown_without_claiming_billing(tmp_path):
    guard = ledger(tmp_path, "NOT_OBSERVED")
    evaluate_at(guard, [run()])
    item = evaluate_at(guard, [run()], NOW + dt.timedelta(minutes=15))["workflows"][0]
    assert item["failure_category"] == "NOT_OBSERVED"
    assert item["remediation_state"] == "NOT_DUE"
    guard.close()


@pytest.mark.parametrize(
    "text",
    [
        None,
        "{",
        '{"schema":2,"entries":{}}',
        json.dumps(
            {
                "schema": 1,
                "entries": {
                    json.dumps(KEY): {"attempts": ["not-a-date"], "blocked_at": None}
                },
            }
        ),
        json.dumps(
            {
                "schema": 1,
                "entries": {
                    json.dumps(KEY): {
                        "attempts": ["2026-09-08T12:00:00"],
                        "blocked_at": None,
                    }
                },
            }
        ),
    ],
)
def test_missing_or_corrupt_state_fails_closed_without_hiding_observation(
    tmp_path, text
):
    path = tmp_path / "attempts.json"
    if text is not None:
        path.write_text(text)
    guard = retry.RetryLedger(path, classifier=lambda *a, **k: "OTHER_FAILURE")
    calls = []
    report = evaluate_at(guard, [run()], dispatch=lambda *a, **k: calls.append(1))
    assert not calls
    assert report["observer_ready"] is True
    assert report["remediation_ready"] is False
    assert report["workflows"][0]["remediation_state"] == "LEDGER_UNAVAILABLE"
    assert path.read_text() == text if text is not None else not path.exists()
    guard.close()


def test_write_failure_blocks_post(tmp_path, monkeypatch):
    guard = ledger(tmp_path, "OTHER_FAILURE")

    def broken(*a, **k):
        raise OSError("disk full")

    monkeypatch.setattr(retry, "atomic_write", broken)
    calls = []
    report = evaluate_at(guard, [run()], dispatch=lambda *a, **k: calls.append(1))
    assert not calls
    assert report["remediation_ready"] is False
    assert report["workflows"][0]["remediation_state"] == "LEDGER_UNAVAILABLE"
    guard.close()


def test_single_writer_and_explicit_initialization(tmp_path):
    first = ledger(tmp_path)
    second = retry.RetryLedger(first.path)
    assert first.ready and not second.ready
    second.close()
    with pytest.raises(ValueError, match="reset"):
        retry.RetryLedger.initialize(first.path)
    first.close()
    third = retry.RetryLedger(first.path)
    assert third.ready
    assert first.path.stat().st_mode & 0o777 == 0o600
    third.close()


def test_atomic_write_fsyncs_file_and_parent(tmp_path, monkeypatch):
    original = retry.os.fsync
    fds = []

    def observe(fd):
        fds.append(fd)
        original(fd)

    monkeypatch.setattr(retry.os, "fsync", observe)
    retry.RetryLedger.initialize(tmp_path / "attempts.json")
    assert len(fds) == 2


def test_classifier_uses_fixed_api_paths_and_does_not_retain_text(monkeypatch):
    calls = []

    def get(repo, path, token):
        calls.append(path)
        if "check-suites" in path:
            return {
                "total_count": 1,
                "check_runs": [
                    {
                        "id": 30,
                        "app": {"slug": "github-actions"},
                        "output": {
                            "annotations_count": 1,
                            "annotations_url": "http://private/secret",
                        },
                    }
                ],
            }
        return [
            {
                "annotation_level": "failure",
                "message": "The job was not started because an Actions budget is preventing further use.",
            }
        ]

    monkeypatch.setattr(retry, "_get", get)
    assert retry.classify_failure(KEY[0], run()) == "BILLING_BLOCKED"
    assert calls == [
        "/check-suites/20/check-runs?per_page=100",
        "/check-runs/30/annotations?per_page=100",
    ]


def test_classifier_does_not_call_failure_a_billing_error(monkeypatch):
    monkeypatch.setattr(retry, "_get", lambda *a: {"total_count": 0, "check_runs": []})
    assert retry.classify_failure(KEY[0], run()) == "NOT_OBSERVED"
    with pytest.raises(ValueError):
        retry.classify_failure(KEY[0], {"id": 10})


def test_classifier_caches_only_complete_observations_per_attempt(tmp_path):
    guard = ledger(tmp_path)
    calls = []

    def classify(*a, **k):
        calls.append(1)
        return "BILLING_BLOCKED"

    guard.classifier = classify
    for _ in range(3):
        evaluate_at(guard, [run()])
    evaluate_at(guard, [{**run(), "run_attempt": 2}])
    assert len(calls) == 2
    guard.close()


def test_rollback_disables_remediation():
    text = (Path("deploy/qnap-upstream-watchdog/compose.yaml")).read_text()
    result = qnap_images.watchdog_observation_only(text)
    assert "--remediate" not in result
    assert "--listen" in result
    assert "--remediation-ledger" in result
    with pytest.raises(qnap_images.ImageError):
        qnap_images.watchdog_observation_only("command: [watch, --remediate]")


def test_provision_refuses_lost_existing_ledger():
    class Session:
        def execute(self, command):
            assert command.startswith("if test -f")
            return "missing"

    with pytest.raises(qnap_images.ImageError, match="lost"):
        qnap_images.prepare_watchdog_ledger(Session(), "docker", "image", "")


def test_unknown_ref_cannot_clear_billing(tmp_path):
    guard = ledger(tmp_path)
    evaluate_at(guard, [run()])
    incomplete = run(2, ago=-60, conclusion="success")
    del incomplete["head_branch"]
    report = evaluate_at(guard, [incomplete, run()])
    assert report["workflows"][0]["monitored_state"] == "UNKNOWN"
    assert guard.entries[json.dumps(KEY)]["blocked_at"] is not None
    guard.close()


@pytest.mark.parametrize("value", [False, 0, "", [], {}])
def test_semantically_invalid_block_date_is_rejected(tmp_path, value):
    path = tmp_path / "attempts.json"
    path.write_text(
        json.dumps(
            {
                "schema": 1,
                "entries": {json.dumps(KEY): {"attempts": [], "blocked_at": value}},
            }
        )
    )
    guard = retry.RetryLedger(path)
    assert not guard.ready
    guard.close()


def test_lost_file_is_not_silently_recreated(tmp_path):
    guard = ledger(tmp_path, "OTHER_FAILURE")
    guard.path.unlink()
    calls = []
    report = evaluate_at(guard, [run()], dispatch=lambda *a, **k: calls.append(1))
    assert not guard.path.exists() and not calls
    assert not report["remediation_ready"]
    guard.close()


def test_temporarily_empty_annotations_are_retried(tmp_path):
    guard = ledger(tmp_path)
    values = iter(["NOT_OBSERVED", "BILLING_BLOCKED"])
    guard.classifier = lambda *a, **k: next(values)
    assert (
        evaluate_at(guard, [run()])["workflows"][0]["failure_category"]
        == "NOT_OBSERVED"
    )
    assert (
        evaluate_at(guard, [run()])["workflows"][0]["failure_category"]
        == "BILLING_BLOCKED"
    )
    guard.close()


def test_health_rejects_failed_remediation_storage(tmp_path):
    from tools.upstream_watchdog import validate_status

    guard = retry.RetryLedger(
        tmp_path / "missing.json", classifier=lambda *a, **k: "OTHER_FAILURE"
    )
    report = evaluate_at(guard, [run()])
    assert not validate_status(report, MANIFEST, now=NOW)
    guard.close()


def test_annotation_transport_failure_without_prior_block_uses_24_hours(tmp_path):
    guard = ledger(tmp_path)

    def unavailable(*args, **kwargs):
        raise OSError("HTTP403")

    guard.classifier = unavailable
    first = evaluate_at(guard, [run()])["workflows"][0]
    assert first["failure_category"] == "NOT_OBSERVED"
    assert first["failure_observation"] == "UNAVAILABLE"
    second = evaluate_at(guard, [run()], NOW + dt.timedelta(minutes=15))["workflows"][0]
    assert second["remediation_state"] == "NOT_DUE"
    guard.close()
