#!/usr/bin/env python3
"""Export a default-deny semantic Kodi routine profile."""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import tempfile
import xml.etree.ElementTree as ET
from pathlib import Path, PurePosixPath


POLICY_SCHEMA = 2
REVISION_SCHEMAS = {2, 3}
SAFE_ADAPTER_ID = re.compile(r"^[A-Za-z0-9._-]+$")
SAFE_SETTING_ID = SAFE_ADAPTER_ID
SAFE_TARGET_TAG = re.compile(r"^[a-z0-9][a-z0-9._:-]{0,63}$")
SAFE_LOGICAL_DEVICE = re.compile(r"^[a-z0-9][a-z0-9._-]{0,63}$")
CLASSES = {"portable", "device_overlay", "secret", "device_local", "excluded"}
APPLY_MODES = {"hot_apply", "next_start", "host_only"}
TYPES = {"boolean", "integer", "string"}


def canonical_json(value):
    return json.dumps(
        value, sort_keys=True, separators=(",", ":"), ensure_ascii=False
    ).encode("utf-8")


def digest(payload):
    return hashlib.sha256(payload).hexdigest()


def load_routine_policy(path):
    document = json.loads(Path(path).read_text(encoding="utf-8"))
    if document.get("schema") != POLICY_SCHEMA:
        raise ValueError("routine export requires profile policy schema 2")
    scopes = document.get("scopes")
    routine = scopes.get("routine") if isinstance(scopes, dict) else None
    if not isinstance(routine, dict) or routine.get("default") != "excluded":
        raise ValueError("routine policy must be default-deny")
    if routine.get("default_profile_only") is not True:
        raise ValueError("MVP routine policy must require the default profile")
    adapters = routine.get("adapters")
    if not isinstance(adapters, list):
        raise ValueError("routine policy adapters must be a list")
    seen = set()
    layer_selectors = {}
    for adapter in adapters:
        if not isinstance(adapter, dict):
            raise ValueError("routine adapter must be an object")
        adapter_id = adapter.get("id")
        if (
            not isinstance(adapter_id, str)
            or not SAFE_ADAPTER_ID.fullmatch(adapter_id)
            or adapter_id in seen
        ):
            raise ValueError("routine adapter has invalid or duplicate id")
        seen.add(adapter_id)
        if adapter.get("adapter") != "settings_xml":
            raise ValueError("%s uses an unsupported adapter" % adapter_id)
        relative = PurePosixPath(str(adapter.get("path", "")))
        if (
            not relative.parts
            or relative.is_absolute()
            or ".." in relative.parts
        ):
            raise ValueError("%s uses an unsafe path" % adapter_id)
        if adapter.get("apply_mode") not in APPLY_MODES:
            raise ValueError("%s has invalid apply mode" % adapter_id)
        settings = adapter.get("settings")
        if not isinstance(settings, dict) or not settings:
            raise ValueError("%s has no managed settings" % adapter_id)
        for setting_id, rule in settings.items():
            expected_keys = {"type", "class"}
            if isinstance(rule, dict) and rule.get("class") == "device_overlay":
                expected_keys.add("layer")
            if (
                not isinstance(setting_id, str)
                or not SAFE_SETTING_ID.fullmatch(setting_id)
                or not isinstance(rule, dict)
                or set(rule) != expected_keys
                or rule["type"] not in TYPES
                or rule["class"] not in CLASSES
            ):
                raise ValueError("%s has an invalid setting rule" % adapter_id)
            if rule["class"] == "device_overlay":
                layer = rule["layer"]
                if not isinstance(layer, dict) or set(layer) != {
                    "id",
                    "selector",
                }:
                    raise ValueError("%s has an invalid profile layer" % adapter_id)
                layer_id = layer["id"]
                selector = layer["selector"]
                if (
                    not isinstance(layer_id, str)
                    or not SAFE_ADAPTER_ID.fullmatch(layer_id)
                ):
                    raise ValueError("%s has an invalid profile layer" % adapter_id)
                _validate_layer_selector(selector, adapter_id)
                previous = layer_selectors.setdefault(layer_id, selector)
                if previous != selector:
                    raise ValueError(
                        "%s redefines a profile layer selector" % adapter_id
                    )
    return document, routine


def _validate_layer_selector(selector, adapter_id):
    if (
        not isinstance(selector, dict)
        or not selector
        or not set(selector).issubset(
            {"all_target_tags", "logical_device_id"}
        )
    ):
        raise ValueError("%s has an invalid profile layer selector" % adapter_id)
    tags = selector.get("all_target_tags", [])
    if (
        not isinstance(tags, list)
        or ("all_target_tags" in selector and not tags)
        or len(tags) > 16
        or len(tags) != len(set(tags))
        or tags != sorted(tags)
        or any(
            not isinstance(tag, str) or not SAFE_TARGET_TAG.fullmatch(tag)
            for tag in tags
        )
    ):
        raise ValueError("%s has invalid profile layer tags" % adapter_id)
    logical_id = selector.get("logical_device_id")
    if logical_id is not None and (
        not isinstance(logical_id, str)
        or not SAFE_LOGICAL_DEVICE.fullmatch(logical_id)
    ):
        raise ValueError(
            "%s has an invalid layer logical device id" % adapter_id
        )


def _settings_values(path):
    root = ET.parse(path).getroot()
    result = {}
    for setting in root.findall(".//setting"):
        setting_id = setting.attrib.get("id")
        if not setting_id:
            continue
        value = setting.attrib.get("value")
        if value is None:
            value = setting.text or ""
        result[setting_id] = value
    return result


def _typed_value(value, expected_type, setting_id):
    if expected_type == "string":
        return value
    if expected_type == "boolean":
        normalized = value.strip().lower()
        if normalized not in {"true", "false"}:
            raise ValueError("%s is not a boolean" % setting_id)
        return normalized == "true"
    if not re.fullmatch(r"-?\d+", value.strip()):
        raise ValueError("%s is not an integer" % setting_id)
    return int(value)


def _adapter_document(adapter, values):
    item = {
        "adapter": adapter["adapter"],
        "apply_mode": adapter["apply_mode"],
        "managed_settings": sorted(adapter["settings"]),
        "values": values,
    }
    for optional in ("addon_id", "compatible_versions"):
        if optional in adapter:
            item[optional] = adapter[optional]
    return item


def export_routine_profile(
    profile_root, policy_path, kodi_major, revision_schema=2
):
    profile_root = Path(profile_root).resolve()
    if not profile_root.is_dir():
        raise ValueError("Kodi profile root does not exist")
    if not isinstance(kodi_major, int) or kodi_major < 19:
        raise ValueError("invalid Kodi major")
    if revision_schema not in REVISION_SCHEMAS:
        raise ValueError("unsupported profile revision schema")
    policy, routine = load_routine_policy(policy_path)
    portable = {}
    layers = {}
    for adapter in routine["adapters"]:
        for rule in adapter["settings"].values():
            if rule["class"] != "device_overlay":
                continue
            layer = rule["layer"]
            layers.setdefault(
                layer["id"],
                {
                    "id": layer["id"],
                    "selector": layer["selector"],
                    "adapters": {},
                },
            )
    for adapter in routine["adapters"]:
        adapter_id = adapter["id"]
        relative = PurePosixPath(adapter["path"])
        source = profile_root.joinpath(*relative.parts)
        if source.is_symlink():
            raise ValueError("%s source cannot be a symlink" % adapter_id)
        if not source.is_file():
            continue
        values = _settings_values(source)
        portable_values = {}
        overlay_values = {}
        for setting_id, rule in sorted(adapter["settings"].items()):
            if setting_id not in values:
                continue
            if rule["class"] == "portable":
                target = portable_values
            elif rule["class"] == "device_overlay":
                target = overlay_values.setdefault(rule["layer"]["id"], {})
            else:
                continue
            target[setting_id] = _typed_value(
                values[setting_id], rule["type"], setting_id
            )
        portable[adapter_id] = _adapter_document(
            adapter, portable_values
        )
        for layer_id, layer_values in overlay_values.items():
            layers[layer_id]["adapters"][adapter_id] = _adapter_document(
                adapter, layer_values
            )
    common = {
        "schema": revision_schema,
        "policy_sha256": digest(canonical_json(policy)),
        "kodi_major": kodi_major,
    }
    if revision_schema == 2:
        identity = {**common, "adapters": portable}
    else:
        ordered_layers = sorted(
            layers.values(),
            key=lambda layer: (
                "logical_device_id" in layer["selector"],
                layer["id"],
            ),
        )
        identity = {
            **common,
            "base": {"adapters": portable},
            "layers": ordered_layers,
        }
    return {
        **identity,
        "revision_id": "sha256:" + digest(canonical_json(identity)),
    }


def write_manifest(path, manifest):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    payload = json.dumps(manifest, indent=2, sort_keys=True) + "\n"
    descriptor, temporary = tempfile.mkstemp(
        prefix=".%s." % path.name, dir=str(path.parent), text=True
    )
    try:
        with os.fdopen(descriptor, "w", encoding="utf-8") as handle:
            handle.write(payload)
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(temporary, path)
    finally:
        if os.path.exists(temporary):
            os.unlink(temporary)


def main():
    repository = Path(__file__).resolve().parents[1]
    parser = argparse.ArgumentParser()
    parser.add_argument("profile_root")
    parser.add_argument("output")
    parser.add_argument("--kodi-major", required=True, type=int)
    parser.add_argument(
        "--revision-schema",
        type=int,
        choices=sorted(REVISION_SCHEMAS),
        default=2,
    )
    parser.add_argument(
        "--policy",
        default=str(repository / "manifests/kodi-profile-policy.json"),
    )
    args = parser.parse_args()
    manifest = export_routine_profile(
        args.profile_root,
        args.policy,
        args.kodi_major,
        revision_schema=args.revision_schema,
    )
    adapters = (
        manifest["adapters"]
        if manifest["schema"] == 2
        else manifest["base"]["adapters"]
    )
    write_manifest(args.output, manifest)
    print(
        json.dumps(
            {
                "revision_id": manifest["revision_id"],
                "adapters": sorted(adapters),
            },
            indent=2,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
