from tools.upstream_sync.models import (
    AvailabilityState,
    ContentState,
    Discovery,
    HistoryState,
    PolicyAction,
    PrepareState,
    ProvenanceState,
    ValidationState,
    decide_action,
)


def test_noop_requires_both_content_and_provenance_to_be_unchanged():
    result = Discovery(
        component="umbrella",
        content=ContentState.UNCHANGED,
        provenance=ProvenanceState.UNCHANGED,
        history=HistoryState.FAST_FORWARD,
    )
    assert decide_action(result) == PolicyAction.NOOP


def test_magneto_reachable_replacement_is_a_provenance_pr():
    result = Discovery(
        component="provider_observations",
        content=ContentState.UNCHANGED,
        provenance=ProvenanceState.CHANGED,
        availability=AvailabilityState.DEGRADED,
        history=HistoryState.NOT_APPLICABLE,
    )
    assert decide_action(result) == PolicyAction.OPEN_OR_UPDATE_PR


def test_rewrite_stops_before_prepare():
    result = Discovery(
        component="umbrella",
        content=ContentState.UNKNOWN,
        provenance=ProvenanceState.CHANGED,
        history=HistoryState.REWRITTEN,
    )
    assert decide_action(result) == PolicyAction.STOP


def test_invalid_candidate_is_quarantined():
    result = Discovery(
        component="watchnixtoons2",
        content=ContentState.CHANGED,
        provenance=ProvenanceState.CHANGED,
        prepare=PrepareState.PREPARED,
        validation=ValidationState.INVALID,
    )
    assert decide_action(result) == PolicyAction.QUARANTINE


def test_transient_error_does_not_mutate_source_state():
    result = Discovery(
        component="provider_observations",
        availability=AvailabilityState.TRANSIENT_ERROR,
        history=HistoryState.NOT_APPLICABLE,
    )
    assert decide_action(result) == PolicyAction.OPEN_OR_UPDATE_ISSUE
