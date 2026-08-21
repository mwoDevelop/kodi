#!/usr/bin/env python3
"""Remove non-portable remote Kodi database bindings from a device profile."""

from __future__ import annotations

import hashlib
import tempfile
import xml.etree.ElementTree as ET
from pathlib import Path

from tools.kodi_profile import adb_command


REMOTE_ADVANCEDSETTINGS = (
    "/sdcard/Android/data/org.xbmc.kodi/files/.kodi/userdata/advancedsettings.xml"
)
REMOTE_STAGING = "/sdcard/Download/.mwo-advancedsettings.xml"
REMOTE_DATABASE_ELEMENTS = frozenset({"musicdatabase", "videodatabase"})


def _local_name(tag):
    return str(tag).rsplit("}", 1)[-1]


def sanitize_advancedsettings(payload):
    """Return a valid profile without QNAP/MySQL library bindings."""
    parser = ET.XMLParser(target=ET.TreeBuilder(insert_comments=True))
    root = ET.fromstring(payload, parser=parser)
    if _local_name(root.tag) != "advancedsettings":
        raise ValueError("advancedsettings.xml has an unexpected root")
    removed = []
    for child in list(root):
        name = _local_name(child.tag)
        if name in REMOTE_DATABASE_ELEMENTS:
            root.remove(child)
            removed.append(name)
    if not removed:
        return payload, ()
    output = ET.tostring(root, encoding="utf-8", xml_declaration=True)
    return output + (b"" if output.endswith(b"\n") else b"\n"), tuple(
        sorted(removed)
    )


def reconcile_android_advancedsettings(adb, port, serial):
    """Idempotently remove remote databases and verify the device write."""
    exists = adb_command(
        adb,
        port,
        serial,
        "shell",
        "test -f '%s'" % REMOTE_ADVANCEDSETTINGS,
        check=False,
    )
    if exists.returncode != 0:
        return {"status": "ABSENT", "removed": []}

    try:
        with tempfile.TemporaryDirectory(prefix="kodi-advancedsettings-") as temporary:
            source = Path(temporary) / "advancedsettings.xml"
            result = adb_command(
                adb,
                port,
                serial,
                "pull",
                REMOTE_ADVANCEDSETTINGS,
                str(source),
                check=False,
                timeout=60,
            )
            if result.returncode != 0 or not source.is_file():
                raise RuntimeError("cannot read Android advancedsettings.xml")
            output, removed = sanitize_advancedsettings(source.read_bytes())
            if not removed:
                return {
                    "status": "NO_CHANGE",
                    "removed": [],
                    "sha256": hashlib.sha256(output).hexdigest(),
                }
            sanitized = Path(temporary) / "advancedsettings.sanitized.xml"
            sanitized.write_bytes(output)
            adb_command(adb, port, serial, "push", str(sanitized), REMOTE_STAGING)
            adb_command(
                adb,
                port,
                serial,
                "shell",
                "mv -f '%s' '%s'" % (REMOTE_STAGING, REMOTE_ADVANCEDSETTINGS),
            )
            verified = Path(temporary) / "advancedsettings.verified.xml"
            adb_command(
                adb,
                port,
                serial,
                "pull",
                REMOTE_ADVANCEDSETTINGS,
                str(verified),
                timeout=60,
            )
            actual = verified.read_bytes()
            _, remaining = sanitize_advancedsettings(actual)
            if remaining or actual != output:
                raise RuntimeError("Android advancedsettings policy verification failed")
            return {
                "status": "UPDATED",
                "removed": list(removed),
                "sha256": hashlib.sha256(actual).hexdigest(),
            }
    finally:
        adb_command(
            adb,
            port,
            serial,
            "shell",
            "rm -f '%s'" % REMOTE_STAGING,
            check=False,
        )
