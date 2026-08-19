import json
from pathlib import Path

import pytest

from tools.umbrella_forward_rollback import prepare


CURRENT = "3b772adff9de10f1a144522b83c0d8ad698b0348"


def test_prepares_higher_version_from_known_good_sources(tmp_path):
    output = tmp_path / "candidate"
    value = prepare(
        Path("umbrella"), CURRENT, CURRENT, "6.7.81.21", "incident-test", output
    )

    assert value["kind"] == "forward_rollback"
    assert value["known_good_version"] == "6.7.81.20"
    assert value["release_version"] == "6.7.81.21"
    assert value["upstream_base_version"] == "6.7.81"
    addon = (output / "plugin.video.umbrella/addon.xml").read_text()
    assert 'version="6.7.81.21"' in addon
    assert "forward-rollback.json" not in value["files"]


def test_rejects_downgrade_disguised_as_rollback(tmp_path):
    with pytest.raises(ValueError, match="newer"):
        prepare(
            Path("umbrella"),
            CURRENT,
            CURRENT,
            "6.7.81.19",
            "incident-test",
            tmp_path / "candidate",
        )
