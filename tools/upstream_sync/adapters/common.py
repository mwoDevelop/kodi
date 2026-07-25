"""Read-only subprocess and network helpers for adapters."""

import json
import os
import subprocess
import time
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen


MAX_DOWNLOAD = 64 * 1024 * 1024


class SourceUnavailable(RuntimeError):
    pass


class TransientSourceError(RuntimeError):
    pass


def run_git(checkout, *args):
    result = subprocess.run(
        ["git", "-C", str(checkout), *args],
        check=False,
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
    )
    if result.returncode:
        raise RuntimeError("git %s failed: %s" % (" ".join(args), result.stdout.strip()))
    return result.stdout.strip()


def ls_remote(repository, branch):
    url = "https://github.com/%s.git" % repository
    result = subprocess.run(
        ["git", "ls-remote", "--heads", url, "refs/heads/%s" % branch],
        check=False,
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
    )
    if result.returncode:
        raise TransientSourceError(result.stdout.strip())
    fields = result.stdout.split()
    if len(fields) != 2:
        raise SourceUnavailable("branch was not found: %s@%s" % (repository, branch))
    return fields[0]


def fetch_commit(checkout, repository, commit):
    run_git(
        checkout,
        "fetch",
        "--no-tags",
        "https://github.com/%s.git" % repository,
        commit,
    )


def read_url(url, limit=MAX_DOWNLOAD, attempts=3):
    headers = {"User-Agent": "mwoDevelop-upstream-sync/1"}
    token = os.environ.get("GITHUB_TOKEN")
    if token and url.startswith("https://api.github.com/"):
        headers["Authorization"] = "Bearer " + token
    last_error = None
    for attempt in range(attempts):
        try:
            with urlopen(Request(url, headers=headers), timeout=30) as response:
                payload = response.read(limit + 1)
            if len(payload) > limit:
                raise ValueError("download exceeds limit: %s" % url)
            return payload
        except HTTPError as error:
            if error.code in (404, 410):
                raise SourceUnavailable("%s returned HTTP %s" % (url, error.code)) from error
            if error.code not in (429, 500, 502, 503, 504):
                raise
            last_error = error
        except (TimeoutError, URLError) as error:
            last_error = error
        if attempt + 1 < attempts:
            time.sleep(2**attempt)
    raise TransientSourceError("transient fetch failure: %s" % url) from last_error


def github_commit(repository, ref):
    payload = json.loads(
        read_url(
            "https://api.github.com/repos/%s/commits/%s" % (repository, ref),
            limit=2 * 1024 * 1024,
        )
    )
    commit = payload.get("sha", "")
    if len(commit) != 40 or any(char not in "0123456789abcdef" for char in commit):
        raise ValueError("invalid GitHub commit response")
    return commit


def raw_url(repository, commit, path):
    return "https://raw.githubusercontent.com/%s/%s/%s" % (
        repository,
        commit,
        path.lstrip("/"),
    )
