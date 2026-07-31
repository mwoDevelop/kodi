"""Configure, pair and synchronize Profile Sync inside a real Kodi process."""

from __future__ import annotations

import hashlib
import json
import os
import sys

import xbmcaddon
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
        from resources.lib.mwoprofilesync.state import StateStore
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
        if config["action"] == "sync":
            applier = TransactionalApplier(
                profile,
                state,
                KodiAddonSettings(xbmcaddon.Addon),
            )
            sync_result = ReadOnlySync(addon, state, applier=applier)()
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
