"""Read-only discovery for external provider repository artifacts."""

import hashlib
import json
from pathlib import Path
from xml.etree import ElementTree

from ..candidate_bundle import canonical_json
from ..models import (
    AvailabilityState,
    ContentState,
    Discovery,
    HistoryState,
    Identity,
    ProvenanceState,
)
from .common import (
    SourceUnavailable,
    TransientSourceError,
    github_commit,
    raw_url,
    read_url,
)
from .vendored_kodi_addon import _inspect_zip


class ProviderFeedAdapter:
    version = 1

    def __init__(self, context):
        self.context = context

    def discover(self):
        sources = _load(
            self.context.checkout / self.context.config["sources_path"], "sources"
        )
        accepted = _load(
            self.context.checkout / self.context.config["state_path"], "sources"
        )
        observed = {}
        messages = []
        availability = AvailabilityState.HEALTHY
        content = ContentState.UNCHANGED
        provenance = ProvenanceState.UNCHANGED
        for name, source in sorted(sources.items()):
            current = accepted.get(name)
            if not current:
                content = ContentState.UNKNOWN
                provenance = ProvenanceState.UNKNOWN
                messages.append("%s: no reviewed observation" % name)
                continue
            try:
                item = _discover_source(source)
                observed[name] = item
                if (
                    item["version"] != current["version"]
                    or item["sha256"] != current["sha256"]
                ):
                    content = ContentState.CHANGED
                if (
                    item["commit"] != current["commit"]
                    or item["url"] != current["url"]
                ):
                    provenance = ProvenanceState.CHANGED
                    try:
                        read_url(current["url"])
                    except SourceUnavailable:
                        availability = AvailabilityState.DEGRADED
                        messages.append("%s: reviewed URL is unavailable" % name)
                    except TransientSourceError:
                        availability = AvailabilityState.TRANSIENT_ERROR
                        messages.append(
                            "%s: reviewed URL failed transiently" % name
                        )
            except SourceUnavailable as error:
                availability = AvailabilityState.UNAVAILABLE
                content = ContentState.UNKNOWN
                messages.append("%s: %s" % (name, error))
            except TransientSourceError as error:
                if availability != AvailabilityState.UNAVAILABLE:
                    availability = AvailabilityState.TRANSIENT_ERROR
                content = ContentState.UNKNOWN
                messages.append("%s: %s" % (name, error))
        accepted_digest = _digest_sources(accepted)
        observed_digest = _digest_sources(observed) if observed else None
        return Discovery(
            component=self.context.name,
            accepted=Identity(sha256=accepted_digest),
            observed=Identity(sha256=observed_digest),
            content=content,
            provenance=provenance,
            availability=availability,
            history=HistoryState.NOT_APPLICABLE,
            changed_paths=None,
            messages=tuple(messages),
        )


def _load(path, field):
    payload = json.loads(Path(path).read_text(encoding="utf-8"))
    if payload.get("schema") != 1 or not isinstance(payload.get(field), dict):
        raise ValueError("invalid provider %s document" % field)
    return payload[field]


def _discover_source(source):
    commit = github_commit(source["repository"], source["ref"])
    feed_url = raw_url(source["repository"], commit, source["feed_path"])
    version = _addon_version(read_url(feed_url), source["addon_id"])
    artifact_path = source["artifact_path"].format(version=version)
    url = raw_url(source["repository"], commit, artifact_path)
    payload = read_url(url)
    _inspect_zip(payload)
    return {
        "repository": source["repository"],
        "ref": source["ref"],
        "commit": commit,
        "version": version,
        "url": url,
        "sha256": hashlib.sha256(payload).hexdigest(),
    }


def _addon_version(payload, addon_id):
    root = ElementTree.fromstring(payload)
    for addon in root.findall("addon"):
        if addon.get("id") == addon_id and addon.get("version"):
            return addon.get("version")
    raise ValueError("add-on was not found in provider feed: %s" % addon_id)


def _digest_sources(sources):
    return hashlib.sha256(canonical_json(sources)).hexdigest()
