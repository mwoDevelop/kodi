# Sony Android TV: NordVPN / Torrentio diagnosis

Date: 2026-07-26

## Outcome

The Sony installation was healthy and Real-Debrid authorization was valid.
The failure was isolated to the current NordVPN route: Torrentio returned HTTP
403 on Sony while the same requests returned HTTP 200 on BlueStacks and from
the development host.

NordVPN remains connected on the TV. Android TV split tunneling excludes Kodi
from the VPN while other selected applications continue to use the tunnel.
After that change, Torrentio and Umbrella searches and playback work on Sony.

## Controlled network probe

| Endpoint | Sony through NordVPN | Sony with Kodi excluded | BlueStacks control |
| --- | ---: | ---: | ---: |
| Real-Debrid `/time` | HTTP 200 | HTTP 200 | HTTP 200 |
| Torrentio, Sintel | HTTP 403 / 0 streams | HTTP 200 / 5 streams | HTTP 200 / 5 streams |
| Torrentio, House of the Dragon S03E01 | HTTP 403 / 0 streams | HTTP 200 / 122 streams | HTTP 200 / 122 streams |

The split-tunnel network capabilities exclude Kodi UID 10196. The VPN
interface remains connected and validated, and other application UIDs remain
assigned to it.

## Sony configuration changes

- NordVPN split tunneling enabled; Kodi excluded from the tunnel.
- Umbrella provider cache TTL changed from 48 to 6 hours.
- Umbrella provider cache cleared after a local backup.
- Umbrella debugging enabled at level 1.
- `rd_cloud.enabled` left disabled, matching the user's workaround.
- `realdebrid.saveToCloud` disabled to match the working BlueStacks profile.
- Filename and uncached-source filters were not tightened, because that could
  hide otherwise usable results.

The new provider database contains four cache entries after the controlled
tests. Real-Debrid reauthorization was not needed.

## Device E2E results

| Device | Case | Result | Resolve | Observed playback |
| --- | --- | --- | ---: | ---: |
| Sony Android TV / Kodi 21.2 | Sintel | played | 20.552 s | 16.162 s |
| Sony Android TV / Kodi 21.2 | House of the Dragon S01E01 | played | 26.574 s | 16.172 s |
| Sony Android TV / Kodi 21.2 | House of the Dragon S03E01 | played | 18.378 s | 16.147 s |
| BlueStacks1 / Kodi 21.3 | House of the Dragon S03E01 | played | 16.110 s | 16.054 s |

The focused TV search for `House of the Dragon` also passed on both devices
and returned the exact series. Reports contain no credentials, magnets, or
resolved media URLs.

## Reproduction

Playback:

```bash
.venv/bin/python tests/e2e/sony_kodi_matrix.py \
  --adb /home/mwo/android-sdk/platform-tools/adb \
  --serial 192.168.1.12:5555 \
  --host 127.0.0.1 \
  --jsonrpc-port 19091 \
  --direct-play \
  --case house_of_the_dragon_s03e01 \
  --observe-seconds 15 \
  --result docs/e2e-results/sony-hotd-s03e01.json
```

TV search:

```bash
.venv/bin/python tests/e2e/umbrella_search_e2e.py \
  --adb /home/mwo/android-sdk/platform-tools/adb \
  --serial 192.168.1.12:5555 \
  --host 127.0.0.1 \
  --jsonrpc-port 19091 \
  --term "House of the Dragon" \
  --media-type tv \
  --result docs/e2e-results/sony-tv-search.json
```

References:

- [Real-Debrid VPN cooperation list](https://real-debrid.com/vpn)
- [NordVPN on Android TV](https://support.nordvpn.com/hc/en-us/articles/19928244437777-Installing-and-using-NordVPN-on-Android-TV-or-Nvidia-Shield)
- [NordVPN split tunneling](https://support.nordvpn.com/hc/en-us/articles/19618692366865-What-is-Split-Tunneling-and-how-to-use-it)
