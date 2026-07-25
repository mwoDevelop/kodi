import pytest

from tools.upstream_sync.versioning import (
    KodiVersion,
    next_downstream_version,
    require_strictly_newer,
)


@pytest.mark.parametrize(
    ("older", "newer"),
    [
        ("2.2.1", "2.2.9"),
        ("2.2.9", "2.2.10"),
        ("2.2.1~alpha", "2.2.1~beta"),
        ("2.2.1~beta2", "2.2.1~beta10"),
        ("2.2.1~beta", "2.2.1"),
        ("6.7.81.8", "6.7.81.9"),
    ],
)
def test_kodi_version_order(older, newer):
    assert KodiVersion(older) < KodiVersion(newer)


def test_umbrella_revision_increments_on_same_upstream():
    assert next_downstream_version("6.7.81", "6.7.81.9") == "6.7.81.10"


def test_revision_resets_on_new_upstream():
    assert next_downstream_version("6.7.82", "6.7.81.9") == "6.7.82.1"


def test_watch_revision_matches_existing_policy():
    assert next_downstream_version("0.25", "0.25.1") == "0.25.2"


def test_candidate_must_be_newer_than_both_channels():
    assert require_strictly_newer("6.7.82.1", "6.7.81.9", "6.7.81.8")
    with pytest.raises(ValueError):
        require_strictly_newer("6.7.81.9", "6.7.81.9", "6.7.81.8")
