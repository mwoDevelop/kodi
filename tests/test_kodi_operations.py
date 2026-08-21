import json
import stat
import subprocess

import pytest

from tools.kodi_operations import planner
from tools.kodi_operations import runner as operation_runner
from tools.kodi_operations.model import OperationPlan, PlanStep, RunStatus, StepResult
from tools.kodi_operations.runner import (
    DeviceUnavailable,
    OperationAdapterError,
    OperationRunner,
    ProductionExecutor,
    StepOutcome,
    qnap_service_is_operational,
    release_rollout_result,
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


def test_restore_plans_qualified_flatpak_lifecycle(monkeypatch, tmp_path):
    root = repository(tmp_path)
    flatpak = fleet()
    flatpak["order"].append("nuc-mwo")
    flatpak["devices"]["nuc-mwo"] = {"platform": "linux-flatpak"}
    monkeypatch.setattr(planner, "load_fleet", lambda _root: flatpak)
    policy = json.loads(
        (root / "manifests/kodi-operations.json").read_text()
    )
    policy["device_order"].append("nuc-mwo")
    (root / "manifests/kodi-operations.json").write_text(json.dumps(policy))

    plan = planner.restore_plan(root, "nuc-mwo", "reinstall")

    restore_steps = [step for step in plan.steps if step.step_id.startswith("restore:")]
    assert restore_steps
    assert {step.adapter for step in restore_steps} == {"flatpak-restore"}
    assert {"uninstall", "install", "profile"}.issubset(
        step.action for step in restore_steps
    )


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


def test_qnap_reconcile_deploys_before_health_evaluation(monkeypatch, tmp_path):
    root = repository(tmp_path)
    executor = object.__new__(ProductionExecutor)
    executor.repository = root
    calls = []
    executor._run_json = lambda argv, timeout: calls.append((argv, timeout)) or {}

    def status(_env, repository):
        assert repository == root
        assert calls, "approved lock must be deployed before health is evaluated"
        return {"control-plane": {"status": "running", "health": "healthy"}}

    monkeypatch.setattr(operation_runner, "qnap_status", status)
    step = PlanStep(
        step_id="qnap",
        wave=0,
        adapter="qnap",
        action="reconcile",
        mutation=True,
        required=True,
        capabilities=("probe", "deploy"),
    )

    outcome = executor.execute(step, dry_run=False)

    assert outcome.result == StepResult.PASS
    assert outcome.summary["unhealthy"] == []
    assert calls[0][0][-3:] == [
        "deploy",
        "--lock",
        "manifests/locks/qnap-stable.json",
    ]


def test_watchdog_security_alert_is_operational_but_remains_visible():
    assert qnap_service_is_operational(
        "upstream-watchdog",
        {
            "status": "running",
            "health": "unhealthy",
            "checked_at": "2026-08-18T00:00:00+00:00",
            "runtime_healthy": False,
            "workflow_failures": ["example/reconcile.yml"],
        },
    )
    assert not qnap_service_is_operational(
        "upstream-watchdog",
        {
            "status": "running",
            "health": "unhealthy",
            "runtime_status": "not-ready",
        },
    )


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


def test_restore_resume_does_not_reverify_profile_after_device_adapter_ran(
    monkeypatch, tmp_path
):
    root = repository(tmp_path)
    flatpak = fleet()
    flatpak["order"].append("nuc-mwo")
    flatpak["devices"]["nuc-mwo"] = {"platform": "linux-flatpak"}
    monkeypatch.setattr(planner, "load_fleet", lambda _root: flatpak)
    policy_path = root / "manifests/kodi-operations.json"
    policy = json.loads(policy_path.read_text())
    policy["device_order"].append("nuc-mwo")
    policy_path.write_text(json.dumps(policy))
    plan = planner.restore_plan(root, "nuc-mwo", "reinstall")

    class First(FakeExecutor):
        def execute(self, step, *, dry_run, verify_only=False):
            self.calls.append((step.step_id, dry_run, verify_only, step.mutation))
            if step.step_id == "device:nuc-mwo":
                return StepOutcome(StepResult.ERROR, {"failed": True})
            return StepOutcome(StepResult.PASS, {"safe": True})

    first = First()
    report, code = OperationRunner(root, first).run(plan)
    assert code == 5

    class Resume(FakeExecutor):
        def execute(self, step, *, dry_run, verify_only=False):
            if step.step_id == "restore:profile" and verify_only:
                raise AssertionError("profile was superseded by device adapter")
            self.calls.append((step.step_id, dry_run, verify_only, step.mutation))
            return StepOutcome(StepResult.PASS, {"safe": True})

    resumed, code = OperationRunner(root, Resume()).run(
        plan, run_id=report["run_id"], resume=True
    )

    assert code == 0
    assert resumed["status"] == "COMPLETE"


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


def test_release_rollout_preserves_deferred_partial_reason():
    report = {
        "steps": {
            "device:online": {"result": "NO_CHANGE"},
            "device:offline": {"result": "DEFERRED"},
            "e2e": {"result": "PASS"},
        }
    }

    assert release_rollout_result(report, 2) == StepResult.DEFERRED


def test_release_rollout_preserves_diagnostic_failure_over_deferred():
    report = {
        "steps": {
            "device:offline": {"result": "DEFERRED"},
            "device:failed": {"result": "DIAGNOSTIC_FAILED"},
        }
    }

    assert release_rollout_result(report, 2) == StepResult.DIAGNOSTIC_FAILED


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


def test_portable_dispatch_retries_once_after_incomplete_convergence(monkeypatch):
    executor = object.__new__(ProductionExecutor)
    results = iter(
        [
            {"status": "APPLY_PENDING"},
            {"status": "CONVERGED", "apply_status": "NO_CHANGE"},
        ]
    )
    calls = []

    def portable(command, device_id):
        calls.append((command, device_id))
        return next(results)

    monkeypatch.setattr(executor, "_portable", portable)
    monkeypatch.setattr(
        "tools.kodi_operations.runner.time.sleep", lambda _seconds: None
    )

    result = executor._portable_with_retry("apply", "sony-tv")

    assert result == {"status": "CONVERGED", "apply_status": "NO_CHANGE"}
    assert calls == [("apply", "sony-tv"), ("apply", "sony-tv")]


def test_json_adapter_supports_explicit_bounded_third_attempt(monkeypatch):
    executor = object.__new__(ProductionExecutor)
    calls = []

    def run_json(argv, timeout=900, adapter=None, attempts=2):
        calls.append((tuple(argv), timeout, adapter))
        if len(calls) < 3:
            raise OperationAdapterError(adapter)
        return {"status": "VIP_REQUIRED"}

    monkeypatch.setattr(executor, "_run_json", run_json)
    monkeypatch.setattr(
        "tools.kodi_operations.runner.time.sleep", lambda _seconds: None
    )

    result = executor._run_json_with_retry(
        ["python", "adapter.py"], adapter="opensubtitles", attempts=3
    )

    assert result == {"status": "VIP_REQUIRED"}
    assert len(calls) == 3


def test_preflight_reconnects_only_android_transports_without_reporting_endpoints(
    monkeypatch, tmp_path
):
    executor = object.__new__(ProductionExecutor)
    executor.repository = tmp_path
    executor.adb = "adb"
    executor.adb_server_port = 5038
    executor.fleet = {
        "order": ["android", "flatpak"],
        "devices": {
            "android": {
                "platform": "android-tv",
                "endpoints": {"adb": "192.0.2.10:5555"},
            },
            "flatpak": {
                "platform": "linux-flatpak",
                "endpoints": {"ssh": "192.0.2.20"},
            },
        },
    }
    calls = []

    def run(argv, **kwargs):
        calls.append((argv, kwargs))
        return type(
            "Result", (), {"returncode": 0, "stdout": "already connected\n"}
        )()

    monkeypatch.setattr("tools.kodi_operations.runner.subprocess.run", run)

    outcome = executor.execute(
        PlanStep("preflight", "preflight", "validate"),
        dry_run=False,
    )

    assert outcome.result == StepResult.PASS
    assert outcome.summary == {
        "policy": "valid",
        "fleet_members": 2,
        "adb_attempted": 1,
        "adb_connected": 1,
    }
    assert calls[0][0] == [
        "adb",
        "-P",
        "5038",
        "connect",
        "192.0.2.10:5555",
    ]
    assert "192.0.2.10:5555" not in json.dumps(outcome.summary)


def test_json_adapter_retries_once_and_preserves_hard_failure(monkeypatch):
    executor = object.__new__(ProductionExecutor)
    calls = []

    def run_json(argv, timeout=900, adapter=None):
        calls.append((argv, timeout, adapter))
        raise OperationAdapterError(adapter)

    monkeypatch.setattr(executor, "_run_json", run_json)
    monkeypatch.setattr(
        "tools.kodi_operations.runner.time.sleep", lambda _seconds: None
    )

    with pytest.raises(OperationAdapterError):
        executor._run_json_with_retry(
            ["python", "adapter.py"], timeout=60, adapter="profile-sync"
        )

    assert calls == [
        (["python", "adapter.py"], 60, "profile-sync"),
        (["python", "adapter.py"], 60, "profile-sync"),
    ]


def test_provider_configuration_uses_only_device_scoped_optional_relay():
    executor = object.__new__(ProductionExecutor)
    executor.adb = "adb"
    executor.adb_server_port = 5038
    executor.fleet = {
        "references": {
            "KODI_DEVICE_X88PRO20_TORRENTIO_ENDPOINT": (
                "http://192.0.2.39:18766/torrentio"
            )
        }
    }

    x88 = executor._provider_configuration_argv("x88pro20", "192.0.2.7:5555")
    sony = executor._provider_configuration_argv("sony-tv", "192.0.2.12:5555")

    assert x88[-2:] == [
        "--torrentio-endpoint",
        "http://192.0.2.39:18766/torrentio",
    ]
    assert "--torrentio-endpoint" not in sony


def test_android_rollout_uses_complete_six_provider_probe():
    assert operation_runner.expanded_provider_probe.__module__ == (
        "tools.kodi_mwoscrapers_probe"
    )


@pytest.mark.parametrize(
    ("version", "expected"),
    (("0.1.10", "legacy"), ("0.2.0", "expanded")),
)
def test_android_rollout_selects_probe_from_promoted_stable_lock(
    monkeypatch, tmp_path, version, expected
):
    executor = object.__new__(ProductionExecutor)
    executor.repository = tmp_path
    executor.adb = "adb"
    executor.adb_server_port = 5038
    lock = tmp_path / "manifests/locks/stable.json"
    lock.parent.mkdir(parents=True)
    lock.write_text(
        json.dumps(
            {
                "components": {
                    "script.module.mwoscrapers": {"version": version}
                }
            }
        ),
        encoding="utf-8",
    )
    calls = []

    def probe(name):
        def execute(*args):
            calls.append((name, args))
            return {"report": {}}

        return execute

    monkeypatch.setattr(
        operation_runner, "legacy_provider_probe", probe("legacy")
    )
    monkeypatch.setattr(
        operation_runner, "expanded_provider_probe", probe("expanded")
    )

    assert executor._provider_probe("serial") == {"report": {}}
    assert calls == [(expected, ("adb", 5038, "serial", 75))]


def test_android_rollout_configures_opensubtitles_from_private_references(
    monkeypatch,
):
    executor = object.__new__(ProductionExecutor)
    executor.adb = "adb"
    executor.adb_server_port = 5038
    executor.fleet = {
        "devices": {
            "bluestacks1": {
                "endpoints": {"adb": "127.0.0.1:5555"},
            }
        },
        "references": {},
    }
    executor.external_attempts = 1
    calls = []
    retry_adapters = []

    def run_json(argv, timeout=900, adapter=None):
        calls.append((tuple(argv), timeout, adapter))
        if adapter == "opensubtitles":
            return {"ok": True, "changed": False}
        if adapter == "opensubtitles-com":
            return {"ok": True, "changed": False}
        if adapter == "rapideo":
            return {"ok": True, "changed": False}
        if adapter == "mwoscrapers":
            return {"ok": True, "changed": False}
        if adapter == "profile-sync":
            return {"status": "NO_CHANGE"}
        if adapter == "umbrella-private":
            return {"status": "NO_CHANGE"}
        return {"result": "pass", "actions": []}

    def run_json_with_retry(argv, timeout=900, adapter=None, attempts=2):
        retry_adapters.append(adapter)
        return run_json(argv, timeout=timeout, adapter=adapter)

    monkeypatch.setattr(executor, "_run_json", run_json)
    monkeypatch.setattr(
        executor, "_run_json_with_retry", run_json_with_retry
    )
    monkeypatch.setattr(
        executor,
        "_portable_with_retry",
        lambda *_args: {"status": "CONVERGED", "apply_status": "NO_CHANGE"},
    )
    monkeypatch.setattr(executor, "_provider_probe", lambda *_args: {})
    monkeypatch.setattr(
        operation_runner, "rd_probe", lambda *_args: {"healthy": True}
    )

    outcome = executor._android_converge("bluestacks1")

    opensubtitles = next(call for call in calls if call[2] == "opensubtitles")
    opensubtitles_com = next(
        call for call in calls if call[2] == "opensubtitles-com"
    )
    assert opensubtitles[0][1:4] == (
        "tools/kodi_opensubtitles_configure.py",
        "--serial",
        "127.0.0.1:5555",
    )
    assert opensubtitles[0][4:6] == ("--references", ".env")
    assert opensubtitles_com[0][1:4] == (
        "tools/kodi_opensubtitles_com_configure.py",
        "--serial",
        "127.0.0.1:5555",
    )
    assert opensubtitles_com[0][4:6] == ("--references", ".env")
    assert retry_adapters == [
        "opensubtitles",
        "opensubtitles-com",
        "profile-sync",
    ]
    assert outcome.summary["opensubtitles"] == "pass"
    assert outcome.summary["opensubtitles_com"] == "pass"


def test_android_rollout_retries_sanitized_provider_network_error(monkeypatch):
    executor = object.__new__(ProductionExecutor)
    executor.adb = "adb"
    executor.adb_server_port = 5038
    executor.fleet = {
        "devices": {
            "sony-tv": {"endpoints": {"adb": "192.0.2.12:5555"}}
        },
        "references": {},
    }
    executor.external_attempts = 2
    executor.retry_seconds = 0
    provider_calls = []

    def run_json(argv, timeout=900, adapter=None, attempts=2):
        if adapter in {"rapideo", "opensubtitles", "opensubtitles-com"}:
            return {"ok": True, "changed": False}
        if adapter == "mwoscrapers":
            return {"ok": True, "changed": False}
        if adapter in {"profile-sync", "umbrella-private"}:
            return {"status": "NO_CHANGE"}
        return {"result": "pass", "actions": []}

    def provider_probe(*_args):
        provider_calls.append(True)
        if len(provider_calls) == 1:
            raise RuntimeError(
                "Kodi provider probe contains network or contract errors"
            )
        return {"report": {}}

    monkeypatch.setattr(executor, "_run_json", run_json)
    monkeypatch.setattr(executor, "_run_json_with_retry", run_json)
    monkeypatch.setattr(
        executor,
        "_portable_with_retry",
        lambda *_args: {"status": "CONVERGED", "apply_status": "NO_CHANGE"},
    )
    monkeypatch.setattr(executor, "_provider_probe", provider_probe)
    monkeypatch.setattr(
        operation_runner, "rd_probe", lambda *_args: {"healthy": True}
    )

    outcome = executor._android_converge("sony-tv")

    assert provider_calls == [True, True]
    assert outcome.result is StepResult.NO_CHANGE
    assert outcome.summary["diagnostics"] == {
        "attempts": 2,
        "provider": True,
        "real_debrid": True,
    }


def test_youtube_configuration_is_explicitly_deferred_without_api_references(
    tmp_path,
):
    executor = object.__new__(ProductionExecutor)
    executor.repository = tmp_path
    executor.fleet = {"references": {"YOUTUBE_USER": "user@example.invalid"}}

    assert executor._youtube_configuration("device") == {
        "ok": True,
        "status": "API_CONFIG_REQUIRED",
        "changed": False,
    }


def test_youtube_configuration_uses_private_session_without_api_references(
    monkeypatch, tmp_path
):
    session = tmp_path / ".kodi-private/youtube/session.json"
    session.parent.mkdir(parents=True)
    session.write_text("{}\n", encoding="utf-8")
    session.chmod(0o600)
    executor = object.__new__(ProductionExecutor)
    executor.repository = tmp_path
    executor.adb = "adb"
    executor.adb_server_port = 5038
    executor.fleet = {
        "references": {"YOUTUBE_USER": "user@example.invalid"}
    }
    calls = []
    monkeypatch.setattr(
        executor,
        "_run_json",
        lambda argv, adapter=None: calls.append((argv, adapter))
        or {"ok": True, "authorization": "ACCOUNT_READY"},
    )

    result = executor._youtube_configuration("192.0.2.9:5555")

    assert result["authorization"] == "ACCOUNT_READY"
    assert calls[0][1] == "youtube"


def test_youtube_configuration_uses_private_adapter_when_references_exist(
    monkeypatch,
):
    executor = object.__new__(ProductionExecutor)
    executor.adb = "adb"
    executor.adb_server_port = 5038
    executor.fleet = {
        "references": {
            "YOUTUBE_API_KEY": "private",
            "YOUTUBE_CLIENT_ID": "private",
            "YOUTUBE_CLIENT_SECRET": "private",
            "YOUTUBE_USER": "private",
        }
    }
    calls = []
    monkeypatch.setattr(
        executor,
        "_run_json",
        lambda argv, adapter=None: calls.append((argv, adapter))
        or {"ok": True, "authorization": "AUTHORIZATION_REQUIRED"},
    )

    result = executor._youtube_configuration("192.0.2.8:5555")

    assert result["authorization"] == "AUTHORIZATION_REQUIRED"
    assert calls[0][1] == "youtube"
    assert calls[0][0][1:4] == [
        "tools/kodi_youtube_configure.py",
        "--serial",
        "192.0.2.8:5555",
    ]
