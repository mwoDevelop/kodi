"""Exercise the installed Profile Sync applier inside a real Kodi process."""

from __future__ import annotations

import json
import os
import sys

import xbmcaddon
import xbmcvfs


ADDON_ID = "service.mwodevelop.profilesync"
UMBRELLA_ID = "plugin.video.umbrella"


def write_marker(path, document):
    temporary = path + ".tmp"
    with open(temporary, "w", encoding="utf-8") as handle:
        json.dump(document, handle, sort_keys=True)
        handle.flush()
        os.fsync(handle.fileno())
    os.replace(temporary, path)


def revision(revision_id, values):
    return {
        "schema": 2,
        "revision_id": revision_id,
        "adapters": {
            "umbrella.preferences": {
                "adapter": "settings_xml",
                "addon_id": UMBRELLA_ID,
                "apply_mode": "next_start",
                "managed_settings": sorted(values),
                "values": values,
            }
        },
    }


def main():
    marker = sys.argv[1]
    addon_root = xbmcvfs.translatePath(
        "special://home/addons/" + ADDON_ID
    )
    if addon_root not in sys.path:
        sys.path.insert(0, addon_root)
    from resources.lib.mwoprofilesync.apply import (
        KodiAddonSettings,
        TransactionalApplier,
    )
    from resources.lib.mwoprofilesync.state import StateStore

    profile = xbmcvfs.translatePath(
        xbmcaddon.Addon(ADDON_ID).getAddonInfo("profile")
    )
    state = StateStore(profile)
    state_existed = state.path.exists()
    state_payload = state.path.read_bytes() if state_existed else None
    settings = KodiAddonSettings(xbmcaddon.Addon)
    original_cache = settings.get(UMBRELLA_ID, "cache.providers")
    original_timeout = settings.get(UMBRELLA_ID, "scrapers.timeout")
    journal = os.path.join(profile, "apply-journal.json")
    if os.path.exists(journal):
        raise RuntimeError("pre-existing apply journal")
    alternate_cache = 5 if original_cache != "5" else 6
    alternate_timeout = 21 if original_timeout != "21" else 22

    class FailingSettings:
        def get(self, addon_id, setting_id):
            return settings.get(addon_id, setting_id)

        def set(self, addon_id, setting_id, value):
            if (
                setting_id == "scrapers.timeout"
                and value == str(alternate_timeout)
            ):
                raise RuntimeError("injected device E2E write failure")
            settings.set(addon_id, setting_id, value)

    result = {
        "schema": 1,
        "ok": False,
        "successful_apply": False,
        "rollback": False,
        "settings_restored": False,
        "journal_clean": False,
    }
    try:
        applier = TransactionalApplier(profile, state, settings)
        applied = applier.apply(
            revision(
                "sha256:" + "1" * 64,
                {"cache.providers": alternate_cache},
            )
        )
        result["successful_apply"] = (
            applied.get("status") == "APPLIED"
            and settings.get(UMBRELLA_ID, "cache.providers")
            == str(alternate_cache)
            and not os.path.exists(journal)
        )
        applier.apply(
            revision(
                "sha256:" + "2" * 64,
                {"cache.providers": int(original_cache)},
            )
        )

        failing = TransactionalApplier(
            profile, state, FailingSettings()
        )
        try:
            failing.apply(
                revision(
                    "sha256:" + "3" * 64,
                    {
                        "cache.providers": alternate_cache,
                        "scrapers.timeout": alternate_timeout,
                    },
                )
            )
        except RuntimeError as error:
            if "injected device E2E write failure" not in str(error):
                raise
        else:
            raise RuntimeError("injected apply failure was not raised")
        public = state.read_public()
        result["rollback"] = (
            public.get("status") == "QUARANTINED"
            and "sha256:" + "3" * 64
            in public.get("quarantined_revisions", [])
            and settings.get(UMBRELLA_ID, "cache.providers")
            == original_cache
            and settings.get(UMBRELLA_ID, "scrapers.timeout")
            == original_timeout
        )
        result["journal_clean"] = not os.path.exists(journal)
        result["settings_restored"] = (
            settings.get(UMBRELLA_ID, "cache.providers")
            == original_cache
            and settings.get(UMBRELLA_ID, "scrapers.timeout")
            == original_timeout
        )
        result["ok"] = all(
            result[key]
            for key in (
                "successful_apply",
                "rollback",
                "settings_restored",
                "journal_clean",
            )
        )
    except Exception as error:
        result["error_type"] = type(error).__name__
    finally:
        settings.set(UMBRELLA_ID, "cache.providers", original_cache)
        settings.set(UMBRELLA_ID, "scrapers.timeout", original_timeout)
        if os.path.exists(journal):
            os.unlink(journal)
        if state_existed:
            temporary = str(state.path) + ".e2e-restore"
            with open(temporary, "wb") as handle:
                handle.write(state_payload)
                handle.flush()
                os.fsync(handle.fileno())
            os.chmod(temporary, 0o600)
            os.replace(temporary, state.path)
        elif state.path.exists():
            state.path.unlink()
        write_marker(marker, result)


if __name__ == "__main__":
    main()
