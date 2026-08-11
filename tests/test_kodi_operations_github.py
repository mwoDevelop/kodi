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

    assert client.validate_promotion_content(
        pr, snapshot, attestation, candidate
    )["head_commit"] == "a" * 40
    candidate["qnap_candidate_sha256"] = "f" * 64
    with pytest.raises(GitHubError, match="QNAP lock differs"):
        client.validate_promotion_content(pr, snapshot, attestation, candidate)
