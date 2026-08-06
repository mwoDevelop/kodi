from email.message import Message
from urllib.error import HTTPError

import pytest

from tools.upstream_sync.adapters import common


class Response:
    def __init__(self, payload):
        self.payload = payload

    def __enter__(self):
        return self

    def __exit__(self, *_args):
        return False

    def read(self, _limit):
        return self.payload


def test_api_request_uses_github_token(monkeypatch):
    observed = {}

    def open_request(request, timeout):
        observed["authorization"] = request.get_header("Authorization")
        observed["timeout"] = timeout
        return Response(b"{}")

    monkeypatch.setenv("GITHUB_TOKEN", "test-token")
    monkeypatch.setattr(common, "urlopen", open_request)

    assert common.read_url("https://api.github.com/repos/o/r") == b"{}"
    assert observed == {
        "authorization": "Bearer test-token",
        "timeout": 30,
    }


def test_rate_limit_403_is_reported_as_transient(monkeypatch):
    headers = Message()
    headers["X-RateLimit-Remaining"] = "0"

    def rate_limited(*_args, **_kwargs):
        raise HTTPError(
            "https://api.github.com/repos/o/r",
            403,
            "rate limit exceeded",
            headers,
            None,
        )

    monkeypatch.setattr(common, "urlopen", rate_limited)
    monkeypatch.setattr(common.time, "sleep", lambda _seconds: None)

    with pytest.raises(common.TransientSourceError, match="transient"):
        common.read_url("https://api.github.com/repos/o/r")


def test_non_rate_limit_403_remains_fatal(monkeypatch):
    headers = Message()

    def forbidden(*_args, **_kwargs):
        raise HTTPError(
            "https://api.github.com/repos/o/r",
            403,
            "forbidden",
            headers,
            None,
        )

    monkeypatch.setattr(common, "urlopen", forbidden)

    with pytest.raises(HTTPError):
        common.read_url("https://api.github.com/repos/o/r")
