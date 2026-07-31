# MwoScrapers 0.1.8 public Comet fallback and stable rollout

Date: 2026-07-31

## Outcome

MwoScrapers 0.1.8 is published in the stable mwoDevelop Kodi repository.
Torrentio remains enabled, while Comet is now an independent, enabled public
fallback. Source resolution and Real-Debrid playback do not depend on QNAP.

The implementation follows the public Stremio endpoint exposed by the
[Comet project](https://github.com/g0ldyy/comet). Its default public endpoint
is configuration-driven in the
[Comet sample environment](https://github.com/g0ldyy/comet/blob/main/.env-sample).
MwoScrapers uses the public metadata endpoint only; Real-Debrid credentials,
magnet submission and playable URL resolution remain inside Umbrella.

## Immutable release

- MwoScrapers source PR:
  [mwoDevelop/script.module.mwoscrapers#12](https://github.com/mwoDevelop/script.module.mwoscrapers/pull/12);
- source merge commit: `e50595c6ba0971499d663079c8acc63b1efb117f`;
- add-on version: `0.1.8`;
- add-on ZIP SHA-256:
  `18d09f6cfc73d46669688a2e8cfd0c2233f54ec1418fd84109ebbf3532f3613f`;
- certified snapshot:
  `c2db18b284b1dea363d8564d677c8a42a3c6fff2f0ad27f09d45620dee659faa`;
- device certification:
  [run 30628413038](https://github.com/mwoDevelop/kodi/actions/runs/30628413038);
- exact-snapshot promotion:
  [run 30628911260](https://github.com/mwoDevelop/kodi/actions/runs/30628911260);
- stable deployment:
  [run 30629172028](https://github.com/mwoDevelop/kodi/actions/runs/30629172028).

The public stable index checksum is
`5d8d10890c0f59fd7762a5afd8f8834f8c4ab7ea5fb24b4fec279c3485d33528`.
The public stable ZIP has the exact certified digest above.
`repository.mwodevelop` remains version `1.0.0`.

## Device rollout

The release order was BlueStacks, X88 Pro 20, then Sony TV.

| Device | Kodi | Umbrella | MwoScrapers | Search | RD playback | WatchNixtoons2 |
| --- | --- | --- | --- | --- | --- | --- |
| BlueStacks | 21.3 | 6.7.81.18 | 0.1.8 | passed | passed | passed |
| X88 Pro 20 | 21.3 | 6.7.81.18 | 0.1.8 | passed | passed | passed |
| Sony TV with NordVPN | 21.3 | 6.7.81.18 | 0.1.8 | passed | passed | passed |

Every functional check used an isolated Kodi process. The post-cleanup
matrices verified inventory, exact versions, repository origins, Umbrella
search, Sintel resolver/playback and WatchNixtoons2 playback.

On all three devices:

- every managed mwoDevelop add-on is owned by
  `repository.mwodevelop`;
- `repository.mwodevelop.testing` is absent;
- the `CARTOONS` favourites artwork rollout matched and materialized all
  seven WatchNixtoons2 shortcuts with zero failures.

Bedroom TV was unreachable at `192.168.1.18:5555` and NUC SSH was unreachable
at `192.168.1.25:22`; both were skipped after TCP and neighbor checks failed.

## Provider independence

The sanitized endpoint probe produced these live results:

| Device | Comet public movie | Torrentio observation |
| --- | ---: | --- |
| BlueStacks | 132 | public timeout |
| X88 Pro 20 | 132 | LAN relay and public timeout |
| Sony TV with NordVPN | 132 | LAN relay timeout, public HTTP 403 |

Umbrella search and Real-Debrid playback still passed on every reachable
device. This demonstrates that a QNAP outage or Torrentio/VPN failure no
longer removes every provider path.

The QNAP relay remained an optional, stateless Torrentio optimization. It
does not receive Real-Debrid credentials, magnets or resolved playback URLs.

## Defects fixed during certification

- Android TV canaries now use X88 after BlueStacks by default.
- Each functional canary force-stops Kodi first, preventing codec or resolver
  state from contaminating the next test.
- Device certification reads add-on versions and origins from inside Kodi,
  which supports Android scoped storage.
- Scoped origin reads resend a dropped EventServer command.
- The endpoint diagnostic probe now also retries a dropped `RunScript`
  command within its original bounded timeout.
- A guarded add-on cleanup tool removes a repository only after proving that
  no installed add-on still uses it as origin. The directory is restored
  atomically if database cleanup fails.

Relevant merged PRs:

- [#81](https://github.com/mwoDevelop/kodi/pull/81),
  [#82](https://github.com/mwoDevelop/kodi/pull/82),
  [#83](https://github.com/mwoDevelop/kodi/pull/83),
  [#84](https://github.com/mwoDevelop/kodi/pull/84),
  [#85](https://github.com/mwoDevelop/kodi/pull/85) and
  [#86](https://github.com/mwoDevelop/kodi/pull/86).

## Reproducible verification

Run the repository tests:

```bash
.venv/bin/pytest -q tests
```

Run the exact stable device matrix:

```bash
python tools/certify_device_matrix.py \
  --snapshot snapshot.tar \
  --devices .kodi-private/devices.json \
  --references .env \
  --device bluestacks1 \
  --device x88pro20 \
  --output post-cleanup-device-matrix.json
```

Run the sanitized provider probe:

```bash
python tools/kodi_mwoscrapers_endpoint_probe.py \
  --serial DEVICE \
  --timeout 120
```

The final local suite passed `216` tests. PR checks for the cleanup and probe
retry passed in runs
[30630458321](https://github.com/mwoDevelop/kodi/actions/runs/30630458321)
and
[30632130038](https://github.com/mwoDevelop/kodi/actions/runs/30632130038).
The final automatic testing publication
[30632298105](https://github.com/mwoDevelop/kodi/actions/runs/30632298105)
passed the malware gate, detected byte-identical public output and correctly
created neither a new snapshot nor a deployment.
