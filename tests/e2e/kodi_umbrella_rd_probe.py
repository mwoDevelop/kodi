"""Sanitized Real-Debrid health probe executed by Kodi's Python runtime."""

import json
import os
import re
import sys
import time

import xbmcaddon
import xbmcvfs


OUTPUT = (
    sys.argv[1]
    if len(sys.argv) > 1 and sys.argv[1]
    else xbmcvfs.translatePath("special://temp/umbrella-rd-probe.json")
)
ADDON_ID = "plugin.video.umbrella"
FAKE_INFO_HASH = "0" * 40


def _error_summary(error):
    if error is None:
        return None
    return {
        "error": str(getattr(error, "error", ""))[:80],
        "error_code": int(getattr(error, "error_code", 0) or 0),
        "http_status": int(getattr(error, "http_status", 0) or 0),
        "retry_after": float(getattr(error, "retry_after", 0.0) or 0.0),
    }


def _timed(operation):
    started = time.monotonic()
    value = operation()
    return value, round(time.monotonic() - started, 3)


def main():
    report = {"ok": False, "schema": 1, "stage": "start"}
    try:
        report["stage"] = "addon"
        addon = xbmcaddon.Addon(ADDON_ID)
        addon_path = xbmcvfs.translatePath(addon.getAddonInfo("path"))
        if addon_path not in sys.path:
            sys.path.insert(0, addon_path)
        # Umbrella's control module uses Addon() without an explicit id because
        # it normally runs through plugin://. RunScript has no addon context,
        # so provide only that missing default inside this disposable process.
        original_addon = xbmcaddon.Addon

        def addon_with_default(addon_id=None):
            return original_addon(addon_id or ADDON_ID)

        xbmcaddon.Addon = addon_with_default
        report["stage"] = "import"
        from resources.lib.debrid.realdebrid import RealDebrid

        report["stage"] = "account"
        debrid = RealDebrid()
        account, account_seconds = _timed(debrid.account_info)
        account_ok = isinstance(account, dict) and bool(account.get("id"))
        report["account"] = {
            "account_type": (
                str(account.get("type", ""))[:24]
                if isinstance(account, dict)
                else ""
            ),
            "elapsed_seconds": account_seconds,
            "error": _error_summary(debrid.last_error),
            "ok": account_ok,
            "token_present": bool(debrid.token),
        }
        report["stage"] = "instant_availability"
        availability, availability_seconds = _timed(
            lambda: debrid.check_cache(FAKE_INFO_HASH)
        )
        availability_error = debrid.last_error
        availability_disabled = (
            int(getattr(availability_error, "error_code", 0) or 0) == 37
        )
        availability_ok = isinstance(availability, dict) and (
            int(getattr(availability_error, "http_status", 0) or 0) == 200
            or availability_disabled
        )
        report["instant_availability"] = {
            "elapsed_seconds": availability_seconds,
            "error": _error_summary(availability_error),
            "mode": (
                "disabled_endpoint"
                if availability_disabled
                else "available" if availability_ok else "error"
            ),
            "ok": availability_ok,
            "response_mapping": availability_ok,
        }
        report["addon_version"] = addon.getAddonInfo("version")
        report["ok"] = account_ok and availability_ok
        report["stage"] = "complete"
    except Exception as error:  # noqa: BLE001 - Kodi runtime boundary
        report["error_type"] = type(error).__name__
        message = re.sub(r"https?://\S+", "<URL>", str(error))
        message = re.sub(
            r"(?i)(token|secret|authorization)[=: ]+\S+",
            r"\1=<REDACTED>",
            message,
        )
        report["error_message"] = message[:160]
    finally:
        os.makedirs(os.path.dirname(OUTPUT), exist_ok=True)
        with open(OUTPUT, "w", encoding="utf-8") as destination:
            json.dump(report, destination, indent=2, sort_keys=True)
            destination.write("\n")


if __name__ == "__main__":
    main()
