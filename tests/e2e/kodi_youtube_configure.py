#!/usr/bin/env python3
"""Configure and verify the official YouTube add-on inside Kodi."""

import json
import os
import sys
from urllib import error as urlerror
from urllib import parse, request

import xbmcaddon
import xbmcvfs

ADDON_ID = "plugin.video.youtube"
EXPECTED_SETTINGS = {
    "kodion.setup_wizard": "false",
    "youtube.api.config.page": "false",
    "kodion.http.listen": "127.0.0.1",
}
SECRET_SETTINGS = {
    "api_key": "youtube.api.key",
    "client_id": "youtube.api.id",
    "client_secret": "youtube.api.secret",
}
PROBE_VIDEO_ID = "aqz-KE-bpKQ"


def _publish(path, report):
    temporary = path + ".tmp"
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(temporary, "w", encoding="utf-8") as destination:
        json.dump(report, destination, indent=2, sort_keys=True)
        destination.write("\n")
        destination.flush()
        os.fsync(destination.fileno())
    os.chmod(temporary, 0o600)
    os.replace(temporary, path)


def _authorization_status():
    path = xbmcvfs.translatePath(
        f"special://profile/addon_data/{ADDON_ID}/access_manager.json"
    )
    try:
        with open(path, encoding="utf-8") as source:
            document = json.load(source)
        manager = document.get("access_manager") or {}
        users = manager.get("users") or {}
        current = manager.get("current_user", 0)
        details = users.get(str(current), users.get(current, {}))
        refresh_tokens = details.get("refresh_token", "").split("|")
        count = len([token for token in refresh_tokens if token])
    except (OSError, TypeError, ValueError):
        count = 0
    if count >= 3:
        return "ACCOUNT_READY"
    if count:
        return "CONSENT_PENDING"
    return "AUTHORIZATION_REQUIRED"


def _probe_api(api_key):
    query = parse.urlencode({"part": "id", "id": PROBE_VIDEO_ID, "key": api_key})
    url = "https://www.googleapis.com/youtube/v3/videos?" + query
    try:
        with request.urlopen(
            request.Request(url, headers={"Accept": "application/json"}),
            timeout=30,
        ) as response:
            document = json.load(response)
            status = response.status
    except urlerror.HTTPError as error:
        status = error.code
        try:
            document = json.load(error)
        except (TypeError, ValueError):
            document = {}
    reason = None
    errors = (document.get("error") or {}).get("errors") or []
    if errors and isinstance(errors[0], dict):
        reason = errors[0].get("reason")
    if status != 200 or not document.get("items"):
        if reason in {"dailyLimitExceeded", "quotaExceeded"}:
            raise RuntimeError("YouTubeQuotaExceeded")
        if reason in {"accessNotConfigured", "forbidden"}:
            raise RuntimeError("YouTubeApiDisabled")
        raise RuntimeError("YouTubeApiProbeFailed")
    return status


def main():
    config_path, report_path = sys.argv[1:3]
    report = {"ok": False, "schema": 1, "stage": "load"}
    addon = None
    previous = {}
    try:
        with open(config_path, encoding="utf-8") as source:
            config = json.load(source)
        required = {
            "schema",
            "addon_version",
            "api_key",
            "client_id",
            "client_secret",
        }
        if set(config) != required or config.get("schema") != 1:
            raise ValueError("invalid private YouTube configuration")
        if not all(
            isinstance(config.get(name), str) and config[name]
            for name in ("api_key", "client_id", "client_secret")
        ):
            raise ValueError("missing private YouTube API configuration")

        addon = xbmcaddon.Addon(ADDON_ID)
        version = addon.getAddonInfo("version")
        if version != config["addon_version"]:
            raise RuntimeError("unsupported YouTube add-on version")

        desired = {
            **EXPECTED_SETTINGS,
            **{setting: config[name] for name, setting in SECRET_SETTINGS.items()},
        }
        previous = {setting: addon.getSetting(setting) for setting in desired}
        report["stage"] = "settings"
        for setting, value in desired.items():
            addon.setSetting(setting, value)
        if any(addon.getSetting(key) != value for key, value in desired.items()):
            raise RuntimeError("YouTube add-on rejected settings")

        report["stage"] = "api_probe"
        api_status = _probe_api(config["api_key"])
        authorization = _authorization_status()
        report.update(
            {
                "addon_id": ADDON_ID,
                "addon_version": version,
                "api_status": api_status,
                "authorization": authorization,
                "changed": previous != desired,
                "http_loopback_only": addon.getSetting("kodion.http.listen")
                == "127.0.0.1",
                "ok": True,
                "personal_api_configured": True,
                "setup_wizard_disabled": addon.getSetting("kodion.setup_wizard")
                == "false",
                "stage": "complete",
            }
        )
    except Exception as error:  # noqa: BLE001 - sanitized Kodi boundary
        report["error_type"] = (
            str(error) if str(error).startswith("YouTube") else type(error).__name__
        )
        if addon is not None and previous:
            try:
                for setting, value in previous.items():
                    addon.setSetting(setting, value)
                report["rolled_back"] = True
            except Exception:  # noqa: BLE001 - best effort rollback
                report["rolled_back"] = False
    finally:
        _publish(report_path, report)


if __name__ == "__main__":
    main()
