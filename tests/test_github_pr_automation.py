import copy

import pytest

from tools import github_pr_automation as policy


def fixture():
    return {"allow_auto_merge": False, "ruleset": {"name": "Product", "target": "branch",
            "enforcement": "active", "conditions": {"ref_name": {"include": ["~DEFAULT_BRANCH"]}},
            "bypass_actors": [{"actor_type": "User", "actor_id": 42, "bypass_mode": "pull_request"}],
            "rules": [{"type": "pull_request", "parameters": {"required_approving_review_count": 1,
                      "dismiss_stale_reviews_on_push": True, "required_review_thread_resolution": True}},
                     {"type": "required_status_checks", "parameters": {"strict_required_status_checks_policy": True,
                      "required_status_checks": [{"context": "test"}]}}, {"type": "deletion"}]}}


def test_preserves_reviews_bypass_and_unrelated_rules():
    before = fixture()
    after = policy.desired(before)
    assert before["allow_auto_merge"] is False
    assert after["allow_auto_merge"] is True
    for index in (0, 2):
        assert after["ruleset"]["rules"][index] == before["ruleset"]["rules"][index]
    assert after["ruleset"]["bypass_actors"] == before["ruleset"]["bypass_actors"]
    assert policy.desired(after) == after


def test_rejects_unexpected_review_baseline():
    before = fixture()
    before["ruleset"]["rules"][0]["parameters"]["required_approving_review_count"] = 0
    with pytest.raises(ValueError):
        policy.desired(before)


def test_dry_run_no_writes_and_apply_is_idempotent(tmp_path):
    state = fixture()
    writes = []
    def request(path, method="GET", body=None):
        if method != "GET":
            writes.append((path, method))
            if path:
                state["ruleset"] = copy.deepcopy(body)
            else:
                state["allow_auto_merge"] = body["allow_auto_merge"]
        return copy.deepcopy(state["ruleset"] if path else state)
    assert policy.configure(tmp_path, request=request)["state"] == "DRY_RUN"
    assert not writes and not list(tmp_path.iterdir())
    assert policy.configure(tmp_path, apply=True, request=request)["state"] == "APPLIED"
    assert len(writes) == 2
    backup = next(tmp_path.iterdir())
    assert backup.stat().st_mode & 0o777 == 0o600
    assert policy.configure(tmp_path, apply=True, request=request)["state"] == "NO_CHANGE"
    assert len(writes) == 2
