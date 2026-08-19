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
    assert workflow.count('--devices "$KODI_DEVICES_FILE"') == 3
    assert workflow.count('--references "$KODI_REFERENCES_FILE"') == 3


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


def test_umbrella_qualification_is_hermetic_and_component_isolated():
    workflow = text(".github/workflows/certify-umbrella-hermetic.yml")

    assert "sudo -n env -i /usr/bin/bwrap" in workflow
    assert "--unshare-user --unshare-net" in workflow
    assert 'chmod 0711 "$sandbox"' in workflow
    assert '--uid "$runner_uid" --gid "$runner_gid"' in workflow
    assert '--ro-bind "$sandbox/repository" /work/repository' in workflow
    assert "python tools/checkout_locked_components.py" in workflow
    assert '--ro-bind "$sandbox/components" /work/components' in workflow
    assert "--setenv KODI_COMPONENT_ROOT /work/components" in workflow
    assert '--ro-bind "$sandbox/umbrella" /work/umbrella' in workflow
    assert "git clone --quiet --no-hardlinks umbrella" in workflow
    assert "git -C umbrella fetch --quiet --unshallow --no-tags origin" in workflow
    assert "run_sandboxed umbrella-tests /work/umbrella" in workflow
    assert "--setenv HOME /tmp" in workflow
    assert "persist-credentials: false" in workflow
    assert "tools/qualify_umbrella_snapshot.py validate" in workflow
    assert "qualification-attestation-$id.json" in workflow
    assert "qnap-stable.json" in workflow


def test_only_one_workflow_owns_pages_deployment():
    owners = []
    for path in Path(".github/workflows").glob("*.yml"):
        if "actions/deploy-pages@" in text(path):
            owners.append(path.name)

    assert owners == ["publish-pages.yml"]


def test_auto_approval_is_observe_only_until_explicitly_enabled():
    workflows = [
        text(".github/workflows/approve-umbrella-update.yml"),
        text(".github/workflows/approve-umbrella-promotion.yml"),
    ]

    assert "tools/umbrella_auto_approval.py" in workflows[0]
    assert "tools/umbrella_promotion_approval.py" in workflows[1]
    for workflow in workflows:
        assert "UMBRELLA_AUTO_MERGE_ENABLED == 'true'" in workflow
        assert "--match-head-commit" in workflow
        assert "environment: umbrella-auto-release" in workflow


def test_umbrella_qualification_failure_is_candidate_bound_and_persistent():
    certify = text(".github/workflows/certify-umbrella-hermetic.yml")
    pages = text(".github/workflows/publish-pages.yml")

    marker = "Umbrella qualification blocked: ${CANDIDATE_ID:0:12}"
    assert "record-qualification-state:" in certify
    assert marker in certify
    assert "candidate_id=$CANDIDATE_ID" in certify
    assert marker in pages
    assert "failure_code=qualification_failed" in pages
