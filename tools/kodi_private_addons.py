#!/usr/bin/env python3
"""Allow-listed private configuration adapters for restored Kodi add-ons."""

from __future__ import annotations

from pathlib import Path

try:
    from kodi_rapideo_configure import (
        ADAPTER as RAPIDEO_ADAPTER,
        configure as configure_rapideo,
        resolve_credentials as resolve_rapideo_credentials,
        validate_profile as validate_rapideo_profile,
    )
except ModuleNotFoundError:
    from tools.kodi_rapideo_configure import (
        ADAPTER as RAPIDEO_ADAPTER,
        configure as configure_rapideo,
        resolve_credentials as resolve_rapideo_credentials,
        validate_profile as validate_rapideo_profile,
    )


ADAPTERS = {
    RAPIDEO_ADAPTER: {
        "configure": configure_rapideo,
        "device_script": "tests/e2e/kodi_rapideo_configure.py",
        "resolve": resolve_rapideo_credentials,
        "validate": validate_rapideo_profile,
    }
}


def validate_profiles(profiles):
    if not isinstance(profiles, list):
        raise ValueError("invalid default add-on private profiles")
    validated = []
    for profile in profiles:
        adapter_name = (
            profile.get("adapter") if isinstance(profile, dict) else None
        )
        adapter = ADAPTERS.get(adapter_name)
        if adapter is None:
            raise ValueError("unsupported private add-on adapter")
        validated.append(adapter["validate"](profile))
    return validated


def validate_references(profiles, references):
    for profile in profiles:
        ADAPTERS[profile["adapter"]]["resolve"](profile, references)


def reconcile(adb, port, serial, profiles, references, repository):
    results = []
    for profile in profiles:
        adapter = ADAPTERS[profile["adapter"]]
        results.append(
            adapter["configure"](
                adb,
                port,
                serial,
                profile,
                references,
                Path(repository) / adapter["device_script"],
            )
        )
    return results
