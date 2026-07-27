import pytest

from tools.profile_sync_admin import validate_base_url


def test_admin_url_requires_https_or_loopback():
    assert validate_base_url("https://profiles.example.test/") == (
        "https://profiles.example.test"
    )
    assert validate_base_url("http://127.0.0.1:8765") == (
        "http://127.0.0.1:8765"
    )
    with pytest.raises(ValueError, match="HTTPS or loopback"):
        validate_base_url("http://private-nas:8765")
