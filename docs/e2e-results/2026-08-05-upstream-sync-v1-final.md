# Upstream Sync v1 final release certification

Date: 2026-08-05

The content-addressed testing snapshot
`b88a0d70c1def535adbebbac9ae160b8ace656241c5011cf31315200612b77b7`
was certified and promoted to stable without rebuilding component archives.
The repository add-on intentionally remains at version `1.0.0`; this release
versions the synchronization mechanism, not the Kodi repository bootstrap.

## Immutable release evidence

- protected device certification
  [run 31028742156](https://github.com/mwoDevelop/kodi/actions/runs/31028742156)
  passed on BlueStacks1 and X88 Pro 20;
- reviewed stable promotion PR
  [#125](https://github.com/mwoDevelop/kodi/pull/125) merged exact snapshot
  `b88a0d70c1de…`;
- stable deployment
  [run 31029695984](https://github.com/mwoDevelop/kodi/actions/runs/31029695984)
  passed;
- the public stable Profile Sync 1.0.2 archive has SHA-256
  `2c644202e185d9f5e80ca6bbdec7cea5181f66b67e84e45bdddf6aad67d5bdea`,
  identical to the certified testing archive;
- stable records source index SHA-256
  `231f627410fb6fddf6ab51d2237cf3e225457597eaa236f57e6f4b97d574222a`
  and artifact manifest SHA-256
  `1c35ca95055bee58f95a84a9b4aa5b4c2c8fdfb4113b84deedf19b1e78b1ac14`;
- local discovery was a deterministic no-op, stable lock remained unchanged,
  and the complete regression run passed: Umbrella 50, WatchNixtoons2 17,
  mwoScrapers 47 and root repository 325 tests.

Profile Sync 1.0.2 fixes the case in which an assignment expired after that
exact signed revision had already been applied. Such a device now remains
healthy instead of incorrectly rejecting its current state. Its component CI
and the three upstream component workflows use pinned actions compatible with
the Node 24 runtime. The reviewed root component-pointer PR
[#124](https://github.com/mwoDevelop/kodi/pull/124) preserved exact release
bytes.

## Stable device matrix

| Device | Stable add-ons | Umbrella | WatchNixtoons2 | Profile Sync / portable state |
| --- | --- | --- | --- | --- |
| BlueStacks1 | exact stable versions and origins | search + resolver + playback pass | playback pass | 1.0.2, `NO_CHANGE`, pass |
| X88 Pro 20 | exact stable versions and origins | search + resolver + playback pass | playback pass | 1.0.2, `NO_CHANGE`, pass |
| Sony TV | stable Profile Sync | previously certified playback; portable audit repeated | portable audit repeated | 1.0.2, `NO_CHANGE`, pass |
| Bedroom TV | stable Profile Sync | previously certified playback; portable audit repeated | portable audit repeated | 1.0.2, `NO_CHANGE`, pass |

All four Android devices use distinct production enrollments on channel
`home-stable` and converge on active revision
`sha256:4c7d728d214a6d31d1d277d2fd6b30957bc2d07d873648df5e0ffda69a1c905e`.
Each has the same eight favourites, seven portable WatchNixtoons2 actions and
no missing artwork. Private machine-readable evidence is retained outside Git
under `.kodi-private/e2e/`.

X88 required recovery from device-local drift before it passed. Repository and
custom add-on directories were rebuilt from exact stable ZIPs; the incomplete
official `script.module.urllib3` was replaced with Kodi's verified 2.2.3 ZIP;
Profile Sync received a new unique enrollment; and missing Umbrella/Real-Debrid
and mwoScrapers settings were transactionally restored from private host
state. The reusable settings rollout now uses Kodi's restore lock, rollback,
post-restart semantic verification and sanitized evidence. A second sync
returned `NO_CHANGE`, followed by the complete X88 playback matrix.

The testing repository remains available only as an explicit certification
channel on selected canary-capable devices. Every released mwoDevelop add-on
used by the matrix is owned by the stable origin. Bedroom TV remains
stable-only. The testing repository is not removed automatically because a
repository uninstall can delete dependent add-ons or `addon_data`; disabling
or retiring it requires a separately verified migration.

## Scheduled operation and security

The central reconcile workflow, Umbrella updater, WatchNixtoons2 updater and
mwoScrapers provider discovery have current successful scheduled/no-op runs.
The central manual verification
[run 31027430984](https://github.com/mwoDevelop/kodi/actions/runs/31027430984)
also passed. The independent QNAP watchdog is running and healthy from an
immutable image with a read-only filesystem and `unless-stopped` restart
policy.

Foreign candidates pass the fail-closed ClamAV and semantic policy gate before
they can reach a writer. The positive/negative malware drill, including its
EICAR rejection path, passed in
[run 30822178765](https://github.com/mwoDevelop/kodi/actions/runs/30822178765).
No upstream component is auto-merged into a product branch, and stable
promotion remains a reviewed manual decision over exact certified bytes.

Both configured NUC/Flatpak principals were retried on the release date, but
the host was unreachable over both ICMP and SSH (`No route to host`). They are
therefore an explicit availability exception, not reported as passing and not
misclassified as a software regression. Their read-only qualification remains
the next action when the host returns; no Android release work is blocked.
