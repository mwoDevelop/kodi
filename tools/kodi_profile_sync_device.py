"""Configure, pair and synchronize Profile Sync inside a real Kodi process."""

from __future__ import annotations

import hashlib
import json
import os
import sys

import xbmc
import xbmcaddon
import xbmcvfs

ADDON_ID = "service.mwodevelop.profilesync"


def _write_atomic(path, payload, mode=0o600):
    temporary = path + ".tmp"
    with open(temporary, "wb") as handle:
        handle.write(payload)
        handle.flush()
        os.fsync(handle.fileno())
    os.chmod(temporary, mode)
    os.replace(temporary, path)


def main():
    config_path, marker = sys.argv[1:3]
    try:
        with open(config_path, encoding="utf-8") as source:
            config = json.load(source)
        addon_root = xbmcvfs.translatePath("special://home/addons/" + ADDON_ID)
        if addon_root not in sys.path:
            sys.path.insert(0, addon_root)
        from resources.lib.mwoprofilesync.apply import (
            KodiAddonSettings,
            TransactionalApplier,
        )
        from resources.lib.mwoprofilesync.pairing import pair_with_code
        from resources.lib.mwoprofilesync.portable import (
            KodiFavourites,
            PortableFavouritesAdapter,
        )
        from resources.lib.mwoprofilesync.state import StateStore
        from resources.lib.mwoprofilesync.sync import ReadOnlySync

        addon = xbmcaddon.Addon(ADDON_ID)
        profile = xbmcvfs.translatePath(addon.getAddonInfo("profile"))
        os.makedirs(profile, mode=0o700, exist_ok=True)
        with open(config["ca_source"], "rb") as source:
            ca_payload = source.read()
        if hashlib.sha256(ca_payload).hexdigest() != config["ca_sha256"]:
            raise ValueError("Profile Sync CA digest differs")
        ca_path = os.path.join(profile, "profile-sync-ca.pem")
        _write_atomic(ca_path, ca_payload)
        for setting_id, value in {
            "enabled": "true",
            "server_url": config["server_url"],
            "ca_certificate": (
                "special://profile/addon_data/"
                + ADDON_ID
                + "/profile-sync-ca.pem"
            ),
            "logical_device_id": config["logical_device_id"],
            "channel": config["channel"],
            "startup_delay_seconds": config["startup_delay_seconds"],
            "interval_hours": config["interval_hours"],
            "read_only": config["read_only"],
        }.items():
            addon.setSetting(setting_id, value)
        state = StateStore(profile)
        local = state.read()
        if config.get("replace_enrollment") and local.get("enrollment"):
            current = local["enrollment"]
            if (
                current.get("logical_device_id")
                != config["logical_device_id"]
                or current.get("channel") != config["channel"]
            ):
                raise ValueError("Profile Sync replacement identity differs")
            os.remove(state.path)
            local = state.read()
        if local.get("enrollment") is None:
            code = config.get("pairing_code")
            if not code:
                raise ValueError("Profile Sync enrollment is missing")
            pair_with_code(addon, state, code)
            local = state.read()
        enrollment = local["enrollment"]
        if (
            enrollment["logical_device_id"] != config["logical_device_id"]
            or enrollment["channel"] != config["channel"]
        ):
            raise ValueError("Profile Sync enrollment identity differs")
        applier = TransactionalApplier(
            profile,
            state,
            KodiAddonSettings(xbmcaddon.Addon),
            portable=PortableFavouritesAdapter(
                xbmcvfs.translatePath("special://profile"),
                KodiFavourites(xbmc.executeJSONRPC),
            ),
        )
        applier.recover()
        sync_result = ReadOnlySync(addon, state, applier=applier)()
        local = state.read()
        result = {
            "ok": True,
            "addon_version": addon.getAddonInfo("version"),
            "logical_device_id": enrollment["logical_device_id"],
            "enrollment_id": enrollment["enrollment_id"],
            "status": local.get("status"),
            "assigned_revision": local.get("assigned_revision"),
            "applied_revision": local.get("applied_revision"),
            "pending_report": bool(local.get("pending_report")),
            "sync_status": sync_result.get("status"),
        }
    except Exception as error:  # noqa: BLE001 - Kodi runtime boundary
        result = {
            "ok": False,
            "error_type": type(error).__name__,
            "error_code": getattr(error, "code", None),
            "http_status": getattr(error, "status", None),
        }
    _write_atomic(
        marker,
        (json.dumps(result, sort_keys=True) + "\n").encode("utf-8"),
    )


if __name__ == "__main__":
    main()
