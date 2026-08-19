from pathlib import Path

import pytest

from tools.testing_lock_candidate import component_repository_targets, prepare


def test_repository_targets_include_non_upstream_components():
    root = Path("/checkout")
    components = {
        "managed": {
            "repository": "example/fork",
            "source": "fork/addon",
        },
        "owned": {
            "repository": "example/owned",
            "source": "owned-addon",
            "branch": "master",
        },
    }
    upstreams = {
        "managed": {
            "local_path": "fork",
            "target": {
                "repository": "example/fork",
                "branch": "mwo-main",
            },
        }
    }

    assert component_repository_targets(root, components, upstreams) == {
        "example/fork": (root / "fork", "mwo-main"),
        "example/owned": (root / "owned-addon", "master"),
    }


@pytest.mark.parametrize("source", ("../escape", "/absolute"))
def test_repository_targets_reject_unconfined_component_source(source):
    with pytest.raises(ValueError, match="confined relative path"):
        component_repository_targets(
            Path("/checkout"),
            {
                "owned": {
                    "repository": "example/owned",
                    "source": source,
                }
            },
            {},
        )


def test_component_mode_rejects_unknown_component(tmp_path):
    manifests = tmp_path / "manifests"
    (manifests / "locks").mkdir(parents=True)
    (manifests / "components.json").write_text('{"components": {}}')

    with pytest.raises(ValueError, match="unknown requested component"):
        prepare(tmp_path / "candidate", root=tmp_path, component_id="missing")
