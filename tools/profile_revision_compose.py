#!/usr/bin/env python3
"""Compose partial profile exports without dropping active components."""

from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path

from tools.kodi_routine_profile import canonical_json, write_manifest


def _unsigned(document):
    if not isinstance(document, dict) or document.get("schema") not in {2, 3}:
        raise ValueError("unsupported revision")
    return {
        key: value
        for key, value in document.items()
        if key not in {"revision_id", "created_utc", "signature"}
    }


def _adapters(document):
    return document["adapters"] if document["schema"] == 2 else document["base"]["adapters"]


def compose(active, update, portable_favourites=None):
    active = _unsigned(active)
    update = _unsigned(update)
    if active["schema"] != update["schema"]:
        raise ValueError("revision schemas differ")
    schema = update["schema"]
    result = dict(update)
    merged = dict(_adapters(active))
    merged.update(_adapters(update))
    if portable_favourites is not None:
        if not isinstance(portable_favourites, dict):
            raise ValueError("portable favourites adapter is invalid")
        merged["kodi.favourites"] = portable_favourites
    if schema == 2:
        result["adapters"] = merged
    else:
        active_layers = {layer["id"]: layer for layer in active["layers"]}
        update_layers = {layer["id"]: layer for layer in update["layers"]}
        active_layers.update(update_layers)
        result["base"] = {"adapters": merged}
        result["layers"] = sorted(
            active_layers.values(),
            key=lambda layer: (
                "logical_device_id" in layer["selector"],
                layer["id"],
            ),
        )
    capabilities = set(active.get("required_capabilities", []))
    capabilities.update(update.get("required_capabilities", []))
    if "kodi.favourites" in merged:
        capabilities.add("portable_favourites_v1")
    if capabilities:
        result["required_capabilities"] = sorted(capabilities)
    minimums = [
        value
        for value in (
            active.get("minimum_client_version"),
            update.get("minimum_client_version"),
            "1.0.0" if "kodi.favourites" in merged else None,
        )
        if value is not None
    ]
    if minimums:
        result["minimum_client_version"] = max(
            minimums, key=lambda value: tuple(int(part) for part in value.split("."))
        )
    revision_id = "sha256:" + hashlib.sha256(canonical_json(result)).hexdigest()
    return {**result, "revision_id": revision_id}


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--active", required=True)
    parser.add_argument("--update", required=True)
    parser.add_argument("--portable-favourites")
    parser.add_argument("--output", required=True)
    args = parser.parse_args()
    active = json.loads(Path(args.active).read_text(encoding="utf-8"))
    update = json.loads(Path(args.update).read_text(encoding="utf-8"))
    favourites = (
        json.loads(Path(args.portable_favourites).read_text(encoding="utf-8"))
        if args.portable_favourites
        else None
    )
    result = compose(active, update, favourites)
    write_manifest(args.output, result)
    print(json.dumps({"revision_id": result["revision_id"]}, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
