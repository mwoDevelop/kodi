#!/usr/bin/env python3
"""Single operator entry point for project-owned offline legacy migrations."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path


REPOSITORY_ROOT = Path(__file__).resolve().parents[1]
if str(REPOSITORY_ROOT) not in sys.path:
    sys.path.insert(0, str(REPOSITORY_ROOT))


def main():
    repository = Path(__file__).resolve().parents[1]
    parser = argparse.ArgumentParser()
    subparsers = parser.add_subparsers(dest="command", required=True)
    config = subparsers.add_parser("config")
    config.add_argument("--config", default=str(repository / ".kodi-private/kodi-reinstall.json"))
    config.add_argument("--devices", default=str(repository / ".kodi-private/devices.json"))
    config.add_argument("--publisher", action="append", default=[])
    config.add_argument("--platform", action="append", default=[])
    config.add_argument("--apply", action="store_true")
    policy = subparsers.add_parser("policy")
    policy.add_argument("path")
    policy.add_argument("--apply", action="store_true")
    snapshot = subparsers.add_parser("snapshot")
    snapshot.add_argument("source")
    snapshot.add_argument("output")
    snapshot.add_argument("--apply", action="store_true")
    snapshot.add_argument(
        "--current-addon",
        default=str(repository / "watchnixtoons2/mwodevelop/plugin.video.watchnixtoons2.mwodevelop"),
    )
    args = parser.parse_args()
    if args.command == "config":
        from tools.migrations.legacy_config import _platforms, migrate_config_pair

        devices, migrated, changed = migrate_config_pair(
            args.config,
            args.devices,
            repository,
            publishers=args.publisher,
            platforms=_platforms(args.platform),
            apply=args.apply,
        )
        result = {"changed": changed, "applied": bool(changed and args.apply), "schema": migrated["schema"], "devices": sorted(devices["devices"])}
    elif args.command == "policy":
        from tools.migrations.legacy_policy import migrate_policy

        migrated, changed = migrate_policy(args.path, apply=args.apply)
        result = {"changed": changed, "applied": bool(changed and args.apply), "schema": migrated["schema"]}
    else:
        from tools.kodi_profile import snapshot_restore_status

        if not args.apply:
            result = {"changed": snapshot_restore_status(args.source) != "CURRENT", "applied": False, "status": snapshot_restore_status(args.source)}
        else:
            from tools.migrations.watchnixtoons2_snapshot import migrate_snapshot

            migrated, evidence = migrate_snapshot(args.source, args.output, args.current_addon)
            result = {"changed": True, "applied": True, "snapshot_id": migrated["snapshot_id"], "migrated_from": evidence["migrated_from"]}
    print(json.dumps(result, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
