"""Configure, pair and synchronize Profile Sync inside a real Kodi process."""

from __future__ import annotations

import hashlib
import json
import os
import sys

import xbmc
import xbmcaddon
import xbmcgui
import xbmcvfs


ADDON_ID = "service.mwodevelop.profilesync"


def write_atomic(path, payload, mode=0o600):
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
        config = json.loads(open(config_path, encoding="utf-8").read())
        addon_root = xbmcvfs.translatePath(
            "special://home/addons/" + ADDON_ID
        )
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
        from resources.lib.mwoprofilesync.skin_menu import (
            HANDLER_ID as SKIN_MENU_HANDLER_ID,
            SkinMenuAdapter,
        )
        from resources.lib.mwoprofilesync.sync import ReadOnlySync

        addon = xbmcaddon.Addon(ADDON_ID)
        profile = xbmcvfs.translatePath(addon.getAddonInfo("profile"))
        os.makedirs(profile, mode=0o700, exist_ok=True)
        ca_payload = open(config["ca_source"], "rb").read()
        if hashlib.sha256(ca_payload).hexdigest() != config["ca_sha256"]:
            raise ValueError("Profile Sync CA digest differs")
        ca_path = os.path.join(profile, "profile-sync-ca.pem")
        write_atomic(ca_path, ca_payload)
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
            "read_only": "true" if config["read_only"] else "false",
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
                raise ValueError(
                    "Profile Sync replacement identity differs"
                )
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
        sync_result = None
        favourites_result = None
        if config["action"] in {"sync", "sync-favourites"}:
            settings = KodiAddonSettings(
                xbmcaddon.Addon, xbmc.executeJSONRPC
            )
            applier = TransactionalApplier(
                profile,
                state,
                settings,
                portable=PortableFavouritesAdapter(
                    xbmcvfs.translatePath("special://profile"),
                    KodiFavourites(xbmc.executeJSONRPC),
                ),
                handlers={
                    SKIN_MENU_HANDLER_ID: SkinMenuAdapter(
                        xbmcvfs.translatePath("special://profile"),
                        xbmcvfs.translatePath("special://skin"),
                        settings,
                        xbmcaddon.Addon,
                        xbmc.executebuiltin,
                        xbmcgui.Window(10000),
                        lambda: xbmc.Player().isPlayingVideo(),
                        state=state,
                    )
                },
            )
            applier.recover()
            sync_result = ReadOnlySync(addon, state, applier=applier)()
            local = state.read()
        if config["action"] == "sync-favourites":
            from resources.lib.mwoprofilesync.favourites_state import (
                FavouritesApplier,
                FavouritesJournal,
                FavouritesSync,
            )
            from resources.lib.mwoprofilesync.portable import (
                PortableFavouritesExporter,
            )

            kodi_profile = xbmcvfs.translatePath("special://profile")
            kodi_favourites = KodiFavourites(xbmc.executeJSONRPC)
            portable = PortableFavouritesAdapter(kodi_profile, kodi_favourites)
            favourites_applier = FavouritesApplier(profile, portable)
            favourites_applier.recover()
            favourites_result = FavouritesSync(
                addon,
                state,
                FavouritesJournal(profile),
                PortableFavouritesExporter(kodi_profile, kodi_favourites),
                favourites_applier,
            )()
            local = state.read()
        result = {
            "ok": True,
            "addon_version": addon.getAddonInfo("version"),
            "logical_device_id": enrollment["logical_device_id"],
            "enrollment_id": enrollment["enrollment_id"],
            "target_tags": enrollment.get("target_tags", []),
            "status": local.get("status"),
            "assigned_revision": local.get("assigned_revision"),
            "applied_revision": local.get("applied_revision"),
            "pending_report": bool(local.get("pending_report")),
            "sync_status": sync_result.get("status") if sync_result else None,
            "skin_menu_status": local.get("skin_menu_status"),
            "favourites_sync_status": (
                favourites_result.get("status") if favourites_result else None
            ),
            "playback_status": local.get("playback_status"),
            "playback_cursor": local.get("playback_cursor"),
            "playback_pending_events": local.get("playback_pending_events"),
            "playback_pending_mapping": local.get("playback_pending_mapping"),
            "playback_pending_application": local.get(
                "playback_pending_application"
            ),
            "playback_error_code": local.get("playback_error_code"),
            "favourites_status": local.get("favourites_status"),
            "favourites_last_success_utc": local.get(
                "favourites_last_success_utc"
            ),
            "favourites_last_attempt_utc": local.get(
                "favourites_last_attempt_utc"
            ),
            "favourites_error_code": local.get("favourites_error_code"),
            "favourites_cursor": local.get("favourites_cursor"),
            "favourites_pending_count": local.get(
                "favourites_pending_count"
            ),
            "favourites_dynamic_fence": bool(
                local.get("favourites_dynamic_fence")
            ),
        }
    except Exception as error:
        result = {
            "ok": False,
            "error_type": type(error).__name__,
            "error_code": getattr(error, "code", None),
            "http_status": getattr(error, "status", None),
        }
    write_atomic(
        marker,
        (json.dumps(result, sort_keys=True) + "\n").encode("utf-8"),
    )


if __name__ == "__main__":
    main()
