#!/usr/bin/env python3
"""Create the ignored portable OAuth session used by the YouTube adapter."""

from __future__ import annotations

import argparse
import base64
import json
import os
import time
import urllib.error
import urllib.parse
import urllib.request
from pathlib import Path

try:
    from kodi_inventory import load_private_references
    from kodi_youtube_configure import (
        ADAPTER,
        DEFAULT_SESSION_FILE,
        EXPECTED_ADDON_VERSION,
        configuration,
    )
except ModuleNotFoundError:
    from tools.kodi_inventory import load_private_references
    from tools.kodi_youtube_configure import (
        ADAPTER,
        DEFAULT_SESSION_FILE,
        EXPECTED_ADDON_VERSION,
        configuration,
    )


DEVICE_CODE_URL = "https://accounts.google.com/o/oauth2/device/code"
TOKEN_URL = "https://www.googleapis.com/oauth2/v4/token"
SCOPE = "https://www.googleapis.com/auth/youtube"
TV_CLIENT_ID = base64.b64decode(
    b"ODYxNTU2NzA4NDU0LWQ2ZGxtM2xoMDVpZGQ4bnBlazE4azZiZThiYTNvYzY4"
).decode("ascii")
TV_CLIENT_SECRET = base64.b64decode(
    b"U2JvVmhvRzlzMHJOYWZpeENTR0dLWEFU"
).decode("ascii")
VR_CLIENT_ID = base64.b64decode(
    b"NjUyNDY5MzEyMTY5LTRsdnM5Ym5ocjlscG5zOXY0NTFqNW9pdmQ4MXZqdnUx"
).decode("ascii")
VR_CLIENT_SECRET = base64.b64decode(
    b"M2ZUV3JCSkk1VW9qbTFUSzdfaUpDVzVa"
).decode("ascii")


def _client_id(value):
    suffix = ".apps.googleusercontent.com"
    return value if value.endswith(suffix) else value + suffix


def _post(values, url):
    encoded = urllib.parse.urlencode(values).encode("ascii")
    try:
        with urllib.request.urlopen(
            urllib.request.Request(
                url,
                data=encoded,
                headers={"Content-Type": "application/x-www-form-urlencoded"},
            ),
            timeout=30,
        ) as response:
            return response.status, json.load(response)
    except urllib.error.HTTPError as error:
        try:
            document = json.load(error)
        except (TypeError, ValueError):
            document = {}
        return error.code, document


def authorize_client(label, client_id, client_secret):
    client_id = _client_id(client_id)
    status, device = _post(
        {"client_id": client_id, "scope": SCOPE}, DEVICE_CODE_URL
    )
    if status != 200 or not device.get("device_code") or not device.get("user_code"):
        raise RuntimeError("YouTubeDeviceCodeRequestFailed")
    print(
        "{}: otwórz {} i wpisz kod {}".format(
            label,
            device.get("verification_url", "https://www.google.com/device"),
            device["user_code"],
        ),
        flush=True,
    )
    interval = max(3, min(60, int(device.get("interval", 5))))
    deadline = time.monotonic() + int(device.get("expires_in", 1800))
    while time.monotonic() < deadline:
        status, token = _post(
            {
                "client_id": client_id,
                "client_secret": client_secret,
                "code": device["device_code"],
                "grant_type": "http://oauth.net/grant_type/device/1.0",
            },
            TOKEN_URL,
        )
        if status == 200 and token.get("access_token") and token.get("refresh_token"):
            return token
        reason = token.get("error")
        if reason == "slow_down":
            interval = min(60, interval + 5)
        elif reason != "authorization_pending":
            raise RuntimeError("YouTubeDeviceAuthorizationFailed")
        time.sleep(interval)
    raise RuntimeError("YouTubeDeviceAuthorizationExpired")


def expected_channel(api_key, access_token):
    query = urllib.parse.urlencode(
        {"part": "id", "mine": "true", "key": api_key}
    )
    request = urllib.request.Request(
        "https://www.googleapis.com/youtube/v3/channels?" + query,
        headers={
            "Accept": "application/json",
            "Authorization": "Bearer " + access_token,
        },
    )
    try:
        with urllib.request.urlopen(request, timeout=30) as response:
            channels = json.load(response).get("items") or []
    except (OSError, ValueError, urllib.error.HTTPError) as error:
        raise RuntimeError("YouTubeAccountProbeFailed") from error
    if len(channels) != 1 or not str(channels[0].get("id", "")).startswith("UC"):
        raise RuntimeError("YouTubeAccountProbeFailed")
    return channels[0]["id"]


def write_session(path, document):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
    path.parent.chmod(0o700)
    if path.exists() and (not path.is_file() or path.is_symlink()):
        raise ValueError("unsafe YouTube session destination")
    temporary = path.with_name(path.name + ".tmp")
    descriptor = os.open(
        temporary,
        os.O_WRONLY | os.O_CREAT | os.O_EXCL,
        0o600,
    )
    try:
        with os.fdopen(descriptor, "w", encoding="utf-8") as destination:
            json.dump(document, destination, sort_keys=True, separators=(",", ":"))
            destination.write("\n")
            destination.flush()
            os.fsync(destination.fileno())
        os.replace(temporary, path)
    finally:
        if temporary.exists():
            temporary.unlink()


def main():
    root = Path(__file__).resolve().parents[1]
    parser = argparse.ArgumentParser()
    parser.add_argument("--references", default=".env")
    parser.add_argument("--session", default=DEFAULT_SESSION_FILE)
    args = parser.parse_args()
    references_path = Path(args.references)
    if not references_path.is_absolute():
        references_path = root / references_path
    references = load_private_references(references_path)
    profile = {
        "adapter": ADAPTER,
        "api_key_ref": "YOUTUBE_API_KEY",
        "client_id_ref": "YOUTUBE_CLIENT_ID",
        "client_secret_ref": "YOUTUBE_CLIENT_SECRET",
        "account_hint_ref": "YOUTUBE_USER",
    }
    api_key, client_id, client_secret, account_hint, _old = configuration(
        root, profile, references
    )
    if not api_key or not account_hint:
        raise RuntimeError("YouTubeApiConfigurationRequired")
    clients = (
        ("YouTube TV", TV_CLIENT_ID, TV_CLIENT_SECRET),
        ("konto użytkownika", client_id, client_secret),
        ("YouTube VR", VR_CLIENT_ID, VR_CLIENT_SECRET),
    )
    tokens = [authorize_client(*client) for client in clients]
    channel_id = expected_channel(api_key, tokens[1]["access_token"])
    session_path = Path(args.session)
    if not session_path.is_absolute():
        session_path = root / session_path
    private_root = (root / ".kodi-private").resolve()
    session_path = session_path.resolve()
    if private_root not in session_path.parents:
        raise ValueError("YouTube session must remain below .kodi-private")
    write_session(
        session_path,
        {
            "schema": 1,
            "addon_id": "plugin.video.youtube",
            "addon_version": EXPECTED_ADDON_VERSION,
            "account_hint": account_hint,
            "expected_channel_id": channel_id,
            "api_key": api_key,
            "client_id": client_id,
            "client_secret": client_secret,
            "tv_refresh_token": tokens[0]["refresh_token"],
            "personal_refresh_token": tokens[1]["refresh_token"],
            "vr_refresh_token": tokens[2]["refresh_token"],
        },
    )
    print(
        json.dumps(
            {
                "ok": True,
                "account_verified": True,
                "refresh_tokens": 3,
                "session_file": str(session_path.relative_to(root)),
            },
            indent=2,
            sort_keys=True,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
