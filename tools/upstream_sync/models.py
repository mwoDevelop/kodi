"""Typed, multi-axis state used by every upstream adapter."""

from dataclasses import asdict, dataclass, field
from enum import Enum


class TextEnum(str, Enum):
    def __str__(self):
        return self.value


class ContentState(TextEnum):
    UNCHANGED = "unchanged"
    CHANGED = "changed"
    UNKNOWN = "unknown"


class ProvenanceState(TextEnum):
    UNCHANGED = "unchanged"
    CHANGED = "changed"
    UNKNOWN = "unknown"


class AvailabilityState(TextEnum):
    HEALTHY = "healthy"
    DEGRADED = "degraded"
    UNAVAILABLE = "unavailable"
    TRANSIENT_ERROR = "transient_error"


class HistoryState(TextEnum):
    FAST_FORWARD = "fast_forward"
    REWRITTEN = "rewritten"
    NOT_APPLICABLE = "not_applicable"
    UNKNOWN = "unknown"


class PrepareState(TextEnum):
    NOT_STARTED = "not_started"
    PREPARED = "prepared"
    CONFLICT = "conflict"
    QUARANTINED = "quarantined"


class ValidationState(TextEnum):
    NOT_STARTED = "not_started"
    VALID = "valid"
    INVALID = "invalid"


class PolicyAction(TextEnum):
    NOOP = "noop"
    OPEN_OR_UPDATE_PR = "open_or_update_pr"
    OPEN_OR_UPDATE_ISSUE = "open_or_update_issue"
    QUARANTINE = "quarantine"
    STOP = "stop"


@dataclass(frozen=True)
class Identity:
    version: str | None = None
    commit: str | None = None
    url: str | None = None
    sha256: str | None = None


@dataclass(frozen=True)
class Discovery:
    component: str
    accepted: Identity = field(default_factory=Identity)
    observed: Identity = field(default_factory=Identity)
    content: ContentState = ContentState.UNKNOWN
    provenance: ProvenanceState = ProvenanceState.UNKNOWN
    availability: AvailabilityState = AvailabilityState.HEALTHY
    history: HistoryState = HistoryState.UNKNOWN
    prepare: PrepareState = PrepareState.NOT_STARTED
    validation: ValidationState = ValidationState.NOT_STARTED
    changed_paths: tuple[str, ...] | None = None
    messages: tuple[str, ...] = ()

    def to_dict(self):
        return _enum_values(asdict(self))


def _enum_values(value):
    if isinstance(value, Enum):
        return value.value
    if isinstance(value, dict):
        return {key: _enum_values(item) for key, item in value.items()}
    if isinstance(value, (list, tuple)):
        return [_enum_values(item) for item in value]
    return value


def decide_action(discovery):
    """Derive the mutation policy without adapter-specific branching."""

    if discovery.history == HistoryState.REWRITTEN:
        return PolicyAction.STOP
    if discovery.prepare == PrepareState.CONFLICT:
        return PolicyAction.QUARANTINE
    if discovery.prepare == PrepareState.QUARANTINED:
        return PolicyAction.QUARANTINE
    if discovery.validation == ValidationState.INVALID:
        return PolicyAction.QUARANTINE
    if discovery.availability in (
        AvailabilityState.DEGRADED,
        AvailabilityState.UNAVAILABLE,
        AvailabilityState.TRANSIENT_ERROR,
    ):
        if (
            discovery.content == ContentState.UNCHANGED
            and discovery.provenance == ProvenanceState.CHANGED
        ):
            return PolicyAction.OPEN_OR_UPDATE_PR
        return PolicyAction.OPEN_OR_UPDATE_ISSUE
    if discovery.content == ContentState.CHANGED:
        return PolicyAction.OPEN_OR_UPDATE_PR
    if discovery.provenance == ProvenanceState.CHANGED:
        return PolicyAction.OPEN_OR_UPDATE_PR
    if (
        discovery.content == ContentState.UNCHANGED
        and discovery.provenance == ProvenanceState.UNCHANGED
    ):
        return PolicyAction.NOOP
    return PolicyAction.OPEN_OR_UPDATE_ISSUE
