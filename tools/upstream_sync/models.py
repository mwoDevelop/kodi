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
    COMPONENT_CANDIDATE = "component_candidate"
    PROVENANCE_ONLY_CANDIDATE = "provenance_only_candidate"
    TESTING_LOCK_CANDIDATE = "testing_lock_candidate"
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
    accepted_availability: AvailabilityState | None = None
    observed_availability: AvailabilityState | None = None
    sources: tuple["Discovery", ...] = ()

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


def decide_action(discovery, policy_profile="component_code"):
    """Derive a typed action from facts and a trusted policy profile."""

    if discovery.history == HistoryState.REWRITTEN:
        return PolicyAction.STOP
    if discovery.prepare == PrepareState.CONFLICT:
        return PolicyAction.QUARANTINE
    if discovery.prepare == PrepareState.QUARANTINED:
        return PolicyAction.QUARANTINE
    if discovery.validation == ValidationState.INVALID:
        return PolicyAction.QUARANTINE
    if policy_profile == "provider_observation":
        observed = discovery.observed_availability or discovery.availability
        if observed != AvailabilityState.HEALTHY:
            return PolicyAction.OPEN_OR_UPDATE_ISSUE
        if discovery.content == ContentState.CHANGED:
            return PolicyAction.QUARANTINE
        if (
            discovery.content == ContentState.UNCHANGED
            and discovery.provenance == ProvenanceState.CHANGED
        ):
            return PolicyAction.PROVENANCE_ONLY_CANDIDATE
        if (
            discovery.content == ContentState.UNCHANGED
            and discovery.provenance == ProvenanceState.UNCHANGED
        ):
            return PolicyAction.NOOP
        return PolicyAction.OPEN_OR_UPDATE_ISSUE
    if policy_profile != "component_code":
        raise ValueError("unknown policy profile: %s" % policy_profile)
    if discovery.availability in (
        AvailabilityState.DEGRADED,
        AvailabilityState.UNAVAILABLE,
        AvailabilityState.TRANSIENT_ERROR,
    ):
        return PolicyAction.OPEN_OR_UPDATE_ISSUE
    if discovery.content == ContentState.CHANGED:
        return PolicyAction.COMPONENT_CANDIDATE
    if discovery.provenance == ProvenanceState.CHANGED:
        return PolicyAction.COMPONENT_CANDIDATE
    if (
        discovery.content == ContentState.UNCHANGED
        and discovery.provenance == ProvenanceState.UNCHANGED
    ):
        return PolicyAction.NOOP
    return PolicyAction.OPEN_OR_UPDATE_ISSUE
