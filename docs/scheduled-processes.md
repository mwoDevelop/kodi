# Scheduled processes

This is the operational catalogue of recurring automation for the mwoDevelop
Kodi project. Workflow files and Compose manifests remain executable sources
of truth; this document explains their ownership, effects, failure boundary
and monitoring in one place.

All GitHub cron expressions use UTC. GitHub may start scheduled workflows
later than the nominal minute, so the schedule is not an SLA. Every workflow
also supports `workflow_dispatch` for a controlled retry.

## GitHub Actions

| UTC | Repository | Workflow | Purpose | Write boundary |
| --- | --- | --- | --- | --- |
| 04:20 daily | `mwoDevelop/kodi` | `reconcile-upstreams.yml` | Discover all managed component states and prepare an exact testing-lock candidate. | Discovery is read-only. A changed lock is proposed on `automation/testing-lock`; it is never merged or promoted automatically. |
| 04:23 daily | `mwoDevelop/script.module.mwoscrapers` | `check-provider-upstreams.yml` | Download the accepted immutable Coco, Magneto and Viper artifacts, verify their pinned digests and scan them with the shared malware control. | Read-only. It uploads a 14-day audit artifact and never changes a branch. Any unavailable artifact, digest mismatch or failed scan fails the workflow. |
| 04:35 daily | `mwoDevelop/ch.repo` | `mwodevelop-watchnixtoons2-update.yml` | Discover WatchNixtoons2 upstream, materialize and scan an isolated candidate, and test it. | A verified change may update `automation/watchnixtoons2-upstream` and open a review-gated PR. It does not publish the Kodi repository. |
| 04:41 daily | `mwoDevelop/script.module.mwoscrapers` | `discover-provider-upstreams.yml` | Observe the latest provider feeds and maintain provenance-only review state. | A changed observation may update `automation/provider-provenance` and open a review-gated PR. It does not import or execute provider code. |
| 04:50 daily | `mwoDevelop/umbrellaplug.github.io` | `propose-upstream-update.yml` | Replay the downstream Umbrella patch stack on the exact upstream commit, scan the candidate and test it. | A verified change may update `automation/umbrella-upstream` and open a review-gated PR. Protected paths must remain unchanged. |

The provider audit and provider discovery are intentionally separate:

- the 04:23 audit proves that every already accepted artifact is still
  downloadable, byte-identical and scan-clean;
- the 04:41 discovery observes new upstream state and can report or propose a
  provenance update without accepting new executable bytes.

No scheduled workflow merges a PR, promotes `testing` to `stable`, changes
Real-Debrid credentials, or writes Kodi user configuration.

## Monitoring on QNAP

`qnap-upstream-watchdog` runs in Container Station and polls GitHub every six
hours. The monitored workflow list is versioned in
`manifests/upstream-watchdog.json`. A workflow is unhealthy when its latest run
is missing, failed, or older than 36 hours. The container healthcheck reads the
result every five minutes and QTS/Container Station is responsible for the
external notification.

The watchdog has public GitHub read access only. It cannot retry a workflow,
change a branch or repair an upstream artifact. A successful discovery does
not mask a failed accepted-artifact audit; both mwoScrapers workflows are
monitored independently.

The other QNAP container healthchecks are service-liveness probes, not update
schedules:

| Service | Interval | Probe |
| --- | --- | --- |
| Profile Sync backend | 30 seconds | local HTTPS readiness endpoint inside the container |
| mwoScrapers provider relay | 30 seconds | local `/health` endpoint inside the container |
| upstream watchdog | 5 minutes | last persisted GitHub workflow evaluation |

## Kodi Profile Sync clients

`service.mwodevelop.profilesync` is a separate device-local periodic process.
The standard home profile waits 15 seconds after Kodi starts and checks its
signed `home-stable` assignment every six hours. Device-specific enrollment,
tokens, signing material and last-applied revision stay local and are excluded
from the synchronized profile payload.

Profile Sync does not install add-on code, run GitHub workflows, promote a
repository channel, or use the provider relay. Its backend and schedule are
therefore monitored separately from upstream synchronization.

## Manual and event-driven processes

Build, CI, malware drills, testing publication, certification, stable
promotion and deployment workflows are intentionally not scheduled. They run
from a push, pull request or explicit `workflow_dispatch` and retain their own
review and exact-head checks.

## Operational verification

Check the latest scheduled runs without relying on a historical release
report:

```bash
gh run list --repo mwoDevelop/kodi \
  --workflow reconcile-upstreams.yml --event schedule --limit 1
gh run list --repo mwoDevelop/script.module.mwoscrapers \
  --workflow check-provider-upstreams.yml --event schedule --limit 1
gh run list --repo mwoDevelop/script.module.mwoscrapers \
  --workflow discover-provider-upstreams.yml --event schedule --limit 1
gh run list --repo mwoDevelop/ch.repo \
  --workflow mwodevelop-watchnixtoons2-update.yml --event schedule --limit 1
gh run list --repo mwoDevelop/umbrellaplug.github.io \
  --workflow propose-upstream-update.yml --event schedule --limit 1
```

For the deployed watchdog, inspect `/run/watchdog/status.json` inside the
`qnap-upstream-watchdog-upstream-watchdog-1` container. A healthy container is
evidence only for the workflows present in the versioned watchdog manifest.

When adding or removing a scheduled upstream workflow, update together:

1. its workflow file and cron;
2. this catalogue;
3. `manifests/upstream-watchdog.json`;
4. watchdog tests and the immutable QNAP watchdog image;
5. the live QNAP deployment, followed by a functional status check.

Historical reports below `docs/e2e-results/` describe their stated
certification date and must not be treated as current operational status.
