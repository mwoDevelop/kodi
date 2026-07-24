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
import subprocess
from pathlib import Path

ROOT = Path(__file__).parents[2]
KODI_ROOT = "/sdcard/Android/data/org.xbmc.kodi/files/.kodi"
EXPECTED = {
    "plugin.video.umbrella": "6.7.81.3",
    "script.module.mwoscrapers": "0.1.1",
    "repository.mwodevelop.testing": "1.0.0",
}


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


def kodi_version(adb, serial):
    return shell(
        adb,
        serial,
        "dumpsys package org.xbmc.kodi | sed -n 's/.*versionName=//p' | head -1",
    ).strip()


def sha256(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def prepare(args):
    backup = Path(args.backup_dir).resolve()
    backup.mkdir(parents=True, exist_ok=False)
    if kodi_version(args.adb, args.serial) != "21.2":
        raise RuntimeError("BlueStacks1 must run Kodi 21.2")

    settings = "%s/userdata/addon_data/plugin.video.umbrella/settings.xml" % KODI_ROOT
    database = "%s/userdata/Database" % KODI_ROOT
    run(args.adb, args.serial, "pull", settings, str(backup / "umbrella-settings.xml"))
    run(args.adb, args.serial, "pull", database, str(backup / "Database"))

    package = ROOT / "dist/repository.mwodevelop.testing-1.0.0.zip"
    if not package.is_file():
        raise RuntimeError("build dist first with tools/build_repo.py")
    remote = "/sdcard/Download/" + package.name
    run(args.adb, args.serial, "push", str(package), remote)
    report = {
        "phase": "prepared",
        "device": "BlueStacks1",
        "serial": args.serial,
        "kodi": "21.2",
        "repository_zip": remote,
        "repository_zip_sha256": sha256(package),
        "backup": str(backup),
    }
    print(json.dumps(report, indent=2, sort_keys=True))
    print(
        "\nIn Kodi select: Add-ons -> Install from zip file -> External storage "
        "-> Download -> repository.mwodevelop.testing-1.0.0.zip; then install "
        "Umbrella from mwoDevelop Add-ons (Testing). Run this script with "
        "--phase verify afterwards."
    )


def verify(args):
    versions = {
        addon_id: addon_version(args.adb, args.serial, addon_id)
        for addon_id in EXPECTED
    }
    if versions != EXPECTED:
        raise RuntimeError("unexpected installed versions: %r" % versions)

    backup = Path(args.backup_dir).resolve()
    if not backup.is_dir():
        raise RuntimeError("prepare backup does not exist: %s" % backup)
    log_path = backup / "kodi-after-install.log"
    run(args.adb, args.serial, "pull", KODI_ROOT + "/temp/kodi.log", str(log_path))
    log_text = log_path.read_text(encoding="utf-8", errors="replace")
    evidence = [
        line
        for line in log_text.splitlines()
        if "mwodevelop.github.io/kodi" in line.lower()
        or "repository.mwodevelop.testing" in line.lower()
        or "script.module.mwoscrapers" in line.lower()
        or "plugin.video.umbrella v6.7.81.3 installed" in line.lower()
    ]
    if not any("script.module.mwoscrapers v0.1.0 installed" in line for line in evidence):
        raise RuntimeError("Kodi log does not prove MwoScrapers installation")
    report = {
        "phase": "verified",
        "device": "BlueStacks1",
        "serial": args.serial,
        "kodi": kodi_version(args.adb, args.serial),
        "installed": versions,
        "repository_log_evidence": evidence[-60:],
        "backup": str(backup),
    }
    result = Path(args.result).resolve()
    result.parent.mkdir(parents=True, exist_ok=True)
    result.write_text(
        json.dumps(report, indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )
    print(json.dumps(report, indent=2, sort_keys=True))


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--phase", choices=("prepare", "verify"), required=True)
    parser.add_argument("--adb", required=True)
    parser.add_argument("--serial", default="127.0.0.1:5556")
    parser.add_argument("--backup-dir", required=True)
    parser.add_argument("--result", default="docs/e2e-results/bluestacks1.json")
    args = parser.parse_args()
    (prepare if args.phase == "prepare" else verify)(args)


if __name__ == "__main__":
    main()
