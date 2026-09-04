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
    assert workflow.count('--devices "$KODI_DEVICES_FILE"') == 5
    assert workflow.count('--references "$KODI_REFERENCES_FILE"') == 5


def test_certification_restores_authoritative_umbrella_secrets_before_matrix():
    workflow = text(".github/workflows/certify-testing.yml")

    adapter = "python tools/kodi_umbrella_settings.py apply"
    matrix = "python tools/certify_device_matrix.py"
    assert workflow.count(adapter) == 2
    assert workflow.index(adapter) < workflow.index(matrix)
    assert 'umbrella_settings="$(dirname "$KODI_REFERENCES_FILE")/' in workflow
    assert workflow.count('--settings "$umbrella_settings"') == 2


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


def test_pure_stable_lock_promotion_does_not_rebuild_testing():
    workflow = text(".github/workflows/publish-testing.yml")
    trigger = workflow.split("permissions:", 1)[0]

    assert '"manifests/locks/stable.json"' in trigger
    assert '"manifests/locks/qnap-stable.json"' in trigger


def test_umbrella_auto_approval_ignores_device_qualified_promotions():
    workflow = text(".github/workflows/approve-umbrella-promotion.yml")

    assert 'attestation_kind" != "hermetic_ci"' in workflow
    assert "Non-hermetic stable promotion is outside Umbrella auto-approval" in workflow
    assert workflow.index('attestation_kind" != "hermetic_ci"') < workflow.index(
        "tools/umbrella_promotion_approval.py"
    )


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
    assert "https://github.com/umbrellaplug/umbrellaplug.github.io.git" in workflow
    assert '"$upstream_base:refs/upstream-base/$upstream_base"' in workflow
    assert '"refs/upstream-base/$upstream_base:refs/upstream-base/$upstream_base"' in workflow
    assert workflow.index('git -C "$sandbox/umbrella" cat-file -e') < workflow.index(
        "run_sandboxed umbrella-tests /work/umbrella"
    )
    assert "run_sandboxed umbrella-tests /work/umbrella" in workflow
    assert "--setenv HOME /tmp" in workflow
    assert "python -m tools.qualification_attestation create" in workflow
    assert "python -m tools.qualification_attestation verify" in workflow
    assert "persist-credentials: false" in workflow
    assert "tools/qualify_umbrella_snapshot.py validate" in workflow
    assert "qualification-attestation-$id.json" in workflow
    assert "qnap-stable.json" in workflow


def test_attestation_cli_uses_package_safe_entrypoint_in_release_workflows():
    for path in (
        ".github/workflows/certify-umbrella-hermetic.yml",
        ".github/workflows/approve-umbrella-promotion.yml",
        ".github/workflows/deploy-stable.yml",
    ):
        workflow = text(path)
        assert "python tools/qualification_attestation.py" not in workflow
        assert "python -m tools.qualification_attestation" in workflow


def test_only_one_workflow_owns_pages_deployment():
    owners = []
    for path in Path(".github/workflows").glob("*.yml"):
        if "actions/deploy-pages@" in text(path):
            owners.append(path.name)

    assert owners == ["publish-pages.yml"]


def test_pages_publication_waits_for_umbrella_certification():
    workflow = text(".github/workflows/publish-pages.yml")
    triggers = workflow.split("permissions:", 1)[0]

    assert "- certify Umbrella hermetically" in triggers
    assert "- deploy stable" in triggers
    assert "- publish testing" not in triggers


def test_policy_automerge_is_explicitly_gated_without_human_approval():
    workflows = [
        text(".github/workflows/approve-umbrella-update.yml"),
        text(".github/workflows/approve-umbrella-promotion.yml"),
    ]

    assert "tools/umbrella_auto_approval.py" in workflows[0]
    assert "tools/umbrella_promotion_approval.py" in workflows[1]
    for workflow in workflows:
        assert "UMBRELLA_AUTO_MERGE_ENABLED == 'true'" in workflow
        assert "GH_TOKEN: ${{ github.token }}" in workflow
        assert "actions: write" in workflow
        assert "--match-head-commit" in workflow
        assert "environment: umbrella-auto-release" not in workflow
        assert "gh pr review" not in workflow
        assert 'actions/runs/$run_id/approve' in workflow
        assert '--event pull_request' in workflow
        assert 'test "$run_conclusion" = "success"' in workflow
    assert "gh workflow run publish-testing.yml" in workflows[0]
    assert "gh workflow run deploy-stable.yml" in workflows[1]


def test_reconcile_reuses_an_identical_open_candidate_head():
    workflow = text(".github/workflows/reconcile-upstreams.yml")

    assert 'git diff --quiet "$remote_sha" HEAD -- manifests/locks/testing.json' in workflow
    assert 'git reset --hard "$remote_sha"' in workflow
    assert 'remote_base="$(git merge-base "$remote_sha" "$BASE_COMMIT")"' in workflow


def test_umbrella_qualification_failure_is_candidate_bound_and_persistent():
    certify = text(".github/workflows/certify-umbrella-hermetic.yml")
    pages = text(".github/workflows/publish-pages.yml")

    marker = "Umbrella qualification blocked: ${CANDIDATE_ID:0:12}"
    assert "record-qualification-state:" in certify
    assert marker in certify
    assert "candidate_id=$CANDIDATE_ID" in certify
    assert marker in pages
    assert "failure_code=qualification_failed" in pages
