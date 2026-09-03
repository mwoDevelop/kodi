import re
from pathlib import Path


NODE24_ACTIONS = {
    "actions/checkout": "3d3c42e5aac5ba805825da76410c181273ba90b1",
    "actions/setup-python": "5fda3b95a4ea91299a34e894583c3862153e4b97",
    "actions/upload-artifact": "043fb46d1a93c77aae656e7c1c64a875d1fc6a0a",
    "actions/download-artifact": "3e5f45b2cfb9172054b4087a40e8e0b5a5461e7c",
    "actions/upload-pages-artifact": (
        "fc324d3547104276b827a68afc52ff2a11cc49c9"
    ),
    "actions/deploy-pages": "cd2ce8fcbc39b97be8ca5fce6e763baed58fa128",
    "docker/setup-buildx-action": (
        "bb05f3f5519dd87d3ba754cc423b652a5edd6d2c"
    ),
    "docker/login-action": "dbcb813823bdd20940b903addbd779551569679fd",
    "docker/build-push-action": (
        "53b7df96c91f9c12dcc8a07bcb9ccacbed38856a"
    ),
}
ACTION_REFERENCE = re.compile(
    r"uses:\s*([A-Za-z0-9._-]+/[A-Za-z0-9._-]+(?:/[A-Za-z0-9_./-]+)?)@"
    r"([A-Za-z0-9._-]+)"
)


def test_external_javascript_actions_use_reviewed_node24_commits():
    observed = {name: set() for name in NODE24_ACTIONS}
    unexpected = set()

    for workflow in sorted(Path(".github/workflows").glob("*.yml")):
        contents = workflow.read_text(encoding="utf-8")
        for action, reference in ACTION_REFERENCE.findall(contents):
            if action not in observed:
                unexpected.add(action)
                continue
            observed[action].add(reference)

    assert not unexpected, "review Node runtime for new actions: %s" % sorted(unexpected)
    assert all(observed.values())
    assert observed == {
        action: {commit} for action, commit in NODE24_ACTIONS.items()
    }


def test_upstream_discovery_uses_the_read_only_repository_token():
    workflow = Path(
        ".github/workflows/reconcile-upstreams.yml"
    ).read_text(encoding="utf-8")
    step = workflow.split(
        "- name: Discover immutable upstream state", 1
    )[1].split("- name: Publish read-only report", 1)[0]

    assert "GITHUB_TOKEN: ${{ github.token }}" in step
    assert "python -m tools.upstream_sync.cli discover" in step
