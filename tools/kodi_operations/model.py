"""Strict public model for Kodi operation plans and reports."""

from __future__ import annotations

import hashlib
import json
import re
from dataclasses import asdict, dataclass, field
from enum import Enum
from typing import Any


SCHEMA = 1


class RunStatus(str, Enum):
    COMPLETE = "COMPLETE"
    PARTIAL = "PARTIAL"
    WAITING_APPROVAL = "WAITING_APPROVAL"
    FAILED = "FAILED"
    DRIFTED = "DRIFTED"
    RECOVERY_REQUIRED = "RECOVERY_REQUIRED"


class StepResult(str, Enum):
    PASS = "PASS"
    NO_CHANGE = "NO_CHANGE"
    DEFERRED = "DEFERRED"
    DIAGNOSTIC_FAILED = "DIAGNOSTIC_FAILED"
    ROLLED_BACK = "ROLLED_BACK"
    SKIPPED = "SKIPPED"
    ERROR = "ERROR"


EXIT_CODES = {
    RunStatus.COMPLETE: 0,
    RunStatus.PARTIAL: 2,
    RunStatus.WAITING_APPROVAL: 3,
    RunStatus.DRIFTED: 4,
    RunStatus.FAILED: 5,
    RunStatus.RECOVERY_REQUIRED: 6,
}


def canonical_json(value: Any) -> bytes:
    return json.dumps(
        value,
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=False,
    ).encode("utf-8")


def digest_document(value: Any) -> str:
    return hashlib.sha256(canonical_json(value)).hexdigest()


@dataclass(frozen=True)
class PlanStep:
    step_id: str
    adapter: str
    action: str
    target: str | None = None
    mutation: bool = False
    required: bool = True
    wave: int = 0
    capabilities: tuple[str, ...] = ()

    def public(self) -> dict[str, Any]:
        value = asdict(self)
        value["capabilities"] = list(self.capabilities)
        return value


@dataclass(frozen=True)
class OperationPlan:
    operation: str
    repository_commit: str
    stable_lock_sha256: str
    stable_snapshot_id: str
    qnap_lock_sha256: str | None
    scope: str
    devices: tuple[str, ...]
    canaries: tuple[str, ...]
    steps: tuple[PlanStep, ...]
    options: dict[str, Any] = field(default_factory=dict)
    schema: int = SCHEMA

    def payload(self) -> dict[str, Any]:
        return {
            "schema": self.schema,
            "operation": self.operation,
            "repository_commit": self.repository_commit,
            "stable_lock_sha256": self.stable_lock_sha256,
            "stable_snapshot_id": self.stable_snapshot_id,
            "qnap_lock_sha256": self.qnap_lock_sha256,
            "scope": self.scope,
            "devices": list(self.devices),
            "canaries": list(self.canaries),
            "steps": [step.public() for step in self.steps],
            "options": self.options,
        }

    def document(self) -> dict[str, Any]:
        payload = self.payload()
        return {**payload, "plan_id": digest_document(payload)}

    @classmethod
    def from_document(cls, document: dict[str, Any]):
        if not isinstance(document, dict) or document.get("schema") != SCHEMA:
            raise ValueError("unsupported persisted operation plan")
        fields = {
            "schema",
            "operation",
            "repository_commit",
            "stable_lock_sha256",
            "stable_snapshot_id",
            "qnap_lock_sha256",
            "scope",
            "devices",
            "canaries",
            "steps",
            "options",
            "plan_id",
        }
        if set(document) != fields:
            raise ValueError("persisted operation plan has unsupported fields")
        payload = {key: value for key, value in document.items() if key != "plan_id"}
        if document["plan_id"] != digest_document(payload):
            raise ValueError("persisted operation plan ID mismatch")
        digests = (
            document["repository_commit"],
            document["stable_lock_sha256"],
            document["stable_snapshot_id"],
        )
        if (
            not all(isinstance(item, str) for item in digests)
            or not re.fullmatch(r"[0-9a-f]{40}", document["repository_commit"])
            or any(not re.fullmatch(r"[0-9a-f]{64}", item) for item in digests[1:])
            or (
                document["qnap_lock_sha256"] is not None
                and (
                    not isinstance(document["qnap_lock_sha256"], str)
                    or not re.fullmatch(r"[0-9a-f]{64}", document["qnap_lock_sha256"])
                )
            )
            or document["operation"] not in {"release", "rollout", "restore"}
            or document["scope"] not in {"full", "scoped"}
            or not isinstance(document["devices"], list)
            or not isinstance(document["canaries"], list)
            or not isinstance(document["steps"], list)
            or not isinstance(document["options"], dict)
        ):
            raise ValueError("persisted operation plan payload is invalid")
        step_fields = {
            "step_id",
            "adapter",
            "action",
            "target",
            "mutation",
            "required",
            "wave",
            "capabilities",
        }
        if any(not isinstance(item, dict) or set(item) != step_fields for item in document["steps"]):
            raise ValueError("persisted operation plan step is invalid")
        steps = tuple(
            PlanStep(
                step_id=item["step_id"],
                adapter=item["adapter"],
                action=item["action"],
                target=item["target"],
                mutation=item["mutation"],
                required=item["required"],
                wave=item["wave"],
                capabilities=tuple(item["capabilities"]),
            )
            for item in document["steps"]
        )
        if (
            len({step.step_id for step in steps}) != len(steps)
            or any(
                not step.step_id
                or not step.adapter
                or not step.action
                or not isinstance(step.mutation, bool)
                or not isinstance(step.required, bool)
                or not isinstance(step.wave, int)
                or step.wave < 0
                or any(not isinstance(item, str) or not item for item in step.capabilities)
                for step in steps
            )
        ):
            raise ValueError("persisted operation plan step values are invalid")
        return cls(
            operation=document["operation"],
            repository_commit=document["repository_commit"],
            stable_lock_sha256=document["stable_lock_sha256"],
            stable_snapshot_id=document["stable_snapshot_id"],
            qnap_lock_sha256=document["qnap_lock_sha256"],
            scope=document["scope"],
            devices=tuple(document["devices"]),
            canaries=tuple(document["canaries"]),
            steps=steps,
            options=document["options"],
            schema=document["schema"],
        )


def overall_status(results: list[StepResult]) -> RunStatus:
    if any(result == StepResult.ERROR for result in results):
        return RunStatus.FAILED
    if any(result == StepResult.ROLLED_BACK for result in results):
        return RunStatus.FAILED
    if any(
        result in {StepResult.DEFERRED, StepResult.DIAGNOSTIC_FAILED}
        for result in results
    ):
        return RunStatus.PARTIAL
    return RunStatus.COMPLETE
