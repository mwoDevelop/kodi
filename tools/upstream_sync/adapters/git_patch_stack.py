"""Read-only discovery for a Git fork with an explicit downstream patch stack."""

import re

from ..models import (
    AvailabilityState,
    ContentState,
    Discovery,
    HistoryState,
    Identity,
    ProvenanceState,
)
from .common import SourceUnavailable, TransientSourceError, fetch_commit, ls_remote, run_git


BASE = re.compile(r'^  base: "([0-9a-f]{40})"$', re.MULTILINE)


class GitPatchStackAdapter:
    version = 1

    def __init__(self, context):
        self.context = context

    def discover(self):
        state_path = self.context.checkout / self.context.config["state_path"]
        match = BASE.search(state_path.read_text(encoding="utf-8"))
        if not match:
            raise ValueError("patch stack has no accepted upstream base")
        accepted = match.group(1)
        upstream = self.context.config["upstream"]
        try:
            observed = ls_remote(upstream["repository"], upstream["branch"])
            fetch_commit(self.context.checkout, upstream["repository"], observed)
        except SourceUnavailable as error:
            return Discovery(
                component=self.context.name,
                accepted=Identity(commit=accepted),
                availability=AvailabilityState.UNAVAILABLE,
                history=HistoryState.UNKNOWN,
                messages=(str(error),),
            )
        except TransientSourceError as error:
            return Discovery(
                component=self.context.name,
                accepted=Identity(commit=accepted),
                availability=AvailabilityState.TRANSIENT_ERROR,
                history=HistoryState.UNKNOWN,
                messages=(str(error),),
            )
        unchanged = accepted == observed
        history = HistoryState.FAST_FORWARD
        if not unchanged and not _is_ancestor(self.context.checkout, accepted, observed):
            history = HistoryState.REWRITTEN
        changed_paths = ()
        if not unchanged and history == HistoryState.FAST_FORWARD:
            changed_paths = tuple(
                line
                for line in run_git(
                    self.context.checkout,
                    "diff",
                    "--name-only",
                    accepted,
                    observed,
                ).splitlines()
                if line
            )
        return Discovery(
            component=self.context.name,
            accepted=Identity(commit=accepted),
            observed=Identity(commit=observed),
            content=ContentState.UNCHANGED if unchanged else ContentState.CHANGED,
            provenance=(
                ProvenanceState.UNCHANGED if unchanged else ProvenanceState.CHANGED
            ),
            availability=AvailabilityState.HEALTHY,
            history=history,
            changed_paths=changed_paths if history == HistoryState.FAST_FORWARD else None,
        )


def _is_ancestor(checkout, accepted, observed):
    import subprocess

    return (
        subprocess.run(
            ["git", "-C", str(checkout), "merge-base", "--is-ancestor", accepted, observed],
            check=False,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
        ).returncode
        == 0
    )
