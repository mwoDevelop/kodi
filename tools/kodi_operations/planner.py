"""Content-addressed plans for release, rollout and restore."""

from __future__ import annotations

import hashlib
import json
import subprocess
from pathlib import Path

from .manifest import load_fleet, load_policy
from .model import OperationPlan, PlanStep


class PlanError(ValueError):
    pass


def _sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _git(repository: Path, *args: str) -> str:
    return subprocess.run(
        ("git", "-C", str(repository), *args),
        check=True,
        capture_output=True,
        text=True,
    ).stdout.strip()


def repository_commit(repository: Path) -> str:
    commit = _git(repository, "rev-parse", "HEAD")
    if len(commit) != 40:
        raise PlanError("repository HEAD is not an exact commit")
    return commit


def _stable_identity(repository: Path):
    path = repository / "manifests/locks/stable.json"
    lock = json.loads(path.read_text(encoding="utf-8"))
    if lock.get("schema") != 2 or lock.get("channel") != "stable":
        raise PlanError("rollout requires a schema 2 stable lock")
    snapshot = lock.get("source_snapshot_id")
    if not isinstance(snapshot, str) or len(snapshot) != 64:
        raise PlanError("stable lock has no valid source snapshot")
    return _sha256(path), snapshot


def _qnap_lock_identity(repository: Path) -> str | None:
    path = repository / "manifests/locks/qnap-stable.json"
    return _sha256(path) if path.is_file() else None


def _ordered_devices(policy, fleet, requested):
    members = fleet["order"]
    policy_order = policy["device_order"]
    unknown = sorted(set(members).difference(policy_order))
    if unknown:
        raise PlanError(
            "fleet contains devices absent from operations policy: %s"
            % ", ".join(unknown)
        )
    if requested:
        requested = list(dict.fromkeys(requested))
        absent = sorted(set(requested).difference(members))
        if absent:
            raise PlanError("unknown requested devices: %s" % ", ".join(absent))
        selected = set(requested)
    else:
        selected = set(members)
    return tuple(item for item in policy_order if item in selected)


def rollout_plan(
    repository: Path,
    requested_devices=(),
    full_diagnostics=False,
):
    policy = load_policy(repository)
    fleet = load_fleet(repository)
    devices = _ordered_devices(policy, fleet, requested_devices)
    scope = "scoped" if requested_devices else "full"
    canaries = tuple(item for item in policy["canaries"] if item in devices)
    stable_sha, snapshot = _stable_identity(repository)
    qnap_sha = _qnap_lock_identity(repository)
    steps = [
        PlanStep(
            "preflight",
            "preflight",
            "validate",
            required=True,
            capabilities=("probe",),
        ),
        PlanStep(
            "qnap",
            "qnap",
            "reconcile" if scope == "full" and qnap_sha else "health",
            mutation=bool(scope == "full" and qnap_sha),
            required=True,
            wave=0,
            capabilities=("probe", "deploy") if qnap_sha else ("probe",),
        ),
    ]
    if scope == "full":
        steps.append(
            PlanStep(
                "profile-sync",
                "profile-sync",
                "converge",
                mutation=True,
                required=True,
                wave=1,
                capabilities=("portable-state", "candidate", "promote"),
            )
        )
    for index, device_id in enumerate(devices, 1):
        platform = fleet["devices"][device_id]["platform"]
        steps.append(
            PlanStep(
                "device:%s" % device_id,
                "android" if platform.startswith("android") else "flatpak",
                "converge",
                target=device_id,
                mutation=True,
                required=device_id in canaries or scope == "scoped",
                wave=index + (1 if scope == "full" else 0),
                capabilities=(
                    "probe",
                    "addons",
                    "profile-sync",
                    "portable-state",
                    "diagnostics",
                ),
            )
        )
    steps.append(
        PlanStep(
            "e2e",
            "tests",
            "verify",
            required=True,
            wave=len(devices) + (2 if scope == "full" else 1),
            capabilities=("probe",),
        )
    )
    return OperationPlan(
        operation="rollout",
        repository_commit=repository_commit(repository),
        stable_lock_sha256=stable_sha,
        stable_snapshot_id=snapshot,
        qnap_lock_sha256=qnap_sha,
        scope=scope,
        devices=devices,
        canaries=canaries,
        steps=tuple(steps),
        options={
            "full_diagnostics": bool(full_diagnostics),
            "external_attempts": policy["diagnostics"]["external_attempts"],
            "retry_seconds": policy["diagnostics"]["retry_seconds"],
        },
    )


def restore_plan(repository: Path, device: str, mode: str):
    if mode not in {"repair", "reinstall"}:
        raise PlanError("restore mode must be repair or reinstall")
    fleet = load_fleet(repository)
    if device not in fleet["devices"]:
        raise PlanError("unknown restore device: %s" % device)
    platform = fleet["devices"][device]["platform"]
    if not platform.startswith("android") and platform != "linux-flatpak":
        raise PlanError("restore platform is unsupported: %s" % platform)
    restore_adapter = (
        "restore" if platform.startswith("android") else "flatpak-restore"
    )
    base = rollout_plan(repository, (device,), full_diagnostics=True)
    steps = [
        PlanStep(
            "restore:preflight", restore_adapter, "preflight", device, False, True
        ),
        PlanStep(
            "restore:backup", restore_adapter, "backup", device, True, True
        ),
    ]
    if mode == "reinstall":
        steps.extend(
            (
                PlanStep(
                    "restore:uninstall",
                    restore_adapter,
                    "uninstall",
                    device,
                    True,
                    True,
                ),
                PlanStep(
                    "restore:install",
                    restore_adapter,
                    "install",
                    device,
                    True,
                    True,
                ),
            )
        )
    steps.extend(
        (
            PlanStep(
                "restore:profile", restore_adapter, "profile", device, True, True
            ),
            *base.steps[2:],
        )
    )
    return OperationPlan(
        operation="restore",
        repository_commit=base.repository_commit,
        stable_lock_sha256=base.stable_lock_sha256,
        stable_snapshot_id=base.stable_snapshot_id,
        qnap_lock_sha256=base.qnap_lock_sha256,
        scope="scoped",
        devices=(device,),
        canaries=base.canaries,
        steps=tuple(steps),
        options={"mode": mode, "full_diagnostics": True},
    )


def release_plan(
    repository: Path,
    no_promote=False,
    no_rollout=False,
    android_tv_canary="x88pro20",
):
    if (
        not isinstance(android_tv_canary, str)
        or not android_tv_canary
        or android_tv_canary == "bluestacks1"
    ):
        raise ValueError("release Android TV canary is invalid")
    stable_sha, snapshot = _stable_identity(repository)
    qnap_sha = _qnap_lock_identity(repository)
    actions = (
        ("release:preflight", "preflight", False),
        ("release:test", "test", False),
        ("release:security", "security", False),
        ("release:publish-testing", "publish-testing", True),
        ("release:qnap", "qnap", True),
        ("release:certify", "certify", True),
        ("release:promote", "promote", True),
        ("release:approval", "approval", False),
        ("release:deploy", "deploy", True),
        ("release:rollout", "rollout", True),
    )
    steps = []
    for index, (step_id, action, mutation) in enumerate(actions):
        skipped = (no_promote and action in {"promote", "approval", "deploy", "rollout"}) or (
            no_rollout and action == "rollout"
        )
        steps.append(
            PlanStep(
                step_id,
                "release",
                "skip" if skipped else action,
                mutation=mutation and not skipped,
                required=not skipped,
                wave=index,
                capabilities=("github",) if mutation else ("probe",),
            )
        )
    return OperationPlan(
        operation="release",
        repository_commit=repository_commit(repository),
        stable_lock_sha256=stable_sha,
        stable_snapshot_id=snapshot,
        qnap_lock_sha256=qnap_sha,
        scope="full",
        devices=(),
        canaries=("bluestacks1", android_tv_canary),
        steps=tuple(steps),
        options={
            "no_promote": no_promote,
            "no_rollout": no_rollout,
            "android_tv_canary": android_tv_canary,
        },
    )
