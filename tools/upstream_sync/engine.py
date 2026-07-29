"""OCP registry and orchestration for read-only discovery."""

import hashlib
import json
from pathlib import Path

from .config import load_manifest
from .models import decide_action


class AdapterRegistry:
    def __init__(self):
        self._factories = {}

    def register(self, name, factory):
        if name in self._factories:
            raise ValueError("adapter already registered: %s" % name)
        self._factories[name] = factory

    def create(self, name, context):
        try:
            factory = self._factories[name]
        except KeyError as error:
            raise ValueError("adapter is not implemented: %s" % name) from error
        return factory(context)


class Context:
    def __init__(self, root, name, config):
        self.root = Path(root).resolve()
        self.name = name
        self.config = config

    @property
    def checkout(self):
        path = (self.root / self.config["local_path"]).resolve()
        if self.root not in path.parents:
            raise ValueError("component checkout escapes root")
        return path

    @property
    def config_digest(self):
        payload = json.dumps(
            self.config, ensure_ascii=False, separators=(",", ":"), sort_keys=True
        ).encode("utf-8")
        return hashlib.sha256(payload).hexdigest()


def default_registry():
    from .adapters.git_patch_stack import GitPatchStackAdapter
    from .adapters.provider_feed import ProviderFeedAdapter
    from .adapters.vendored_kodi_addon import VendoredKodiAddonAdapter

    registry = AdapterRegistry()
    registry.register("git_patch_stack", GitPatchStackAdapter)
    registry.register("provider_feed", ProviderFeedAdapter)
    registry.register("vendored_kodi_addon", VendoredKodiAddonAdapter)
    return registry


def discover_all(root, manifest_path, registry=None, enabled_only=True):
    manifest = load_manifest(manifest_path)
    registry = registry or default_registry()
    results = []
    for name, config in sorted(manifest["components"].items()):
        if enabled_only and not config["enabled"]:
            continue
        context = Context(root, name, config)
        discovery = registry.create(config["adapter"], context).discover()
        policy_profile = config["policy_profile"]
        source_actions = [
            {
                **source.to_dict(),
                "action": decide_action(source, policy_profile).value,
            }
            for source in discovery.sources
        ]
        if source_actions:
            precedence = {
                "stop": 6,
                "quarantine": 5,
                "open_or_update_issue": 4,
                "provenance_only_candidate": 3,
                "component_candidate": 2,
                "testing_lock_candidate": 1,
                "noop": 0,
            }
            action = max(source_actions, key=lambda item: precedence[item["action"]])[
                "action"
            ]
        else:
            action = decide_action(discovery, policy_profile).value
        results.append(
            {
                **discovery.to_dict(),
                "action": action,
                "action_owner": (
                    "component"
                    if action
                    in ("component_candidate", "provenance_only_candidate")
                    else "control_plane"
                    if action == "testing_lock_candidate"
                    else "human"
                    if action in ("open_or_update_issue", "quarantine", "stop")
                    else "none"
                ),
                "source_actions": source_actions,
                "config_sha256": context.config_digest,
            }
        )
    return {"schema": 1, "sources": results}


def render_markdown(report):
    lines = [
        "# Upstream discovery",
        "",
        "| Component | Accepted | Observed | Content | Provenance | "
        "Availability | History | Action |",
        "|---|---|---|---|---|---|---|---|",
    ]
    for item in report["sources"]:
        accepted = item["accepted"].get("commit") or item["accepted"].get("version") or "-"
        observed = item["observed"].get("commit") or item["observed"].get("version") or "-"
        lines.append(
            "| %s | `%s` | `%s` | %s | %s | %s | %s | %s |"
            % (
                item["component"],
                accepted[:12],
                observed[:12],
                item["content"],
                item["provenance"],
                item["availability"],
                item["history"],
                item["action"],
            )
        )
    lines.extend(
        [
            "",
            "No candidate code was executed and no remote state was changed.",
            "",
        ]
    )
    return "\n".join(lines)
