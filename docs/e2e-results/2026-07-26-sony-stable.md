# Sony Android TV stable verification — 2026-07-26

Target: Sony BRAVIA 4K GB ATV3, Android 9, Kodi 21.2, ADB
`192.168.1.12:5555`.

## Installed from repository.mwodevelop

| Add-on | Version | Kodi origin |
| --- | --- | --- |
| repository.mwodevelop | 1.0.0 | repository.mwodevelop |
| plugin.video.umbrella | 6.7.81.10 | repository.mwodevelop |
| script.module.mwoscrapers | 0.1.3 | repository.mwodevelop |
| script.mwoscrapers | 0.1.1 | repository.mwodevelop |
| plugin.video.watchnixtoons2.mwodevelop | 0.25.2 | repository.mwodevelop |

The public stable Umbrella ZIP and the promoted testing ZIP were byte-identical:

`c2802365ec91be704c3ec92f16a647142e7736a7f37844d51b1503af121acca6`

Selected downstream policy and integration files on the TV matched the public
stable ZIP by SHA-256 after installation through Kodi's add-on manager.

## Playback results

| Test | Result | Resolve | Observation |
| --- | --- | ---: | ---: |
| Umbrella / Sintel (2010) | played | 19.389 s | 16.581 s |
| Umbrella / House of the Dragon S01E01 | played | 33.188 s | 16.165 s |
| Umbrella / The Matrix (1999) | unplayable | no stream | n/a |
| WatchNixtoons2 / latest releases | 15 catalogue entries | n/a | n/a |
| WatchNixtoons2 / Mao episode 17 | played | 16.142 s | 12 s |

`The Matrix` loaded Umbrella's source progress and Kodi rejected the result as
unplayable. The controlled Real-Debrid diagnostic performed before the stable
promotion returned HTTP 451 / Real-Debrid code 35 (`infringing_file`) for all
eight sampled unique candidates. This is a provider-side rejection, not an
authentication, repository, scraper, or resolver crash.

The final successful Umbrella runs exercised the chain
Umbrella -> MwoScrapers -> Real-Debrid -> Kodi VideoPlayer. Kodi created the
input stream and demuxer and advanced playback during the observation window.
WatchNixtoons2 independently loaded its live catalogue, resolved a known path,
created the demuxer, and advanced playback.

## Fixed issues covered by the release

- Real-Debrid collection responses that are lists no longer raise
  `AttributeError` in transport classification.
- The downstream add-on discovers `repository.mwodevelop` without hard-coding
  the upstream repository ID.
- Autoplay uses a bounded, diversified queue and honors `Only try one source`.
- Real-Debrid code 35 failures are logged without exposing magnets and are
  cached negatively for the session.
- Invalid OpenSubtitles `(None, filename)` responses are ignored instead of
  raising URL and empty-subtitle exceptions.
- The Sony test harness detects Kodi's terminal unplayable result instead of
  waiting for the full resolver timeout.

## Reproduction

With Kodi JSON-RPC/EventServer enabled and an isolated ADB server:

```bash
export ADB_SERVER_SOCKET=tcp:localhost:5038
tests/e2e/sony_kodi_matrix.py \
  --adb /home/mwo/android-sdk/platform-tools/adb \
  --serial 192.168.1.12:5555 \
  --host 192.168.1.12 \
  --case sintel \
  --case house_of_the_dragon_s01e01

tests/e2e/sony_watchnixtoons2.py \
  --adb /home/mwo/android-sdk/platform-tools/adb \
  --serial 192.168.1.12:5555 \
  --host 192.168.1.12
```

The WatchNixtoons2 harness requires its playback method to be temporarily set
to `1` (Auto Play Highest Quality), so no modal quality dialog remains for
remote automation.

The temporary debugging/autoplay settings were not retained. The original
Umbrella settings were restored exactly, and the temporary WatchNixtoons2
settings file was removed after the test.
