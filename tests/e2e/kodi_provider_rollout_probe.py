"""Configure a private provider endpoint and verify Umbrella's module filter.

This helper runs inside Kodi. The report contains no URLs, source names,
hashes, credentials, tokens or provider response bodies.
"""

import ipaddress
import json
import os
import sys
from urllib.parse import urlsplit

import xbmc
import xbmcaddon
import xbmcvfs

OUTPUT = xbmcvfs.translatePath(
    "special://temp/mwodevelop-provider-rollout-probe.json"
)
UMBRELLA_ROOT = xbmcvfs.translatePath(
    "special://home/addons/plugin.video.umbrella"
)


def _safe_relay_endpoint(value):
    parsed = urlsplit(value)
    if (
        parsed.scheme != "http"
        or parsed.username is not None
        or parsed.password is not None
        or parsed.query
        or parsed.fragment
        or parsed.path.rstrip("/") != "/torrentio"
    ):
        return False
    try:
        address = ipaddress.ip_address(parsed.hostname or "")
    except ValueError:
        return False
    return any(
        address in network
        for network in (
            ipaddress.ip_network("10.0.0.0/8"),
            ipaddress.ip_network("172.16.0.0/12"),
            ipaddress.ip_network("192.168.0.0/16"),
        )
    )


def main():
    report = {
        "endpoint_configured": False,
        "mwoscrapers_candidate": False,
        "own_addon_filtered": False,
        "schema": 1,
    }
    try:
        endpoint = sys.argv[1] if len(sys.argv) > 1 else ""
        if endpoint:
            if not _safe_relay_endpoint(endpoint):
                raise ValueError("unsafe relay endpoint")
            xbmcaddon.Addon("script.module.mwoscrapers").setSetting(
                "provider.torrentio.endpoint",
                endpoint.rstrip("/"),
            )
            report["endpoint_configured"] = True
        if UMBRELLA_ROOT not in sys.path:
            sys.path.insert(0, UMBRELLA_ROOT)
        from resources.lib.downstream.addon_policy import (
            external_provider_candidates,
        )
        response = json.loads(
            xbmc.executeJSONRPC(
                '{"jsonrpc":"2.0","id":1,"method":"Addons.GetAddons",'
                '"params":{"type":"xbmc.python.module",'
                '"properties":["thumbnail","name"]}}'
            )
        )
        candidates = external_provider_candidates(
            response.get("result", {}).get("addons", []),
            "plugin.video.umbrella",
        )
        candidate_ids = {
            item.get("addonid") for item in candidates if item.get("addonid")
        }
        report["mwoscrapers_candidate"] = (
            "script.module.mwoscrapers" in candidate_ids
        )
        report["own_addon_filtered"] = (
            "plugin.video.umbrella" not in candidate_ids
        )
    except Exception as error:  # noqa: BLE001 - Kodi probe records the boundary
        report["error_type"] = type(error).__name__
    os.makedirs(os.path.dirname(OUTPUT), exist_ok=True)
    with open(OUTPUT, "w", encoding="utf-8") as destination:
        json.dump(report, destination, indent=2, sort_keys=True)
        destination.write("\n")


if __name__ == "__main__":
    main()
