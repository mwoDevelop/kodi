# WatchNixtoons2 0.26.1 rollout

Date: 2026-07-28

## Artifact and publication

- fork commit: `83560a2a5ccf7ab56724183959688a42b63b9615`;
- upstream release: `0.26` at
  `6b3183f56aef4e90ba1f0eb067c88ad2bc69e593`;
- downstream version: `0.26.1`;
- deterministic/public ZIP SHA-256:
  `01a84245391da1beef7bc65982b4d47dd517595c533296473b65763e6a1e2312`;
- testing publication:
  <https://github.com/mwoDevelop/kodi/actions/runs/30373242032>;
- public artifact:
  <https://mwodevelop.github.io/kodi/testing/omega/plugin.video.watchnixtoons2.mwodevelop/plugin.video.watchnixtoons2.mwodevelop-0.26.1.zip>.

The public ZIP was downloaded and its digest was checked before each rollout.
Kodi performed each update through its `Install from zip file` GUI. Kodi leaves
the `installed.origin` field empty for this path; the source is proven by the
public URL and matching digest rather than by claiming a repository-manager
origin.

## Device matrix

All three devices resolved the same content path,
`mao-episode-17-english-subbed`, selected the `480 (SD)` source and reported
the same total duration of 25:19.

| Device | Kodi | Add-on | Resolve | Playback evidence |
|---|---:|---:|---:|---|
| BlueStacks1 (`127.0.0.1:5715`) | 21.3 | 0.26.1 | 2.009 s | input stream, demux, AAC decoder, 12 s progression |
| Sony TV (`192.168.1.12:5555`) | 21.3 | 0.26.1 | 5.056 s | input stream, demux, AAC decoder, 12 s progression |
| Bedroom TV (`192.168.1.18:5555`) | 21.3 | 0.26.1 | 2.021 s | input stream, demux, AAC decoder, 12 s progression |

Sanitized machine-readable reports:

- [BlueStacks1](2026-07-28-bluestacks1-watchnixtoons2-0.26.1.json)
- [Sony TV](2026-07-28-sony-watchnixtoons2-0.26.1.json)
- [Bedroom TV](2026-07-28-bedroom-tv-watchnixtoons2-0.26.1.json)

## Cyclic update proof

The first remote cycle prepared a content-addressed candidate in a read-only
job, verified it in the writer job and opened reviewed PR
<https://github.com/mwoDevelop/ch.repo/pull/5>. The post-merge cycle initially
found that a fresh checkout did not contain the accepted immutable upstream
object. PR <https://github.com/mwoDevelop/ch.repo/pull/7> fixed that by fetching
the exact accepted commit when absent.

The final second cycle completed successfully and skipped candidate
preparation, artifact upload and PR creation as a true no-op:
<https://github.com/mwoDevelop/ch.repo/actions/runs/30374992303>.

`mwonuc` was unreachable at `192.168.1.25` during this rollout (`No route to
host`), so no NUC mutation was attempted. Its two account-specific SSH keys
remain installed and previously passed cross-account rejection tests.
