# Profile sync implementation status

Date: 2026-07-27

## Implemented

- `manifests/devices.schema.json` with compatible schema 1/2 validation and a
  redacted Android/Flatpak schema 2 example;
- private device inventory loader normalizing schema 1/2 to the internal v2
  model;
- idempotent, atomic registry 1 -> 2 migration with a private backup and
  byte-equivalent endpoint assertion;
- opaque per-account principal IDs, explicit platform, physical host grouping
  and exactly one neutral ADB/SSH transport;
- separate `AdbTransport`/`SshTransport` and
  `AndroidKodiLifecycle`/`FlatpakKodiLifecycle` contracts;
- read-only `tools/kodi_inventory.py` with redacted output;
- pinned SSH host keys, private-key mode checks, disabled agent forwarding,
  UID/home/owner validation and symlink-escape rejection;
- Android lifecycle inventory qualified live on BlueStacks, Sony TV and
  Bedroom TV;
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
- authenticated immutable revision download in the server;
- add-on 0.1.5 testing candidate with a default-deny Umbrella adapter,
  private pre-write journal, startup recovery, health check, rollback and
  revision quarantine; device apply E2E is still pending;
- add-on 0.1.5 read-only regression passed on BlueStacks and Sony after
  verifying the real service disable/enable lifecycle;
- QNAP Container Station Compose contract with an ARMv7 image gate;
- live QNAP preflight confirming Container Station 3, Docker 26, Compose 2,
  `overlay2`, sufficient capacity and an available Python 3.11 ARMv7 base
  image.

## Private state

The migration created:

```text
.kodi-private/devices.json
.kodi-private/devices.json.schema1.bak
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
python tools/kodi_inventory.py bluestacks1 \
  --adb /home/mwo/android-sdk/platform-tools/adb \
  --adb-server-port 5038
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

Linux/Flatpak host support additionally remains read-only until:

- the NUC is reachable and separate SSH keys are enrolled for both accounts;
- `special://home` and `special://profile` are qualified from inside the real
  Flatpak Kodi process;
- repository bootstrap uses a supported Kodi UI/API path or returns
  `BOOTSTRAP_REQUIRES_USER`.

Revision schema 3 and administratively bound compatibility tags are now
implemented in the generator, server and add-on. Device rollout remains the
release gate.

## Layered routine revisions

Schema 2 remains readable and exports only the portable common subset.
Schema 3 contains `base.adapters` and a canonically ordered `layers` array.
Class layers selected by `all_target_tags` precede layers selected by
`logical_device_id`. Target tags are assigned during server-side enrollment
and must match the signed candidate assignment; heartbeat observations never
select a layer.

Generate schema 3 explicitly:

```bash
python tools/kodi_routine_profile.py \
  /path/to/kodi/profile \
  /path/to/revision.json \
  --kodi-major 21 \
  --revision-schema 3
```
