# Umbrella search regression on Sony and BlueStacks — 2026-07-26

## Outcome

Umbrella search works on both running Kodi installations with the stable
`plugin.video.umbrella` 6.7.81.13 from `repository.mwodevelop` 1.0.0.

The Sony failure was reproduced as a stale Umbrella `source_progress` modal.
The modal could remain alive after a terminal resolver path and prevent the
virtual keyboard from opening. The downstream lifecycle policy now arms the
keep-alive property synchronously before starting the modal thread; the monitor
only waits for release and never re-arms an already released window.

Autoplay resolution also runs each selected-source resolver call through a
bounded worker. A late result cannot be accepted after the 8-second attempt
deadline. Both changes live in downstream policy modules and patch
registration, keeping the fork reconstructable and isolated from upstream
code under the project's OCP policy.

## Released artifacts

- Umbrella tag: `mwo-6.7.81.13`
- Umbrella release commit: `fb689588a9b4e3502886e1ca63a48ccaa9f399c2`
- Public stable ZIP SHA-256:
  `5ddb813669fde54096caf5c3f9b86ac7a0e26bf9ae132197d996f1b18b378d58`
- Public stable `addons.xml` SHA-256:
  `a8de1caf21b8bce85413a0af2476cfb515282c71298c16b62b0fec5fb63a9213`
- `repository.mwodevelop` remains at version `1.0.0`.

The public stable ZIP was downloaded again after deployment and matched the
stable lock byte-for-byte.

## Device regression

| Device | Kodi | Test | Result |
| --- | ---: | --- | --- |
| Sony BRAVIA | 21.2 | Search `Big Buck Bunny` after a resolver attempt, without restarting Kodi | 2 matching results |
| Sony BRAVIA | 21.2 | Search `Sintel` immediately after a deterministic 180-second resolver timeout, without restarting Kodi | `Sintel (2010)` |
| BlueStacks1 / Rvc64 | 21.3 | Search `Big Buck Bunny` | 2 matching results |

The final Kodi add-on manifests report Umbrella 6.7.81.13 on both devices.
Their add-on databases report all five mwoDevelop add-ons enabled and
originating from `repository.mwodevelop`:

- `plugin.video.umbrella`;
- `plugin.video.watchnixtoons2.mwodevelop`;
- `script.module.mwoscrapers`;
- `script.mwoscrapers`;
- `repository.mwodevelop`.

Machine-readable reports:

- [Sony search after resolver timeout](2026-07-26-sony-search-after-jsonrpc-timeout-6.7.81.13.json)
- [Sony deterministic resolver attempt](2026-07-26-sony-sintel-jsonrpc-6.7.81.13.json)
- [BlueStacks1 search](2026-07-26-bluestacks1-big-buck-bunny-search-6.7.81.13.json)

## Separate resolver observation

The deterministic Sony `Sintel` run invoked the plug-in URL through
acknowledged Kodi JSON-RPC and loaded Umbrella's source-progress UI, but the
complete provider scrape did not produce a player within 180 seconds. This is
separate from the fixed search-window lifecycle: search succeeded immediately
after that timeout in the same Kodi process.

The 8-second bound added in 6.7.81.13 applies to an individual selected-source
resolution attempt. It intentionally does not abort provider discovery, which
can precede resolution and is governed by its own provider timeouts.

The E2E matrix now uses JSON-RPC `Player.Open` for direct playback instead of
the unacknowledged and device-dependent EventServer transport. Every direct
invocation carries a unique E2E nonce so Kodi cannot reuse a previous plug-in
path.

## Reproduction

```bash
export ADB_SERVER_SOCKET=tcp:localhost:5038

PYTHONPATH=tests/e2e .venv/bin/python tests/e2e/umbrella_search_e2e.py \
  --adb /home/mwo/android-sdk/platform-tools/adb \
  --serial 192.168.1.12:5555 \
  --host 127.0.0.1 \
  --jsonrpc-port 19091 \
  --term Sintel \
  --result docs/e2e-results/sony-umbrella-search.json

PYTHONPATH=tests/e2e .venv/bin/python tests/e2e/umbrella_search_e2e.py \
  --adb /home/mwo/android-sdk/platform-tools/adb \
  --serial 127.0.0.1:5555 \
  --host 127.0.0.1 \
  --jsonrpc-port 19190 \
  --term "Big Buck Bunny" \
  --result docs/e2e-results/bluestacks1-umbrella-search.json
```

The complete local suite passed: `58 passed`.

## Restored device state

The original Umbrella search databases were restored after testing. Their
post-restart SHA-256 values match the pre-test backups:

- Sony:
  `a708a44cb2254b4e60ae4e95a0ebe58c967e8813c3f25597d67cb60b03d0c85b`;
- BlueStacks1:
  `536ee51ff0a2c0f1d1e397a7cd1f333bedff5463f4c7c5a2f0e7f7c8b83ffd81`.

No Real-Debrid credentials, magnets, or resolved media URLs are stored in the
reports.
