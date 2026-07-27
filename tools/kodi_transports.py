#!/usr/bin/env python3
"""Neutral, capability-limited host transports for Kodi administration."""

from __future__ import annotations

import hashlib
import os
import re
import shlex
import stat
import subprocess
from abc import ABC, abstractmethod
from dataclasses import dataclass
from pathlib import Path


SAFE_USER = re.compile(r"^[A-Za-z_][A-Za-z0-9._-]{0,63}$")
READ_ONLY_PROGRAMS = {
    "cat",
    "flatpak",
    "getent",
    "id",
    "pgrep",
    "readlink",
    "stat",
    "uname",
}


class TransportError(RuntimeError):
    """Raised when a transport cannot prove the expected host state."""


@dataclass(frozen=True)
class CommandResult:
    returncode: int
    stdout: str
    stderr: str


@dataclass(frozen=True)
class ReadOnlyCommand:
    argv: tuple[str, ...]
    allowed_returncodes: tuple[int, ...] = (0,)

    def __post_init__(self):
        if not self.argv or self.argv[0] not in READ_ONLY_PROGRAMS:
            raise ValueError("command is not in the read-only allowlist")
        if any(
            not isinstance(token, str)
            or not token
            or "\x00" in token
            or "\n" in token
            or "\r" in token
            for token in self.argv
        ):
            raise ValueError("read-only command contains an invalid token")
        if (
            not self.allowed_returncodes
            or any(
                not isinstance(code, int) or code < 0
                for code in self.allowed_returncodes
            )
        ):
            raise ValueError("invalid allowed return codes")


@dataclass(frozen=True)
class HostIdentity:
    transport: str
    user: str
    uid: int
    home: str
    architecture: str
    model: str
    fingerprint: str


class Transport(ABC):
    """Low-level transport consumed only by a platform lifecycle."""

    kind: str

    @abstractmethod
    def probe_identity(self):
        raise NotImplementedError


def _completed(result):
    return CommandResult(
        returncode=result.returncode,
        stdout=result.stdout or "",
        stderr=result.stderr or "",
    )


class AdbTransport(Transport):
    kind = "adb"

    def __init__(self, endpoint, adb="adb", server_port=5038, runner=None):
        if not isinstance(endpoint, str) or not endpoint:
            raise ValueError("ADB endpoint must be a non-empty string")
        self.endpoint = endpoint
        self.adb = adb
        self.server_port = int(server_port)
        self._runner = runner or subprocess.run

    def _invoke(self, *args, allowed_returncodes=(0,)):
        result = self._runner(
            [
                self.adb,
                "-P",
                str(self.server_port),
                "-s",
                self.endpoint,
                *args,
            ],
            capture_output=True,
            text=True,
            check=False,
        )
        completed = _completed(result)
        if completed.returncode not in allowed_returncodes:
            raise TransportError(
                "ADB command failed with exit code %s" % completed.returncode
            )
        return completed

    def _shell_output(self, *argv, allowed_returncodes=(0,)):
        if not argv or any(
            not isinstance(token, str)
            or not token
            or "\x00" in token
            or "\n" in token
            or "\r" in token
            for token in argv
        ):
            raise ValueError("invalid ADB shell command")
        return self._invoke(
            "shell",
            *argv,
            allowed_returncodes=allowed_returncodes,
        ).stdout

    def package_dump(self, package):
        if not re.fullmatch(r"[A-Za-z0-9._-]+", package):
            raise ValueError("invalid Android package id")
        return self._shell_output("dumpsys", "package", package)

    def process_id(self, package):
        if not re.fullmatch(r"[A-Za-z0-9._-]+", package):
            raise ValueError("invalid Android package id")
        return self._shell_output(
            "pidof",
            package,
            allowed_returncodes=(0, 1),
        ).strip()

    def probe_identity(self):
        state = self._invoke("get-state").stdout.strip()
        if state != "device":
            raise TransportError("ADB endpoint is not an authorized device")
        model = self._shell_output("getprop", "ro.product.model").strip()
        serial = self._shell_output("getprop", "ro.serialno").strip()
        architecture = self._shell_output(
            "getprop", "ro.product.cpu.abilist"
        ).strip()
        if not model or not architecture:
            raise TransportError("ADB identity probe returned incomplete data")
        fingerprint = hashlib.sha256(
            ("%s\0%s" % (serial, model)).encode("utf-8")
        ).hexdigest()
        return HostIdentity(
            transport=self.kind,
            user="android-owner",
            uid=0,
            home="",
            architecture=architecture,
            model=model,
            fingerprint=fingerprint,
        )


class SshTransport(Transport):
    kind = "ssh"

    def __init__(
        self,
        host,
        user,
        identity_file,
        known_hosts_file,
        ssh="ssh",
        runner=None,
        connect_timeout=10,
    ):
        if not isinstance(host, str) or not host:
            raise ValueError("SSH host must be a non-empty string")
        if not isinstance(user, str) or not SAFE_USER.fullmatch(user):
            raise ValueError("SSH user is invalid")
        self.host = host
        self.user = user
        self.identity_file = Path(identity_file).expanduser().resolve()
        self.known_hosts_file = Path(known_hosts_file).expanduser().resolve()
        self.ssh = ssh
        self._runner = runner or subprocess.run
        self.connect_timeout = int(connect_timeout)
        self._validate_credentials()

    @classmethod
    def from_device(cls, device, references, **kwargs):
        endpoint = device["endpoints"]["ssh"]
        missing = [
            name
            for name in (
                endpoint["user_ref"],
                endpoint["credential_ref"],
                endpoint["known_hosts_ref"],
            )
            if not references.get(name)
        ]
        if missing:
            raise ValueError(
                "missing private SSH references: %s" % ", ".join(sorted(missing))
            )
        return cls(
            host=endpoint["host"],
            user=references[endpoint["user_ref"]],
            identity_file=references[endpoint["credential_ref"]],
            known_hosts_file=references[endpoint["known_hosts_ref"]],
            **kwargs,
        )

    def _validate_credentials(self):
        if not self.identity_file.is_file():
            raise ValueError("SSH identity file does not exist")
        if not self.known_hosts_file.is_file():
            raise ValueError("SSH known_hosts file does not exist")
        mode = stat.S_IMODE(self.identity_file.stat().st_mode)
        if mode & 0o077:
            raise ValueError("SSH identity file permissions are too broad")

    def base_argv(self):
        return [
            self.ssh,
            "-T",
            "-o",
            "BatchMode=yes",
            "-o",
            "IdentitiesOnly=yes",
            "-o",
            "ForwardAgent=no",
            "-o",
            "StrictHostKeyChecking=yes",
            "-o",
            "UserKnownHostsFile=%s" % self.known_hosts_file,
            "-o",
            "IdentityFile=%s" % self.identity_file,
            "-o",
            "ConnectTimeout=%s" % self.connect_timeout,
            "%s@%s" % (self.user, self.host),
        ]

    def execute_read_only(self, command):
        if not isinstance(command, ReadOnlyCommand):
            raise TypeError("SSH transport accepts only ReadOnlyCommand")
        remote = " ".join(shlex.quote(token) for token in command.argv)
        result = self._runner(
            [*self.base_argv(), remote],
            capture_output=True,
            text=True,
            check=False,
            env={
                **os.environ,
                "SSH_AUTH_SOCK": "",
            },
        )
        completed = _completed(result)
        if completed.returncode not in command.allowed_returncodes:
            raise TransportError(
                "SSH read-only command failed with exit code %s"
                % completed.returncode
            )
        return completed

    def _output(self, *argv):
        return self.execute_read_only(ReadOnlyCommand(tuple(argv))).stdout.strip()

    def probe_identity(self):
        uid_text = self._output("id", "-u")
        username = self._output("id", "-un")
        if username != self.user:
            raise TransportError("SSH account identity differs from user_ref")
        try:
            uid = int(uid_text)
        except ValueError as error:
            raise TransportError("SSH account returned invalid uid") from error
        passwd = self._output("getent", "passwd", username)
        fields = passwd.split(":")
        if len(fields) < 7 or fields[0] != username:
            raise TransportError("getent returned invalid account data")
        try:
            passwd_uid = int(fields[2])
        except ValueError as error:
            raise TransportError("getent returned invalid account uid") from error
        if passwd_uid != uid:
            raise TransportError("SSH uid differs from passwd database")
        home = fields[5]
        if not home.startswith("/") or home == "/":
            raise TransportError("SSH account has unsafe home")
        architecture = self._output("uname", "-m")
        machine_id = self._output("cat", "/etc/machine-id")
        model_result = self.execute_read_only(
            ReadOnlyCommand(
                ("cat", "/sys/class/dmi/id/product_name"),
                allowed_returncodes=(0, 1),
            )
        )
        model = model_result.stdout.strip() or "unknown"
        if not architecture or not machine_id:
            raise TransportError("SSH identity probe returned incomplete data")
        fingerprint = hashlib.sha256(
            machine_id.encode("utf-8")
        ).hexdigest()
        return HostIdentity(
            transport=self.kind,
            user=username,
            uid=uid,
            home=home,
            architecture=architecture,
            model=model,
            fingerprint=fingerprint,
        )


def transport_for_device(
    device,
    references=None,
    adb="adb",
    adb_server_port=5038,
    ssh="ssh",
    runner=None,
):
    endpoints = device["endpoints"]
    if "adb" in endpoints:
        return AdbTransport(
            endpoints["adb"],
            adb=adb,
            server_port=adb_server_port,
            runner=runner,
        )
    if "ssh" in endpoints:
        return SshTransport.from_device(
            device,
            references or {},
            ssh=ssh,
            runner=runner,
        )
    raise ValueError("device has no supported host transport")
