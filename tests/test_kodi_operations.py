import json
import os
import stat
import subprocess

import pytest

from tools.kodi_operations import planner
from tools.kodi_operations.model import OperationPlan, PlanStep, StepResult
from tools.kodi_operations.model import RunStatus
from tools.kodi_operations.runner import (
    DeviceUnavailable,
    OperationAdapterError,
    OperationRunner,
    ProductionExecutor,
    StepOutcome,
)
from tools.kodi_operations.store import RunStore, StoreError


def repository(tmp_path):
    root = tmp_path / "repo"
    (root / "manifests/locks").mkdir(parents=True)
    (root / ".kodi-private").mkdir(mode=0o700)
    (root / "manifests/kodi-operations.json").write_text(
        json.dumps(
            {
                "schema": 1,
                "canaries": ["bluestacks1", "x88pro20"],
                "device_order": [
                    "bluestacks1",
                    "x88pro20",
                    "sony-tv",
                ],
                "diagnostics": {
                    "external_attempts": 3,
                    "retry_seconds": 0,
                },
                "run_retention_days": 30,
            }
        )
    )
    (root / "manifests/locks/stable.json").write_text(
        json.dumps(
            {
                "schema": 2,
                "channel": "stable",
                "source_snapshot_id": "a" * 64,
            }
        )
    )
    subprocess.run(("git", "init", "-q", str(root)), check=True)
    subprocess.run(("git", "-C", str(root), "add", "."), check=True)
    subprocess.run(
        (
            "git",
            "-C",
            str(root),
            "-c",
            "user.name=test",
            "-c",
            "user.email=test@example.invalid",
            "commit",
            "-qm",
            "fixture",
        ),
        check=True,
    )
    return root


def fleet():
    return {
        "order": ["bluestacks1", "sony-tv", "x88pro20"],
        "devices": {
            "bluestacks1": {"platform": "android-emulator"},
            "sony-tv": {"platform": "android"},
            "x88pro20": {"platform": "android"},
        },
    }


def test_full_rollout_orders_canaries_before_remaining_fleet(monkeypatch, tmp_path):
    root = repository(tmp_path)
    monkeypatch.setattr(planner, "load_fleet", lambda _root: fleet())

    plan = planner.rollout_plan(root)

    assert plan.scope == "full"
    assert plan.devices == ("bluestacks1", "x88pro20", "sony-tv")
    assert plan.canaries == ("bluestacks1", "x88pro20")
    assert [step.target for step in plan.steps if step.target] == list(plan.devices)


def test_scoped_rollout_has_no_hidden_canary(monkeypatch, tmp_path):
    root = repository(tmp_path)
    monkeypatch.setattr(planner, "load_fleet", lambda _root: fleet())

    plan = planner.rollout_plan(root, ("sony-tv",))

    assert plan.scope == "scoped"
    assert plan.devices == ("sony-tv",)
    assert plan.canaries == ()
    assert plan.steps[1].action == "health"
    assert not plan.steps[1].mutation


def test_persisted_plan_round_trip_keeps_content_identity(monkeypatch, tmp_path):
    root = repository(tmp_path)
    monkeypatch.setattr(planner, "load_fleet", lambda _root: fleet())
    original = planner.rollout_plan(root, ("sony-tv",))

    restored = OperationPlan.from_document(original.document())

    assert restored == original
    assert restored.document() == original.document()


def test_persisted_plan_rejects_unknown_step_fields(monkeypatch, tmp_path):
    root = repository(tmp_path)
    monkeypatch.setattr(planner, "load_fleet", lambda _root: fleet())
    document = planner.rollout_plan(root, ("sony-tv",)).document()
    document["steps"][0]["unexpected"] = True
    from tools.kodi_operations.model import digest_document

    payload = {key: value for key, value in document.items() if key != "plan_id"}
    document["plan_id"] = digest_document(payload)

    with pytest.raises(ValueError, match="step"):
        OperationPlan.from_document(document)


def test_restore_repair_never_plans_binary_install(monkeypatch, tmp_path):
    root = repository(tmp_path)
    monkeypatch.setattr(planner, "load_fleet", lambda _root: fleet())

    repair = planner.restore_plan(root, "sony-tv", "repair")
    reinstall = planner.restore_plan(root, "sony-tv", "reinstall")

    assert not {"uninstall", "install"}.intersection(
        step.action for step in repair.steps
    )
    assert {"uninstall", "install"}.issubset(
        step.action for step in reinstall.steps
    )


def test_restore_rejects_unqualified_flatpak_lifecycle(monkeypatch, tmp_path):
    root = repository(tmp_path)
    flatpak = fleet()
    flatpak["order"].append("nuc-mwo")
    flatpak["devices"]["nuc-mwo"] = {"platform": "linux-flatpak"}
    monkeypatch.setattr(planner, "load_fleet", lambda _root: flatpak)

    with pytest.raises(planner.PlanError, match="Flatpak restore"):
        planner.restore_plan(root, "nuc-mwo", "reinstall")


def test_private_run_store_is_atomic_and_mode_restricted(tmp_path):
    root = repository(tmp_path)
    store = RunStore(root, "a" * 32)
    store.create()
    store.write("plan.json", {"secret": "not-a-real-secret"})

    assert stat.S_IMODE(store.root.stat().st_mode) == 0o700
    assert stat.S_IMODE((store.root / "plan.json").stat().st_mode) == 0o600


def test_private_run_store_rejects_symlink(tmp_path):
    root = repository(tmp_path)
    target = tmp_path / "outside"
    target.mkdir()
    (root / ".kodi-private/kodi-ops").symlink_to(target, target_is_directory=True)

    with pytest.raises(StoreError, match="symlink"):
        RunStore(root, "b" * 32)


class FakeExecutor:
    def __init__(self):
        self.calls = []

    def execute(self, step, *, dry_run, verify_only=False):
        self.calls.append((step.step_id, dry_run, verify_only, step.mutation))
        return StepOutcome(StepResult.NO_CHANGE, {"safe": True})


def test_dry_run_does_not_execute_mutations(monkeypatch, tmp_path):
    root = repository(tmp_path)
    monkeypatch.setattr(planner, "load_fleet", lambda _root: fleet())
    plan = planner.rollout_plan(root, ("sony-tv",))
    executor = FakeExecutor()

    report, code = OperationRunner(root, executor).run(plan, dry_run=True)

    assert code == 0
    assert report["status"] == "COMPLETE"
    assert all(dry_run for _step, dry_run, _verify, _mutation in executor.calls)


def test_resume_reprobes_completed_steps(monkeypatch, tmp_path):
    root = repository(tmp_path)
    monkeypatch.setattr(planner, "load_fleet", lambda _root: fleet())
    plan = planner.rollout_plan(root, ("sony-tv",))
    first = FakeExecutor()
    report, _code = OperationRunner(root, first).run(plan, dry_run=True)
    second = FakeExecutor()

    resumed, code = OperationRunner(root, second).run(
        plan,
        dry_run=True,
        run_id=report["run_id"],
        resume=True,
    )

    assert code == 0
    assert resumed["status"] == "COMPLETE"
    assert second.calls
    assert all(verify for _step, _dry, verify, _mutation in second.calls)


def test_canary_diagnostic_failure_stops_later_waves(monkeypatch, tmp_path):
    root = repository(tmp_path)
    monkeypatch.setattr(planner, "load_fleet", lambda _root: fleet())
    plan = planner.rollout_plan(root)

    class DiagnosticExecutor(FakeExecutor):
        def execute(self, step, *, dry_run, verify_only=False):
            self.calls.append((step.step_id, dry_run, verify_only, step.mutation))
            if step.target == "bluestacks1":
                return StepOutcome(StepResult.DIAGNOSTIC_FAILED, {})
            return StepOutcome(StepResult.NO_CHANGE, {})

    executor = DiagnosticExecutor()
    report, code = OperationRunner(root, executor).run(plan)

    assert code == 2
    assert report["status"] == "PARTIAL"
    assert "device:x88pro20" not in report["steps"]


def test_unavailable_non_canary_is_deferred_and_later_steps_continue(
    monkeypatch, tmp_path
):
    root = repository(tmp_path)
    monkeypatch.setattr(planner, "load_fleet", lambda _root: fleet())
    plan = planner.rollout_plan(root)

    class UnavailableExecutor(FakeExecutor):
        def execute(self, step, *, dry_run, verify_only=False):
            self.calls.append((step.step_id, dry_run, verify_only, step.mutation))
            if step.target == "sony-tv":
                raise DeviceUnavailable("offline")
            return StepOutcome(StepResult.NO_CHANGE, {})

    report, code = OperationRunner(root, UnavailableExecutor()).run(plan)

    assert code == 2
    assert report["status"] == "PARTIAL"
    assert report["steps"]["device:sony-tv"]["result"] == "DEFERRED"
    assert report["steps"]["e2e"]["result"] == "NO_CHANGE"


def test_unavailable_canary_stops_later_waves(monkeypatch, tmp_path):
    root = repository(tmp_path)
    monkeypatch.setattr(planner, "load_fleet", lambda _root: fleet())
    plan = planner.rollout_plan(root)

    class UnavailableExecutor(FakeExecutor):
        def execute(self, step, *, dry_run, verify_only=False):
            if step.target == "bluestacks1":
                raise DeviceUnavailable("offline")
            return StepOutcome(StepResult.NO_CHANGE, {})

    report, code = OperationRunner(root, UnavailableExecutor()).run(plan)

    assert code == 2
    assert report["steps"]["device:bluestacks1"]["result"] == "DEFERRED"
    assert "device:x88pro20" not in report["steps"]


def test_terminal_waiting_approval_has_dedicated_status_and_exit_code(
    monkeypatch, tmp_path
):
    root = repository(tmp_path)
    monkeypatch.setattr(planner, "load_fleet", lambda _root: fleet())
    plan = planner.rollout_plan(root, ("sony-tv",))

    class ApprovalExecutor(FakeExecutor):
        def execute(self, step, *, dry_run, verify_only=False):
            return StepOutcome(
                StepResult.DEFERRED,
                {"pull_request": 1},
                RunStatus.WAITING_APPROVAL,
            )

    report, code = OperationRunner(root, ApprovalExecutor()).run(plan)

    assert report["status"] == "WAITING_APPROVAL"
    assert code == 3


def test_exception_text_and_sentinel_secret_never_enter_run_documents(
    monkeypatch, tmp_path
):
    root = repository(tmp_path)
    monkeypatch.setattr(planner, "load_fleet", lambda _root: fleet())
    plan = planner.rollout_plan(root, ("sony-tv",))
    sentinel = "SENTINEL-PRIVATE-CREDENTIAL"

    class SecretFailureExecutor(FakeExecutor):
        def execute(self, step, *, dry_run, verify_only=False):
            raise RuntimeError("failure contained " + sentinel)

    report, code = OperationRunner(root, SecretFailureExecutor()).run(plan)
    run = root / ".kodi-private/kodi-ops/runs" / report["run_id"]
    persisted = "\n".join(
        path.read_text(encoding="utf-8") for path in run.rglob("*.json")
    )

    assert code == 5
    assert sentinel not in persisted


def test_portable_dispatch_retries_once_and_preserves_hard_failure(monkeypatch):
    executor = object.__new__(ProductionExecutor)
    calls = []

    def portable(command, device_id):
        calls.append((command, device_id))
        raise OperationAdapterError("portable-state")

    monkeypatch.setattr(executor, "_portable", portable)
    monkeypatch.setattr(
        "tools.kodi_operations.runner.time.sleep", lambda _seconds: None
    )

    with pytest.raises(OperationAdapterError):
        executor._portable_with_retry("publish", "sony-tv")

    assert calls == [("publish", "sony-tv"), ("publish", "sony-tv")]
