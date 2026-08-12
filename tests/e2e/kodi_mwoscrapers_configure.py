"""Apply and verify the canonical non-secret mwoScrapers provider settings."""

import base64
import ipaddress
import json
import os
import sys
from urllib.parse import urlsplit

import xbmcaddon
import xbmcvfs

MODULE_ID = "script.module.mwoscrapers"
UMBRELLA_ID = "plugin.video.umbrella"
PUBLIC_TORRENTIO = "https://torrentio.strem.fun"
PUBLIC_COMET = "https://comet.feels.legal"
PUBLIC_ENDPOINTS = {
    "torrentio": PUBLIC_TORRENTIO,
    "comet": PUBLIC_COMET,
    "torz": "https://stremthru.elfhosted.com/stremio/torz",
    "mediafusion": "https://mediafusionfortheweebs.midnightignite.me",
    "eztv": "https://eztvx.to",
    "piratebay": "https://apibay.org",
}
CANONICAL_PROVIDERS = list(PUBLIC_ENDPOINTS)


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


def _configuration():
    if len(sys.argv) == 4:
        return {
            "enabled": CANONICAL_PROVIDERS,
            "endpoints": {
                "torrentio": sys.argv[2],
                "comet": sys.argv[3],
            },
        }
    if len(sys.argv) != 3:
        raise ValueError("invalid provider configuration arguments")
    encoded = sys.argv[2].encode("ascii")
    encoded += b"=" * (-len(encoded) % 4)
    payload = json.loads(base64.urlsafe_b64decode(encoded).decode("utf-8"))
    if set(payload) != {"enabled", "endpoints"}:
        raise ValueError("invalid provider configuration payload")
    return payload


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
    output = sys.argv[1]
    report = {"ok": False, "schema": 1}
    stage = "validation"
    try:
        configuration = _configuration()
        enabled = configuration["enabled"]
        endpoints = configuration["endpoints"]
        if (
            not isinstance(enabled, list)
            or not all(isinstance(name, str) for name in enabled)
            or set(enabled) - set(PUBLIC_ENDPOINTS)
            or set(endpoints) != set(PUBLIC_ENDPOINTS)
        ):
            raise ValueError("invalid provider set")
        validated = {}
        for name, expected in PUBLIC_ENDPOINTS.items():
            value = str(endpoints[name]).rstrip("/")
            if name == "torrentio":
                value = _torrentio_endpoint(value)
            elif name == "comet":
                value = _comet_endpoint(value)
            elif value != expected:
                raise ValueError(f"unexpected {name} endpoint")
            validated[name] = value
        stage = "settings"
        addon = xbmcaddon.Addon(MODULE_ID)
        module_expected = {}
        for name, endpoint in validated.items():
            module_expected[f"provider.{name}"] = (
                "true" if name in enabled else "false"
            )
            module_expected[f"provider.{name}.endpoint"] = endpoint
        module_changed = any(
            addon.getSetting(key) != value
            for key, value in module_expected.items()
        )
        for key, value in module_expected.items():
            if addon.getSetting(key) != value:
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
        umbrella_changed = any(
            umbrella.getSetting(key) != value
            for key, value in umbrella_expected.items()
        )
        for key, value in umbrella_expected.items():
            if umbrella.getSetting(key) != value:
                umbrella.setSetting(key, value)
        if any(
            umbrella.getSetting(key) != value
            for key, value in umbrella_expected.items()
        ):
            raise RuntimeError("Umbrella provider binding did not converge")
        changed = module_changed or umbrella_changed
        stage = "cache-clear"
        cache_mode = "not-needed"
        cache_path = xbmcvfs.translatePath(
            "special://profile/addon_data/plugin.video.umbrella/providers.db"
        )
        if changed and os.path.exists(cache_path):
            os.remove(cache_path)
            cache_mode = "file-reset"
        if changed and os.path.exists(cache_path):
            raise RuntimeError("Umbrella provider cache file remains")
        report.update(
            {
                "cache_cleared": changed,
                "cache_clear_mode": cache_mode,
                "changed": changed,
                "external_provider_enabled": True,
                "external_provider_module": MODULE_ID,
                "module_version": addon.getAddonInfo("version"),
                "ok": True,
                "providers": {
                    name: {
                        "enabled": name in enabled,
                        "endpoint_class": _endpoint_class(endpoint),
                    }
                    for name, endpoint in validated.items()
                },
                "torrentio_enabled": "torrentio" in enabled,
                "torrentio_endpoint_class": _endpoint_class(
                    validated["torrentio"]
                ),
                "comet_enabled": "comet" in enabled,
                "comet_endpoint_class": "public",
            }
        )
    except Exception as error:  # noqa: BLE001 - sanitized device boundary
        report["error_type"] = type(error).__name__
        report["error_stage"] = stage
    _write(output, report)


if __name__ == "__main__":
    main()
