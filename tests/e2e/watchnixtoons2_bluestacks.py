#!/usr/bin/env python3
"""Verify a GUI-driven WatchNixtoons2 playback test on BlueStacks1.

Kodi installation, catalogue navigation, quality selection, and playback are
intentionally performed through the GUI. This verifier reads only the resulting
add-on database and log, so it does not bypass Kodi's add-on manager.
"""

import argparse
import json
import re
import sqlite3
import subprocess
import tempfile
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).parents[2]
KODI_ROOT = "/sdcard/Android/data/org.xbmc.kodi/files/.kodi"
ADDON_ID = "plugin.video.watchnixtoons2.mwodevelop"
ORIGINAL_ID = "plugin.video.watchnixtoons2"
STABLE_ORIGIN = "repository.mwodevelop"
TESTING_ORIGIN = "repository.mwodevelop.testing"


def run(adb, serial, *args, check=True, capture=False):
    return subprocess.run(
        [adb, "-s", serial, *args],
        check=check,
        text=True,
        stdout=subprocess.PIPE if capture else None,
        stderr=subprocess.STDOUT if capture else None,
    )


def shell(adb, serial, command, check=True):
    return run(adb, serial, "shell", command, check=check, capture=True).stdout or ""


def kodi_version(adb, serial):
    return shell(
        adb,
        serial,
        "dumpsys package org.xbmc.kodi | sed -n "
        "'s/.*versionName=//p' | head -1",
    ).strip()


def addon_version(adb, serial, addon_id):
    path = "%s/addons/%s/addon.xml" % (KODI_ROOT, addon_id)
    payload = shell(adb, serial, "sed -n '1,12p' '%s'" % path, check=False)
    match = re.search(r'<addon[^>]+version="([^"]+)"', payload.replace("\n", " "))
    return match.group(1) if match else None


def pull_addons_database(adb, serial, destination):
    remote = shell(
        adb,
        serial,
        "ls '%s/userdata/Database'/Addons*.db 2>/dev/null | sort -V | tail -1"
        % KODI_ROOT,
        check=False,
    ).strip()
    if not remote:
        raise RuntimeError("Kodi Addons database was not found")
    run(adb, serial, "pull", remote, str(destination))


def installed_rows(database):
    with sqlite3.connect(database) as connection:
        rows = connection.execute(
            "SELECT addonID, enabled, origin, disabledReason FROM installed"
        )
        return {
            addon_id: {
                "enabled": bool(enabled),
                "origin": origin,
                "disabled_reason": disabled_reason,
            }
            for addon_id, enabled, origin, disabled_reason in rows
        }


def playback_log_evidence(log_text, content_path):
    lines = log_text.splitlines()
    candidates = [
        index
        for index, line in enumerate(lines)
        if "VideoPlayer::OpenFile: plugin://%s/" % ADDON_ID in line
        and content_path in line
    ]
    if not candidates:
        raise RuntimeError("Kodi log does not contain the requested playback")

    playback_lines = lines[candidates[-1] :]
    required = (
        "Creating InputStream",
        "Creating Demuxer",
        "Successful opened audio decoder",
        "CVideoPlayer::CloseFile()",
    )
    evidence = [playback_lines[0]]
    for marker in required:
        match = next((line for line in playback_lines if marker in line), None)
        if not match:
            raise RuntimeError("Kodi playback log is missing marker: %s" % marker)
        evidence.append(match)

    addon_errors = [
        line
        for line in playback_lines
        if ADDON_ID in line
        and ("error <general>" in line.lower() or "exception" in line.lower())
    ]
    if addon_errors:
        raise RuntimeError("WatchNixtoons2 logged an error: %s" % addon_errors[-1])
    return evidence


def stable_component():
    lock = json.loads(
        (ROOT / "manifests/locks/stable.json").read_text(encoding="utf-8")
    )
    try:
        component = lock["components"][ADDON_ID]
    except KeyError as error:
        raise RuntimeError("stable lock does not contain %s" % ADDON_ID) from error
    return component


def verify(args):
    component = stable_component()
    expected_version = component["version"]
    actual_kodi = kodi_version(args.adb, args.serial)
    if actual_kodi != args.expected_kodi:
        raise RuntimeError(
            "unexpected Kodi version: %s (expected %s)"
            % (actual_kodi, args.expected_kodi)
        )
    actual_version = addon_version(args.adb, args.serial, ADDON_ID)
    if actual_version != expected_version:
        raise RuntimeError(
            "unexpected %s version: %s (expected %s)"
            % (ADDON_ID, actual_version, expected_version)
        )

    with tempfile.TemporaryDirectory(prefix="watchnixtoons2-e2e-") as temporary:
        temporary_path = Path(temporary)
        database = temporary_path / "addons.db"
        log_path = temporary_path / "kodi.log"
        pull_addons_database(args.adb, args.serial, database)
        run(
            args.adb,
            args.serial,
            "pull",
            KODI_ROOT + "/temp/kodi.log",
            str(log_path),
        )
        installed = installed_rows(database)
        own = installed.get(ADDON_ID)
        if not own or not own["enabled"] or own["origin"] != STABLE_ORIGIN:
            raise RuntimeError("unexpected installed state for %s: %r" % (ADDON_ID, own))
        if ORIGINAL_ID in installed:
            raise RuntimeError("original WatchNixtoons2 is still installed")
        if TESTING_ORIGIN in installed:
            raise RuntimeError("testing repository is still installed")
        old_salt_dependents = sorted(
            addon_id
            for addon_id, state in installed.items()
            if state["origin"] == "repository.oldsalt"
        )
        evidence = playback_log_evidence(
            log_path.read_text(encoding="utf-8", errors="replace"),
            args.content_path,
        )

    if args.catalog_items < 1:
        raise RuntimeError("catalogue item count must be recorded")
    if args.quality not in args.qualities:
        raise RuntimeError("selected quality is absent from recorded qualities")
    if args.observed_seconds < 1:
        raise RuntimeError("playback observation time must be recorded")

    report = {
        "schema": 1,
        "captured_at": datetime.now(timezone.utc).isoformat(),
        "device": "BlueStacks1",
        "serial": args.serial,
        "kodi": actual_kodi,
        "channel": "stable",
        "installed": {
            ADDON_ID: {
                "version": actual_version,
                "enabled": own["enabled"],
                "origin": own["origin"],
            },
            STABLE_ORIGIN: {
                "enabled": installed[STABLE_ORIGIN]["enabled"],
                "origin": installed[STABLE_ORIGIN]["origin"],
            },
        },
        "artifact": {
            "commit": component["commit"],
            "zip_sha256": component["zip_sha256"],
            "url": (
                "https://mwodevelop.github.io/kodi/stable/omega/%s/%s-%s.zip"
                % (ADDON_ID, ADDON_ID, expected_version)
            ),
        },
        "catalogue": {
            "section": "Latest Releases",
            "items": args.catalog_items,
            "title": args.title,
            "content_path": args.content_path,
            "qualities": args.qualities,
            "selected_quality": args.quality,
        },
        "playback": {
            "observed_seconds": args.observed_seconds,
            "native_hls_without_inputstream_adaptive": (
                "inputstream.adaptive" not in installed
            ),
            "log_evidence": evidence,
            "result": "pass",
        },
        "cleanup": {
            "original_addon_removed": ORIGINAL_ID not in installed,
            "testing_repository_removed": TESTING_ORIGIN not in installed,
            "old_salt_repository_retained_for": old_salt_dependents,
        },
        "result": "pass",
    }
    result = Path(args.result).resolve()
    result.parent.mkdir(parents=True, exist_ok=True)
    result.write_text(
        json.dumps(report, indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )
    print(json.dumps(report, indent=2, sort_keys=True))


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--adb", required=True)
    parser.add_argument("--serial", default="emulator-5554")
    parser.add_argument("--expected-kodi", default="21.3")
    parser.add_argument(
        "--result",
        default="docs/e2e-results/2026-07-25-bluestacks1-watchnixtoons2.json",
    )
    parser.add_argument(
        "--title", default="Beyblade X Episode 120 English Dubbed"
    )
    parser.add_argument(
        "--content-path", default="beyblade-x-episode-120-english-dubbed"
    )
    parser.add_argument("--catalog-items", type=int, default=16)
    parser.add_argument("--qualities", nargs="+", type=int, default=[480, 720, 1080])
    parser.add_argument("--quality", type=int, default=720)
    parser.add_argument("--observed-seconds", type=int, default=25)
    verify(parser.parse_args())


if __name__ == "__main__":
    main()
