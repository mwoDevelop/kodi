#!/usr/bin/env python3
"""Verify the public repository source through Kodi's own filesystem engine."""

import argparse
import json
import socket
import subprocess
from pathlib import Path


DEFAULT_URL = "https://mwodevelop.github.io/kodi/repo/"
DEFAULT_ZIP = "repository.mwodevelop-1.0.0.zip"


def adb(adb_path, serial, *args):
    return subprocess.check_output(
        [str(adb_path), "-s", serial, *args],
        text=True,
    ).strip()


def json_rpc(port, request_id, method, params=None):
    request = {"jsonrpc": "2.0", "id": request_id, "method": method}
    if params is not None:
        request["params"] = params

    with socket.create_connection(("127.0.0.1", port), timeout=10) as connection:
        connection.sendall(json.dumps(request).encode("utf-8") + b"\n")
        connection.settimeout(30)
        payload = connection.recv(256 * 1024)

    response = json.loads(payload)
    if "error" in response:
        raise RuntimeError("Kodi JSON-RPC error: %s" % response["error"])
    return response["result"]


def directory(port, request_id, path):
    result = json_rpc(
        port,
        request_id,
        "Files.GetDirectory",
        {
            "directory": path,
            "media": "files",
            "properties": ["file", "size"],
        },
    )
    return result.get("files", [])


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--adb", type=Path, default=Path("adb"))
    parser.add_argument("--serial", default="emulator-5554")
    parser.add_argument("--url", default=DEFAULT_URL)
    parser.add_argument("--repository-zip", default=DEFAULT_ZIP)
    args = parser.parse_args()

    local_port = int(
        adb(args.adb, args.serial, "forward", "tcp:0", "tcp:9090")
    )
    try:
        if json_rpc(local_port, 1, "JSONRPC.Ping") != "pong":
            raise AssertionError("Kodi JSON-RPC did not answer with pong")

        source_items = directory(local_port, 2, args.url)
        repository = next(
            (
                item
                for item in source_items
                if item.get("label") == args.repository_zip
            ),
            None,
        )
        if repository is None:
            raise AssertionError(
                "%s not listed by Kodi at %s" % (args.repository_zip, args.url)
            )

        archive_items = directory(local_port, 3, repository["file"])
        addon_root = next(
            (
                item
                for item in archive_items
                if item.get("label") == "repository.mwodevelop"
            ),
            None,
        )
        if addon_root is None:
            raise AssertionError("repository ZIP has no repository.mwodevelop root")

        addon_items = directory(local_port, 4, addon_root["file"])
        if not any(item.get("label") == "addon.xml" for item in addon_items):
            raise AssertionError("repository ZIP has no add-on manifest")

        print(
            json.dumps(
                {
                    "kodi_source": args.url,
                    "repository_zip": args.repository_zip,
                    "archive_root": "repository.mwodevelop",
                    "manifest": "addon.xml",
                    "status": "verified",
                },
                indent=2,
                sort_keys=True,
            )
        )
    finally:
        subprocess.run(
            [
                str(args.adb),
                "-s",
                args.serial,
                "forward",
                "--remove",
                "tcp:%d" % local_port,
            ],
            check=False,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
        )


if __name__ == "__main__":
    main()
