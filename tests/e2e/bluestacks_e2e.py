#!/usr/bin/env python3
"""Prepare and verify a real Kodi repository test on BlueStacks1.

The installation itself deliberately goes through Kodi's GUI. Android scoped
storage prevents a non-root ADB shell from safely injecting add-ons into Kodi's
profile, and bypassing Kodi's add-on manager would not be a valid E2E test.
"""

import argparse
import hashlib
import json
import re
import sqlite3
import subprocess
from pathlib import Path

ROOT = Path(__file__).parents[2]
KODI_ROOT = "/sdcard/Android/data/org.xbmc.kodi/files/.kodi"
COMPONENT_VERSIONS = {
    "plugin.video.umbrella": "6.7.81.7",
    "script.module.mwoscrapers": "0.1.2",
}
REPOSITORY_VERSION = "1.0.0"
DEFAULT_ORIGIN = "repository.mwodevelop.testing"


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


def addon_version(adb, serial, addon_id):
    path = "%s/addons/%s/addon.xml" % (KODI_ROOT, addon_id)
    payload = shell(adb, serial, "sed -n '1,8p' '%s'" % path, check=False)
    match = re.search(r'<addon[^>]+version="([^"]+)"', payload.replace("\n", " "))
    return match.group(1) if match else None


def expected_versions(origin):
    return {**COMPONENT_VERSIONS, origin: REPOSITORY_VERSION}


def addon_origins(database, addon_ids):
    placeholders = ",".join("?" for _ in addon_ids)
    with sqlite3.connect(database) as connection:
        rows = connection.execute(
            "SELECT addonID, origin FROM installed "
            "WHERE addonID IN (%s)" % placeholders,
            tuple(addon_ids),
        )
        return dict(rows)


def pull_addons_database(args, destination):
    remote = shell(
        args.adb,
        args.serial,
        "ls '%s/userdata/Database'/Addons*.db 2>/dev/null | sort -V | tail -1"
        % KODI_ROOT,
        check=False,
    ).strip()
    if not remote:
        raise RuntimeError("Kodi Addons database was not found")
    run(args.adb, args.serial, "pull", remote, str(destination))


def kodi_version(adb, serial):
    return shell(
        adb,
        serial,
        "dumpsys package org.xbmc.kodi | sed -n 's/.*versionName=//p' | head -1",
    ).strip()


def sha256(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def log_line_count(adb, serial):
    payload = shell(
        adb,
        serial,
        "wc -l < '%s/temp/kodi.log'" % KODI_ROOT,
        check=False,
    ).strip()
    return int(payload) if payload.isdigit() else 0


def playback_log_evidence(log_text, title, imdb):
    lines = log_text.splitlines()
    candidates = [
        index
        for index, line in enumerate(lines)
        if "VideoPlayer::OpenFile: plugin://plugin.video.umbrella/" in line
        and ("title=%s" % title) in line
        and ("imdb=%s" % imdb) in line
    ]
    if not candidates:
        raise RuntimeError("Kodi log does not contain the requested Umbrella playback")
    playback_lines = lines[candidates[-1] :]
    markers = (
        "Creating InputStream",
        "Creating Demuxer",
        "Using codec:",
        "Successful opened audio decoder",
        "CVideoPlayer::CloseFile()",
    )
    evidence = ["VideoPlayer::OpenFile title=%s imdb=%s" % (title, imdb)]
    for marker in markers:
        match = next((line for line in playback_lines if marker in line), None)
        if not match:
            raise RuntimeError("Kodi playback log is missing marker: %s" % marker)
        evidence.append(match)
    return evidence


def prepare(args):
    backup = Path(args.backup_dir).resolve()
    backup.mkdir(parents=True, exist_ok=False)
    if kodi_version(args.adb, args.serial) != "21.3":
        raise RuntimeError("BlueStacks1 must run Kodi 21.3")

    settings = "%s/userdata/addon_data/plugin.video.umbrella/settings.xml" % KODI_ROOT
    database = "%s/userdata/Database" % KODI_ROOT
    run(
        args.adb,
        args.serial,
        "pull",
        settings,
        str(backup / "umbrella-settings.xml"),
        check=False,
    )
    run(args.adb, args.serial, "pull", database, str(backup / "Database"))
    before = {
        addon_id: addon_version(args.adb, args.serial, addon_id)
        for addon_id in expected_versions(args.expected_origin)
    }
    log_lines_before = log_line_count(args.adb, args.serial)
    (backup / "prepare-state.json").write_text(
        json.dumps(
            {
                "installed_before": before,
                "log_lines_before": log_lines_before,
            },
            indent=2,
            sort_keys=True,
        )
        + "\n",
        encoding="utf-8",
    )
    if not args.allow_existing and any(
        before[addon_id]
        for addon_id in ("plugin.video.umbrella", "script.module.mwoscrapers")
    ):
        raise RuntimeError(
            "clean dependency test requires Umbrella and MwoScrapers to be absent; "
            "backup was created at %s" % backup
        )

    package = ROOT / ("dist/%s-%s.zip" % (args.expected_origin, REPOSITORY_VERSION))
    if not package.is_file():
        raise RuntimeError("build dist first with tools/build_repo.py")
    remote = "/sdcard/Download/" + package.name
    run(args.adb, args.serial, "push", str(package), remote)
    report = {
        "phase": "prepared",
        "device": "BlueStacks1",
        "serial": args.serial,
        "kodi": "21.3",
        "repository_zip": remote,
        "repository_zip_sha256": sha256(package),
        "backup": str(backup),
        "installed_before": before,
        "log_lines_before": log_lines_before,
    }
    print(json.dumps(report, indent=2, sort_keys=True))
    print(
        (
            "\nIn Kodi select: Add-ons -> Install from zip file -> External "
            "storage -> Download -> %s; then install Umbrella from that "
            "repository. Run this script with --phase verify afterwards."
        )
        % package.name
    )


def verify(args):
    expected = expected_versions(args.expected_origin)
    versions = {
        addon_id: addon_version(args.adb, args.serial, addon_id)
        for addon_id in expected
    }
    if versions != expected:
        raise RuntimeError("unexpected installed versions: %r" % versions)

    backup = Path(args.backup_dir).resolve()
    if not backup.is_dir():
        raise RuntimeError("prepare backup does not exist: %s" % backup)
    prepare_state = json.loads(
        (backup / "prepare-state.json").read_text(encoding="utf-8")
    )
    before = prepare_state["installed_before"]
    clean_dependency_test = not before.get("plugin.video.umbrella") and not before.get(
        "script.module.mwoscrapers"
    )
    if not args.allow_existing and not clean_dependency_test:
        raise RuntimeError("prepare phase was not a clean dependency test")
    database_path = backup / "addons-after-install.db"
    pull_addons_database(args, database_path)
    origins = addon_origins(database_path, expected)
    expected_origins = {addon_id: args.expected_origin for addon_id in expected}
    if origins != expected_origins:
        raise RuntimeError(
            "unexpected installed origins: %r (expected %r)"
            % (origins, expected_origins)
        )
    log_path = backup / "kodi-after-install.log"
    run(args.adb, args.serial, "pull", KODI_ROOT + "/temp/kodi.log", str(log_path))
    log_text = log_path.read_text(encoding="utf-8", errors="replace")
    log_lines = log_text.splitlines()
    marker = int(prepare_state.get("log_lines_before", 0))
    if marker > len(log_lines):
        raise RuntimeError("Kodi log rotated after prepare; repeat the clean test")
    test_lines = log_lines[marker:]
    evidence = [
        line
        for line in test_lines
        if "mwodevelop.github.io/kodi" in line.lower()
        or args.expected_origin in line.lower()
        or "script.module.mwoscrapers v0.1.2 installed" in line
        or "plugin.video.umbrella v6.7.81.7 installed" in line
    ]
    if not any("script.module.mwoscrapers v0.1.2" in line for line in evidence):
        raise RuntimeError("Kodi log does not prove MwoScrapers installation")
    report = {
        "phase": "verified",
        "device": "BlueStacks1",
        "serial": args.serial,
        "kodi": kodi_version(args.adb, args.serial),
        "installed": versions,
        "installed_origins": origins,
        "installed_before": before,
        "automatic_dependency_proven": clean_dependency_test,
        "repository_log_evidence": evidence[-60:],
        "backup": str(backup),
    }
    result = Path(args.result).resolve()
    result.parent.mkdir(parents=True, exist_ok=True)
    result.write_text(
        json.dumps(report, indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )
    print(json.dumps(report, indent=2, sort_keys=True))


def verify_playback(args):
    result = Path(args.result).resolve()
    if not result.is_file():
        raise RuntimeError("installation result does not exist: %s" % result)
    report = json.loads(result.read_text(encoding="utf-8"))
    if not report.get("automatic_dependency_proven"):
        raise RuntimeError("playback requires a successful clean dependency test")

    backup = Path(args.backup_dir).resolve()
    log_path = backup / "kodi-final-playback.log"
    run(args.adb, args.serial, "pull", KODI_ROOT + "/temp/kodi.log", str(log_path))
    log_text = log_path.read_text(encoding="utf-8", errors="replace")
    evidence = playback_log_evidence(log_text, args.title, args.imdb)
    install_evidence = [
        line
        for line in report.get("repository_log_evidence", [])
        if "script.module.mwoscrapers v0.1.2 installed" in line
        or "plugin.video.umbrella v6.7.81.7 installed" in line
    ]
    report.update(
        {
            "phase": "verified_playback",
            "provider": args.provider,
            "sources_displayed": args.sources,
            "test_content": {
                "title": args.title,
                "year": args.year,
                "imdb": args.imdb,
            },
            "playback": {
                "observed_seconds": args.observed_seconds,
                "result": "pass",
                "log_evidence": evidence,
            },
            "repository_log_evidence": install_evidence,
        }
    )
    result.write_text(
        json.dumps(report, indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )
    print(json.dumps(report, indent=2, sort_keys=True))


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--phase", choices=("prepare", "verify", "playback"), required=True
    )
    parser.add_argument("--adb", required=True)
    parser.add_argument("--serial", default="127.0.0.1:5556")
    parser.add_argument("--backup-dir", required=True)
    parser.add_argument("--result", default="docs/e2e-results/bluestacks1.json")
    parser.add_argument(
        "--expected-origin",
        default=DEFAULT_ORIGIN,
        choices=("repository.mwodevelop", "repository.mwodevelop.testing"),
        help="repository ID that must own the repository and installed components",
    )
    parser.add_argument(
        "--allow-existing",
        action="store_true",
        help="permit a regression run that does not prove dependency installation",
    )
    parser.add_argument("--title", default="Sintel")
    parser.add_argument("--year", type=int, default=2010)
    parser.add_argument("--imdb", default="tt1727587")
    parser.add_argument("--provider", default="torrentio")
    parser.add_argument("--sources", type=int, default=0)
    parser.add_argument("--observed-seconds", type=int, default=0)
    args = parser.parse_args()
    if args.phase == "prepare":
        prepare(args)
    elif args.phase == "verify":
        verify(args)
    else:
        verify_playback(args)


if __name__ == "__main__":
    main()
