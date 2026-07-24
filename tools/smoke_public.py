#!/usr/bin/env python3
"""Verify the public Pages snapshot against its published manifest."""

import argparse
import hashlib
from urllib.parse import urljoin
from urllib.request import Request, urlopen


def fetch(url):
    with urlopen(Request(url, headers={"User-Agent": "mwo-kodi-smoke/1"}), timeout=30) as response:
        if response.status != 200:
            raise RuntimeError("%s returned %s" % (url, response.status))
        return response.read()


def verify(base):
    base = base.rstrip("/") + "/"
    manifest = fetch(urljoin(base, "artifact-manifest.sha256")).decode("ascii")
    checked = []
    for line in manifest.splitlines():
        digest, relative = line.split("  ", 1)
        payload = fetch(urljoin(base, relative))
        actual = hashlib.sha256(payload).hexdigest()
        if actual != digest:
            raise ValueError("%s checksum mismatch" % relative)
        checked.append(relative)
    return checked


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--base", default="https://mwodevelop.github.io/kodi/")
    args = parser.parse_args()
    checked = verify(args.base)
    print("verified %d public files" % len(checked))


if __name__ == "__main__":
    main()
