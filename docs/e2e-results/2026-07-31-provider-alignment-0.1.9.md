# Provider alignment 0.1.9 and VPN resolver certification

Date: 2026-07-31

## Outcome

The candidate combines MwoScrapers 0.1.9 and Umbrella 6.7.81.19. Torrentio
and Comet are enabled on every target. Android TV targets use the optional LAN
Torrentio relay followed by the public fallback; BlueStacks and X88 use the
public endpoint directly. Comet always uses its independent public endpoint.

Umbrella's provider cache is six hours, RD Cloud is disabled, and `Only try
one source` is false on the managed profiles. The configuration command resets
only `providers.db` after an endpoint change.

Umbrella keeps each RD attempt bounded, but the common deadline is 45 seconds.
This covers the serialized API calls observed through NordVPN without starting
overlapping resolver workers. The E2E runner separately waits for an actual
JSON-RPC player or an explicit close event; a slow demuxer/MediaCodec startup
is not treated as stopped playback.

## Device evidence

| Device | Torrentio path | VPN | Resolve | Observed playback | Result |
| --- | --- | --- | ---: | ---: | --- |
| BlueStacks | public | no | 37.665 s | 10.112 s | passed |
| X88 Pro 20 | public | unavailable on this hardware | 40.757 s | 10.492 s | passed |
| Sony TV | LAN relay plus public fallback | NordLynx | 49.894 s | 10.271 s | passed |
| Bedroom TV | LAN relay plus public fallback | NordVPN | 45.457 s | 10.392 s | passed |

Sony initially resolved a playable RD URL but its three-day-old NordLynx
connection to Warsaw #297 timed out while opening the CDN stream. Reconnecting
to a fresh Warsaw #308 tunnel preserved the Kodi split-tunnel assignment and
the same controlled Sintel scenario passed. This separates provider and RD
resolution success from a stale VPN media path.

## Reproduce

Align one target:

```bash
python3 tools/kodi_mwoscrapers_configure.py \
  --serial DEVICE \
  --torrentio-endpoint ENDPOINT \
  --comet-endpoint https://comet.feels.legal
```

Run playback through Kodi JSON-RPC and the device EventServer:

```bash
python3 tests/e2e/sony_kodi_matrix.py \
  --adb /home/mwo/android-sdk/platform-tools/adb \
  --serial DEVICE \
  --host 127.0.0.1 \
  --jsonrpc-port FORWARDED_PORT \
  --event-via-adb \
  --case sintel \
  --timeout 240 \
  --observe-seconds 10 \
  --direct-play \
  --result result.json
```

The sanitized result records add-on versions, endpoint classes, resolver
outcomes and a non-reversible source fingerprint. It never stores RD tokens,
magnets or resolved media URLs.
