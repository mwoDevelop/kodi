# X88 selective profile recovery

Date: 2026-07-29

## Incident and root cause

Removing `repository.mwodevelop.testing` through Kodi also removed managed
add-ons and `addon_data`, despite their installed origin having already been
assigned to `repository.mwodevelop`. The exact stable add-on packages were
restored, but Umbrella could search metadata without resolving playback.

A redacted in-Kodi settings probe established that:

- Real-Debrid was enabled, but all authorization values were absent;
- the external provider was disabled and no longer selected;
- the provider cache had returned to 48 hours.

The add-on code, repository candidate, dependency graph and enabled state were
valid. WatchNixtoons2 still resolved and played, isolating the failure to
Umbrella user settings rather than Kodi playback transport.

## Recovery

`tools/kodi_profile.py restore-path` restored only:

```text
userdata/addon_data/plugin.video.umbrella/settings.xml
```

from the verified private Sony snapshot. The command accepts only exact paths
declared by that snapshot, verifies the complete snapshot before building a
minimal archive, validates the device-side restored file count, restarts Kodi
and removes staging files.

The first real-device run also demonstrated that Kodi can lose an EventServer
datagram immediately after startup. The restore transport now retries with a
fresh client and a bounded per-attempt timeout. The subsequent real-device run
completed without manual intervention and reported exactly one restored file.

## Post-recovery E2E

| Test | Result |
|---|---|
| Umbrella movie search, `Sintel` | matching result returned |
| Umbrella movie playback, `Sintel` | resolved in 20.834 s; played for 12.354 s |
| Umbrella episode search, `Breaking Bad` | matching results returned |
| Umbrella episode playback, `Breaking Bad S01E01` | resolved in 16.873 s; played for 15.046 s |
| WatchNixtoons2 live catalogue | 16 current entries returned |
| WatchNixtoons2 playback, `Mao Episode 17` | resolved in 3.047 s; played for 12 s |
| Portable WatchNixtoons2 favourite artwork | 5 matched, 5 materialized, 0 failed |
| Local repository suite | 192 passed |

The installed versions were Umbrella `6.7.81.18`, MwoScrapers `0.1.6`,
MwoScrapers Manager `0.1.1`, WatchNixtoons2 `0.26.1` and
`repository.mwodevelop` `1.0.0`.

## Independent review hardening

A subsequent independent review found and the implementation closed these
additional failure modes:

- a lost EventServer acknowledgement could start concurrent full restores;
- fixed staging markers could be confused across operations;
- success was reported without proving that an add-on service had not reverted
  settings after restart;
- selective recovery admitted add-on code as well as profile data;
- a completion timeout or interrupted host could leave an unsafe or stale
  device lock;
- add-on versions containing a `+` suffix were not comparable.

The hardened protocol uses an atomic started acknowledgement, a random
operation ID, a selection digest and a single device lock. It retries only
before acknowledgement, stops Kodi before releasing the lock when a writer may
still be active, and provides an explicit `recover-lock` command for an
interrupted host. Selective paths are limited to `userdata`; `addon_data`
requires a compatible installed add-on version both before and after restart.
Ordinary files receive size and SHA-256 verification. Add-on settings are
applied through Kodi's settings API and verified semantically after restart.

On X88, a current control run restored and post-restart verified one neutral
profile file. A deliberate retry of the older Umbrella snapshot was rejected:
Umbrella cleared the stale Trakt authorization during startup, so the tool did
not report a false success. The device remained functional:

| Review regression test | Result |
|---|---|
| Selective neutral profile restore | 1 restored, 1 post-restart verified |
| Old Umbrella OAuth state | rejected after the add-on invalidated it |
| Umbrella `Sintel` playback | resolved in 20.603 s; played for 12.362 s |
| WatchNixtoons2 `Mao Episode 17` | resolved in 3.065 s; played for 12 s |
| Reproducible local suite | 209 passed |
| Device staging and restore lock | clean after both success and failure |

## Cleanup policy

Superseded repository add-ons must be disabled rather than uninstalled until a
separate migration test proves that Kodi preserves both managed add-ons and
their `addon_data`. Repository-origin reassignment alone is not sufficient
evidence that uninstall is safe.
