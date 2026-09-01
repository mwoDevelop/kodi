import base64
import hashlib
import json

import pytest

from tools.kodi_operations.github import GitHubClient, GitHubError


def test_verify_run_requires_exact_successful_head(tmp_path):
    client = GitHubClient(tmp_path)
    client.gh_json = lambda *_args: {
        "databaseId": 123,
        "headSha": "a" * 40,
        "status": "completed",
        "conclusion": "success",
        "url": "https://example.invalid/run/123",
    }

    assert client.verify_run("123", "a" * 40)["run_id"] == "123"
    with pytest.raises(GitHubError, match="exact-SHA"):
        client.verify_run("123", "b" * 40)
    with pytest.raises(GitHubError, match="invalid"):
        client.verify_run("not-a-run", "a" * 40)


def test_publication_dispatch_waits_for_stable_idle_queue(monkeypatch, tmp_path):
    client = GitHubClient(tmp_path)
    polls = iter(
        [
            [{"databaseId": 1, "status": "in_progress"}],
            [],
            [],
            [],
            [],
            [],
            [],
            [],
            [],
            [],
            [],
            [],
        ]
    )
    sleeps = []

    client.gh_json = lambda *_args: next(polls)
    monkeypatch.setattr("tools.kodi_operations.github.time.sleep", sleeps.append)

    client.wait_publication_queue_idle(quiet_polls=3, poll_seconds=2)

    assert sleeps == [2, 2, 2]


def test_default_idle_window_catches_a_delayed_workflow_run(monkeypatch, tmp_path):
    client = GitHubClient(tmp_path)
    calls = 0
    sleeps = []

    def gh_json(*_args):
        nonlocal calls
        calls += 1
        # Three complete empty polls have already happened when the delayed
        # workflow_run becomes visible in the fourth poll.
        if calls == 10:
            return [{"databaseId": 7, "status": "in_progress"}]
        return []

    client.gh_json = gh_json
    monkeypatch.setattr(
        "tools.kodi_operations.github.time.sleep", sleeps.append
    )

    client.wait_publication_queue_idle()

    assert len(sleeps) == 11
    assert calls == 36


def test_promotion_content_is_bound_to_exact_pr_head(tmp_path):
    client = GitHubClient(tmp_path)
    stable = json.dumps(
        {
            "schema": 2,
            "channel": "stable",
            "source_snapshot_id": "b" * 64,
            "attestation_id": "c" * 64,
            "attestation_sha256": "d" * 64,
        }
    ).encode()
    qnap = json.dumps({"candidate_id": "e" * 64}).encode()

    def gh_json(*args):
        joined = " ".join(args)
        if "stable.json?ref=" in joined and "qnap-stable" not in joined:
            payload = stable
        elif "qnap-stable.json?ref=" in joined:
            payload = qnap
        elif args[:2] == ("pr", "view"):
            return {
                "files": [
                    {"path": "manifests/locks/stable.json"},
                    {"path": "manifests/locks/qnap-stable.json"},
                ]
            }
        else:
            raise AssertionError(args)
        return {
            "encoding": "base64",
            "content": base64.b64encode(payload).decode(),
        }

    client.gh_json = gh_json
    pr = {"number": 7, "headRefOid": "a" * 40}
    snapshot = {"snapshot_id": "b" * 64}
    attestation = {
        "attestation_id": "c" * 64,
        "attestation_sha256": "d" * 64,
    }
    candidate = {
        "candidate_id": "e" * 64,
        "qnap_candidate_sha256": hashlib.sha256(qnap).hexdigest(),
    }

    assert (
        client.validate_promotion_content(pr, snapshot, attestation, candidate)[
            "head_commit"
        ]
        == "a" * 40
    )
    candidate["qnap_candidate_sha256"] = "f" * 64
    with pytest.raises(GitHubError, match="QNAP lock differs"):
        client.validate_promotion_content(pr, snapshot, attestation, candidate)


def test_wait_deploy_redispatches_once_when_pending_run_was_replaced(
    monkeypatch, tmp_path
):
    client = GitHubClient(tmp_path)
    commit = "a" * 40
    listings = iter(
        [
            [
                {
                    "databaseId": 10,
                    "headSha": commit,
                    "status": "completed",
                    "conclusion": "cancelled",
                    "url": "https://example.invalid/run/10",
                }
            ],
            [
                {
                    "databaseId": 11,
                    "headSha": commit,
                    "status": "completed",
                    "conclusion": "success",
                    "url": "https://example.invalid/run/11",
                }
            ],
        ]
    )
    dispatched = []

    client.gh_json = lambda *_args: next(listings)
    client.dispatch = lambda workflow, head, fields: dispatched.append(
        (workflow, head, fields)
    )

    class Result:
        stdout = commit + "\n"

    client._run = lambda *_args, **_kwargs: Result()
    monkeypatch.setattr("tools.kodi_operations.github.time.sleep", lambda _s: None)

    result = client.wait_deploy(commit)

    assert result["run_id"] == "11"
    assert dispatched == [("deploy-stable.yml", commit, {"dry_run": "false"})]
