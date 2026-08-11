#!/usr/bin/env python3
"""Configure and verify Rapideo without exposing account data."""

from __future__ import annotations

import json
import os
import runpy
import sys

import xbmcaddon
import xbmcvfs


ADDON_ID = "plugin.video.rapideo_pl"


def _write(path, document):
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w", encoding="utf-8") as destination:
        json.dump(document, destination, sort_keys=True)
        destination.write("\n")


def _credentials(path):
    with open(path, "r", encoding="utf-8") as source:
        document = json.load(source)
    if set(document) != {"schema", "username", "password", "authtoken"}:
        raise ValueError("unsupported credential fields")
    if document["schema"] != 1:
        raise ValueError("unsupported credential schema")
    for name in ("username", "password"):
        value = document[name]
        if not isinstance(value, str) or not value or len(value) > 512:
            raise ValueError("invalid %s" % name)
    token = document["authtoken"]
    if token is not None and (
        not isinstance(token, str) or not token or len(token) > 2048
    ):
        raise ValueError("invalid authtoken")
    return document["username"], document["password"], token


def main():
    config_path, marker_path = sys.argv[1:3]
    report = {"ok": False, "schema": 1, "stage": "credentials"}
    try:
        username, password, authoritative_token = _credentials(config_path)
        report["stage"] = "settings"
        addon = xbmcaddon.Addon(ADDON_ID)
        credentials_changed = (
            addon.getSetting("login") != username
            or addon.getSetting("password") != password
        )
        if addon.getSetting("login") != username:
            addon.setSetting("login", username)
        if addon.getSetting("password") != password:
            addon.setSetting("password", password)

        report["stage"] = "load"
        addon_path = xbmcvfs.translatePath(addon.getAddonInfo("path"))
        original_addon = xbmcaddon.Addon

        def addon_with_default(addon_id=None):
            return original_addon(addon_id or ADDON_ID)

        xbmcaddon.Addon = addon_with_default
        namespace = runpy.run_path(
            os.path.join(addon_path, "addon.py"),
            run_name="mwo_rapideo_private_adapter",
        )

        report["stage"] = "authenticate"
        storage = namespace["auth_store"]
        token = str(storage.get("authtoken", "") or "")
        if authoritative_token and token != authoritative_token:
            token = authoritative_token
            storage["authtoken"] = token
            storage.sync()
        authenticated = False
        if not token:
            response = namespace["requests"].post(
                namespace["base_url"] + "/login",
                data={"login": username, "password": password},
                timeout=30,
            )
            report["authentication_transport"] = {
                "content_type": str(
                    response.headers.get("content-type", "")
                )[:80],
                "http_status": int(response.status_code),
            }
            authentication = response.json()
            token = (
                authentication.get("authtoken", "")
                if isinstance(authentication, dict)
                else ""
            )
            authenticated = True
        token_present = bool(token)
        if not token_present:
            report["authentication_api_error"] = (
                int(authentication.get("error", 0) or 0)
                if authenticated and isinstance(authentication, dict)
                else None
            )
            raise RuntimeError("Rapideo authentication was rejected")
        if authenticated:
            storage["authtoken"] = token
            storage.sync()

        report["stage"] = "account"
        response = namespace["requests"].post(
            namespace["base_url"] + "/account",
            data={"authtoken": token},
            timeout=30,
        )
        report["account_transport"] = {
            "content_type": str(
                response.headers.get("content-type", "")
            )[:80],
            "http_status": int(response.status_code),
        }
        account = response.json()
        account_details = (
            account.get("account", account)
            if isinstance(account, dict)
            else None
        )
        account_ok = (
            isinstance(account, dict)
            and int(account.get("error", 0) or 0) == 0
            and isinstance(account_details, dict)
            and bool(account_details.get("login"))
        )
        report.update(
            {
                "account_verified": account_ok,
                "addon_version": addon.getAddonInfo("version"),
                "changed": credentials_changed or authenticated,
                "credentials_stored": True,
                "ok": token_present and account_ok,
                "stage": "complete",
                "token_present": token_present,
            }
        )
    except Exception as error:  # noqa: BLE001 - Kodi runtime boundary
        report["error_type"] = type(error).__name__
        if isinstance(error, ModuleNotFoundError):
            report["error_module"] = str(error.name or "")[:128]
    finally:
        _write(marker_path, report)


if __name__ == "__main__":
    main()
