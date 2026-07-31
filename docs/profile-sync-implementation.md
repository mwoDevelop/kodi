# Profile sync implementation status

Date: 2026-07-31

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
- Android lifecycle inventory qualified live on BlueStacks, Sony TV,
  Bedroom TV and X88 Pro 20;
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
- add-on 0.1.6 testing candidate reads schema 2 and applies signed schema 3
  layers selected from server-bound target tags; Bedroom TV passed
  testing-repository install, pairing, authenticated heartbeat, signed
  candidate verification and the read-only no-apply invariant;
- X88 Pro 20 passed clean Kodi 21.3 restore and stable-origin verification.
  BlueStacks, Sony TV and X88 Pro 20 all passed Profile Sync 0.1.6
  pairing/read-only E2E and a reversible in-process apply canary covering
  successful apply, injected failure, rollback, quarantine, journal cleanup
  and byte-exact restoration of managed settings;
- QNAP Container Station Compose contract with an ARMv7 image gate;
- live QNAP preflight confirming Container Station 3, Docker 26, Compose 2,
  `overlay2`, sufficient capacity and an available Python 3.11 ARMv7 base
  image;
- immutable server 0.1.0 GHCR manifest qualified for `linux/amd64` and
  `linux/arm/v7`;
- isolated QNAP 6A smoke with `/ready`, database schema 2, process restart,
  controlled unavailability/recovery and zero remaining Compose resources;
- production QNAP lifecycle with a fixed managed root, healthy-RAID gate,
  immutable-image enforcement, pinned SSH host key, verified TLS 1.2+ and
  confined read-only security mounts;
- online SQLite backup, atomic off-NAS download, AES-256-GCM encryption and a
  successful decrypt plus SQLite integrity restore drill;
- separate `kodi.favourites` portable-state adapter for user content that must
  not be embedded in semantic routine settings revisions;
- deterministic exact-inventory bundle generation, bounded file/XML
  validation, content-addressed artwork verification and transactional
  apply/recovery;
- legacy WatchNixtoons2 favourite-action migration to the mwoDevelop add-on ID;
- `.env`-driven authoritative sync membership, publisher and network
  endpoints, with logical identity and expected hardware retained in the
  private registry;
- repeatable Android rollout with in-Kodi audit, JSON-RPC/EventServer
  fallbacks, post-apply convergence proof and `NO_CHANGE` idempotence;
- per-device Profile Sync identity profiles sourced from `.env` and the
  logical registry, without cloning enrollment tokens or signing seeds;
- identity-preserving device E2E cleanup: temporary verified-backend pairing
  restores the previous settings and state instead of blanking the profile.

## Private state

The migration created:

```text
.kodi-private/devices.json
.kodi-private/devices.json.schema1.bak
.kodi-private/kodi-reinstall.json
.kodi-private/kodi-reinstall.json.schema1.bak
.kodi-private/routine/bluestacks1.json
.kodi-private/portable-state/<bundle-sha256>.zip
```

All files remain ignored by Git. The mode-`0600` `.env` additionally contains
`KODI_SYNC_PUBLISHER`, `KODI_SYNC_DEVICES` and per-logical-device ADB/SSH host
keys. It also stores the Profile Sync channel, startup delay, interval and
read-only policy. These values are not written to public fixtures or test
output.

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
.venv/bin/python tools/kodi_portable_state_rollout.py audit \
  --result .kodi-private/e2e/portable-state-audit.json
.venv/bin/python tools/kodi_portable_state_rollout.py sync \
  --result .kodi-private/e2e/portable-state-sync.json
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

The production backend is active on QNAP using the immutable server 0.2.0
multi-architecture image, a dedicated private CA and verified TLS. Live
preflight reports RAID `[UU]` with no recovery in progress. The initial
off-NAS backup passed authenticated encryption, byte-exact decryption and
`PRAGMA integrity_check=ok` on schema 2.

Remaining rollout work is the signed production assignment/apply/rollback
qualification in device order, followed by exact-candidate promotion. Client
enrollment tokens remain device-local by design and are not copied into the
portable profile or disaster-recovery archive.

Linux/Flatpak host support additionally remains read-only until:

- the NUC is reachable again; separate SSH keys are already enrolled for both
  accounts and passed positive plus cross-account rejection checks;
- `special://home` and `special://profile` are qualified from inside the real
  Flatpak Kodi process;
- repository bootstrap uses a supported Kodi UI/API path or returns
  `BOOTSTRAP_REQUIRES_USER`.

The portable-state rollout follows the same gate. An unreachable NUC is
reported as `UNAVAILABLE`; a reachable NUC still refuses mutation until its
real in-process profile path is qualified. Android devices do not share this
blocker because the adapter runs inside Kodi and resolves
`special://profile` there.

Android identity profiles can be prepared before that gate: each device has
its own `logical_device_id`, channel and schedule, but stays `UNPAIRED` with no
server URL. Live 2026-07-30 E2E on BlueStacks, Sony TV and X88 Pro 20 passed
unique pairing, authenticated heartbeat, signed assignment discovery,
successful settings apply, injected-failure rollback, journal cleanup and
byte-exact settings restoration. Persistent enrollment remains gated on the
authenticated HTTPS production endpoint.

Revision schema 3 and administratively bound compatibility tags are now
implemented in the generator, server and add-on. Read-only rollout passed on
Bedroom TV and X88 Pro 20. BlueStacks, Sony TV and X88 passed the isolated
journaled apply/rollback canary; signed backend assignment-to-apply and the
remaining target matrix remain release gates.

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
