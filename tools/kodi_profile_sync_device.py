"""Configure, pair and synchronize Profile Sync inside a real Kodi process."""

from __future__ import annotations

import hashlib
import json
import os
import sys
import traceback

import xbmc
import xbmcaddon
import xbmcgui
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


def clear_recovered_terminal_block(state, profile):
    """Only a verified successful apply can retire an old terminal error."""
    local = state.read()
    if not local.get("terminal_configuration_fingerprint"):
        return False
    revision = local.get("applied_revision")
    if (
        local.get("status") not in {"APPLIED", "NO_CHANGE"}
        or not revision
        or local.get("assigned_revision") != revision
        or revision in local.get("quarantined_revisions", [])
        or local.get("pending_report")
        or os.path.exists(os.path.join(profile, "apply-journal.json"))
    ):
        raise RuntimeError("terminal recovery requires a verified applied revision")
    # The backup remains in Kodi's private 0700 profile; never in Download.
    import tempfile

    descriptor, backup = tempfile.mkstemp(
        prefix="terminal-recovery-", suffix=".json", dir=profile
    )
    with os.fdopen(descriptor, "wb") as handle:
        handle.write((json.dumps(local, sort_keys=True) + "\n").encode("utf-8"))
        handle.flush()
        os.fsync(handle.fileno())
    os.chmod(backup, 0o600)
    state.update_public(
        terminal_configuration_fingerprint=None,
        consecutive_failures=0,
        last_error_code=None,
        next_retry_utc=None,
    )
    return True


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
        from resources.lib.mwoprofilesync.skin_menu import (
            HANDLER_ID as SKIN_MENU_HANDLER_ID,
        )
        from resources.lib.mwoprofilesync.skin_menu import (
            SkinMenuAdapter,
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
                "special://profile/addon_data/" + ADDON_ID + "/profile-sync-ca.pem"
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
                current.get("logical_device_id") != config["logical_device_id"]
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
        settings = KodiAddonSettings(xbmcaddon.Addon, xbmc.executeJSONRPC)
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
        terminal_block_cleared = clear_recovered_terminal_block(state, profile)
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
            "skin_menu_status": local.get("skin_menu_status"),
            "terminal_block_cleared": terminal_block_cleared,
        }
    except Exception as error:  # noqa: BLE001 - Kodi runtime boundary
        frame = traceback.extract_tb(error.__traceback__)[-1]
        result = {
            "ok": False,
            "error_type": type(error).__name__,
            "error_code": getattr(error, "code", None),
            "http_status": getattr(error, "status", None),
            # No exception text, local variables or full device paths: those
            # can contain credentials. The code location is enough to diagnose.
            "error_location": "%s:%s:%s"
            % (os.path.basename(frame.filename), frame.lineno, frame.name),
        }
    _write_atomic(
        marker,
        (json.dumps(result, sort_keys=True) + "\n").encode("utf-8"),
    )


if __name__ == "__main__":
    main()
