"""Sanitized endpoint-fallback probe executed by Kodi's Python runtime."""

import json
import os
import sys
import time
from urllib.parse import urlsplit

import xbmcaddon
import xbmcvfs

OUTPUT = (
    sys.argv[1]
    if len(sys.argv) > 1 and sys.argv[1]
    else xbmcvfs.translatePath(
        "special://temp/mwoscrapers-endpoint-probe.json"
    )
)
LIBRARY = xbmcvfs.translatePath(
    "special://home/addons/script.module.mwoscrapers/lib"
)
MODULE_ID = "script.module.mwoscrapers"
MOVIE = {
    "title": "Sintel",
    "year": 2010,
    "imdb": "tt1727587",
}
EPISODE = {
    "title": "Pilot",
    "year": 2008,
    "imdb": "tt0903747",
    "season": 1,
    "episode": 1,
    "tvshowtitle": "Breaking Bad",
}
UNAVAILABLE_RELAY = "http://127.0.0.1:9/torrentio"


def _endpoint_class(url):
    hostname = (urlsplit(url).hostname or "").lower()
    if hostname in {"localhost", "::1"} or hostname.startswith("127."):
        return "loopback-test"
    octets = hostname.split(".")
    if len(octets) == 4 and all(part.isdigit() for part in octets):
        first, second = int(octets[0]), int(octets[1])
        if (
            first == 10
            or (first == 172 and 16 <= second <= 31)
            or (first == 192 and second == 168)
        ):
            return "lan-relay"
    if hostname.endswith(".lan"):
        return "lan-relay"
    return "public"


def _probe(provider_class, data):
    from mwoscrapers.health import _STATE

    _STATE.clear()
    provider = provider_class()
    provider.timeout = min(provider.timeout, 3)
    original_request = provider._request_json
    attempts = []

    def observed_request(url):
        attempt = {"endpoint_class": _endpoint_class(url)}
        started = time.monotonic()
        try:
            payload = original_request(url)
            attempt["outcome"] = "response"
            streams = payload.get("streams") if isinstance(payload, dict) else None
            attempt["stream_contract"] = isinstance(streams, list)
            return payload
        except Exception as error:
            attempt["error_type"] = type(error).__name__
            attempt["http_status"] = getattr(error, "code", None)
            attempt["outcome"] = "error"
            raise
        finally:
            attempt["elapsed_seconds"] = round(
                time.monotonic() - started, 3
            )
            attempts.append(attempt)

    provider._request_json = observed_request
    started = time.monotonic()
    results = provider.sources(dict(data), {})
    return {
        "attempts": attempts,
        "elapsed_seconds": round(time.monotonic() - started, 3),
        "result_count": len(results or ()),
    }


def _with_endpoint(addon, key, endpoint, provider_class, data):
    addon.setSetting(key, endpoint)
    return _probe(provider_class, data)


def main():
    report = {"ok": False, "schema": 1}
    addon = None
    original_torrentio = None
    original_comet = None
    try:
        if LIBRARY not in sys.path:
            sys.path.insert(0, LIBRARY)
        from mwoscrapers.providers.torrents.comet import source as comet
        from mwoscrapers.providers.torrents.torrentio import (
            source as torrentio,
        )
        from mwoscrapers.settings import provider_enabled

        addon = xbmcaddon.Addon(MODULE_ID)
        original_torrentio = addon.getSetting(
            "provider.torrentio.endpoint"
        )
        original_comet = addon.getSetting("provider.comet.endpoint")
        report.update(
            {
                "configured": {
                    "comet_enabled": provider_enabled("comet"),
                    "torrentio_endpoint_class": _endpoint_class(
                        original_torrentio or torrentio.base_url
                    ),
                    "torrentio_enabled": provider_enabled("torrentio"),
                },
                "module_version": addon.getAddonInfo("version"),
            }
        )
        report["configured_movie"] = _with_endpoint(
            addon,
            "provider.torrentio.endpoint",
            original_torrentio,
            torrentio,
            MOVIE,
        )
        report["configured_episode"] = _with_endpoint(
            addon,
            "provider.torrentio.endpoint",
            original_torrentio,
            torrentio,
            EPISODE,
        )
        report["public_movie"] = _with_endpoint(
            addon,
            "provider.torrentio.endpoint",
            torrentio.base_url,
            torrentio,
            MOVIE,
        )
        report["unavailable_relay_movie"] = _with_endpoint(
            addon,
            "provider.torrentio.endpoint",
            UNAVAILABLE_RELAY,
            torrentio,
            MOVIE,
        )
        report["comet_public_movie"] = _with_endpoint(
            addon,
            "provider.comet.endpoint",
            comet.base_url,
            comet,
            MOVIE,
        )
        report["ok"] = True
    except Exception as error:  # noqa: BLE001 - report Kodi probe boundary
        report["error_type"] = type(error).__name__
    finally:
        if addon is not None:
            if original_torrentio is not None:
                addon.setSetting(
                    "provider.torrentio.endpoint",
                    original_torrentio,
                )
            if original_comet is not None:
                addon.setSetting("provider.comet.endpoint", original_comet)
        os.makedirs(os.path.dirname(OUTPUT), exist_ok=True)
        with open(OUTPUT, "w", encoding="utf-8") as destination:
            json.dump(report, destination, indent=2, sort_keys=True)
            destination.write("\n")


if __name__ == "__main__":
    main()
