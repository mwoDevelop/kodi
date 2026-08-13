#!/usr/bin/env python3
"""Configure and verify OpenSubtitles.org without exporting credentials."""

import base64
import json
import os
import socket
import sys
import zlib
from xmlrpc import client

import xbmc
import xbmcaddon
import xbmcvfs

ADDON_ID = "service.subtitles.opensubtitles"
# The upstream add-on still targets this XML-RPC API. Use TLS for the rollout
# probe so private credentials never cross the network in cleartext.
API_URL = "https://api.opensubtitles.org/xml-rpc"
INSECURE_ENDPOINT = b'BASE_URL_XMLRPC = u"http://api.opensubtitles.org/xml-rpc"'
SECURE_ENDPOINT = b'BASE_URL_XMLRPC = u"https://api.opensubtitles.org/xml-rpc"'
VIP_PLACEHOLDER_MARKERS = (
    b"become opensubtitles.org vip member",
    b"osdb.link/vip",
)


class VipRequiredError(RuntimeError):
    """The legacy API returned its promotional SRT instead of subtitles."""


def _is_vip_placeholder(payload):
    sample = payload[:4096].lower()
    return any(marker in sample for marker in VIP_PLACEHOLDER_MARKERS)


def _secure_addon_transport(addon):
    source_path = os.path.join(
        xbmcvfs.translatePath(addon.getAddonInfo("path")),
        "resources",
        "lib",
        "OSUtilities.py",
    )
    with open(source_path, "rb") as source:
        previous = source.read()
    if SECURE_ENDPOINT in previous:
        return source_path, previous, False
    if previous.count(INSECURE_ENDPOINT) != 1:
        raise RuntimeError("unknown OpenSubtitles API endpoint declaration")
    temporary = source_path + ".mwo-tls.tmp"
    with open(temporary, "wb") as destination:
        destination.write(previous.replace(INSECURE_ENDPOINT, SECURE_ENDPOINT))
    os.replace(temporary, source_path)
    with open(source_path, "rb") as source:
        current = source.read()
    if SECURE_ENDPOINT not in current or INSECURE_ENDPOINT in current:
        raise RuntimeError("OpenSubtitles TLS endpoint update did not persist")
    return source_path, previous, True


def _rpc(method, params=None):
    request = {"jsonrpc": "2.0", "id": 1, "method": method}
    if params is not None:
        request["params"] = params
    response = json.loads(xbmc.executeJSONRPC(json.dumps(request)))
    if "error" in response:
        raise RuntimeError("Kodi JSON-RPC setting update failed")
    return response.get("result")


def _get_setting(setting_id):
    result = _rpc("Settings.GetSettingValue", {"setting": setting_id})
    return result.get("value") if isinstance(result, dict) else None


def _set_setting(setting_id, value):
    if (
        _rpc(
            "Settings.SetSettingValue",
            {"setting": setting_id, "value": value},
        )
        is not True
    ):
        raise RuntimeError("Kodi rejected subtitle setting")


def _safe_previous_setting(setting_id, value, vip_required):
    if (
        vip_required
        and setting_id in {"subtitles.movie", "subtitles.tv"}
        and value == ADDON_ID
    ):
        return ""
    return value


def _publish(path, report):
    temporary = path + ".tmp"
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(temporary, "w", encoding="utf-8") as destination:
        json.dump(report, destination, indent=2, sort_keys=True)
        destination.write("\n")
    os.replace(temporary, path)


def main():
    config_path, report_path = sys.argv[1:3]
    report = {"ok": False, "schema": 1, "stage": "load"}
    addon = None
    token = None
    previous_addon = {}
    previous_kodi = {}
    previous_source = None
    source_path = None
    transport_changed = False
    username = None
    password = None
    desired_kodi = {
        "locale.subtitlelanguage": "Polish",
        "subtitles.languages": ["Polish", "English"],
        "subtitles.movie": ADDON_ID,
        "subtitles.tv": ADDON_ID,
    }
    try:
        with open(config_path, encoding="utf-8") as source:
            config = json.load(source)
        if (
            set(config) != {"schema", "username", "password"}
            or config.get("schema") != 1
        ):
            raise ValueError("invalid private OpenSubtitles configuration")
        username = config.get("username")
        password = config.get("password")
        if not isinstance(username, str) or not username or len(username) > 512:
            raise ValueError("invalid OpenSubtitles username")
        if not isinstance(password, str) or not password or len(password) > 512:
            raise ValueError("invalid OpenSubtitles password")

        report["stage"] = "settings"
        addon = xbmcaddon.Addon(ADDON_ID)
        source_path, previous_source, transport_changed = _secure_addon_transport(addon)
        previous_addon = {
            "OSuser": addon.getSetting("OSuser"),
            "OSpass": addon.getSetting("OSpass"),
        }
        previous_kodi = {
            setting_id: _get_setting(setting_id) for setting_id in desired_kodi
        }
        addon.setSetting("OSuser", username)
        addon.setSetting("OSpass", password)
        for setting_id, value in desired_kodi.items():
            _set_setting(setting_id, value)

        report["stage"] = "login"
        socket.setdefaulttimeout(20)
        server = client.ServerProxy(API_URL, allow_none=True)
        login = server.LogIn(
            username,
            password,
            "en",
            "XBMC_Subtitles_Login_v{}".format(addon.getAddonInfo("version")),
        )
        report["login_status"] = login.get("status")
        account = login.get("data") or {}
        report["vip"] = str(account.get("IsVIP", "0")).lower() in {
            "1",
            "true",
            "yes",
        }
        token = login.get("token")
        if login.get("status") != "200 OK" or not token:
            raise RuntimeError("OpenSubtitles authentication failed")

        report["stage"] = "search"
        search = server.SearchSubtitles(
            token,
            [{"sublanguageid": "pol", "query": "Sintel"}],
        )
        candidates = search.get("data") or []
        report["search_status"] = search.get("status")
        report["search_results"] = len(candidates)
        candidate = next(
            (
                item
                for item in candidates
                if isinstance(item, dict) and item.get("IDSubtitleFile")
            ),
            None,
        )
        if search.get("status") != "200 OK" or candidate is None:
            raise RuntimeError("OpenSubtitles returned no Polish test subtitle")

        report["stage"] = "download"
        downloaded = server.DownloadSubtitles(token, [candidate["IDSubtitleFile"]])
        payloads = downloaded.get("data") or []
        if downloaded.get("status") != "200 OK" or not payloads:
            raise RuntimeError("OpenSubtitles test download failed")
        packed = base64.b64decode(payloads[0].get("data") or "", validate=True)
        subtitle = zlib.decompress(packed, 16 + zlib.MAX_WBITS)
        if len(subtitle) < 32:
            raise RuntimeError("OpenSubtitles test subtitle is empty")
        if _is_vip_placeholder(subtitle):
            report["vip_placeholder"] = True
            raise VipRequiredError(
                "OpenSubtitles returned a VIP placeholder instead of subtitles"
            )

        report.update(
            {
                "addon_id": ADDON_ID,
                "addon_version": addon.getAddonInfo("version"),
                "changed": transport_changed
                or previous_addon != {"OSuser": username, "OSpass": password}
                or previous_kodi != desired_kodi,
                "credentials_stored": addon.getSetting("OSuser") == username
                and addon.getSetting("OSpass") == password,
                "default_movie_service": _get_setting("subtitles.movie") == ADDON_ID,
                "default_tv_service": _get_setting("subtitles.tv") == ADDON_ID,
                "download_bytes": len(subtitle),
                "languages": _get_setting("subtitles.languages"),
                "login_status": login.get("status"),
                "ok": True,
                "preferred_language": _get_setting("locale.subtitlelanguage"),
                "stage": "complete",
                "tls_endpoint": True,
                "transport_changed": transport_changed,
                "vip_placeholder": False,
            }
        )
    except Exception as error:  # noqa: BLE001 - sanitized device boundary
        report["error_type"] = type(error).__name__
        vip_required = isinstance(error, VipRequiredError)
        if vip_required:
            report["status"] = "VIP_REQUIRED"
        if vip_required and addon is not None and previous_addon:
            try:
                for setting_id, value in previous_kodi.items():
                    _set_setting(
                        setting_id,
                        _safe_previous_setting(
                            setting_id, value, vip_required
                        ),
                    )
                report["credentials_stored"] = (
                    addon.getSetting("OSuser") == username
                    and addon.getSetting("OSpass") == password
                )
                report["credentials_retained"] = report["credentials_stored"]
                report["default_service_quarantined"] = all(
                    _get_setting(setting_id) != ADDON_ID
                    for setting_id in ("subtitles.movie", "subtitles.tv")
                )
                report["tls_endpoint"] = True
                report["transport_changed"] = transport_changed
            except Exception:  # noqa: BLE001 - preserve original diagnosis
                report["credentials_retained"] = False
        elif addon is not None and previous_addon:
            try:
                for setting_id, value in previous_addon.items():
                    addon.setSetting(setting_id, value)
                for setting_id, value in previous_kodi.items():
                    _set_setting(setting_id, value)
                report["rolled_back"] = True
            except Exception:  # noqa: BLE001 - preserve original diagnosis
                report["rolled_back"] = False
        if (
            not vip_required
            and transport_changed
            and source_path
            and previous_source is not None
        ):
            try:
                temporary = source_path + ".mwo-tls.tmp"
                with open(temporary, "wb") as destination:
                    destination.write(previous_source)
                os.replace(temporary, source_path)
                report["transport_rolled_back"] = True
            except Exception:  # noqa: BLE001 - preserve original diagnosis
                report["transport_rolled_back"] = False
    finally:
        if token:
            try:
                server.LogOut(token)
            except Exception:  # noqa: BLE001,S110 - logout is best effort
                pass
        _publish(report_path, report)


if __name__ == "__main__":
    main()
