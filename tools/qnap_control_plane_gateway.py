#!/usr/bin/env python3
"""Build, install and verify the QTS HTTPS gateway for Control Plane."""

from __future__ import annotations

import argparse
import base64
import hashlib
import re
import shlex
import subprocess
import tempfile
from pathlib import Path, PurePosixPath
from urllib.request import urlopen

try:
    from qnap_profile_sync import connect
except ModuleNotFoundError:
    from tools.qnap_profile_sync import connect


NAME = "KodiCPGateway"
VERSION = "0.1.1"
BACKEND_PORT = 19445
PROXY_PATH = "/control-plane"
QDK_VERSION = "2.5.3"
QDK_URL = "https://github.com/qnap-dev/QDK/releases/download/v2.5.3/qdk_2.5.3_amd64.deb"
QDK_SHA256 = "17b3841b7d4590a4ee025844ba583304b5e3c497d9fa8934d5175131d3908022"
REMOTE_PACKAGE = PurePosixPath(
    "/share/CACHEDEV3_DATA/.mwodevelop/control-plane/app/KodiCPGateway.qpkg"
)


class GatewayError(RuntimeError):
    pass


def source_root(repository):
    return Path(repository).resolve() / "deploy/qnap-control-plane-gateway"


def validate_source(repository):
    root = source_root(repository)
    config = (root / "qpkg.cfg").read_text(encoding="utf-8")
    expected = {
        "QPKG_NAME": NAME,
        "QPKG_VER": VERSION,
        # Keep the desktop target canonical. QTS still adds a separator to the
        # generated proxy destination; the BFF normalizes that known hop.
        "QPKG_WEBUI": PROXY_PATH,
        "QPKG_WEB_PORT": str(BACKEND_PORT),
        "QPKG_USE_PROXY": "1",
        "QPKG_PROXY_PATH": PROXY_PATH,
        "QPKG_DESKTOP_APP": "0",
        "QPKG_VISIBLE": "0",
        "QPKG_FORCE_VISIBLE": "1",
    }
    for key, value in expected.items():
        if not re.search(rf'^{key}="{re.escape(value)}"$', config, re.MULTILINE):
            raise GatewayError(f"unsafe or missing QPKG field: {key}")
    service = root / "shared" / f"{NAME}.sh"
    if not service.is_file() or service.is_symlink():
        raise GatewayError("gateway service program is missing or unsafe")
    forbidden = ("password", "secret", "token", "private_key")
    for path in root.rglob("*"):
        if path.is_file() and any(
            word in path.read_text(encoding="utf-8").lower() for word in forbidden
        ):
            raise GatewayError("gateway package must not contain secrets")
    return {
        "name": NAME,
        "version": VERSION,
        "backend_port": BACKEND_PORT,
        "proxy_path": PROXY_PATH,
    }


def _download(url, destination):
    with urlopen(url, timeout=30) as response, destination.open("wb") as handle:
        while chunk := response.read(1024 * 1024):
            handle.write(chunk)


def build(repository, output_directory):
    validate_source(repository)
    output = Path(output_directory).resolve()
    output.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(prefix="mwodevelop-qdk-") as temporary:
        temporary = Path(temporary)
        archive = temporary / "qdk.deb"
        _download(QDK_URL, archive)
        digest = hashlib.sha256(archive.read_bytes()).hexdigest()
        if digest != QDK_SHA256:
            raise GatewayError("downloaded QDK package digest differs")
        qdk_root = temporary / "qdk"
        subprocess.run(("dpkg-deb", "-x", str(archive), str(qdk_root)), check=True)
        qbuild = qdk_root / "usr/share/QDK/bin/qbuild"
        subprocess.run(
            (
                str(qbuild),
                "--root",
                str(source_root(repository)),
                "--build-dir",
                str(output),
                "--build-arch",
                "arm-x41",
            ),
            check=True,
            env={
                "PATH": str(qdk_root / "usr/bin") + ":/usr/bin:/bin",
                "QDK_PATH": str(qbuild.parents[1]),
            },
        )
    packages = sorted(output.glob(f"{NAME}_{VERSION}*.qpkg"))
    if len(packages) != 1 or not packages[0].is_file():
        raise GatewayError("QDK did not produce one expected gateway package")
    return packages[0]


def install(session, repository):
    validate_source(repository)
    try:
        return verify(session)
    except GatewayError:
        pass
    with tempfile.TemporaryDirectory(prefix="mwodevelop-gateway-") as temporary:
        package = build(repository, temporary)
        encoded = base64.b64encode(package.read_bytes()).decode("ascii")
        encoded_path = str(REMOTE_PACKAGE) + ".b64"
        session.upload_text(encoded_path, encoded + "\n", 0o600)
        session.execute(
            "base64 -d "
            + shlex.quote(encoded_path)
            + " > "
            + shlex.quote(str(REMOTE_PACKAGE))
            + " && chmod 600 "
            + shlex.quote(str(REMOTE_PACKAGE))
            + " && rm -f "
            + shlex.quote(encoded_path)
        )
        try:
            # QTS rejects locally built, unsigned packages in qpkgd before its
            # documented ignore-cert flag is evaluated. Run the verified QDK
            # self-extracting installer directly, matching qpkgd's own execution.
            install_output = session.execute(
                "QNAP_QPKG="
                + NAME
                + " /bin/sh "
                + shlex.quote(str(REMOTE_PACKAGE))
                + " 2>&1",
                allowed=(0, 10),
                timeout=180,
            )
        finally:
            session.execute("rm -f " + shlex.quote(str(REMOTE_PACKAGE)), allowed=(0, 1))
    registered = session.execute(
        "/sbin/getcfg " + NAME + " Version -d missing -f /etc/config/qpkg.conf",
        allowed=(0, 1, 250),
    )
    if registered != VERSION:
        detail = (
            install_output.splitlines()[-1][:240] if install_output else "no diagnostic"
        )
        raise GatewayError("QPKG installation failed: " + detail)
    session.execute("/sbin/setcfg " + NAME + " Enable TRUE -f /etc/config/qpkg.conf")
    session.execute(
        "/etc/init.d/" + NAME + ".sh start",
        allowed=(0, 1),
        timeout=60,
    )
    return verify(session)


def verify(session):
    fields = {}
    for field in (
        "Version",
        "Enable",
        "WebUI",
        "Web_Port",
        "Use_Proxy",
        "Proxy_Path",
        "Desktop",
        "Visible",
        "Force_Visible",
    ):
        fields[field] = session.execute(
            "/sbin/getcfg "
            + NAME
            + " "
            + field
            + " -d missing -f /etc/config/qpkg.conf",
            allowed=(0, 1, 250),
        )
    expected = {
        "Version": VERSION,
        "Enable": "TRUE",
        "WebUI": PROXY_PATH,
        "Web_Port": str(BACKEND_PORT),
        "Use_Proxy": "1",
        "Proxy_Path": PROXY_PATH,
        "Desktop": "0",
        "Visible": "0",
        "Force_Visible": "1",
    }
    for field, value in expected.items():
        if fields.get(field) != value:
            raise GatewayError(f"installed QPKG field differs: {field}")
    return fields


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--repository", default=".")
    parser.add_argument("--references", default=".env")
    subparsers = parser.add_subparsers(dest="command", required=True)
    build_parser = subparsers.add_parser("build")
    build_parser.add_argument("--output", required=True)
    subparsers.add_parser("deploy")
    subparsers.add_parser("status")
    args = parser.parse_args()
    if args.command == "build":
        print(build(args.repository, args.output))
        return
    session = connect(args.repository, args.references)
    try:
        result = (
            install(session, args.repository)
            if args.command == "deploy"
            else verify(session)
        )
        print(result)
    finally:
        session.close()


if __name__ == "__main__":
    main()
