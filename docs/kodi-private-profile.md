# Private Kodi profile snapshots

This workflow restores a new Android Kodi installation without committing
credentials or tokens. Private snapshots live under `.kodi-private/`, which is
excluded from Git, Docker build contexts, and normal repository artifacts.

The snapshot is intentionally unencrypted in schema 1. Treat the directory as
secret material: keep it mode `0700`, do not attach it to issues or releases,
and do not copy it to an untrusted backup target. The next storage phase should
encrypt the snapshot before it is allowed into Git, for example with `age` or
SOPS and keys held outside this repository.

## Contents

The policy is defined in
`manifests/kodi-profile-policy.json`. It retains:

- installed add-on code and manifests, including the selected skin;
- top-level Kodi XML/JSON settings, sources, keymaps, playlists, and profiles;
- each add-on's persistent `addon_data`, including Umbrella and Real-Debrid
  credentials;
- the selected skin's settings;
- the exact Android Kodi APK needed to reproduce the installation.

It excludes:

- Kodi databases, thumbnails, peripheral data, logs, temporary files, and
  downloaded add-on packages;
- Umbrella artwork, provider, search, metadata, Trakt synchronization, and
  other rebuildable caches;
- every add-on `cache/` and `temp/` directory.

Kodi rebuilds its add-on database after restore. Media-library databases are
deferred from schema 1 because replacing a live Kodi database is not an atomic
or portable operation. This follows Kodi's distinction between persistent
[userdata](https://kodi.wiki/view/Userdata) and a broader full-profile
[backup](https://kodi.wiki/view/Backup).

## Export

From the repository root:

```bash
mkdir -p .kodi-private/snapshots
chmod 700 .kodi-private .kodi-private/snapshots

.venv/bin/python tools/kodi_profile.py \
  --serial 127.0.0.1:5555 \
  export \
  --output .kodi-private/snapshots/bluestacks1-$(date -u +%Y%m%dT%H%M%SZ)
```

The exporter briefly stops Kodi to obtain a coherent settings snapshot and
starts it again afterward. It validates that the destination is below the
Git-ignored private directory, records SHA-256 for every file, and writes the
snapshot only after the complete export succeeds.

Verify a snapshot before using or copying it:

```bash
.venv/bin/python tools/kodi_profile.py verify \
  .kodi-private/snapshots/SNAPSHOT_NAME
```

## Restore on a clean Android device

The target must be reachable through ADB and compatible with the recorded Kodi
version and CPU ABI:

```bash
.venv/bin/python tools/kodi_profile.py \
  --serial 127.0.0.1:5715 \
  install-kodi \
  .kodi-private/snapshots/SNAPSHOT_NAME

.venv/bin/python tools/kodi_profile.py \
  --serial 127.0.0.1:5715 \
  restore \
  .kodi-private/snapshots/SNAPSHOT_NAME
```

The installer grants Kodi's required Android media permissions. Restore runs
inside Kodi's own process, verifies every archived file before replacing it,
rebuilds the add-on inventory, enables the recorded add-ons, activates the
recorded skin, and removes its temporary transfer files.

The tool prints counts and snapshot identifiers only. It never prints add-on
settings, credentials, tokens, magnets, or resolved streaming URLs.

## Validation checklist

After restore:

1. `verify` the local snapshot again.
2. Confirm `JSONRPC.Ping`, the active skin, and the enabled state of required
   add-ons.
3. Run `tests/e2e/umbrella_search_e2e.py` for a real Umbrella search.
4. Run `tests/e2e/sony_kodi_matrix.py --direct-play` for at least one film and
   one episode.
5. Run `tests/e2e/sony_watchnixtoons2.py` for catalogue and playback coverage.

The E2E runners redact credentials, magnets, plug-in URLs, and resolved media
URLs from their reports.
