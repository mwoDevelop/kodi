# Profile Sync 1.0.1 stable final rollout

Date: 2026-08-03

The immutable testing snapshot
`e12d6b8ba1839cbe5ed7e43c3c3e4a0cf7208e0fb12075471dcdcd44460055d3`
was certified and promoted without rebuilding its component archives. The
public stable Profile Sync archive has SHA-256
`99b05e41c24e3e1c4d1bad83ccb7dbe0a618441065b81ae36cc070b8fae0eb4e`.
`repository.mwodevelop` intentionally remains at version `1.0.0`.

## Release evidence

- device certification run `30847171206` passed on BlueStacks1 and X88 Pro 20;
- stable promotion run `30847934079` passed;
- reviewed lock-only promotion PR `#108` was merged;
- stable deployment run `30848088877` passed;
- public stable bytes reproduce the certified Profile Sync SHA-256;
- the deterministic local build and complete regression suite passed with
  `299 passed`.

The certification found two device-independent rollout defects. Umbrella was
not always bound to the external `script.module.mwoscrapers` provider, and
wireless Kodi candidate rollout could lose the device-local EventServer
packet. The provider configuration now explicitly enables and selects
mwoScrapers. LAN rollout now falls back to a host-sent EventServer command.
Concurrent production sync probes also use invocation-scoped mode-0600 config
files, preventing one device identity from racing another. The first fix was
released before certification; the rollout harness fixes were merged in PR
`#109` after local and CI regression tests passed.

## Stable device matrix

| Device | Profile Sync | Portable profile | Umbrella | WatchNixtoons2 |
| --- | --- | --- | --- | --- |
| BlueStacks1 | 1.0.1, `NO_CHANGE` | pass | certified search and playback | certified playback |
| X88 Pro 20 | 1.0.1, `NO_CHANGE` | pass | certified search and playback | certified playback |
| Sony TV | 1.0.1, `NO_CHANGE` | pass | search, Sintel and Breaking Bad playback pass | playback pass |
| Bedroom TV | 1.0.1, `NO_CHANGE` | pass | search, Sintel and Breaking Bad playback pass | playback pass |

All four Android installations use production enrollment on channel
`home-stable` with the same active revision
`sha256:4c7d728d214a6d31d1d277d2fd6b30957bc2d07d873648df5e0ffda69a1c905e`,
unique logical identities, HTTPS CA validation and no pending report. Each has
the same eight favourites and seven portable WatchNixtoons2 entries, with no
missing artwork. All five mwoDevelop components are enabled and owned by
`repository.mwodevelop`; `repository.mwodevelop.testing` is absent.

Bedroom TV initially crashed Kodi in Android `surfaceDestroyed` while the
Google TV Streamer was asleep. ABI inspection showed a matching 32-bit Android
and Kodi build. Waking the display and launching Kodi's explicit activity
removed the failure; no reinstall or profile mutation was required. The final
Bedroom checks resolved and observed Sintel for 15 seconds, resolved and
observed Breaking Bad S01E01 for 15 seconds, and played a WatchNixtoons2 item
for 15 seconds.

The two Linux/Flatpak NUC principals were probed again but their SSH transport
was unavailable. They are not reported as passing and do not invalidate the
completed Android release.

## Production backup

After final convergence, QNAP produced an online-consistent epoch containing
the SQLite database and six content-addressed blobs. The epoch was downloaded,
encrypted off-NAS with AES-256-GCM and stored locally as a mode-0600 private
backup. A decrypt-and-open drill reproduced the exact plaintext digest;
SQLite `integrity_check` returned `ok` with seven enrollments. No credential,
token, signing seed or private backup path is committed in this report.

Private machine-readable device reports remain outside version control under
`.kodi-private/e2e` and `.kodi-private/profile-sync-production/e2e`.
