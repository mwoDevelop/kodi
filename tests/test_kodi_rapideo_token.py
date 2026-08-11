import io
import json
import pickle

import pytest

from tools.kodi_rapideo_configure import load_authoritative_token
from tools.kodi_rapideo_token import _RestrictedUnpickler, _token


def test_restricted_store_extracts_only_token():
    payload = pickle.dumps(
        {"authtoken": ("token-value", 123.0)}, protocol=2
    )
    assert _token(payload) == "token-value"


def test_restricted_store_rejects_globals():
    payload = pickle.dumps(Exception("not safe"), protocol=2)
    with pytest.raises(pickle.UnpicklingError, match="global"):
        _RestrictedUnpickler(io.BytesIO(payload)).load()


def test_private_token_cache_requires_private_mode(tmp_path):
    path = tmp_path / "token.json"
    path.write_text(json.dumps({"schema": 1, "authtoken": "value"}))
    path.chmod(0o600)
    assert load_authoritative_token(path) == "value"
    path.chmod(0o644)
    with pytest.raises(ValueError, match="private"):
        load_authoritative_token(path)
