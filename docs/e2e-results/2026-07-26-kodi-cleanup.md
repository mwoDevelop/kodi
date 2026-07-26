# Kodi cleanup and Android regression — 2026-07-26

## Final state

The BlueStacks1 (`Rvc64`, Kodi 21.3) and Sony BRAVIA Android TV (Kodi 21.2)
installations contain only these enabled repositories:

- `repository.mwodevelop` 1.0.0;
- `repository.xbmc.org`, the official Kodi repository.

The only file-manager source on both devices is:

`mwodevelop -> https://mwodevelop.github.io/kodi/repo/`

The final database and on-disk add-on manifests agree:

| Add-on | Version | Origin |
| --- | ---: | --- |
| Umbrella (mwoDevelop) | 6.7.81.11 | `repository.mwodevelop` |
| WatchNixtoons2 (mwoDevelop) | 0.25.2 | `repository.mwodevelop` |
| MwoScrapers module | 0.1.3 | `repository.mwodevelop` |
| MwoScrapers Manager | 0.1.1 | `repository.mwodevelop` |

Rapideo and its repository were removed. Legacy package-cache entries for
Rapideo, ViperScrapers, ResolveURL, POV, IPTV Lister, MicroJenScrapers,
YouTube helpers, SpeedTester, and Umbrella 6.7.81.10 were also removed where
present: 8 ZIPs on BlueStacks1 and 39 ZIPs on Sony. None of the corresponding
legacy add-ons were installed at deletion time.

Fresh device backups are stored outside the repository in:

`/home/mwo/.local/share/kodi-cleanup-backups/20260726/`

## Resolver correction

Sony exposed an Umbrella provider compatibility error while resolving
`Breaking Bad S01E01`:

`AttributeError: 'source' object has no attribute 'sources_packs'`

Umbrella 6.7.81.11 isolates the optional provider capability behind a
downstream adapter. Providers without pack support are skipped for pack
searches; pack-capable providers receive unchanged arguments and results.
The downstream suite passed 28 tests, including reconstruction from the
upstream base plus the registered patch series.

The exact public stable ZIP has SHA-256:

`c37ba5e4d557c7ec76a6b9d2f6bc2ea2f65ade0e3697a8085b985c0933e98d5d`

It was promoted byte-for-byte from testing. The Kodi repository add-on
remains version 1.0.0.

## Device E2E results

Each resolver case ran independently to prevent a timed-out Kodi window from
affecting the next case.

| Device | Case | Result | Resolve | Observed |
| --- | --- | --- | ---: | ---: |
| BlueStacks1 | Umbrella / Sintel | played | 19.767 s | 12.034 s |
| BlueStacks1 | Umbrella / Breaking Bad S01E01 | played | 15.735 s | 12.043 s |
| Sony | Umbrella / Sintel | played | 19.149 s | 12.137 s |
| Sony | Umbrella / Breaking Bad S01E01 | unplayable source set, no resolver exception | n/a | n/a |
| BlueStacks1 | WatchNixtoons2 / Mao Episode 17 | played | 11.039 s | 12 s |
| Sony | WatchNixtoons2 / Mao Episode 17 | played | 16.451 s | 12 s |

Both WatchNixtoons2 runs also loaded the live `Latest Releases` catalogue and
recorded 15 distinct sample entries. The Sony Breaking Bad run did not find a
usable stream, but the former `sources_packs` exception is absent; the same
case played successfully on BlueStacks1.

Machine-readable reports:

- [BlueStacks1 / Sintel](2026-07-26-cleanup-bluestacks1-sintel.json)
- [BlueStacks1 / Breaking Bad](2026-07-26-cleanup-bluestacks1-breaking-bad.json)
- [BlueStacks1 / WatchNixtoons2](2026-07-26-cleanup-bluestacks1-watchnixtoons2.json)
- [Sony / Sintel](2026-07-26-cleanup-sony-sintel.json)
- [Sony / Breaking Bad](2026-07-26-cleanup-sony-breaking-bad.json)
- [Sony / WatchNixtoons2](2026-07-26-cleanup-sony-watchnixtoons2.json)

## Restored state

Temporary autoplay and WatchNixtoons2 test settings were removed or restored.
Umbrella play modes are back to `0`, `sources.retryall` is back to `true`, and
the original debugging choices were restored (`true` on BlueStacks1, `false`
on Sony). BlueStacks1 EventServer access from all interfaces is back to
`false`, and its temporary ADB JSON-RPC forwarding was removed.

Both devices were started successfully after the final stopped-database audit.
