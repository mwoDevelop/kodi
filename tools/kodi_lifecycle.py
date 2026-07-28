#!/usr/bin/env python3
"""Platform lifecycle probes composed with neutral host transports."""

from __future__ import annotations

import re
from abc import ABC, abstractmethod
from pathlib import Path

try:
    from kodi_transports import (
        AdbTransport,
        ReadOnlyCommand,
        SshTransport,
        TransportError,
    )
except ModuleNotFoundError:
    from tools.kodi_transports import (
        AdbTransport,
        ReadOnlyCommand,
        SshTransport,
        TransportError,
    )


KODI_ANDROID_PACKAGE = "org.xbmc.kodi"


def _major(version):
    match = re.match(r"^(\d+)", str(version))
    if not match:
        raise TransportError("Kodi returned an invalid version")
    return int(match.group(1))


class KodiPlatformLifecycle(ABC):
    """Platform behavior; transport details stay outside profile logic."""

    def __init__(self, device, transport):
        self.device = device
        self.transport = transport

    @abstractmethod
    def probe_kodi(self):
        raise NotImplementedError

    def assert_quiescent(self):
        probe = self.probe_kodi()
        if probe["running"]:
            raise TransportError("Kodi is running; host mutation refused")
        return probe


class AndroidKodiLifecycle(KodiPlatformLifecycle):
    def __init__(self, device, transport):
        if not isinstance(transport, AdbTransport):
            raise TypeError("Android lifecycle requires AdbTransport")
        super().__init__(device, transport)

    def probe_kodi(self):
        identity = self.transport.probe_identity()
        expected = self.device["expected"]
        if identity.model != expected["model"]:
            raise TransportError("Android model differs from device inventory")
        observed_abis = [
            item for item in identity.architecture.split(",") if item
        ]
        expected_abis = expected.get("abi", [])
        if expected_abis and not set(expected_abis).intersection(observed_abis):
            raise TransportError("Android ABI differs from device inventory")
        package = self.transport.package_dump(KODI_ANDROID_PACKAGE)
        version = re.search(r"versionName=([^\s]+)", package)
        if not version:
            raise TransportError("Kodi package is not installed")
        version_name = version.group(1)
        if _major(version_name) != expected["kodi_major"]:
            raise TransportError("Android Kodi major differs from inventory")
        pid = self.transport.process_id(KODI_ANDROID_PACKAGE)
        return {
            "platform": self.device["platform"],
            "transport": identity.transport,
            "model": identity.model,
            "host_fingerprint": identity.fingerprint,
            "abi": observed_abis,
            "kodi_version": version_name,
            "running": bool(pid),
            "runtime_paths_qualified": True,
        }


class FlatpakKodiLifecycle(KodiPlatformLifecycle):
    def __init__(self, device, transport):
        if not isinstance(transport, SshTransport):
            raise TypeError("Flatpak lifecycle requires SshTransport")
        super().__init__(device, transport)

    def _execute(self, argv, allowed_returncodes=(0,)):
        return self.transport.execute_read_only(
            ReadOnlyCommand(tuple(argv), tuple(allowed_returncodes))
        )

    def probe_kodi(self):
        identity = self.transport.probe_identity()
        expected = self.device["expected"]
        if identity.model != expected["model"]:
            raise TransportError("Linux model differs from device inventory")
        expected_abis = expected.get("abi", [])
        if expected_abis and identity.architecture not in expected_abis:
            raise TransportError("Linux architecture differs from inventory")
        app_id = expected["flatpak_app_id"]
        installed = self._execute(
            (
                "flatpak",
                "list",
                "--app",
                "--columns=application,arch,version",
            )
        ).stdout.splitlines()
        matching = [
            line.split("\t")
            for line in installed
            if line.split("\t", 1)[0] == app_id
        ]
        if len(matching) != 1 or len(matching[0]) != 3:
            raise TransportError("Flatpak Kodi inventory is ambiguous")
        _, flatpak_arch, version = (item.strip() for item in matching[0])
        if not version or not flatpak_arch:
            raise TransportError("Flatpak Kodi inventory is incomplete")
        if _major(version) != expected["kodi_major"]:
            raise TransportError("Flatpak Kodi major differs from inventory")
        if expected_abis and flatpak_arch not in expected_abis:
            raise TransportError("Flatpak Kodi ABI differs from inventory")

        home = Path(identity.home)
        candidate = home / expected["kodi_data_root"]
        canonical_text = self._execute(
            ("readlink", "-f", "--", str(candidate))
        ).stdout.strip()
        if not canonical_text:
            raise TransportError("Flatpak Kodi data root does not exist")
        canonical = Path(canonical_text)
        try:
            canonical.relative_to(home)
        except ValueError as error:
            raise TransportError(
                "Flatpak Kodi data root escapes account home"
            ) from error
        metadata = self._execute(
            ("stat", "-Lc", "%u|%F", "--", str(canonical))
        ).stdout.strip()
        owner, separator, file_type = metadata.partition("|")
        if (
            not separator
            or owner != str(identity.uid)
            or file_type != "directory"
        ):
            raise TransportError(
                "Flatpak Kodi data root has invalid owner or type"
            )
        running_result = self._execute(
            (
                "pgrep",
                "-u",
                str(identity.uid),
                "-f",
                "tv.kodi.Kodi|/kodi( |$)",
            ),
            allowed_returncodes=(0, 1),
        )
        return {
            "platform": self.device["platform"],
            "transport": identity.transport,
            "model": identity.model,
            "host_fingerprint": identity.fingerprint,
            "principal_uid": identity.uid,
            "abi": [flatpak_arch],
            "kodi_version": version,
            "running": running_result.returncode == 0,
            "data_root": str(canonical),
            "runtime_paths_qualified": False,
            "runtime_path_status": "REQUIRES_IN_PROCESS_KODI_PROBE",
        }


def lifecycle_for_device(device, transport):
    platform = device["platform"]
    if platform in {"android", "android-emulator"}:
        return AndroidKodiLifecycle(device, transport)
    if platform == "linux-flatpak":
        return FlatpakKodiLifecycle(device, transport)
    raise ValueError("unsupported Kodi platform: %s" % platform)
