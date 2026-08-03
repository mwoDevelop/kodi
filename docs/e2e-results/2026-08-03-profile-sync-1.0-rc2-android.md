# Profile Sync 1.0 RC2 Android E2E

Date: 2026-08-03

The exact public testing artifact `service.mwodevelop.profilesync-1.0.0~rc2.zip`
with SHA-256
`f3d3b2d22abee846a152e47e037a80fabae0b60b38b421cd4b2f6c20973c2e3b`
was qualified against the production QNAP backend and active profile revision
`sha256:4c7d728d214a6d31d1d277d2fd6b30957bc2d07d873648df5e0ffda69a1c905e`.

| Device | Profile apply/repeat | Portable state | Umbrella search | RD playback | WatchNixtoons2 |
| --- | --- | --- | --- | --- | --- |
| BlueStacks1 | pass / `NO_CHANGE` | 8 favourites, 7 portable actions, artwork complete | movie + TV pass | Sintel + Breaking Bad pass | pass |
| X88 Pro 20 | pass / `NO_CHANGE` | 8 favourites, 7 portable actions, artwork complete | movie + TV pass | Sintel + Breaking Bad pass | pass |
| Sony TV | pass / `NO_CHANGE` | 8 favourites, 7 portable actions, artwork complete | movie + TV pass | Breaking Bad pass; Sintel source-specific failure | pass |
| Bedroom TV | pass / `NO_CHANGE` | 8 favourites, 7 portable actions, artwork complete | Sintel + Breaking Bad pass | Sintel + Breaking Bad pass | pass |

Bedroom TV used Kodi 21.3 on Google TV Streamer. The active revision was
applied once and the immediate second sync returned `NO_CHANGE`; the report
queue was empty. Sintel resolved in about 59 seconds and Breaking Bad S01E01
in about 24 seconds, followed by at least 15 seconds of observed playback in
both cases. WatchNixtoons2 resolved in about 2 seconds and played for the
required observation interval.

The two Linux/Flatpak NUC principals were not claimed as passed because their
shared host was unreachable during this run. This is recorded as a device
availability gap, not an Android software failure and not a time-based release
gate.

Private machine-readable reports remain outside version control under
`.kodi-private/e2e` and `.kodi-private/profile-sync-production/e2e`.

## Final version ordering

The first final descriptor `1.0.0` was intentionally rejected before stable
promotion: Kodi retained the installed `1.0.0~rc2` instead of treating
`1.0.0` as an upgrade. The final candidate is therefore `1.0.1`. This keeps
the runtime code unchanged while providing a monotonic upgrade path for every
device that participated in RC qualification. The `1.0.0` testing snapshot is
not eligible for stable promotion.
