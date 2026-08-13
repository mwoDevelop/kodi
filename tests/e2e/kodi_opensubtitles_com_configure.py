#!/usr/bin/env python3
"""Configure and verify both OpenSubtitles.com integrations inside Kodi."""

import json
import os
import re
import sys
from urllib import error as urlerror
from urllib import parse, request

import xbmc
import xbmcaddon
import xbmcvfs

UMBRELLA_ID = "plugin.video.umbrella"
SERVICE_ID = "service.subtitles.opensubtitles-com"
LEGACY_ID = "service.subtitles.opensubtitles"
EXPECTED_BASE_URL = "https://api.opensubtitles.com/api/v1"
UMBRELLA_SETTINGS = ("opensubsusername", "opensubspassword", "opensubstoken")
SERVICE_SETTINGS = ("OSuser", "OSpass")
TEST_IMDB_ID = "1104001"  # Sintel


def _publish(path, report):
    temporary = path + ".tmp"
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(temporary, "w", encoding="utf-8") as destination:
        json.dump(report, destination, indent=2, sort_keys=True)
        destination.write("\n")
        destination.flush()
        os.fsync(destination.fileno())
    os.replace(temporary, path)


def _api_identity(addon):
    module = os.path.join(
        xbmcvfs.translatePath(addon.getAddonInfo("path")),
        "resources",
        "lib",
        "osclient",
        "provider.py",
    )
    with open(module, encoding="utf-8") as source:
        text = source.read()
    base = re.search(r'^API_URL = "([^"]+)/"$', text, re.MULTILINE)
    api_key = addon.getSetting("APIKey")
    if not base or base.group(1) != EXPECTED_BASE_URL:
        raise RuntimeError("unknown OpenSubtitles.com service API identity")
    if not re.fullmatch(r"[A-Za-z0-9_-]{16,128}", api_key):
        raise RuntimeError("invalid OpenSubtitles.com service API key")
    return api_key


def _rpc(method, params=None):
    request_payload = {"jsonrpc": "2.0", "id": 1, "method": method}
    if params is not None:
        request_payload["params"] = params
    response = json.loads(xbmc.executeJSONRPC(json.dumps(request_payload)))
    if "error" in response:
        raise RuntimeError("Kodi JSON-RPC operation failed")
    return response.get("result")


def _get_setting(setting_id):
    result = _rpc("Settings.GetSettingValue", {"setting": setting_id})
    return result.get("value") if isinstance(result, dict) else None


def _set_setting(setting_id, value):
    result = _rpc(
        "Settings.SetSettingValue", {"setting": setting_id, "value": value}
    )
    if result is not True:
        raise RuntimeError("Kodi rejected default subtitle service")


def _addon_enabled(addon_id):
    result = _rpc(
        "Addons.GetAddonDetails",
        {"addonid": addon_id, "properties": ["enabled", "version"]},
    )
    addon = result.get("addon") if isinstance(result, dict) else None
    return bool(addon and addon.get("enabled"))


def _json_request(method, url, api_key, token=None, payload=None):
    headers = {
        "Accept": "application/json",
        "Api-Key": api_key,
        "Content-Type": "application/json",
        "User-Agent": "OpenSubtitles.com Kodi plugin v{}".format(
            xbmcaddon.Addon(SERVICE_ID).getAddonInfo("version")
        ),
    }
    if token:
        headers["Authorization"] = token.removeprefix("Bearer ")
    data = None
    if payload is not None:
        data = json.dumps(payload).encode("utf-8")
    try:
        with request.urlopen(
            request.Request(url, data=data, headers=headers, method=method),
            timeout=30,
        ) as response:
            return response.status, json.load(response)
    except urlerror.HTTPError as request_error:
        return request_error.code, {}


def _user(api_key, token):
    return _json_request(
        "GET", EXPECTED_BASE_URL + "/infos/user", api_key, token=token
    )


def _login(api_key, username, password):
    return _json_request(
        "POST",
        EXPECTED_BASE_URL + "/login",
        api_key,
        payload={"username": username, "password": password},
    )


def _subtitle_payload_is_valid(payload):
    sample = payload[:1024 * 1024]
    lowered = sample.lower()
    return (
        len(payload) >= 64
        and b"-->" in sample
        and b"<html" not in lowered
        and b"<!doctype" not in lowered
    )


def _probe(api_key, token, download):
    query = parse.urlencode({"imdb_id": TEST_IMDB_ID, "languages": "pl"})
    status, result = _json_request(
        "GET",
        EXPECTED_BASE_URL + "/subtitles?" + query,
        api_key,
        token=token,
    )
    rows = result.get("data") or []
    file_id = None
    for row in rows:
        files = (row.get("attributes") or {}).get("files") or []
        if files and files[0].get("file_id"):
            file_id = files[0]["file_id"]
            break
    if status != 200 or file_id is None:
        raise RuntimeError("OpenSubtitles.com returned no Polish test subtitle")
    report = {"search_results": len(rows), "search_status": status}
    if not download:
        return report
    status, result = _json_request(
        "POST",
        EXPECTED_BASE_URL + "/download",
        api_key,
        token=token,
        payload={"file_id": file_id},
    )
    link = result.get("link")
    parsed = parse.urlsplit(link) if isinstance(link, str) else None
    if (
        status != 200
        or parsed is None
        or parsed.scheme != "https"
        or not parsed.hostname
        or not (
            parsed.hostname == "opensubtitles.com"
            or parsed.hostname.endswith(".opensubtitles.com")
        )
    ):
        raise RuntimeError("OpenSubtitles.com returned no download link")
    with request.urlopen(
        request.Request(
            link,
            headers={
                "Accept": "application/octet-stream,text/plain,*/*",
                "User-Agent": "OpenSubtitles.com Kodi plugin v{}".format(
                    xbmcaddon.Addon(SERVICE_ID).getAddonInfo("version")
                ),
            },
        ),
        timeout=30,
    ) as response:
        payload = response.read(4 * 1024 * 1024 + 1)
    if len(payload) > 4 * 1024 * 1024 or not _subtitle_payload_is_valid(payload):
        raise RuntimeError("OpenSubtitles.com returned invalid subtitle bytes")
    report.update({"download_bytes": len(payload), "download_status": status})
    return report


def main():
    config_path, report_path = sys.argv[1:3]
    report = {"ok": False, "schema": 1, "stage": "load"}
    umbrella = None
    service = None
    previous_umbrella = {}
    previous_service = {}
    previous_kodi = {}
    try:
        with open(config_path, encoding="utf-8") as source:
            config = json.load(source)
        if set(config) != {
            "schema",
            "username",
            "password",
            "token",
            "probe_download",
        } or config.get("schema") != 1:
            raise ValueError("invalid private OpenSubtitles.com configuration")
        username = config.get("username")
        password = config.get("password")
        bootstrap_token = config.get("token")
        if not isinstance(username, str) or not username or len(username) > 512:
            raise ValueError("invalid OpenSubtitles.com username")
        if not isinstance(password, str) or not password or len(password) > 512:
            raise ValueError("invalid OpenSubtitles.com password")
        if (
            not isinstance(bootstrap_token, str)
            or not bootstrap_token
            or len(bootstrap_token) > 2048
        ):
            raise ValueError("invalid OpenSubtitles.com token")
        if not isinstance(config.get("probe_download"), bool):
            raise TypeError("invalid OpenSubtitles.com probe mode")

        umbrella = xbmcaddon.Addon(UMBRELLA_ID)
        service = xbmcaddon.Addon(SERVICE_ID)
        xbmcaddon.Addon(LEGACY_ID)
        if not _addon_enabled(SERVICE_ID) or not _addon_enabled(LEGACY_ID):
            raise RuntimeError("OpenSubtitles services are not both enabled")
        api_key = _api_identity(service)
        previous_umbrella = {
            setting: umbrella.getSetting(setting) for setting in UMBRELLA_SETTINGS
        }
        previous_service = {
            setting: service.getSetting(setting) for setting in SERVICE_SETTINGS
        }
        previous_kodi = {
            setting: _get_setting(setting)
            for setting in ("subtitles.movie", "subtitles.tv")
        }
        report["stage"] = "auth"
        selected_token = None
        user = {}
        token_source = None
        seen_tokens = set()
        candidates = (
            ("installed", previous_umbrella["opensubstoken"]),
            ("bootstrap", bootstrap_token),
        )
        for source, candidate in candidates:
            candidate = candidate.removeprefix("Bearer ") if candidate else ""
            if not candidate or candidate in seen_tokens:
                continue
            seen_tokens.add(candidate)
            status, response = _user(api_key, candidate)
            if status == 200:
                selected_token = candidate.removeprefix("Bearer ")
                user = response.get("data") or {}
                token_source = source
                break
        if selected_token is None:
            status, response = _login(api_key, username, password)
            selected_token = response.get("token")
            user = response.get("user") or {}
            token_source = "login"
            if status != 200 or not selected_token:
                raise RuntimeError("OpenSubtitles.com authentication failed")

        report["stage"] = "settings"
        desired_umbrella = {
            "opensubsusername": username,
            "opensubspassword": password,
            "opensubstoken": selected_token,
        }
        desired_service = {"OSuser": username, "OSpass": password}
        for setting, value in desired_umbrella.items():
            umbrella.setSetting(setting, value)
        for setting, value in desired_service.items():
            service.setSetting(setting, value)
        for setting in ("subtitles.movie", "subtitles.tv"):
            _set_setting(setting, SERVICE_ID)
        if any(
            umbrella.getSetting(key) != value
            for key, value in desired_umbrella.items()
        ):
            raise RuntimeError("Umbrella rejected OpenSubtitles.com settings")
        if any(
            service.getSetting(key) != value
            for key, value in desired_service.items()
        ):
            raise RuntimeError("OpenSubtitles.com service rejected credentials")
        if any(
            _get_setting(setting) != SERVICE_ID
            for setting in ("subtitles.movie", "subtitles.tv")
        ):
            raise RuntimeError("OpenSubtitles.com is not the default Kodi service")

        report["stage"] = "probe"
        probe = _probe(api_key, selected_token, config["probe_download"])
        report.update(
            {
                "addon_id": SERVICE_ID,
                "addon_version": service.getAddonInfo("version"),
                "allowed_downloads": user.get("allowed_downloads"),
                "changed": previous_umbrella != desired_umbrella
                or previous_service != desired_service
                or any(
                    value != SERVICE_ID for value in previous_kodi.values()
                ),
                "credentials_stored": True,
                "default_movie_service": True,
                "default_tv_service": True,
                "legacy_service_visible": True,
                "ok": True,
                "remaining_downloads": user.get("remaining_downloads"),
                "stage": "complete",
                "token_source": token_source,
                "umbrella_addon_version": umbrella.getAddonInfo("version"),
                "vip": bool(user.get("vip")),
                **probe,
            }
        )
    except Exception as error:  # noqa: BLE001 - sanitized Kodi boundary
        report["error_type"] = type(error).__name__
        status = getattr(error, "code", None)
        if isinstance(status, int):
            report["http_status"] = status
        if umbrella is not None and service is not None and previous_umbrella:
            try:
                for setting, value in previous_umbrella.items():
                    umbrella.setSetting(setting, value)
                for setting, value in previous_service.items():
                    service.setSetting(setting, value)
                for setting, value in previous_kodi.items():
                    _set_setting(setting, value)
                report["rolled_back"] = True
            except Exception:  # noqa: BLE001 - best-effort rollback at Kodi boundary
                report["rolled_back"] = False
    finally:
        _publish(report_path, report)


if __name__ == "__main__":
    main()
