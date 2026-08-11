#!/usr/bin/env python3
"""Resolve exact stable inputs and invoke the qualified Flatpak adapter."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from types import SimpleNamespace

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from tools.kodi_flatpak_profile_sync_rollout import rollout
from tools.kodi_stable_artifacts import prepare


def stable_rollout(device):
    prepared = prepare(ROOT)
    profile = prepared["addons"]["service.mwodevelop.profilesync"]
    repository = prepared["repository"]
    args = SimpleNamespace(
        device=device,
        revision_id=None,
        server_url=None,
        references=".env",
        devices=".kodi-private/devices.json",
        private_root=".kodi-private/flatpak-profile-sync",
        profile_sync_zip=str(profile["path"]),
        profile_sync_sha256=profile["sha256"],
        repository_zip=str(repository["path"]),
        repository_sha256=repository["sha256"],
        required_addons=None,
        ca_certificate=".kodi-private/profile-sync-production/tls/ca.crt",
        signing_seeds=".kodi-private/profile-sync-production/signing-seeds.json",
        key_registry=".kodi-private/profile-sync-production/key-registry.json",
        timeout=300,
        result=None,
    )
    return rollout(args)


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--device", required=True)
    args = parser.parse_args()
    print(json.dumps(stable_rollout(args.device), indent=2, sort_keys=True))


if __name__ == "__main__":
    main()
