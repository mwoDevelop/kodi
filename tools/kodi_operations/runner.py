"""Resumable execution engine and production adapter boundary."""

from __future__ import annotations

import datetime as dt
import json
import os
import subprocess
import sys
import time
import uuid
from contextlib import nullcontext
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from tools.kodi_inventory import inventory_device
from tools.kodi_mwoscrapers_endpoint_probe import probe as provider_probe
from tools.kodi_profile import create_snapshot, verify_snapshot
from tools.kodi_reinstall import (
    deploy_target,
    install_apk,
    load_config,
    preflight_target,
    uninstall_and_clean,
)
from tools.kodi_sync_inventory import load_sync_inventory
from tools.kodi_transports import TransportError
from tools.kodi_umbrella_rd_probe import probe as rd_probe
from tools.qnap_images import status as qnap_status

from .model import (
    EXIT_CODES,
    OperationPlan,
    PlanStep,
    RunStatus,
    StepResult,
    overall_status,
)
from .github import GitHubClient
from .planner import rollout_plan
from .store import RunStore


def utc_now() -> str:
    return dt.datetime.now(dt.timezone.utc).isoformat()


@dataclass(frozen=True)
class StepOutcome:
    result: StepResult
    summary: dict[str, Any]
    terminal_status: RunStatus | None = None


class DeviceUnavailable(RuntimeError):
    """The registered endpoint cannot currently be reached or authorized."""


class OperationAdapterError(RuntimeError):
    def __init__(self, adapter):
        super().__init__("Kodi operation adapter failed")
        self.adapter = adapter


class OperationLock:
    def __init__(self, repository: Path, run_id: str):
        self.path = repository / ".kodi-private/kodi-ops/operation.lock"
        self.run_id = run_id
        self.acquired = False

    def __enter__(self):
        self.path.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
        self.path.parent.chmod(0o700)
        if self.path.exists() and self.path.is_symlink():
            raise RuntimeError("operation lock cannot be a symlink")
        try:
            descriptor = os.open(
                self.path,
                os.O_WRONLY | os.O_CREAT | os.O_EXCL,
                0o600,
            )
        except FileExistsError as error:
            raise RuntimeError("another Kodi operation owns the local lock") from error
        with os.fdopen(descriptor, "w", encoding="utf-8") as handle:
            handle.write(self.run_id + "\n")
            handle.flush()
            os.fsync(handle.fileno())
        self.acquired = True
        return self

    def __exit__(self, _type, _value, _traceback):
        if self.acquired:
            try:
                if self.path.read_text(encoding="utf-8").strip() == self.run_id:
                    self.path.unlink()
            finally:
                self.acquired = False


class ProductionExecutor:
    """Adapter composition; reports only allowlisted, redacted fields."""

    def __init__(
        self,
        repository: Path,
        adb: str = "/home/mwo/android-sdk/platform-tools/adb",
        adb_server_port: int = 5038,
    ):
        self.repository = Path(repository).resolve()
        self.adb = adb
        self.adb_server_port = adb_server_port
        self.fleet = load_sync_inventory(self.repository)
        operations_policy = json.loads(
            (self.repository / "manifests/kodi-operations.json").read_text(
                encoding="utf-8"
            )
        )
        self.canaries = tuple(operations_policy["canaries"])
        self._restore_targets = {}
        self.github = GitHubClient(self.repository)

    def _connect_android_transports(self) -> dict[str, int]:
        """Restore the local ADB daemon's volatile network connections."""
        attempted = 0
        connected = 0
        for device in self.fleet["devices"].values():
            if not device["platform"].startswith("android"):
                continue
            endpoint = device["endpoints"]["adb"]
            attempted += 1
            try:
                result = subprocess.run(
                    [
                        self.adb,
                        "-P",
                        str(self.adb_server_port),
                        "connect",
                        endpoint,
                    ],
                    cwd=self.repository,
                    check=False,
                    capture_output=True,
                    text=True,
                    timeout=10,
                )
            except (OSError, subprocess.TimeoutExpired):
                continue
            if result.returncode == 0 and "connected" in result.stdout.casefold():
                connected += 1
        return {"adb_attempted": attempted, "adb_connected": connected}

    def _run_json(self, argv: list[str], timeout=900, adapter=None) -> dict[str, Any]:
        try:
            result = subprocess.run(
                argv,
                cwd=self.repository,
                check=True,
                capture_output=True,
                text=True,
                timeout=timeout,
            )
        except (subprocess.CalledProcessError, subprocess.TimeoutExpired) as error:
            raise OperationAdapterError(adapter or Path(argv[1]).stem) from error
        return json.loads(result.stdout)

    def _run_json_with_retry(
        self, argv: list[str], *, timeout=900, adapter=None, delay=3
    ) -> dict[str, Any]:
        """Retry one transient adapter failure without weakening its contract."""
        try:
            return self._run_json(argv, timeout=timeout, adapter=adapter)
        except OperationAdapterError:
            time.sleep(delay)
            return self._run_json(argv, timeout=timeout, adapter=adapter)

    def _inventory(self, device_id: str) -> dict[str, Any]:
        try:
            result = inventory_device(
                self.repository,
                device_id,
                adb=self.adb,
                adb_server_port=self.adb_server_port,
            )
        except TransportError as error:
            message = str(error)
            if message.startswith((
                "ADB command failed with exit code ",
                "ADB endpoint is not an authorized device",
                "SSH read-only command failed with exit code ",
            )):
                raise DeviceUnavailable("registered device is unavailable") from error
            raise
        return {
            key: result[key]
            for key in (
                "logical_device_id",
                "platform",
                "model",
                "kodi_version",
                "running",
                "runtime_paths_qualified",
            )
        }

    def _portable(self, command: str, device_id: str) -> dict[str, Any]:
        result = self._run_json(
            [
                sys.executable,
                "tools/kodi_portable_state_rollout.py",
                command,
                "--adb",
                self.adb,
                "--adb-server-port",
                str(self.adb_server_port),
                "--device",
                device_id,
            ],
            timeout=600,
            adapter="portable-state",
        )
        device = result.get("devices", {}).get(device_id, {})
        return {
            "status": device.get("status"),
            "apply_status": device.get("apply_status"),
            "favourites": device.get("favourites"),
            "missing_artwork_files": device.get("missing_artwork_files"),
        }

    def _portable_with_retry(self, command: str, device_id: str) -> dict[str, Any]:
        """Retry one transient in-Kodi dispatch without masking a hard failure."""
        try:
            return self._portable(command, device_id)
        except OperationAdapterError:
            time.sleep(3)
            return self._portable(command, device_id)

    def _android_converge(self, device_id: str) -> StepOutcome:
        serial = self.fleet["devices"][device_id]["endpoints"]["adb"]
        stable = self._run_json(
            [
                sys.executable,
                "tools/kodi_android_stable_rollout.py",
                "--device",
                device_id,
                "--adb",
                self.adb,
                "--adb-server-port",
                str(self.adb_server_port),
            ],
            adapter="stable-addons",
        )
        defaults = self._run_json(
            [
                sys.executable,
                "tools/kodi_default_addons.py",
                "--serial",
                serial,
                "--adb",
                self.adb,
                "--adb-server-port",
                str(self.adb_server_port),
            ],
            adapter="default-addons",
        )
        rapideo = self._run_json(
            [
                sys.executable,
                "tools/kodi_rapideo_configure.py",
                "--serial",
                serial,
                "--references",
                ".env",
                "--adb",
                self.adb,
                "--adb-server-port",
                str(self.adb_server_port),
            ],
            adapter="rapideo",
        )
        providers = self._run_json(
            [
                sys.executable,
                "tools/kodi_mwoscrapers_configure.py",
                "--serial",
                serial,
                "--adb",
                self.adb,
                "--adb-server-port",
                str(self.adb_server_port),
            ],
            adapter="mwoscrapers",
        )
        profile_sync = self._run_json_with_retry(
            [
                sys.executable,
                "tools/kodi_android_profile_sync.py",
                "--device",
                device_id,
                "--adb",
                self.adb,
                "--adb-server-port",
                str(self.adb_server_port),
            ],
            timeout=600,
            adapter="profile-sync",
        )
        umbrella_private = self._run_json(
            [
                sys.executable,
                "tools/kodi_umbrella_settings.py",
                "apply",
                "--device",
                device_id,
                "--adb",
                self.adb,
                "--adb-server-port",
                str(self.adb_server_port),
            ],
            timeout=600,
            adapter="umbrella-private",
        )
        # Kodi can still be completing UpdateLocalAddons or a settings flush
        # after the preceding adapters. One bounded retry preserves fail-closed
        # behavior while avoiding a false device regression.
        portable = self._portable_with_retry("apply", device_id)
        if portable["status"] != "CONVERGED":
            raise RuntimeError("portable state did not converge")
        changed = any(
            item.get("action") != "unchanged"
            for item in [
                *stable.get("actions", []),
                *defaults.get("actions", []),
            ]
        ) or portable.get("apply_status") not in {None, "NO_CHANGE"} or bool(
            rapideo.get("changed") or providers.get("changed")
        )
        attempts = int(getattr(self, "external_attempts", 3))
        retry_seconds = int(getattr(self, "retry_seconds", 5))
        diagnostics = None
        for attempt in range(1, attempts + 1):
            provider = provider_probe(
                self.adb, self.adb_server_port, serial, 75
            )
            rd = rd_probe(self.adb, self.adb_server_port, serial, 90)
            diagnostics = {
                "attempts": attempt,
                "provider": "report" in provider,
                "real_debrid": bool(rd.get("healthy")),
            }
            if diagnostics["provider"] and diagnostics["real_debrid"]:
                break
            if attempt < attempts:
                time.sleep(retry_seconds)
        diagnostic_failed = not (
            diagnostics["provider"] and diagnostics["real_debrid"]
        )
        return StepOutcome(
            StepResult.DIAGNOSTIC_FAILED
            if diagnostic_failed
            else (StepResult.PASS if changed else StepResult.NO_CHANGE),
            {
                "device": device_id,
                "platform": "android",
                "stable": stable.get("result"),
                "default_addons": defaults.get("result"),
                "rapideo": (
                    "pass"
                    if rapideo.get("ok")
                    else rapideo.get("result", rapideo.get("status"))
                ),
                "providers": (
                    "pass"
                    if providers.get("ok")
                    else providers.get("result", providers.get("status"))
                ),
                "profile_sync": profile_sync.get("status", "pass"),
                "umbrella_private": umbrella_private.get("status"),
                "portable": portable,
                "diagnostics": diagnostics,
            },
        )

    def _restore_target(self, device_id):
        if device_id in self._restore_targets:
            return self._restore_targets[device_id]
        _path, configured = load_config(
            ".kodi-private/kodi-reinstall.json", self.repository
        )
        matches = [item for item in configured if item["name"] == device_id]
        if len(matches) != 1:
            raise ValueError("restore target is not configured exactly once")
        target = preflight_target(
            matches[0],
            self.repository,
            self.adb,
            self.adb_server_port,
        )
        run_id = getattr(self, "run_id", None)
        if run_id:
            backup = (
                self.repository
                / ".kodi-private/kodi-ops/backups"
                / run_id
                / device_id
            )
            if backup.is_dir() and not backup.is_symlink():
                verify_snapshot(backup)
                target["operation_backup"] = backup
        self._restore_targets[device_id] = target
        return target

    def _restore_execute(self, step, dry_run, verify_only):
        target = self._restore_target(step.target)
        if dry_run:
            return StepOutcome(
                StepResult.PASS,
                {
                    "device": step.target,
                    "model": target["model"],
                    "installed_version": target["installed_version"],
                    "target_version": target["expected_version"],
                    "snapshot_id": target["snapshot_manifest"]["snapshot_id"],
                    "action": step.action,
                },
            )
        if verify_only:
            if step.action == "backup":
                backup = target.get("operation_backup")
                if not backup:
                    raise RuntimeError("fresh restore backup is missing")
                verify_snapshot(backup)
            elif step.action == "uninstall" and target["installed_version"] is not None:
                raise RuntimeError("Kodi returned after completed uninstall phase")
            elif step.action in {"install", "profile"} and target[
                "installed_version"
            ] != target["expected_version"]:
                raise RuntimeError("installed Kodi version differs after restore phase")
            return StepOutcome(
                StepResult.PASS,
                {"device": step.target, "action": step.action, "verified": True},
            )
        if step.action == "preflight":
            return StepOutcome(
                StepResult.PASS,
                {
                    "device": step.target,
                    "model": target["model"],
                    "installed_version": target["installed_version"],
                    "target_version": target["expected_version"],
                    "snapshot_id": target["snapshot_manifest"]["snapshot_id"],
                    "action": step.action,
                },
            )
        if step.action == "backup":
            run_id = getattr(self, "run_id", None)
            if not run_id:
                raise RuntimeError("restore executor has no bound run ID")
            backup_id = "%s/%s" % (run_id, step.target)
            destination = (
                self.repository
                / ".kodi-private/kodi-ops/backups"
                / run_id
                / step.target
            )
            if destination.is_dir():
                verified = verify_snapshot(destination)
                target["operation_backup"] = destination
                return StepOutcome(
                    StepResult.NO_CHANGE,
                    {
                        "device": step.target,
                        "backup_id": backup_id,
                        "snapshot_id": verified["snapshot_id"],
                    },
                )
            result = create_snapshot(
                self.adb,
                self.adb_server_port,
                target["serial"],
                destination,
                self.repository / "manifests/kodi-profile-policy.json",
                self.repository,
            )
            verified = verify_snapshot(destination)
            if result["snapshot_id"] != verified["snapshot_id"]:
                raise RuntimeError("fresh restore backup verification differs")
            target["operation_backup"] = destination
            return StepOutcome(
                StepResult.PASS,
                {
                    "device": step.target,
                    "backup_id": backup_id,
                    "snapshot_id": verified["snapshot_id"],
                },
            )
        if step.action in {"uninstall", "install"} and not target.get(
            "operation_backup"
        ):
            raise RuntimeError("destructive restore phase requires a fresh backup")
        if step.action == "uninstall":
            # Re-identify immediately before the destructive call.
            refreshed = preflight_target(
                next(
                    item
                    for item in load_config(
                        ".kodi-private/kodi-reinstall.json", self.repository
                    )[1]
                    if item["name"] == step.target
                ),
                self.repository,
                self.adb,
                self.adb_server_port,
            )
            if refreshed["model"] != target["model"]:
                raise RuntimeError("restore target identity changed")
            uninstall_and_clean(
                self.adb, self.adb_server_port, target["serial"]
            )
            return StepOutcome(StepResult.PASS, {"device": step.target})
        if step.action == "install":
            install_apk(
                self.adb,
                self.adb_server_port,
                target["serial"],
                target["apk"],
                target["expected_version"],
            )
            return StepOutcome(StepResult.PASS, {"device": step.target})
        if step.action == "profile":
            result = deploy_target(
                self.adb,
                self.adb_server_port,
                target,
                self.repository / "tools/kodi_profile_restore_device.py",
                self.repository / "tools/kodi_profile_origin_device.py",
                restore_only=True,
            )
            return StepOutcome(
                StepResult.PASS,
                {
                    "device": step.target,
                    "snapshot_id": result["snapshot_id"],
                    "restored_files": result["restored_files"],
                    "result": result["result"],
                },
            )
        raise NotImplementedError("unknown restore phase")

    def _release_snapshot(self, commit):
        return self.github.snapshot_for_commit(commit)

    def _release_execute(self, step, dry_run, verify_only):
        commit = subprocess.run(
            ("git", "rev-parse", "HEAD"),
            cwd=self.repository,
            check=True,
            capture_output=True,
            text=True,
        ).stdout.strip()
        action = step.action
        if action == "skip":
            return StepOutcome(StepResult.SKIPPED, {"reason": "operator option"})
        if dry_run:
            return StepOutcome(
                StepResult.PASS if action in {"preflight", "test", "security"} else StepResult.SKIPPED,
                {"action": action, "mode": "read-only-plan"},
            )
        if action == "preflight":
            if verify_only:
                status = subprocess.run(
                    ("git", "status", "--porcelain", "--untracked-files=all"),
                    cwd=self.repository,
                    check=True,
                    capture_output=True,
                    text=True,
                ).stdout.strip()
                if status:
                    raise RuntimeError("release worktree is no longer clean")
                return StepOutcome(StepResult.PASS, {"clean": True})
            summary = self.github.exact_main_preflight(commit)
            return StepOutcome(StepResult.PASS, summary)
        if action == "test":
            if not verify_only:
                subprocess.run(
                    (str(self.repository / "tests/e2e/run.sh"),),
                    cwd=self.repository,
                    check=True,
                    timeout=1800,
                )
            return StepOutcome(StepResult.PASS, {"suite": "tests/e2e/run.sh"})
        base_commit = getattr(self, "release_base_commit", None) or getattr(
            self, "plan_repository_commit", commit
        )
        self.release_base_commit = base_commit
        if action == "security":
            if verify_only:
                prior = getattr(self, "prior_summary", {})
                verified = self.github.verify_run(prior.get("run_id"), base_commit)
                return StepOutcome(
                    StepResult.PASS,
                    {"workflow": "publish-testing.yml", **verified},
                )
            run = self.github.dispatch(
                "publish-testing.yml",
                base_commit,
                {"dry_run": "true", "force_snapshot": "false"},
            )
            watched = self.github.watch(run)
            return StepOutcome(StepResult.PASS, {"workflow": "publish-testing.yml", **watched})
        if action == "publish-testing":
            if not verify_only:
                run = self.github.dispatch(
                    "publish-testing.yml",
                    base_commit,
                    {"dry_run": "false", "force_snapshot": "true"},
                )
                self.github.watch(run)
            snapshot = self._release_snapshot(base_commit)
            return StepOutcome(StepResult.PASS, {"snapshot_id": snapshot["snapshot_id"]})
        snapshot = self._release_snapshot(base_commit)
        if action == "qnap":
            if verify_only:
                prior = getattr(self, "prior_summary", {})
                candidate = self.github.qnap_for_snapshot(
                    snapshot,
                    prior.get("qnap_candidate_id"),
                    prior.get("qnap_candidate_sha256"),
                )
            else:
                result = self._run_json(
                    [
                        sys.executable,
                        "tools/qnap_candidate.py",
                        "--snapshot-tag",
                        snapshot["tag"],
                    ],
                    timeout=5400,
                )
                candidate = self.github.qnap_for_snapshot(
                    snapshot,
                    result["candidate_id"],
                    result["sha256"],
                )
            self.qnap_candidate = candidate
            return StepOutcome(
                StepResult.PASS,
                {
                    "snapshot_id": snapshot["snapshot_id"],
                    "qnap_candidate_id": candidate["candidate_id"],
                    "qnap_candidate_sha256": candidate["qnap_candidate_sha256"],
                },
            )
        if action == "certify":
            if not verify_only:
                run = self.github.dispatch(
                    "certify-testing.yml",
                    base_commit,
                    {"snapshot_id": snapshot["snapshot_id"], "android_tv": "x88pro20"},
                )
                self.github.watch(run)
            attestation = self.github.attestation_for_snapshot(snapshot)
            return StepOutcome(
                StepResult.PASS,
                {
                    "snapshot_id": snapshot["snapshot_id"],
                    "attestation_id": attestation["attestation_id"],
                    "attestation_sha256": attestation["attestation_sha256"],
                },
            )
        attestation = self.github.attestation_for_snapshot(snapshot)
        if action == "promote":
            qnap = getattr(self, "qnap_candidate", None)
            if not qnap:
                raise RuntimeError("release has no verified QNAP candidate")
            if not verify_only:
                run = self.github.dispatch(
                    "promote-stable.yml",
                    base_commit,
                    {
                        "snapshot_id": snapshot["snapshot_id"],
                        "attestation_id": attestation["attestation_id"],
                        "attestation_sha256": attestation["attestation_sha256"],
                        "qnap_candidate_id": qnap["candidate_id"],
                        "qnap_candidate_sha256": qnap["qnap_candidate_sha256"],
                    },
                )
                self.github.watch(run)
            pr = self.github.promotion_pr(snapshot["snapshot_id"])
            verified_pr = self.github.validate_promotion_content(
                pr, snapshot, attestation, qnap
            )
            return StepOutcome(
                StepResult.PASS,
                {
                    "pull_request": pr["number"],
                    "url": pr["url"],
                    **verified_pr,
                },
            )
        pr = self.github.promotion_pr(snapshot["snapshot_id"])
        if action == "approval":
            qnap = getattr(self, "qnap_candidate", None)
            if not qnap:
                raise RuntimeError("release has no verified QNAP candidate")
            verified_pr = self.github.validate_promotion_content(
                pr, snapshot, attestation, qnap
            )
            merge_commit = self.github.require_merged_pr(pr)
            if merge_commit is None:
                return StepOutcome(
                    StepResult.DEFERRED,
                    {"pull_request": pr["number"], "url": pr["url"]},
                    RunStatus.WAITING_APPROVAL,
                )
            subprocess.run(("git", "fetch", "origin", "main"), cwd=self.repository, check=True)
            subprocess.run(("git", "merge", "--ff-only", merge_commit), cwd=self.repository, check=True)
            self.release_merge_commit = merge_commit
            return StepOutcome(
                StepResult.PASS,
                {"pull_request": pr["number"], "merge_commit": merge_commit, **verified_pr},
            )
        merge_commit = getattr(self, "release_merge_commit", None) or self.github.require_merged_pr(pr)
        if not merge_commit:
            raise RuntimeError("stable promotion is not merged")
        if action == "deploy":
            deployed = self.github.wait_deploy(merge_commit)
            subprocess.run(
                (sys.executable, "tools/smoke_public.py"),
                cwd=self.repository,
                check=True,
                timeout=600,
            )
            return StepOutcome(StepResult.PASS, {"merge_commit": merge_commit, **deployed})
        if action == "rollout":
            child_plan = rollout_plan(self.repository, full_diagnostics=True)
            child_report, child_code = OperationRunner(
                self.repository, self
            ).run(child_plan, acquire_lock=False)
            if child_code not in {0, 2}:
                raise RuntimeError("post-release rollout failed")
            result = StepResult.PASS if child_code == 0 else StepResult.DIAGNOSTIC_FAILED
            return StepOutcome(
                result,
                {"child_run_id": child_report["run_id"], "status": child_report["status"]},
            )
        raise NotImplementedError("unknown release action")

    def execute(
        self,
        step: PlanStep,
        *,
        dry_run: bool,
        verify_only: bool = False,
    ) -> StepOutcome:
        if step.adapter == "preflight":
            transports = self._connect_android_transports()
            return StepOutcome(
                StepResult.PASS,
                {
                    "policy": "valid",
                    "fleet_members": len(self.fleet["order"]),
                    **transports,
                },
            )
        if step.adapter == "release":
            return self._release_execute(step, dry_run, verify_only)
        if step.adapter == "restore":
            return self._restore_execute(step, dry_run, verify_only)
        if step.adapter == "qnap":
            rows = qnap_status(".env", repository=self.repository)
            unhealthy = sorted(
                name
                for name, value in rows.items()
                if value.get("status") != "running"
                or value.get("health") not in {None, "healthy"}
            )
            summary = {
                "services": len(rows),
                "unhealthy": unhealthy,
                "mode": "health" if dry_run or verify_only else step.action,
            }
            if unhealthy:
                return StepOutcome(StepResult.DIAGNOSTIC_FAILED, summary)
            if step.action == "reconcile" and not dry_run and not verify_only:
                # The deploy adapter is enabled only after the versioned QNAP
                # lock exists. Its exact lock-to-private-state bridge is kept in
                # qnap_lock.py and refuses unapproved digests.
                self._run_json(
                    [
                        sys.executable,
                        "tools/qnap_lock.py",
                        "deploy",
                        "--lock",
                        "manifests/locks/qnap-stable.json",
                    ],
                    timeout=1200,
                )
                return StepOutcome(StepResult.PASS, summary)
            return StepOutcome(StepResult.NO_CHANGE, summary)
        if step.adapter == "profile-sync":
            if dry_run or verify_only:
                return StepOutcome(
                    StepResult.NO_CHANGE,
                    {
                        "mode": "verify" if verify_only else "dry-run",
                        "publisher": self.fleet["publisher"],
                        "canaries": list(self.canaries),
                    },
                )
            self._run_json(
                [
                    sys.executable,
                    "tools/kodi_rapideo_token.py",
                    "export",
                    "--device",
                    self.fleet["publisher"],
                    "--adb",
                    self.adb,
                    "--adb-server-port",
                    str(self.adb_server_port),
                ],
                timeout=120,
                adapter="rapideo-token",
            )
            self._run_json(
                [
                    sys.executable,
                    "tools/kodi_umbrella_settings.py",
                    "export",
                    "--device",
                    self.fleet["publisher"],
                    "--adb",
                    self.adb,
                    "--adb-server-port",
                    str(self.adb_server_port),
                ],
                timeout=120,
                adapter="umbrella-private",
            )
            published = self._portable_with_retry(
                "publish", self.fleet["publisher"]
            )
            if published["status"] != "CONVERGED":
                raise RuntimeError("portable-state publisher did not converge")
            command = [
                sys.executable,
                "tools/profile_sync_portable_release.py",
                "converge",
                "--adb",
                self.adb,
                "--adb-server-port",
                str(self.adb_server_port),
            ]
            for canary in self.canaries:
                command.extend(("--canary", canary))
            result = self._run_json(
                command,
                timeout=1800,
                adapter="profile-sync",
            )
            return StepOutcome(
                StepResult.NO_CHANGE
                if result.get("status") == "NO_CHANGE"
                else StepResult.PASS,
                {
                    "status": result.get("status"),
                    "bundle_id": result.get("bundle_id"),
                    "active_revision": result.get("active_revision"),
                    "canary_checks": len(result.get("canaries", [])),
                    "backups": result.get("backups", []),
                },
            )
        if step.adapter in {"android", "flatpak"}:
            inventory = self._inventory(step.target)
            if dry_run or verify_only:
                if step.adapter == "android":
                    portable = self._portable("audit", step.target)
                    inventory["portable_status"] = portable.get("status")
                return StepOutcome(StepResult.PASS, inventory)
            if step.adapter == "android":
                return self._android_converge(step.target)
            # The existing Flatpak adapter already contains target binding,
            # lifecycle qualification, rollback and exact artifact checks.
            # Its invocation is assembled by the dedicated helper.
            result = self._run_json(
                [
                    sys.executable,
                    "tools/kodi_flatpak_stable_rollout.py",
                    "--device",
                    step.target,
                ],
                timeout=1200,
            )
            status = result.get("rollout_mode")
            return StepOutcome(
                StepResult.NO_CHANGE if status == "NO_CHANGE" else StepResult.PASS,
                {
                    "device": step.target,
                    "platform": "linux-flatpak",
                    "rollout_mode": status,
                    "sync_status": result.get("sync_status"),
                },
            )
        if step.adapter == "tests":
            if dry_run:
                return StepOutcome(StepResult.SKIPPED, {"reason": "dry-run"})
            command = [str(self.repository / "tests/e2e/run.sh")]
            subprocess.run(command, cwd=self.repository, check=True, timeout=1800)
            return StepOutcome(StepResult.PASS, {"suite": "tests/e2e/run.sh"})
        if step.action == "skip":
            return StepOutcome(StepResult.SKIPPED, {"reason": "operator option"})
        raise NotImplementedError("adapter is not implemented: %s" % step.adapter)


class OperationRunner:
    def __init__(self, repository: Path, executor=None):
        self.repository = Path(repository).resolve()
        self.executor = executor or ProductionExecutor(self.repository)

    def _fresh_state(self, run_id, plan_document, dry_run):
        return {
            "schema": 1,
            "run_id": run_id,
            "plan_id": plan_document["plan_id"],
            "operation": plan_document["operation"],
            "status": None,
            "dry_run": bool(dry_run),
            "created_at": utc_now(),
            "updated_at": utc_now(),
            "steps": {},
        }

    def _assert_plan_current(self, plan_document):
        if plan_document["operation"] == "release":
            # Release begins from the pinned base lock and intentionally changes
            # it through a reviewed PR. The release adapter validates that exact
            # transition before deploy and rollout.
            return
        stable = self.repository / "manifests/locks/stable.json"
        import hashlib

        current = hashlib.sha256(stable.read_bytes()).hexdigest()
        if current != plan_document["stable_lock_sha256"]:
            raise RuntimeError("stable lock drifted from plan")
        qnap = self.repository / "manifests/locks/qnap-stable.json"
        expected = plan_document.get("qnap_lock_sha256")
        observed = hashlib.sha256(qnap.read_bytes()).hexdigest() if qnap.is_file() else None
        if observed != expected:
            raise RuntimeError("QNAP stable lock drifted from plan")

    def run(
        self,
        plan: OperationPlan,
        *,
        dry_run=False,
        run_id=None,
        resume=False,
        acquire_lock=True,
    ):
        plan_document = plan.document()
        run_id = run_id or uuid.uuid4().hex
        store = RunStore(self.repository, run_id)
        if hasattr(self.executor, "run_id") or isinstance(
            self.executor, ProductionExecutor
        ):
            self.executor.run_id = run_id
        if hasattr(self.executor, "plan_repository_commit") or isinstance(
            self.executor, ProductionExecutor
        ):
            self.executor.plan_repository_commit = plan_document[
                "repository_commit"
            ]
        if isinstance(self.executor, ProductionExecutor):
            options = plan_document.get("options", {})
            self.executor.external_attempts = options.get(
                "external_attempts", 3
            )
            self.executor.retry_seconds = options.get("retry_seconds", 5)
        if resume:
            stored_plan = store.read("plan.json")
            if stored_plan != plan_document:
                raise RuntimeError("resume plan differs from persisted plan")
            state = store.read("state.json")
            if bool(state["dry_run"]) != bool(dry_run):
                raise RuntimeError("resume cannot change dry-run mode")
        else:
            store.create()
            store.write("plan.json", plan_document)
            state = self._fresh_state(run_id, plan_document, dry_run)
            store.write("state.json", state)
        lock = OperationLock(self.repository, run_id) if acquire_lock else nullcontext()
        with lock:
            try:
                self._assert_plan_current(plan_document)
            except RuntimeError:
                state["status"] = RunStatus.DRIFTED.value
                state["updated_at"] = utc_now()
                store.write("state.json", state)
                raise
            outcomes = []
            terminal_status = None
            for step in plan.steps:
                prior = state["steps"].get(step.step_id)
                if isinstance(self.executor, ProductionExecutor):
                    self.executor.prior_summary = (prior or {}).get("summary", {})
                try:
                    if prior and prior["result"] in {
                        StepResult.PASS.value,
                        StepResult.NO_CHANGE.value,
                    }:
                        superseded = (
                            plan.operation == "restore"
                            and step.action == "uninstall"
                            and any(
                                state["steps"].get(later.step_id, {}).get("result")
                                in {
                                    StepResult.PASS.value,
                                    StepResult.NO_CHANGE.value,
                                }
                                for later in plan.steps
                                if later.action in {"install", "profile"}
                            )
                        )
                        if superseded:
                            outcomes.append(StepResult(prior["result"]))
                            continue
                        outcome = self.executor.execute(
                            step,
                            dry_run=dry_run,
                            verify_only=True,
                        )
                        if outcome.result not in {
                            StepResult.PASS,
                            StepResult.NO_CHANGE,
                        }:
                            raise RuntimeError("completed step verification failed")
                        outcomes.append(StepResult(prior["result"]))
                        continue
                    outcome = self.executor.execute(step, dry_run=dry_run)
                except DeviceUnavailable:
                    outcome = StepOutcome(
                        StepResult.DEFERRED,
                        {"reason": "device_unavailable"},
                    )
                except OperationAdapterError as error:
                    outcome = StepOutcome(
                        StepResult.ERROR,
                        {
                            "error_type": type(error).__name__,
                            "adapter": error.adapter,
                        },
                    )
                except Exception as error:
                    outcome = StepOutcome(
                        StepResult.ERROR,
                        {"error_type": type(error).__name__},
                    )
                state["steps"][step.step_id] = {
                    "result": outcome.result.value,
                    "summary": outcome.summary,
                    "finished_at": utc_now(),
                }
                state["updated_at"] = utc_now()
                store.write("state.json", state)
                store.write_evidence(
                    "%s.json" % step.step_id.replace(":", "-"),
                    {
                        "schema": 1,
                        "step_id": step.step_id,
                        "result": outcome.result.value,
                        "summary": outcome.summary,
                    },
                )
                outcomes.append(outcome.result)
                if outcome.terminal_status is not None:
                    terminal_status = outcome.terminal_status
                    break
                if outcome.result == StepResult.ERROR and step.required:
                    break
                if (
                    step.target in plan.canaries
                    and outcome.result
                    in {StepResult.DEFERRED, StepResult.DIAGNOSTIC_FAILED}
                ):
                    break
            state["status"] = (
                terminal_status or overall_status(outcomes)
            ).value
            state["updated_at"] = utc_now()
            store.write("state.json", state)
            report = {
                "schema": 1,
                "run_id": run_id,
                "plan_id": plan_document["plan_id"],
                "operation": plan.operation,
                "scope": plan.scope,
                "status": state["status"],
                "dry_run": bool(dry_run),
                "devices": list(plan.devices),
                "steps": state["steps"],
                "finished_at": utc_now(),
            }
            store.write("report.json", report)
        return report, EXIT_CODES[RunStatus(report["status"])]
