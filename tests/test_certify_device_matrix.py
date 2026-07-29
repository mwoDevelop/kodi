from tools.certify_device_matrix import TESTING_ORIGIN, _allowed_origins


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
