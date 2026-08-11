"""Versioned policy and private inventory loading for Kodi operations."""

from __future__ import annotations

import json
from pathlib import Path

from tools.kodi_sync_inventory import load_sync_inventory


class ManifestError(ValueError):
    pass


def load_policy(repository: Path, path: str = "manifests/kodi-operations.json"):
    document = json.loads((repository / path).read_text(encoding="utf-8"))
    if set(document) != {
        "schema",
        "canaries",
        "device_order",
        "diagnostics",
        "run_retention_days",
    }:
        raise ManifestError("Kodi operations policy has unsupported fields")
    if document["schema"] != 1:
        raise ManifestError("unsupported Kodi operations policy schema")
    order = document["device_order"]
    canaries = document["canaries"]
    if (
        not isinstance(order, list)
        or not order
        or len(order) != len(set(order))
        or any(not isinstance(item, str) or not item for item in order)
    ):
        raise ManifestError("invalid device order")
    if (
        not isinstance(canaries, list)
        or not canaries
        or len(canaries) != len(set(canaries))
        or not set(canaries).issubset(order)
    ):
        raise ManifestError("invalid canary list")
    diagnostics = document["diagnostics"]
    if set(diagnostics) != {"external_attempts", "retry_seconds"}:
        raise ManifestError("invalid diagnostics policy")
    if not 1 <= diagnostics["external_attempts"] <= 10:
        raise ManifestError("external_attempts is outside supported bounds")
    if not 0 <= diagnostics["retry_seconds"] <= 60:
        raise ManifestError("retry_seconds is outside supported bounds")
    if not 1 <= document["run_retention_days"] <= 365:
        raise ManifestError("run retention is outside supported bounds")
    return document


def load_fleet(
    repository: Path,
    devices_file: str = ".kodi-private/devices.json",
    references_file: str = ".env",
):
    return load_sync_inventory(
        repository,
        devices_file=devices_file,
        references_file=references_file,
    )
