# Profile Sync 0.1.8 stable rollout

Date: 2026-07-31

## Released artifacts

- Kodi add-on: `service.mwodevelop.profilesync` 0.1.8;
- add-on commit: `69fd1921906e32a2e1bd4e5106690ebe103b41a2`;
- public stable ZIP SHA-256:
  `0542cad64b30c2491ae42ce1b4a07011d002ba1de6b064092443cea1ba942574`;
- immutable testing snapshot:
  `b89c7205c1a6a40f573c24bc1a9e68725da066c3b5b49a50d5308ada05d50698`;
- QNAP server: 0.2.1, build
  `git:0e36e579078c57034be05b440c933096e5807007`;
- QNAP image:
  `ghcr.io/mwodevelop/kodi-profile-sync-server@sha256:166a4303b083daf23a10e18d4ffc756e0b16d3aedb9a073583c755addc20390f`.

`repository.mwodevelop` intentionally remains version 1.0.0.

## Promotion evidence

- testing publication run: `30640650514`;
- device certification run: `30643501928`;
- exact-snapshot promotion run: `30644134769`;
- reviewed promotion PR: `#93`;
- stable deployment run: `30644515552`.

The certification ran against BlueStacks and X88 Pro 20. The stable workflow
copied the certified snapshot payload without rebuilding component ZIPs. A
post-deploy HTTP check downloaded the public stable ZIP and reproduced the
SHA-256 above.

## Device results

| Device | Kodi | Stable origin | Isolated signed check | Production sync | Apply/rollback |
|---|---:|---|---|---|---|
| BlueStacks1 | 21.3 | pass | pass | pass | pass |
| X88 Pro 20 | 21.3 | pass | pass | pass | pass |
| Sony TV | 21.3 | pass | pass | paired; active revision discovered | pass |

BlueStacks and X88 retained their original production enrollment byte-for-byte
after the isolated test. Sony received a separate production enrollment. No
pairing code, access token, signing seed or credential is present in this
report. One-time pairing files were removed after use.

The X88 production probe exposed a lossy one-shot EventServer launch. The E2E
harness now prefers JSON-RPC and falls back to EventServer. The isolated probe
also now removes production state only inside its temporary transaction,
waits for an explicit cleanup marker and restores the original state before
reporting success.

## Portable state and repositories

The final read-only audit on BlueStacks, X88 and Sony returned `OK` for every
device and the same favourites digest. Each had:

- 8 favourites;
- 7 current WatchNixtoons2 actions;
- 7 portable WatchNixtoons2 items;
- no missing artwork files;
- a unique, consistent Profile Sync logical identity and production
  enrollment.

After promotion, the testing repository was removed from BlueStacks and X88.
All three devices expose only `repository.mwodevelop` 1.0.0 and the official
Kodi repository, and all five mwoDevelop components have stable origin.

Bedroom TV and both NUC accounts were unavailable and are deliberately not
reported as passing this final rollout.

## Reproducible checks

```bash
PYTHON=/path/to/venv/bin/python tests/e2e/run.sh
PYTHONPATH=. /path/to/venv/bin/python \
  tests/e2e/profile_sync_addon_device.py \
  --repository-channel stable --device <logical-device-id> \
  --devices /path/to/private/devices.json \
  --server-repository /path/to/kodi-profile-sync-server
PYTHONPATH=. /path/to/venv/bin/python \
  tests/e2e/profile_sync_production_device.py \
  --action sync --device <logical-device-id> \
  --devices /path/to/private/devices.json \
  --server-url https://<private-qnap>:18765 \
  --ca-certificate /path/to/private/ca.crt
PYTHONPATH=. /path/to/venv/bin/python \
  tools/kodi_portable_state_rollout.py audit \
  --devices /path/to/private/devices.json \
  --references /path/to/private/.env
```

The repository build was generated twice and compared recursively. The final
suite result was `275 passed`.
