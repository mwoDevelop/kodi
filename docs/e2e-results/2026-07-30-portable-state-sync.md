# Portable Kodi state convergence E2E — 2026-07-30

The deterministic `kodi.favourites` bundle was exported from the registered
Sony TV publisher and applied through Kodi's own process.

Bundle:
`sha256:4da887aa98967d543c782245c7f467697671dfd8c35d48c9a27242ba73a29708`

| Logical device | Result | Favourites | WatchNixtoons2 | Portable artwork | Current fork actions |
| --- | --- | ---: | ---: | ---: | ---: |
| `bluestacks1` | `NO_CHANGE` | 8 | 7 | 7 | 7 |
| `sony-tv` | `NO_CHANGE` | 8 | 7 | 7 | 7 |
| `x88pro20` | `NO_CHANGE` | 8 | 7 | 7 | 7 |
| `bedroom-tv` | `UNAVAILABLE` (ADB offline) | — | — | — | — |
| `nuc-mwo` | `UNAVAILABLE` (SSH) | — | — | — | — |
| `nuc-alek` | `UNAVAILABLE` (SSH) | — | — | — | — |

Before convergence, BlueStacks had no favourites; X88 had five WatchNixtoons2
entries referencing five absent local files; Sony had seven portable images
but all seven actions still targeted the legacy add-on ID. The publisher
materialization completed with seven verified images, seven migrated actions
and zero failures. The post-apply in-Kodi probes confirmed the exact
`favourites.xml` digest and no missing referenced artwork on every reachable
target.

The private machine-readable evidence is retained at
`.kodi-private/e2e/2026-07-30-portable-and-profile-sync-final.json`.

The same final rollout configured each reachable device with its own Profile
Sync logical ID, `home-stable`, a 15-second startup delay, six-hour interval
and read-only safety mode. All remained deliberately unpaired because no
persistent authenticated HTTPS backend is deployed.

A separate verified-backend E2E then passed on all three devices:

- unique one-time pairing and local-only token/signing seed;
- authenticated heartbeat and signed candidate assignment;
- preservation of the prepared identity profile after E2E cleanup;
- successful settings apply plus injected-failure rollback;
- clean journal and byte-exact settings restoration.

Private evidence:

- `.kodi-private/e2e/2026-07-30-profile-sync-identity-preserving-e2e.json`;
- `.kodi-private/e2e/2026-07-30-DEVICE-profile-sync-apply.json`;
- `.kodi-private/e2e/2026-07-30-post-profile-sync-e2e-audit.json`.
