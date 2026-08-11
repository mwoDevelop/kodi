from pathlib import Path


def text(path):
    return Path(path).read_text(encoding="utf-8")


def test_certification_publishes_versioned_immutable_attestation():
    workflow = text(".github/workflows/certify-testing.yml")

    assert 'filename="device-attestation-$attestation_id.json"' in workflow
    assert "attestation_sha256" in workflow
    assert "attestation_id" in workflow


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
        "../kodi-profile-sync-server/.github/workflows/container.yml",
    )

    for path in workflows:
        workflow = text(path)
        assert "Scan exact head before executing the Docker build" in workflow
        assert "qnap-image-approval.json" in workflow
        assert "security_report_sha256" in workflow
        assert "input_sha256" in workflow
        assert "workflow_run_id" in workflow


def test_deploy_requires_both_reviewed_locks():
    workflow = text(".github/workflows/deploy-stable.yml")

    assert '"manifests/locks/stable.json"' in workflow
    assert '"manifests/locks/qnap-stable.json"' in workflow
    assert "tools/qnap_lock.py validate" in workflow
