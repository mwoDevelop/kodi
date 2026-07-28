"""Sanitized mwoScrapers network probe executed by Kodi's Python runtime.

This file is pushed to a device and invoked with ``RunScript``. It writes no
URLs, stream names, hashes, credentials or provider response bodies.
"""

import json
import os
import sys
import time
from urllib.request import Request, urlopen

import xbmcvfs


OUTPUT = xbmcvfs.translatePath(
    "special://temp/mwoscrapers-provider-probe.json"
)
LIBRARY = xbmcvfs.translatePath(
    "special://home/addons/script.module.mwoscrapers/lib"
)
CASES = (
    (
        "movie",
        {
            "title": "Sintel",
            "year": 2010,
            "imdb": "tt1727587",
        },
    ),
    (
        "episode",
        {
            "title": "Pilot",
            "year": 2008,
            "imdb": "tt0903747",
            "season": 1,
            "episode": 1,
            "tvshowtitle": "Breaking Bad",
        },
    ),
)
HEADER_PROFILES = (
    ("current", {"User-Agent": "MwoScrapers/0.1"}),
    (
        "browser",
        {
            "Accept": "application/json",
            "User-Agent": (
                "Mozilla/5.0 (Linux; Android 14; TV) "
                "AppleWebKit/537.36 (KHTML, like Gecko) "
                "Chrome/126.0 Safari/537.36"
            ),
        },
    ),
    (
        "stremio",
        {
            "Accept": "application/json",
            "User-Agent": "Stremio/4.4",
        },
    ),
)


def _probe_provider(provider_name, provider_class, case_name, data):
    provider = provider_class()
    failure = []
    original = provider._request_json

    def observed_request(url):
        del url
        try:
            return original(provider._stream_url(data))
        except Exception as error:
            failure.append(
                {
                    "error_type": type(error).__name__,
                    "http_status": getattr(error, "code", None),
                }
            )
            raise

    provider._request_json = observed_request
    started = time.monotonic()
    results = provider.sources(dict(data), {})
    return {
        "case": case_name,
        "elapsed_seconds": round(time.monotonic() - started, 3),
        "error_type": failure[-1]["error_type"] if failure else None,
        "http_status": failure[-1]["http_status"] if failure else None,
        "provider": provider_name,
        "result_count": len(results or ()),
    }


def _probe_headers(provider_class):
    provider = provider_class()
    url = provider._stream_url(CASES[0][1])
    reports = []
    for profile, headers in HEADER_PROFILES:
        started = time.monotonic()
        status = None
        error_type = None
        try:
            with urlopen(
                Request(url, headers=headers),
                timeout=provider.timeout,
            ) as response:
                status = response.status
                response.read(1)
        except Exception as error:
            error_type = type(error).__name__
            status = getattr(error, "code", None)
        reports.append(
            {
                "elapsed_seconds": round(time.monotonic() - started, 3),
                "error_type": error_type,
                "http_status": status,
                "profile": profile,
            }
        )
    return reports


def main():
    report = {
        "header_probe": [],
        "probe": [],
        "relay_probe": None,
        "registry_error": None,
        "schema": 1,
    }
    try:
        if LIBRARY not in sys.path:
            sys.path.insert(0, LIBRARY)
        from mwoscrapers import sources

        providers = sources(ret_all=True)
        for provider_name, provider_class in providers:
            for case_name, data in CASES:
                report["probe"].append(
                    _probe_provider(
                        provider_name,
                        provider_class,
                        case_name,
                        data,
                    )
                )
            if provider_name == "torrentio":
                report["header_probe"] = _probe_headers(provider_class)
                if len(sys.argv) > 1 and sys.argv[1]:
                    relay_class = type(
                        "RelayTorrentio",
                        (provider_class,),
                        {"base_url": sys.argv[1].rstrip("/")},
                    )
                    report["relay_probe"] = _probe_provider(
                        "torrentio-relay",
                        relay_class,
                        CASES[0][0],
                        CASES[0][1],
                    )
    except Exception as error:
        report["registry_error"] = type(error).__name__
    os.makedirs(os.path.dirname(OUTPUT), exist_ok=True)
    with open(OUTPUT, "w", encoding="utf-8") as destination:
        json.dump(report, destination, indent=2, sort_keys=True)
        destination.write("\n")


if __name__ == "__main__":
    main()
