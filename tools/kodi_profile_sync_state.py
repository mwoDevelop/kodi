#!/usr/bin/env python3
"""Redacted in-Kodi probe/configuration for mwoDevelop Profile Sync."""

from __future__ import annotations

import hashlib
import json
import os
import re
import sys
import tempfile
from pathlib import Path
from urllib.parse import urlsplit


ADDON_ID = "service.mwodevelop.profilesync"
STATE_SCHEMA = 2
SUPPORTED_STATE_SCHEMAS = {1, STATE_SCHEMA}
SAFE_LOGICAL_ID = re.compile(r"^[a-z0-9][a-z0-9._-]{0,63}$")
SAFE_CHANNEL = SAFE_LOGICAL_ID
SETTING_IDS = (
    "enabled",
    "server_url",
    "ca_certificate",
    "logical_device_id",
    "channel",
    "startup_delay_seconds",
    "interval_hours",
    "read_only",
)


def canonical_json(value):
    return json.dumps(
        value, sort_keys=True, separators=(",", ":"), ensure_ascii=False
    ).encode("utf-8")


def _atomic_write(path, payload):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    descriptor, temporary = tempfile.mkstemp(
        prefix=".%s." % path.name, dir=str(path.parent)
    )
    try:
        with os.fdopen(descriptor, "wb") as handle:
            handle.write(payload)
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(temporary, path)
    finally:
        if os.path.exists(temporary):
            os.unlink(temporary)


def _server_summary(value):
    value = value.strip()
    if not value:
        return {
            "server_url_configured": False,
            "server_url_scheme": None,
            "server_url_sha256": None,
        }
    parsed = urlsplit(value)
    return {
        "server_url_configured": True,
        "server_url_scheme": parsed.scheme,
        "server_url_sha256": hashlib.sha256(
            value.encode("utf-8")
        ).hexdigest(),
    }


def _state_document(profile):
    path = Path(profile) / "state.json"
    if not path.is_file():
        return {
            "schema": STATE_SCHEMA,
            "status": "UNPAIRED",
            "enrollment": None,
        }
    document = json.loads(path.read_text(encoding="utf-8"))
    if (
        not isinstance(document, dict)
        or document.get("schema") not in SUPPORTED_STATE_SCHEMAS
    ):
        raise ValueError("unsupported Profile Sync state")
    return document


def probe(addon, profile):
    settings = {
        setting_id: addon.getSetting(setting_id) for setting_id in SETTING_IDS
    }
    state = _state_document(profile)
    enrollment = state.get("enrollment")
    if enrollment is not None and not isinstance(enrollment, dict):
        raise ValueError("Profile Sync enrollment is invalid")
    logical_id = settings["logical_device_id"].strip()
    channel = settings["channel"].strip()
    enrollment_logical = (
        enrollment.get("logical_device_id") if enrollment else None
    )
    enrollment_channel = enrollment.get("channel") if enrollment else None
    return {
        "addon_version": addon.getAddonInfo("version"),
        "enabled": settings["enabled"].strip().casefold() == "true",
        **_server_summary(settings["server_url"]),
        "ca_certificate_configured": bool(
            settings["ca_certificate"].strip()
        ),
        "logical_device_id": logical_id,
        "channel": channel,
        "startup_delay_seconds": settings["startup_delay_seconds"],
        "interval_hours": settings["interval_hours"],
        "read_only": settings["read_only"].strip().casefold() == "true",
        "status": state.get("status", "UNKNOWN"),
        "paired": enrollment is not None,
        "enrollment_id": enrollment.get("enrollment_id") if enrollment else None,
        "enrollment_generation": (
            enrollment.get("enrollment_generation") if enrollment else None
        ),
        "enrollment_logical_device_id": enrollment_logical,
        "enrollment_channel": enrollment_channel,
        "identity_consistent": bool(enrollment)
        and logical_id == enrollment_logical
        and channel == enrollment_channel,
        "has_access_token": bool(state.get("access_token")),
        "has_signing_seed": bool(state.get("signing_seed")),
        "has_encryption_private_key": bool(
            state.get("encryption_private_key")
        ),
        "encryption_key_registered": bool(
            enrollment and enrollment.get("encryption_key_id")
        ),
        "secret_state": state.get("secret_state"),
        "secret_type": state.get("secret_type"),
        "secret_set_generation": state.get("secret_set_generation"),
        "secret_last_verified_utc": state.get("secret_last_verified_utc"),
        "last_check_utc": state.get("last_check_utc"),
        "assigned_revision": state.get("assigned_revision"),
        "applied_revision": state.get("applied_revision"),
    }


def configure(
    addon,
    profile,
    server_url,
    logical_device_id,
    channel,
    read_only,
    ca_certificate=None,
):
    parsed = urlsplit(server_url)
    if (
        parsed.scheme not in {"http", "https"}
        or not parsed.netloc
        or parsed.username
        or parsed.password
    ):
        raise ValueError("Profile Sync server URL is invalid")
    if not SAFE_LOGICAL_ID.fullmatch(logical_device_id):
        raise ValueError("Profile Sync logical device id is invalid")
    if not SAFE_CHANNEL.fullmatch(channel):
        raise ValueError("Profile Sync channel is invalid")
    if read_only not in {"true", "false"}:
        raise ValueError("Profile Sync read_only value is invalid")
    ca_certificate = str(ca_certificate or "").strip()
    if ca_certificate and parsed.scheme != "https":
        raise ValueError("Profile Sync CA certificate requires HTTPS")
    if ca_certificate and (
        not ca_certificate.startswith("special://profile/")
        or ".." in ca_certificate.split("/")
    ):
        raise ValueError("Profile Sync CA certificate path is invalid")
    state = _state_document(profile)
    enrollment = state.get("enrollment")
    if enrollment and (
        enrollment.get("logical_device_id") != logical_device_id
        or enrollment.get("channel") != channel
    ):
        raise ValueError(
            "existing enrollment identity differs; explicit re-pair is required"
        )
    addon.setSetting("enabled", "true")
    addon.setSetting("server_url", server_url)
    addon.setSetting("ca_certificate", ca_certificate)
    addon.setSetting("logical_device_id", logical_device_id)
    addon.setSetting("channel", channel)
    addon.setSetting("read_only", read_only)
    return probe(addon, profile)


def configure_identity(
    addon,
    profile,
    logical_device_id,
    channel,
    startup_delay_seconds,
    interval_hours,
    read_only,
):
    if not SAFE_LOGICAL_ID.fullmatch(logical_device_id):
        raise ValueError("Profile Sync logical device id is invalid")
    if not SAFE_CHANNEL.fullmatch(channel):
        raise ValueError("Profile Sync channel is invalid")
    try:
        startup_delay = int(startup_delay_seconds)
        interval = float(interval_hours)
    except ValueError as error:
        raise ValueError("Profile Sync schedule is invalid") from error
    if not 0 <= startup_delay <= 300 or not 0.25 <= interval <= 168:
        raise ValueError("Profile Sync schedule is outside allowed bounds")
    if read_only not in {"true", "false"}:
        raise ValueError("Profile Sync read_only value is invalid")
    state = _state_document(profile)
    enrollment = state.get("enrollment")
    if enrollment and (
        enrollment.get("logical_device_id") != logical_device_id
        or enrollment.get("channel") != channel
    ):
        raise ValueError(
            "existing enrollment identity differs; explicit re-pair is required"
        )
    addon.setSetting("enabled", "true")
    addon.setSetting("logical_device_id", logical_device_id)
    addon.setSetting("channel", channel)
    addon.setSetting("startup_delay_seconds", str(startup_delay))
    addon.setSetting("interval_hours", str(interval_hours))
    addon.setSetting("read_only", read_only)
    return probe(addon, profile)


def configure_secret_mode(addon, profile, mode):
    if mode not in {"shadow", "canary", "active"}:
        raise ValueError("Profile Sync secret mode is invalid")
    state = _state_document(profile)
    enrollment = state.get("enrollment")
    if not enrollment or not state.get("encryption_private_key") or not enrollment.get(
        "encryption_key_id"
    ):
        raise ValueError("Profile Sync secret capability is not enrolled")
    addon.setSetting("secret_mode", mode)
    if addon.getSetting("secret_mode") != mode:
        raise RuntimeError("Profile Sync secret mode did not persist")
    return {**probe(addon, profile), "secret_mode": mode}


def _write_marker(path, document):
    _atomic_write(path, canonical_json(document) + b"\n")


def main():
    if len(sys.argv) < 3:
        raise SystemExit(
            "usage: kodi_profile_sync_state.py MODE MARKER [CONFIG...]"
        )
    marker = sys.argv[2]
    try:
        import xbmcaddon
        import xbmcvfs

        addon = xbmcaddon.Addon(ADDON_ID)
        profile = xbmcvfs.translatePath(addon.getAddonInfo("profile"))
        if sys.argv[1] == "probe" and len(sys.argv) == 3:
            result = probe(addon, profile)
        elif sys.argv[1] == "configure" and len(sys.argv) in {7, 8}:
            result = configure(
                addon,
                profile,
                sys.argv[3],
                sys.argv[4],
                sys.argv[5],
                sys.argv[6],
                sys.argv[7] if len(sys.argv) == 8 else None,
            )
        elif sys.argv[1] == "configure-identity" and len(sys.argv) == 8:
            result = configure_identity(
                addon,
                profile,
                sys.argv[3],
                sys.argv[4],
                sys.argv[5],
                sys.argv[6],
                sys.argv[7],
            )
        elif sys.argv[1] == "configure-secret-mode" and len(sys.argv) == 4:
            result = configure_secret_mode(addon, profile, sys.argv[3])
        else:
            raise ValueError("invalid Profile Sync state command")
        _write_marker(marker, {"ok": True, **result})
    except Exception as error:
        _write_marker(
            marker,
            {
                "ok": False,
                "error_type": type(error).__name__,
                "error": str(error)[:500],
            },
        )


if __name__ == "__main__":
    main()
