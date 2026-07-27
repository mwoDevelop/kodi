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
- host-side `tools/profile_sync_admin.py`.

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
PYTHONPATH=src ../kodi/.venv/bin/python -m profile_sync_server.http \
  --database /tmp/mwo-profile-sync-smoke.sqlite \
  --port 18765 \
  --unsafe-accept-signatures
curl --fail http://127.0.0.1:18765/health
```

## Deliberate blockers

The server is not deployable to QNAP yet. Production remains blocked by:

- degraded RAID and missing confirmed off-NAS backup;
- no qualified enrollment signature implementation for Kodi ARMv7/x86;
- no production pairing/key registry;
- no encrypted-secret feasibility result;
- no Kodi service add-on or device E2E for routine apply.
