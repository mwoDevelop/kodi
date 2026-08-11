#!/usr/bin/env python3
"""One public entry point for Kodi release, rollout and restore."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from tools.kodi_operations.planner import release_plan, restore_plan, rollout_plan
from tools.kodi_operations.runner import OperationRunner, ProductionExecutor
from tools.kodi_operations.model import OperationPlan
from tools.kodi_operations.store import RunStore


def parser():
    result = argparse.ArgumentParser()
    result.add_argument("--adb", default="/home/mwo/android-sdk/platform-tools/adb")
    result.add_argument("--adb-server-port", type=int, default=5038)
    commands = result.add_subparsers(dest="operation", required=True)

    rollout = commands.add_parser("rollout")
    rollout.add_argument("--device", action="append", default=[])
    rollout.add_argument("--full-diagnostics", action="store_true")
    rollout.add_argument("--dry-run", action="store_true")
    rollout.add_argument("--resume")

    restore = commands.add_parser("restore")
    restore.add_argument("--device", required=True)
    restore.add_argument("--mode", choices=("repair", "reinstall"), required=True)
    restore.add_argument("--dry-run", action="store_true")
    restore.add_argument("--yes", action="store_true")
    restore.add_argument("--resume")

    release = commands.add_parser("release")
    release.add_argument("--dry-run", action="store_true")
    release.add_argument("--no-promote", action="store_true")
    release.add_argument("--no-rollout", action="store_true")
    release.add_argument("--resume")
    return result


def main(argv=None):
    args = parser().parse_args(argv)
    if args.resume:
        if args.operation == "rollout" and args.device:
            raise SystemExit("--resume cannot be combined with --device")
        if args.operation == "release" and (args.no_promote or args.no_rollout):
            raise SystemExit("--resume cannot change release options")
        plan = OperationPlan.from_document(
            RunStore(ROOT, args.resume).read("plan.json")
        )
        if plan.operation != args.operation:
            raise SystemExit("run operation differs from requested command")
        if args.operation == "restore" and (
            plan.devices != (args.device,) or plan.options.get("mode") != args.mode
        ):
            raise SystemExit("restore resume target or mode differs")
    elif args.operation == "rollout":
        plan = rollout_plan(
            ROOT,
            args.device,
            full_diagnostics=args.full_diagnostics,
        )
    elif args.operation == "restore":
        if not args.dry_run and not args.yes:
            raise SystemExit("restore requires --yes after reviewing --dry-run")
        plan = restore_plan(ROOT, args.device, args.mode)
    else:
        plan = release_plan(
            ROOT,
            no_promote=args.no_promote,
            no_rollout=args.no_rollout,
        )
    runner = OperationRunner(
        ROOT,
        ProductionExecutor(ROOT, args.adb, args.adb_server_port),
    )
    report, exit_code = runner.run(
        plan,
        dry_run=args.dry_run,
        run_id=args.resume,
        resume=bool(args.resume),
    )
    print(json.dumps(report, indent=2, sort_keys=True))
    return exit_code


if __name__ == "__main__":
    raise SystemExit(main())
