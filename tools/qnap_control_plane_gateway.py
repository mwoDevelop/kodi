#!/usr/bin/env python3
"""Build, install and verify the QTS HTTPS gateway for Control Plane."""

from __future__ import annotations

import argparse
import base64
import binascii
import hashlib
import json
import re
import shlex
import shutil
import stat
import subprocess
import tempfile
from pathlib import Path, PurePosixPath
from urllib.parse import parse_qs, urlparse
from urllib.request import urlopen

try:
    from qnap_profile_sync import connect
except ModuleNotFoundError:
    from tools.qnap_profile_sync import connect


NAME = "KodiCPGateway"
VERSION = "0.3.0"
BACKEND_PORT = 19445
CGI_ROOT = f"/cgi-bin/qpkg/{NAME}"
PUBLIC_BASE = f"{CGI_ROOT}/gateway.cgi/control-plane"
WEBUI = PUBLIC_BASE + "/"
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


def load_operator(path):
    """Load only the credentials needed by the generated, private QPKG."""
    path = Path(path).expanduser().resolve()
    if not path.is_file() or path.is_symlink():
        raise GatewayError("Control Plane operator file is missing or unsafe")
    if stat.S_IMODE(path.stat().st_mode) & 0o077:
        raise GatewayError("Control Plane operator file permissions are too broad")
    try:
        document = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeDecodeError, json.JSONDecodeError) as error:
        raise GatewayError("Control Plane operator file is invalid") from error
    username = document.get("username")
    credential = document.get("password")
    totp_uri = document.get("totp_uri")
    if document.get("schema") != 1:
        raise GatewayError("Control Plane operator schema differs")
    if not isinstance(username, str) or not re.fullmatch(r"[A-Za-z0-9._-]{1,64}", username):
        raise GatewayError("Control Plane operator username is invalid")
    if (
        not isinstance(credential, str)
        or not re.fullmatch(r"[A-Za-z0-9._~!@#$%^&*+=:/?-]{14,128}", credential)
    ):
        raise GatewayError("Control Plane operator credential is invalid")
    if not isinstance(totp_uri, str):
        raise GatewayError("Control Plane operator TOTP URI is invalid")
    parsed = urlparse(totp_uri)
    parameters = parse_qs(parsed.query, strict_parsing=True)
    secrets = parameters.get("secret", [])
    if parsed.scheme != "otpauth" or parsed.netloc != "totp" or len(secrets) != 1:
        raise GatewayError("Control Plane operator TOTP URI is invalid")
    secret = secrets[0].strip().upper().rstrip("=")
    if not re.fullmatch(r"[A-Z2-7]{16,128}", secret):
        raise GatewayError("Control Plane operator TOTP secret is invalid")
    try:
        padding = "=" * ((8 - len(secret) % 8) % 8)
        decoded = base64.b32decode(secret + padding, casefold=False)
    except (binascii.Error, ValueError) as error:
        raise GatewayError("Control Plane operator TOTP secret is invalid") from error
    if len(decoded) < 10:
        raise GatewayError("Control Plane operator TOTP secret is too short")
    return {"username": username, "credential": credential, "totp_secret": secret}


def validate_source(repository):
    root = source_root(repository)
    config = (root / "qpkg.cfg").read_text(encoding="utf-8")
    expected = {
        "QPKG_NAME": NAME,
        "QPKG_VER": VERSION,
        "QPKG_WEBUI": WEBUI,
        "QPKG_WEB_PORT": "-2",
        "QPKG_WEB_SSL_PORT": "-1",
        "QPKG_USE_PROXY": "0",
        "QPKG_DESKTOP_APP": "0",
        "QPKG_VISIBLE": "0",
        "QPKG_FORCE_VISIBLE": "1",
    }
    for key, value in expected.items():
        if not re.search(rf'^{key}="{re.escape(value)}"$', config, re.MULTILINE):
            raise GatewayError(f"unsafe or missing QPKG field: {key}")
    if "QPKG_SERVICE_PROGRAM" in config or "QPKG_PROXY_PATH" in config:
        raise GatewayError("gateway must not register a service or QTS proxy")
    gateway = root / "shared/www/gateway.cgi"
    if not gateway.is_file() or gateway.is_symlink():
        raise GatewayError("gateway CGI is missing or unsafe")
    forbidden_assignment = re.compile(
        r"(?im)^\s*(password|secret|token|private_key)\s*="
    )
    for path in root.rglob("*"):
        if path.is_file() and forbidden_assignment.search(
            path.read_text(encoding="utf-8")
        ):
            raise GatewayError("gateway package must not contain secrets")
    return {
        "name": NAME,
        "version": VERSION,
        "backend_port": BACKEND_PORT,
        "public_base": PUBLIC_BASE,
    }


def _download(url, destination):
    with urlopen(url, timeout=30) as response, destination.open("wb") as handle:
        while chunk := response.read(1024 * 1024):
            handle.write(chunk)


def build(repository, output_directory, operator):
    validate_source(repository)
    operator = load_operator(operator)
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
        generated_source = temporary / "source"
        shutil.copytree(source_root(repository), generated_source)
        private = generated_source / "shared/private"
        private.mkdir(mode=0o700)
        for name, value in (
            ("operator-username", operator["username"]),
            ("operator-credential", operator["credential"]),
            ("totp-secret", operator["totp_secret"]),
        ):
            destination = private / name
            destination.write_text(value + "\n", encoding="utf-8")
            destination.chmod(0o600)
        subprocess.run(
            (
                str(qbuild),
                "--root",
                str(generated_source),
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


def install(session, repository, operator):
    validate_source(repository)
    with tempfile.TemporaryDirectory(prefix="mwodevelop-gateway-") as temporary:
        package = build(repository, temporary, operator)
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
            session.execute(
                "rm -f " + shlex.quote(str(REMOTE_PACKAGE)), allowed=(0, 1)
            )
    registered = session.execute(
        "/sbin/getcfg " + NAME + " Version -d missing -f /etc/config/qpkg.conf",
        allowed=(0, 1, 250),
    )
    if registered != VERSION:
        detail = (
            install_output.splitlines()[-1][:240]
            if install_output
            else "no diagnostic"
        )
        raise GatewayError("QPKG installation failed: " + detail)
    session.execute(
        "/sbin/setcfg " + NAME + " Enable TRUE -f /etc/config/qpkg.conf"
    )
    return verify(session)


def verify(session):
    fields = {}
    for field in (
        "Version",
        "Enable",
        "WebUI",
        "Web_Port",
        "Web_SSL_Port",
        "Use_Proxy",
        "Proxy_Path",
        "Service_Program",
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
        "WebUI": WEBUI,
        "Web_Port": "-2",
        "Web_SSL_Port": "-1",
        "Use_Proxy": "0",
        "Proxy_Path": "",
        "Service_Program": "missing",
        "Desktop": "0",
        "Visible": "0",
        "Force_Visible": "1",
    }
    for field, value in expected.items():
        if fields.get(field) != value:
            raise GatewayError(f"installed QPKG field differs: {field}")
    cgi_state = session.execute(
        "install_path=$(/sbin/getcfg "
        + NAME
        + " Install_Path -d missing -f /etc/config/qpkg.conf); "
        + "link=/home/httpd/cgi-bin/qpkg/"
        + NAME
        + "; test ! -L /etc/init.d/"
        + NAME
        + ".sh && test -L \"$link\" && test \"$(readlink \"$link\")\" = "
        + "\"$install_path/www\" && test -x \"$link/gateway.cgi\" && "
        + "install_path=$(/sbin/getcfg "
        + NAME
        + " Install_Path -d missing -f /etc/config/qpkg.conf); "
        + "private=\"$install_path/private\"; "
        + "for item in operator-username operator-credential totp-secret; do "
        + "test -f \"$private/$item\" && test ! -L \"$private/$item\" && "
        + "test \"$(stat -c '%a' \"$private/$item\")\" = 600 || exit 1; done; "
        + "printf cgi-ready",
        allowed=(0, 1),
    )
    if cgi_state != "cgi-ready":
        raise GatewayError("installed CGI link differs")
    fields["CGI"] = cgi_state
    return fields


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--repository", default=".")
    parser.add_argument("--references", default=".env")
    parser.add_argument(
        "--operator", default=".kodi-private/control-plane-operator.json"
    )
    subparsers = parser.add_subparsers(dest="command", required=True)
    build_parser = subparsers.add_parser("build")
    build_parser.add_argument("--output", required=True)
    subparsers.add_parser("deploy")
    subparsers.add_parser("status")
    args = parser.parse_args()
    if args.command == "build":
        print(build(args.repository, args.output, args.operator))
        return
    session = connect(args.repository, args.references)
    try:
        result = (
            install(session, args.repository, args.operator)
            if args.command == "deploy"
            else verify(session)
        )
        print(result)
    finally:
        session.close()


if __name__ == "__main__":
    main()
