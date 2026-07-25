"""Discovery for a downstream add-on imported from a Kodi repository ZIP."""

import hashlib
import io
import json
import stat
import subprocess
import zipfile

from ..models import (
    AvailabilityState,
    ContentState,
    Discovery,
    HistoryState,
    Identity,
    ProvenanceState,
)
from ..versioning import KodiVersion
from .common import SourceUnavailable, TransientSourceError, fetch_commit, ls_remote, run_git
from .git_patch_stack import _is_ancestor


class VendoredKodiAddonAdapter:
    version = 1

    def __init__(self, context):
        self.context = context

    def discover(self):
        state = json.loads(
            (self.context.checkout / self.context.config["state_path"]).read_text(
                encoding="utf-8"
            )
        )
        upstream = self.context.config["upstream"]
        accepted_commit = state["commit"]
        accepted_url = _archive_url(
            upstream["repository"], accepted_commit, state["archive"]
        )
        accepted = Identity(
            version=state["version"],
            commit=accepted_commit,
            url=accepted_url,
            sha256=state["archive_sha256"],
        )
        try:
            observed_commit = ls_remote(upstream["repository"], upstream["branch"])
            fetch_commit(self.context.checkout, upstream["repository"], observed_commit)
        except SourceUnavailable as error:
            return Discovery(
                component=self.context.name,
                accepted=accepted,
                availability=AvailabilityState.UNAVAILABLE,
                history=HistoryState.UNKNOWN,
                messages=(str(error),),
            )
        except TransientSourceError as error:
            return Discovery(
                component=self.context.name,
                accepted=accepted,
                availability=AvailabilityState.TRANSIENT_ERROR,
                history=HistoryState.UNKNOWN,
                messages=(str(error),),
            )
        if accepted_commit == observed_commit:
            return Discovery(
                component=self.context.name,
                accepted=accepted,
                observed=accepted,
                content=ContentState.UNCHANGED,
                provenance=ProvenanceState.UNCHANGED,
                availability=AvailabilityState.HEALTHY,
                history=HistoryState.FAST_FORWARD,
                changed_paths=(),
            )
        if not _is_ancestor(self.context.checkout, accepted_commit, observed_commit):
            return Discovery(
                component=self.context.name,
                accepted=accepted,
                observed=Identity(commit=observed_commit),
                content=ContentState.UNKNOWN,
                provenance=ProvenanceState.CHANGED,
                availability=AvailabilityState.HEALTHY,
                history=HistoryState.REWRITTEN,
            )
        version, archive = _latest_archive(
            self.context.checkout,
            observed_commit,
            state["addon_id"],
        )
        payload = _git_bytes(self.context.checkout, observed_commit, archive)
        _inspect_zip(payload)
        digest = hashlib.sha256(payload).hexdigest()
        observed = Identity(
            version=version,
            commit=observed_commit,
            url=_archive_url(upstream["repository"], observed_commit, archive),
            sha256=digest,
        )
        changed_paths = tuple(
            line
            for line in run_git(
                self.context.checkout,
                "diff",
                "--name-only",
                accepted_commit,
                observed_commit,
            ).splitlines()
            if line
        )
        return Discovery(
            component=self.context.name,
            accepted=accepted,
            observed=observed,
            content=(
                ContentState.UNCHANGED
                if digest == state["archive_sha256"]
                else ContentState.CHANGED
            ),
            provenance=ProvenanceState.CHANGED,
            availability=AvailabilityState.HEALTHY,
            history=HistoryState.FAST_FORWARD,
            changed_paths=changed_paths,
        )


def _archive_url(repository, commit, archive):
    return "https://raw.githubusercontent.com/%s/%s/%s" % (
        repository,
        commit,
        archive,
    )


def _latest_archive(checkout, commit, addon_id):
    prefix = addon_id + "/"
    candidates = []
    for path in run_git(checkout, "ls-tree", "-r", "--name-only", commit).splitlines():
        if not path.startswith(prefix) or not path.endswith(".zip"):
            continue
        filename = path.rsplit("/", 1)[-1]
        marker = addon_id + "-"
        if not filename.startswith(marker):
            continue
        version = filename[len(marker) : -4]
        try:
            candidates.append((KodiVersion(version), version, path))
        except ValueError:
            continue
    if not candidates:
        raise ValueError("upstream add-on archive was not found")
    _, version, path = max(candidates, key=lambda item: item[0])
    return version, path


def _git_bytes(checkout, commit, path):
    result = subprocess.run(
        ["git", "-C", str(checkout), "show", "%s:%s" % (commit, path)],
        check=False,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
    )
    if result.returncode:
        raise ValueError(result.stderr.decode("utf-8", errors="replace"))
    return result.stdout


def _inspect_zip(payload):
    total = 0
    with zipfile.ZipFile(io.BytesIO(payload)) as archive:
        items = archive.infolist()
        for item in items:
            path = item.filename.replace("\\", "/")
            parts = [part for part in path.split("/") if part]
            if path.startswith("/") or ".." in parts:
                raise ValueError("unsafe archive path: %s" % path)
            mode = item.external_attr >> 16
            if stat.S_ISLNK(mode):
                raise ValueError("archive symlink is forbidden: %s" % path)
            total += item.file_size
            if total > 256 * 1024 * 1024:
                raise ValueError("archive expands beyond limit")
    return {"files": len(items), "uncompressed_bytes": total}
