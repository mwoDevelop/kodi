from pathlib import Path


def text(path):
    return Path(path).read_text(encoding="utf-8")


def test_certification_publishes_versioned_immutable_attestation():
    workflow = text(".github/workflows/certify-testing.yml")

    assert 'filename="device-attestation-$attestation_id.json"' in workflow
    assert "attestation_sha256" in workflow
    assert "attestation_id" in workflow


def test_certification_rolls_testing_to_both_canaries_before_matrix():
    workflow = text(".github/workflows/certify-testing.yml")

    rollout = "python tools/kodi_android_stable_rollout.py"
    matrix = "python tools/certify_device_matrix.py"
    assert workflow.count(rollout) == 2
    assert workflow.index(rollout) < workflow.index(matrix)
    assert "--device bluestacks1" in workflow
    assert '--device "$ANDROID_TV"' in workflow
    assert workflow.count("--channel testing") == 2


def test_promotion_binds_exact_attestation_and_qnap_candidate():
    workflow = text(".github/workflows/promote-stable.yml")

    for required in (
        "attestation_id:",
        "attestation_sha256:",
        "qnap_candidate_id:",
        "qnap_candidate_sha256:",
        "qnap-candidate-$QNAP_CANDIDATE_ID.json",
        "manifests/locks/qnap-stable.json",
    ):
        assert required in workflow


def test_all_qnap_builds_publish_scanned_immutable_approvals():
    workflows = (
        ".github/workflows/build-upstream-watchdog.yml",
        "mwoscrapers/.github/workflows/relay-image.yml",
    )

    for path in workflows:
        workflow = text(path)
        assert "Scan exact head before executing the Docker build" in workflow
        assert "qnap-image-approval.json" in workflow
        assert "security_report_sha256" in workflow
        assert "input_sha256" in workflow
        assert "workflow_run_id" in workflow

    # Profile Sync is a sibling source repository on the operator host, but it
    # is deliberately not part of this checkout in GitHub-hosted CI. Its own
    # repository tests the approval-producing workflow; this repository tests
    # the pinned service contract used to consume that approval.
    qnap = text("tools/qnap_images.py")
    assert '"mwoDevelop/kodi-profile-sync-server"' in qnap
    assert '"container.yml"' in qnap
    assert '("Dockerfile", "pyproject.toml", "README.md", "src")' in qnap


def test_deploy_requires_both_reviewed_locks():
    workflow = text(".github/workflows/deploy-stable.yml")

    assert '"manifests/locks/stable.json"' in workflow
    assert '"manifests/locks/qnap-stable.json"' in workflow
    assert "tools/qnap_lock.py validate" in workflow
