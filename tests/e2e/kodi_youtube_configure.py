#!/usr/bin/env python3
"""Configure and verify the official YouTube add-on inside Kodi."""

import json
import base64
import hashlib
import os
import sys
import time
import uuid
from urllib import error as urlerror
from urllib import parse, request

import xbmcaddon
import xbmcvfs

ADDON_ID = "plugin.video.youtube"
EXPECTED_SETTINGS = {
    "kodion.setup_wizard": "false",
    "kodion.setup_wizard.forced_runs": "1767970800",
    "|end_settings_marker|": "true",
    "youtube.api.config.page": "false",
    "kodion.http.listen": "127.0.0.1",
}
SECRET_SETTINGS = {
    "api_key": "youtube.api.key",
    "client_id": "youtube.api.id",
    "client_secret": "youtube.api.secret",
}
PROBE_VIDEO_ID = "aqz-KE-bpKQ"
TV_CLIENT_ID = base64.b64decode(
    b"ODYxNTU2NzA4NDU0LWQ2ZGxtM2xoMDVpZGQ4bnBlazE4azZiZThiYTNvYzY4"
).decode("ascii")
TV_CLIENT_SECRET = base64.b64decode(
    b"U2JvVmhvRzlzMHJOYWZpeENTR0dLWEFU"
).decode("ascii")
VR_CLIENT_ID = base64.b64decode(
    b"NjUyNDY5MzEyMTY5LTRsdnM5Ym5ocjlscG5zOXY0NTFqNW9pdmQ4MXZqdnUx"
).decode("ascii")
VR_CLIENT_SECRET = base64.b64decode(
    b"M2ZUV3JCSkk1VW9qbTFUSzdfaUpDVzVa"
).decode("ascii")
TOKEN_URL = "https://www.googleapis.com/oauth2/v4/token"


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


def _client_id(value):
    suffix = ".apps.googleusercontent.com"
    return value if value.endswith(suffix) else value + suffix


def _post_form(url, values):
    encoded = parse.urlencode(values).encode("ascii")
    try:
        with request.urlopen(
            request.Request(
                url,
                data=encoded,
                headers={"Content-Type": "application/x-www-form-urlencoded"},
            ),
            timeout=30,
        ) as response:
            return json.load(response)
    except urlerror.HTTPError as error:
        try:
            document = json.load(error)
        except (TypeError, ValueError):
            document = {}
        if document.get("error") == "invalid_grant":
            raise RuntimeError("YouTubeSessionInvalid")
        raise RuntimeError("YouTubeSessionProbeFailed")


def _refresh(client_id, client_secret, refresh_token):
    document = _post_form(
        TOKEN_URL,
        {
            "client_id": _client_id(client_id),
            "client_secret": client_secret,
            "refresh_token": refresh_token,
            "grant_type": "refresh_token",
        },
    )
    if not document.get("access_token"):
        raise RuntimeError("YouTubeSessionProbeFailed")
    return document


def _probe_session(config):
    session = config["session"]
    tv = _refresh(
        TV_CLIENT_ID,
        TV_CLIENT_SECRET,
        session["tv_refresh_token"],
    )
    personal = _refresh(
        config["client_id"],
        config["client_secret"],
        session["personal_refresh_token"],
    )
    vr = _refresh(
        VR_CLIENT_ID,
        VR_CLIENT_SECRET,
        session["vr_refresh_token"],
    )
    query = parse.urlencode(
        {"part": "id", "mine": "true", "key": config["api_key"]}
    )
    try:
        with request.urlopen(
            request.Request(
                "https://www.googleapis.com/youtube/v3/channels?" + query,
                headers={
                    "Accept": "application/json",
                    "Authorization": "Bearer " + personal["access_token"],
                },
            ),
            timeout=30,
        ) as response:
            channels = json.load(response).get("items") or []
    except (OSError, ValueError, urlerror.HTTPError):
        raise RuntimeError("YouTubeAccountProbeFailed")
    if (
        len(channels) != 1
        or channels[0].get("id") != session["expected_channel_id"]
    ):
        raise RuntimeError("YouTubeAccountMismatch")
    return tv, personal, vr


def _addon_data_path():
    return xbmcvfs.translatePath(
        f"special://profile/addon_data/{ADDON_ID}"
    )


def _read_bytes(path):
    try:
        with open(path, "rb") as source:
            return source.read()
    except OSError:
        return None


def _write_atomic(path, document):
    temporary = path + ".tmp"
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(temporary, "w", encoding="utf-8") as destination:
        json.dump(document, destination, sort_keys=True, separators=(",", ":"))
        destination.write("\n")
        destination.flush()
        os.fsync(destination.fileno())
    os.chmod(temporary, 0o600)
    os.replace(temporary, path)


def _restore(path, content):
    if content is None:
        try:
            os.unlink(path)
        except OSError:
            pass
        return
    temporary = path + ".restore"
    with open(temporary, "wb") as destination:
        destination.write(content)
        destination.flush()
        os.fsync(destination.fileno())
    os.chmod(temporary, 0o600)
    os.replace(temporary, path)


def _session_matches(access_path, api_path, config):
    try:
        with open(access_path, encoding="utf-8") as source:
            manager = json.load(source)["access_manager"]
        with open(api_path, encoding="utf-8") as source:
            api = json.load(source)["keys"]["user"]
        current = manager.get("current_user", 0)
        user = manager["users"].get(str(current), manager["users"].get(current))
        desired_refresh = "|".join(
            (
                config["session"]["tv_refresh_token"],
                config["session"]["personal_refresh_token"],
                config["session"]["vr_refresh_token"],
            )
        )
        desired_hash = hashlib.md5(
            "".join(
                (
                    config["api_key"],
                    config["client_id"].replace(
                        ".apps.googleusercontent.com", ""
                    ),
                    config["client_secret"],
                )
            ).encode("utf-8")
        ).hexdigest()
        return (
            isinstance(user, dict)
            and user.get("refresh_token") == desired_refresh
            and user.get("name") == config["session"]["account_hint"]
            and user.get("last_key_hash") == desired_hash
            and api
            == {
                "api_key": config["api_key"],
                "client_id": config["client_id"].replace(
                    ".apps.googleusercontent.com", ""
                ),
                "client_secret": config["client_secret"],
            }
        )
    except (KeyError, OSError, TypeError, ValueError):
        return False


def _apply_session(config, tokens):
    data_root = _addon_data_path()
    access_path = os.path.join(data_root, "access_manager.json")
    api_path = os.path.join(data_root, "api_keys.json")
    previous = {
        access_path: _read_bytes(access_path),
        api_path: _read_bytes(api_path),
    }
    if _session_matches(access_path, api_path, config):
        return False, previous
    tv, personal, vr = tokens
    session = config["session"]
    client_id = config["client_id"].replace(
        ".apps.googleusercontent.com", ""
    )
    key_hash = hashlib.md5(
        "".join(
            (config["api_key"], client_id, config["client_secret"])
        ).encode("utf-8")
    ).hexdigest()
    expires = min(
        int(tv.get("expires_in", 3600)),
        int(personal.get("expires_in", 3600)),
        int(vr.get("expires_in", 3600)),
    )
    access = {
        "access_manager": {
            "current_user": 0,
            "developers": {},
            "last_origin": ADDON_ID,
            "users": {
                "0": {
                    "access_token": "|".join(
                        (
                            tv["access_token"],
                            personal["access_token"],
                            vr["access_token"],
                        )
                    ),
                    "refresh_token": "|".join(
                        (
                            session["tv_refresh_token"],
                            session["personal_refresh_token"],
                            session["vr_refresh_token"],
                        )
                    ),
                    "token_expires": int(time.time()) + expires,
                    "last_key_hash": key_hash,
                    "name": session["account_hint"],
                    "id": uuid.uuid4().hex,
                    "watch_later": "WL",
                    "watch_history": "HL",
                }
            },
        }
    }
    api = {
        "keys": {
            "developer": {},
            "user": {
                "api_key": config["api_key"],
                "client_id": client_id,
                "client_secret": config["client_secret"],
            },
        }
    }
    try:
        _write_atomic(api_path, api)
        _write_atomic(access_path, access)
    except Exception:
        for path, content in previous.items():
            _restore(path, content)
        raise
    return True, previous


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
        schema = config.get("schema")
        if schema == 2:
            required.add("session")
        if set(config) != required or schema not in {1, 2}:
            raise ValueError("invalid private YouTube configuration")
        report["schema"] = schema
        if not all(
            isinstance(config.get(name), str) and config[name]
            for name in ("api_key", "client_id", "client_secret")
        ):
            raise ValueError("missing private YouTube API configuration")
        if schema == 2:
            session = config.get("session")
            if (
                not isinstance(session, dict)
                or set(session)
                != {
                    "account_hint",
                    "expected_channel_id",
                    "tv_refresh_token",
                    "personal_refresh_token",
                    "vr_refresh_token",
                }
                or not all(isinstance(value, str) and value for value in session.values())
            ):
                raise ValueError("invalid private YouTube session")

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
        session_changed = False
        session_previous = {}
        if schema == 2:
            report["stage"] = "session_probe"
            tokens = _probe_session(config)
            report["stage"] = "session_apply"
            session_changed, session_previous = _apply_session(config, tokens)
            authorization = "ACCOUNT_READY"
        else:
            authorization = _authorization_status()
        report.update(
            {
                "addon_id": ADDON_ID,
                "addon_version": version,
                "api_status": api_status,
                "authorization": authorization,
                "account_verified": schema == 2,
                "changed": previous != desired or session_changed,
                "http_loopback_only": addon.getSetting("kodion.http.listen")
                == "127.0.0.1",
                "ok": True,
                "personal_api_configured": True,
                "session_configured": schema == 2,
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
        if "session_previous" in locals() and session_previous:
            try:
                for path, content in session_previous.items():
                    _restore(path, content)
                report["session_rolled_back"] = True
            except Exception:  # noqa: BLE001 - best effort rollback
                report["session_rolled_back"] = False
    finally:
        _publish(report_path, report)


if __name__ == "__main__":
    main()
