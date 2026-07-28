# Umbrella 6.7.81.16 and MwoScrapers 0.1.5 relay rollout

Date: 2026-07-28

## Outcome

The testing candidate passed on BlueStacks, Sony TV and Bedroom TV. Umbrella
no longer offers itself as an external provider, while MwoScrapers remains a
valid choice. Both Android TV devices kept NordVPN connected during the final
tests.

Bedroom TV established the network cause before rollout:

- direct Torrentio calls through its VPN exit returned HTTP 403;
- the same Kodi runtime through the QNAP metadata relay returned 5 movie
  candidates and 49 episode candidates;
- BlueStacks direct, Sony relay and Bedroom relay returned the same 5/49
  counts.

No NordVPN split-tunnel change was required. The final Android connectivity
state exposed Kodi's UID in the connected NordVPN network's assigned UID
ranges on both Sony and Bedroom TV.

## Published components

| Component | Version | Commit / immutable identity |
| --- | --- | --- |
| Umbrella | 6.7.81.16 | `9ccb063e65463b4116d5c9ad2f09be189b051f29` |
| MwoScrapers | 0.1.5 | `6c4b7956734f902c94b51f593a989ef0b3a29510` |
| MwoScrapers relay | 0.1.0 | `ghcr.io/mwodevelop/mwoscrapers-relay@sha256:837e070ef5106fcd294b56f1cdd74a5d0376839d173e4388a6b5361916803198` |

The public testing ZIP digests matched the repository lock:

- Umbrella: `e97d3cb06792663b58b30097072e36f5de04122045a2f47d44ded95d9fd22855`;
- MwoScrapers: `ec9425baa334fbda2b9b106ec0aa558e5a8d37e03d5315e865fbcfb15762c58a`.

## QNAP relay

The multi-architecture manifest passed CI for `linux/amd64` and
`linux/arm/v7`. A disposable ARMv7 QNAP smoke passed health, returned
non-empty Torrentio metadata and created no volumes. Cleanup left zero smoke
containers, networks and volumes.

The production stateless project is bound to the QNAP private LAN address:

- one healthy container and one Compose network;
- zero volumes and zero secrets;
- fixed provider/path allowlist;
- QNAP RAID state `UU`;
- public health response `ok`.

Real-Debrid authorization, magnet submission, resolving and playback do not
pass through this relay.

## Device results

| Device | Kodi | Umbrella | MwoScrapers | Sintel | Breaking Bad S01E01 |
| --- | --- | --- | --- | --- | --- |
| BlueStacks | 21.3 | 6.7.81.16 | 0.1.5 | played, 20.254 s | played, 12.144 s |
| Sony TV | 21.3 | 6.7.81.16 | 0.1.5 | played, 46.481 s | played, 27.000 s |
| Bedroom TV | 21.3 | 6.7.81.16 | 0.1.5 | played, 18.124 s | played, 14.253 s |

Every device selected the same sanitized source fingerprint per case:

- Sintel: `5a6b52180d6a015e`;
- Breaking Bad S01E01: `6f39c1e78d9c75c4`.

Each playback created the input stream and demuxer and advanced for at least
12 seconds. The reports contain no credentials, magnets or resolved URLs:

- [BlueStacks](2026-07-28-bluestacks-provider-relay-rollout.json)
- [Sony TV](2026-07-28-sony-provider-relay-rollout.json)
- [Bedroom TV](2026-07-28-bedroom-provider-relay-rollout.json)

## Stable promotion

The exact public testing candidate was promoted byte-for-byte after the device
rollout:

- promotion gate `30383783693` fetched and checked testing index
  `9bca766697af33afe56e1e1c83a3bdb48b4cfe6111a13542dfa9566ba378a01c`;
- promotion PR #55 changed only `manifests/locks/stable.json` and passed
  repository E2E in run `30383969637`;
- stable deployment `30384195482` passed repository E2E, built only
  lock-addressed bytes and deployed GitHub Pages;
- the public stable ZIP digests for all five components match the promoted
  lock, and the public `addons.xml` matches its declared checksum;
- `repository.mwodevelop` remains version `1.0.0`.

The post-promotion ownership cleanup also passed:

- Kodi refreshed the stable repository to index checksum
  `01dac2b62f0138a99832607e42c442c0365597c4d9b9190ff75ebc14ff02f168`;
- the origin migration required the exact stable and testing index checksums
  and matching candidate versions before changing Kodi's add-on database;
- every installed mwoDevelop add-on on BlueStacks, Sony TV and Bedroom TV is
  enabled and owned by `repository.mwodevelop`;
- `repository.mwodevelop.testing` was removed from Sony TV and Bedroom TV
  after migration and is absent on all three devices;
- the post-cleanup Sintel playback passed again on all three devices for more
  than 12 seconds with source fingerprint `5a6b52180d6a015e`;
- no temporary ADB forwards or device-side migration files remain.

Sanitized post-cleanup reports:

- [BlueStacks](2026-07-28-bluestacks-stable-origin-cleanup.json)
- [Sony TV](2026-07-28-sony-stable-origin-cleanup.json)
- [Bedroom TV](2026-07-28-bedroom-stable-origin-cleanup.json)

## Defect found and fixed during rollout

MwoScrapers 0.1.4 used empty XML defaults for the two endpoint settings.
Kodi accepted the values but logged `CSettingString` default-value errors.
Version 0.1.5 uses the providers' public endpoints as valid defaults.

After installing the exact public 0.1.5 ZIP on all devices:

- the same movie/episode provider probe returned 5/49 on all three;
- zero endpoint-setting schema errors appeared in each new log window;
- all six final playback cases passed.

## Reproducible gates

- Umbrella fork: 41 tests;
- MwoScrapers: Ruff, add-on validation and 36 tests;
- parent repository: two byte-identical builds and 141 tests;
- publication workflow: `30382850144`;
- QNAP smoke and production lifecycle:
  `tools/qnap_provider_relay.py`;
- Kodi provider/filter probe:
  `tests/e2e/kodi_provider_rollout_probe.py`;
- playback:
  `tests/e2e/sony_kodi_matrix.py`.
