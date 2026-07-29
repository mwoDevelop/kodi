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
        results = []
        for name, source in sorted(sources.items()):
            current = accepted.get(name)
            if not current:
                results.append(
                    Discovery(
                        component=name,
                        content=ContentState.UNKNOWN,
                        provenance=ProvenanceState.UNKNOWN,
                        availability=AvailabilityState.DEGRADED,
                        observed_availability=AvailabilityState.DEGRADED,
                        history=HistoryState.NOT_APPLICABLE,
                        messages=("no reviewed observation",),
                    )
                )
                continue
            result, item = _discover_one(name, source, current)
            results.append(result)
            if item:
                observed[name] = item
        accepted_digest = _digest_sources(accepted)
        observed_digest = _digest_sources(observed) if observed else None
        content = _rollup(
            [item.content for item in results],
            (ContentState.CHANGED, ContentState.UNKNOWN, ContentState.UNCHANGED),
        )
        provenance = _rollup(
            [item.provenance for item in results],
            (
                ProvenanceState.CHANGED,
                ProvenanceState.UNKNOWN,
                ProvenanceState.UNCHANGED,
            ),
        )
        availability = _rollup(
            [item.availability for item in results],
            (
                AvailabilityState.UNAVAILABLE,
                AvailabilityState.TRANSIENT_ERROR,
                AvailabilityState.DEGRADED,
                AvailabilityState.HEALTHY,
            ),
        )
        return Discovery(
            component=self.context.name,
            accepted=Identity(sha256=accepted_digest),
            observed=Identity(sha256=observed_digest),
            content=content,
            provenance=provenance,
            availability=availability,
            history=HistoryState.NOT_APPLICABLE,
            changed_paths=None,
            messages=tuple(
                "%s: %s" % (item.component, message)
                for item in results
                for message in item.messages
            ),
            sources=tuple(results),
        )


def _discover_one(name, source, current):
    accepted = Identity(
        version=current["version"],
        commit=current["commit"],
        url=current["url"],
        sha256=current["sha256"],
    )
    try:
        item = _discover_source(source)
    except SourceUnavailable as error:
        return (
            Discovery(
                component=name,
                accepted=accepted,
                content=ContentState.UNKNOWN,
                provenance=ProvenanceState.UNKNOWN,
                availability=AvailabilityState.UNAVAILABLE,
                accepted_availability=None,
                observed_availability=AvailabilityState.UNAVAILABLE,
                history=HistoryState.NOT_APPLICABLE,
                messages=(str(error),),
            ),
            None,
        )
    except TransientSourceError as error:
        return (
            Discovery(
                component=name,
                accepted=accepted,
                content=ContentState.UNKNOWN,
                provenance=ProvenanceState.UNKNOWN,
                availability=AvailabilityState.TRANSIENT_ERROR,
                observed_availability=AvailabilityState.TRANSIENT_ERROR,
                history=HistoryState.NOT_APPLICABLE,
                messages=(str(error),),
            ),
            None,
        )
    content = (
        ContentState.CHANGED
        if item["version"] != current["version"]
        or item["sha256"] != current["sha256"]
        else ContentState.UNCHANGED
    )
    provenance = (
        ProvenanceState.CHANGED
        if item["commit"] != current["commit"] or item["url"] != current["url"]
        else ProvenanceState.UNCHANGED
    )
    accepted_availability = AvailabilityState.HEALTHY
    messages = []
    if provenance == ProvenanceState.CHANGED:
        try:
            read_url(current["url"])
        except SourceUnavailable:
            accepted_availability = AvailabilityState.UNAVAILABLE
            messages.append("reviewed URL is unavailable")
        except TransientSourceError:
            accepted_availability = AvailabilityState.TRANSIENT_ERROR
            messages.append("reviewed URL failed transiently")
    availability = (
        AvailabilityState.HEALTHY
        if accepted_availability == AvailabilityState.HEALTHY
        else AvailabilityState.DEGRADED
    )
    return (
        Discovery(
            component=name,
            accepted=accepted,
            observed=Identity(
                version=item["version"],
                commit=item["commit"],
                url=item["url"],
                sha256=item["sha256"],
            ),
            content=content,
            provenance=provenance,
            availability=availability,
            accepted_availability=accepted_availability,
            observed_availability=AvailabilityState.HEALTHY,
            history=HistoryState.NOT_APPLICABLE,
            messages=tuple(messages),
        ),
        item,
    )


def _rollup(values, precedence):
    for state in precedence:
        if state in values:
            return state
    return precedence[-1]


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
