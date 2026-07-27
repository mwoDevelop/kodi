# QNAP Profile Sync synthetic smoke

Date: 2026-07-27

Scope: Stage 6A only. The run used synthetic public-key data, a one-time
directory outside `/share/ProfileSync`, a loopback-only port and restart
policy `no`. It did not contain Kodi profiles, user credentials, tokens or
production keys.

## Immutable image

- server version: 0.1.0;
- build commit: `b5ece3776f877634f9574def249a4612f49dacc8`;
- manifest:
  `ghcr.io/mwodevelop/kodi-profile-sync-server@sha256:9df7716d8b6606a1657f9dce77752105a8ce6036a974f975b3adc993d44c6671`;
- verified platforms: `linux/amd64`, `linux/arm/v7`;
- release workflow:
  <https://github.com/mwoDevelop/kodi-profile-sync-server/actions/runs/30300480694>.

## Live QNAP evidence

- host architecture: `armv7l`;
- Docker: `26.1.4-qnap2`;
- Compose: `2.27.1-qnap1`;
- storage driver: `overlay2`;
- main array remained degraded and rebuilding (`[U_]`, approximately 30.2%
  during the successful run), so production was not attempted;
- Compose project: `qnap-profile-sync-smoke`;
- published endpoint: QNAP loopback port 28765 only;
- `/ready`: `ready`, API `v1`, database schema 2, verified registry mode;
- a manual process restart returned to `ready`;
- a controlled stop made the endpoint unavailable;
- starting the same immutable deployment returned it to `ready`.

## Cleanup evidence

After verification, Compose down and the guarded cleanup completed:

```json
{
  "containers": 0,
  "networks": 0,
  "volumes": 0,
  "smoke_parent_present": false
}
```

No autostart, tunnel, anonymous volume, Compose network or smoke directory
remained. Production `/share/ProfileSync` paths were never used.

## Reproducible host flow

```bash
cd /home/mwo/projects/kodi

.venv/bin/python tools/qnap_profile_sync.py preflight

.venv/bin/python tools/qnap_profile_sync.py smoke-deploy \
  --image \
  ghcr.io/mwodevelop/kodi-profile-sync-server@sha256:9df7716d8b6606a1657f9dce77752105a8ce6036a974f975b3adc993d44c6671 \
  --run-id profile-sync-YYYYMMDDa

.venv/bin/python tools/qnap_profile_sync.py verify

.venv/bin/python tools/qnap_profile_sync.py destroy-smoke \
  --run-id profile-sync-YYYYMMDDa

.venv/bin/python tools/qnap_profile_sync.py status
```

The tool requires the private mode-0600 `.env` and a pinned QNAP host key.
It never prints the host, username or password.
