"""Strict manifest loading without adding a runtime JSON-schema dependency."""

import json
import re
from pathlib import Path, PurePosixPath


REPOSITORY = re.compile(r"^[A-Za-z0-9_.-]+/[A-Za-z0-9_.-]+$")
REF = re.compile(r"^[A-Za-z0-9._/-]+$")
ADAPTERS = {
    "git_patch_stack",
    "vendored_kodi_addon",
    "provider_feed",
    "kodi_repository",
}
POLICY_PROFILES = {"component_code", "provider_observation"}


def _safe_relative(value, field):
    path = PurePosixPath(value)
    if path.is_absolute() or ".." in path.parts or not value:
        raise ValueError("unsafe %s: %r" % (field, value))
    return value


def _git_endpoint(value, field):
    if not isinstance(value, dict) or set(value) != {"repository", "branch"}:
        raise ValueError("invalid %s endpoint" % field)
    if not REPOSITORY.fullmatch(value["repository"]):
        raise ValueError("invalid %s repository" % field)
    if not REF.fullmatch(value["branch"]) or ".." in value["branch"]:
        raise ValueError("invalid %s branch" % field)


def load_manifest(path):
    payload = json.loads(Path(path).read_text(encoding="utf-8"))
    if payload.get("schema") != 1:
        raise ValueError("unsupported upstream manifest schema")
    slots = payload.get("schedule_slots")
    components = payload.get("components")
    if not isinstance(slots, dict) or not slots:
        raise ValueError("schedule_slots must be a non-empty object")
    if not isinstance(components, dict) or not components:
        raise ValueError("components must be a non-empty object")
    for name, config in components.items():
        if not re.fullmatch(r"[a-z0-9_]+", name):
            raise ValueError("invalid component name: %r" % name)
        if config.get("adapter") not in ADAPTERS:
            raise ValueError("unknown adapter for %s" % name)
        if config.get("policy_profile") not in POLICY_PROFILES:
            raise ValueError("unknown policy profile for %s" % name)
        if config.get("schedule_slot") not in slots:
            raise ValueError("unknown schedule slot for %s" % name)
        if not isinstance(config.get("enabled"), bool):
            raise ValueError("enabled must be boolean for %s" % name)
        _safe_relative(config.get("local_path", ""), "%s.local_path" % name)
        _git_endpoint(config.get("target"), "%s.target" % name)
        if "upstream" in config:
            _git_endpoint(config["upstream"], "%s.upstream" % name)
        for field in ("state_path", "sources_path"):
            if field in config:
                _safe_relative(config[field], "%s.%s" % (name, field))
        protected = config.get("protected_paths", [])
        if not isinstance(protected, list) or len(protected) != len(set(protected)):
            raise ValueError("invalid protected_paths for %s" % name)
        for item in protected:
            _safe_relative(item, "%s.protected_paths" % name)
        if not config.get("version_policy"):
            raise ValueError("missing version policy for %s" % name)
    return payload


def load_release_groups(path):
    payload = json.loads(Path(path).read_text(encoding="utf-8"))
    if payload.get("schema") != 1 or not isinstance(payload.get("groups"), dict):
        raise ValueError("invalid release group manifest")
    for name, group in payload["groups"].items():
        if not REPOSITORY.fullmatch(group.get("repository", "")):
            raise ValueError("invalid release group repository: %s" % name)
        components = group.get("components")
        if not isinstance(components, list) or len(components) < 2:
            raise ValueError("release group requires at least two components")
        if len(components) != len(set(components)):
            raise ValueError("duplicate component in release group")
    return payload
