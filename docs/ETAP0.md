# Etap 0 evidence

Date: 2026-07-24

## Contract

Pinned Umbrella base:
`fb1fa4fe7fdab82091a6502da3f3610df2dcf71f` (`6.7.81`).

Umbrella dynamically imports the configured add-on's `lib` directory and calls
`<module>.sources(ret_all=...)`. Each returned provider class implements:

- `hasMovies`, `hasEpisodes`, `pack_capable`, and `priority`;
- `sources(data, hostDict)`;
- normalized torrent result dictionaries consumed by Umbrella.

MwoScrapers implements that interface without copying provider source code.
Umbrella remains responsible for cross-provider deduplication and resolution.

## Upstream evidence

| Family | Version | Pinned SHA-256 |
|---|---:|---|
| Coco | 1.0.39 | `c6de1ad7ae612fe22a5b102504b9b6f7cebe8fe961de321bdae86b5dced5af59` |
| Viper | 1.5.4 | `9c089bdffa6f30a0a987dfaf289c15eebddeaefc786171609e4e2ef6793f8f4a` |
| Magneto | 6.07.04 | `f46f4d4f25453f3683beebd00bf35ab181e0588da32a4e8dd73917db27615427` |

The packages declare GPL-3.0 in `addon.xml`, but contain no separate license
file and do not establish a complete per-file ownership chain. Consequently,
no provider file was copied. Torrentio and Comet are original adapters against
the public Stremio-compatible JSON shape, with offline fixtures.

## Import threat model

`mwoscrapers/tools/safe_ingest.py` inventories ZIPs without extraction or
module import. It rejects traversal, absolute and Windows drive paths,
symlinks, device files, nested archives, duplicate/case-colliding paths,
excessive file counts, sizes, and compression ratios.

The scheduled audit has `contents: read`, no secrets, pinned Actions, a
concurrency lock, and uploads only the generated report for 14 days.

## Release spike

The main repository builds a complete Pages snapshot from pinned submodule
commits. ZIP timestamps, permissions, order, and compression settings are
fixed. Two independent builds must be byte-identical before publication.

GitHub Pages uses `<hashes>false>` because it cannot serve Kodi's
`content-sha256` response header. CI and the post-deployment smoke test verify
the explicit SHA-256 manifest instead.

Stable initially contains only its repository add-on. Testing contains
Umbrella `6.7.81.1` and MwoScrapers `0.1.0`.
