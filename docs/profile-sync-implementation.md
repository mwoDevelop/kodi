# Profile sync implementation status

Date: 2026-07-27

## Implemented

- `manifests/devices.schema.json` and redacted example;
- private device inventory validator and resolver;
- schema 1 -> 2 reinstall migration with a private backup;
- reinstall config resolution through `logical_device_id`;
- schema 2 profile policy with separate `disaster_recovery` and `routine`;
- semantic, default-deny routine export for Kodi core and selected Umbrella
  settings;
- typed values, deterministic revision ID and secret exclusion;
- local transactional SQLite server in the separate
  `kodi-profile-sync-server` checkout;
- candidate CAS, idempotency, canary assignments and report-gated promotion;
- loopback-only development HTTP API;
- host-side `tools/profile_sync_admin.py`;
- native Ed25519 qualified inside Kodi on BlueStacks x86 and Sony ARMv7;
- one-time pairing, per-installation enrollment/token/key and heartbeat;
- separate `service.mwodevelop.profilesync` repository with read-only checks;
- deterministic publication of the service add-on in the testing lock;
- device E2E for add-on 0.1.4 on BlueStacks x86 and Sony ARMv7, including
  testing-repository origin, pairing, authenticated heartbeat, signed
  candidate check and the read-only no-apply invariant;
- QNAP Container Station Compose contract with an ARMv7 image gate;
- live QNAP preflight confirming Container Station 3, Docker 26, Compose 2,
  `overlay2`, sufficient capacity and an available Python 3.11 ARMv7 base
  image.

## Private state

The migration created:

```text
.kodi-private/devices.json
.kodi-private/kodi-reinstall.json
.kodi-private/kodi-reinstall.json.schema1.bak
.kodi-private/routine/bluestacks1.json
```

All files remain ignored by Git. Endpoint values are emitted only by the
private inventory and are not written to public fixtures or test output.

## Reproducible checks

Main repository:

```bash
.venv/bin/pytest -q
python tools/kodi_devices.py validate
python tools/kodi_routine_profile.py \
  <private-snapshot>/payload \
  .kodi-private/routine/bluestacks1.json \
  --kodi-major 21
PYTHONPATH=. .venv/bin/python \
  tests/e2e/profile_sync_foundation_device.py
```

Server repository:

```bash
PYTHONPATH=src ../kodi/.venv/bin/pytest -q
PYTHONPATH=src ../kodi/.venv/bin/python \
  tests/e2e/verified_loopback.py
PYTHONPATH=src ../kodi/.venv/bin/python -m profile_sync_server.http \
  --database /tmp/mwo-profile-sync-smoke.sqlite \
  --port 18765 \
  --unsafe-accept-signatures
curl --fail http://127.0.0.1:18765/health
```

Kodi crypto capability:

```bash
PYTHONPATH=. .venv/bin/python \
  tests/e2e/profile_sync_crypto_spike.py
```

Kodi add-on on both registered devices:

```bash
PYTHONPATH=. .venv/bin/python \
  tests/e2e/profile_sync_addon_device.py \
  --device bluestacks1 \
  --device sony-tv \
  --result docs/e2e-results/2026-07-27-profile-sync-addon-devices.json
```

The test wakes Kodi before GUI installation, bootstraps the testing
repository when needed, and runs a single in-Kodi probe. The probe exposes
only status, enrollment ID and secret-presence booleans; token and signing
seed values never leave Kodi.

## Deliberate blockers

The backend is technically deployable as a multiarch Container Station
application, but production activation on the current QNAP remains blocked
by:

- degraded RAID and missing confirmed off-NAS backup;
- no protected production admin API/key rotation;
- no encrypted-secret feasibility result;
- no journaled routine apply/rollback device E2E.
