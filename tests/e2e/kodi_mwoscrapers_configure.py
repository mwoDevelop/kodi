"""Apply and verify the canonical non-secret mwoScrapers provider settings."""

import ipaddress
import json
import os
import sys
from urllib.parse import urlsplit

import xbmcvfs
import xbmcaddon


MODULE_ID = "script.module.mwoscrapers"
UMBRELLA_ID = "plugin.video.umbrella"
PUBLIC_TORRENTIO = "https://torrentio.strem.fun"
PUBLIC_COMET = "https://comet.feels.legal"


def _private_relay(endpoint):
    parsed = urlsplit(endpoint)
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
    return address.is_private


def _torrentio_endpoint(value):
    endpoint = value.rstrip("/")
    if endpoint != PUBLIC_TORRENTIO and not _private_relay(endpoint):
        raise ValueError("unsafe Torrentio endpoint")
    return endpoint


def _comet_endpoint(value):
    endpoint = value.rstrip("/")
    if endpoint != PUBLIC_COMET:
        raise ValueError("unexpected Comet endpoint")
    return endpoint


def _endpoint_class(value):
    return "lan-relay" if _private_relay(value) else "public"


def _write(path, payload):
    temporary = path + ".tmp"
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(temporary, "w", encoding="utf-8") as destination:
        json.dump(payload, destination, indent=2, sort_keys=True)
        destination.write("\n")
        destination.flush()
        os.fsync(destination.fileno())
    os.replace(temporary, path)


def main():
    output, torrentio, comet = sys.argv[1:4]
    report = {"ok": False, "schema": 1}
    stage = "validation"
    try:
        torrentio = _torrentio_endpoint(torrentio)
        comet = _comet_endpoint(comet)
        stage = "settings"
        addon = xbmcaddon.Addon(MODULE_ID)
        module_expected = {
            "provider.torrentio": "true",
            "provider.torrentio.endpoint": torrentio,
            "provider.comet": "true",
            "provider.comet.endpoint": comet,
        }
        for key, value in module_expected.items():
            addon.setSetting(key, value)
        if any(
            addon.getSetting(key) != value
            for key, value in module_expected.items()
        ):
            raise RuntimeError("provider settings did not converge")
        umbrella = xbmcaddon.Addon(UMBRELLA_ID)
        umbrella_expected = {
            "provider.external.enabled": "true",
            "external_provider.name": "mwoscrapers",
            "external_provider.module": MODULE_ID,
        }
        for key, value in umbrella_expected.items():
            umbrella.setSetting(key, value)
        if any(
            umbrella.getSetting(key) != value
            for key, value in umbrella_expected.items()
        ):
            raise RuntimeError("Umbrella provider binding did not converge")
        stage = "cache-clear"
        cache_mode = "file-reset"
        cache_path = xbmcvfs.translatePath(
            "special://profile/addon_data/plugin.video.umbrella/providers.db"
        )
        if os.path.exists(cache_path):
            os.remove(cache_path)
        if os.path.exists(cache_path):
            raise RuntimeError("Umbrella provider cache file remains")
        report.update(
            {
                "cache_cleared": True,
                "cache_clear_mode": cache_mode,
                "comet_enabled": True,
                "comet_endpoint_class": "public",
                "external_provider_enabled": True,
                "external_provider_module": MODULE_ID,
                "module_version": addon.getAddonInfo("version"),
                "ok": True,
                "torrentio_enabled": True,
                "torrentio_endpoint_class": _endpoint_class(torrentio),
            }
        )
    except Exception as error:  # noqa: BLE001 - sanitized device boundary
        report["error_type"] = type(error).__name__
        report["error_stage"] = stage
    _write(output, report)


if __name__ == "__main__":
    main()
