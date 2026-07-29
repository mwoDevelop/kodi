import pytest

from tools.certify_device_matrix import (
    TESTING_ORIGIN,
    _allowed_origins,
    _forwarded_port,
    _latest_addons_database,
)


def test_changed_bytes_require_testing_but_identical_bytes_accept_stable():
    testing = {
        "changed": {"zip_sha256": "a" * 64},
        "unchanged": {"zip_sha256": "b" * 64},
    }
    stable = {
        "changed": {"zip_sha256": "c" * 64},
        "unchanged": {"zip_sha256": "b" * 64},
    }

    allowed = _allowed_origins(testing, stable)

    assert allowed["changed"] == {TESTING_ORIGIN}
    assert allowed["unchanged"] == {
        TESTING_ORIGIN,
        "repository.mwodevelop",
    }


def test_latest_addons_database_does_not_require_android_sort_version():
    listing = "\n".join(
        [
            "/profile/Database/Addons9.db",
            "/profile/Database/Addons33.db",
            "/profile/Database/Addons12.db",
            "unrelated",
        ]
    )

    assert _latest_addons_database(listing) == (
        "/profile/Database/Addons33.db"
    )

    with pytest.raises(RuntimeError, match="database is missing"):
        _latest_addons_database("vendor\n")


def test_dynamic_forward_port_is_validated():
    assert _forwarded_port("46454\n") == 46454

    for invalid in ("", "tcp:46454", "0", "65536", "-1"):
        with pytest.raises(RuntimeError, match="dynamic forward port"):
            _forwarded_port(invalid)
