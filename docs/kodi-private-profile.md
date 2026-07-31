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
- content-addressed local artwork for WatchNixtoons2 favourites;
- the selected skin's settings;
- the exact Android Kodi APK needed to reproduce the installation.

It excludes:

- Kodi databases, thumbnails, peripheral data, logs, temporary files, and
downloaded add-on packages;
- Umbrella artwork, provider, search, metadata, Trakt synchronization, and
  other rebuildable caches;
- every add-on `cache/` and `temp/` directory.

WatchNixtoons2 favourites are a deliberate exception to the generic thumbnail
cache exclusion. During export, known legacy CDN URLs are normalized to the
current image host, downloaded with bounded size and image validation, and
stored under `userdata/favourite-artwork/`. `favourites.xml` then references a
content-addressed `special://profile/` path. A small source manifest permits a
later export to refresh the image; if the CDN is temporarily unavailable, the
last verified local image is retained. Cookies and URL header suffixes are
neither used nor persisted.

The routine profile service deliberately manages a small semantic settings
allowlist; it does not carry user content or binary artwork. Favourites use a
separate portable-state adapter so one complete canonical list and its exact
content-addressed artwork set converge together.

The authoritative private rollout membership, publisher and current network
addresses live in the mode-`0600` `.env`:

```bash
KODI_SYNC_PUBLISHER=sony-tv
KODI_SYNC_DEVICES=bluestacks1,sony-tv,bedroom-tv,x88pro20,nuc-mwo,nuc-alek
KODI_DEVICE_SONY_TV_ADB=192.0.2.10:5555
KODI_DEVICE_NUC_MWO_SSH_HOST=192.0.2.20
KODI_PROFILE_SYNC_CHANNEL=home-stable
KODI_PROFILE_SYNC_STARTUP_DELAY_SECONDS=15
KODI_PROFILE_SYNC_INTERVAL_HOURS=6
KODI_PROFILE_SYNC_READ_ONLY=true
```

Logical identity, platform, expected model and credentials references remain
in `.kodi-private/devices.json`; `.env` is authoritative for membership and
network endpoints. The selected publisher must also have the `publisher` role
in that registry.

Audit without changing favourites:

```bash
.venv/bin/python tools/kodi_portable_state_rollout.py audit \
  --result .kodi-private/e2e/portable-state-audit.json
```

Converge every currently reachable target:

```bash
.venv/bin/python tools/kodi_portable_state_rollout.py sync \
  --result .kodi-private/e2e/portable-state-sync.json
```

Before export, legacy WatchNixtoons2 actions are migrated to
`plugin.video.watchnixtoons2.mwodevelop` and verified remote artwork is
materialized. The publisher then creates a deterministic ZIP below
`.kodi-private/portable-state/`. Every target validates the exact archive
inventory, SHA-256 and referenced artwork set, applies it with a private
journal and rollback, restarts Kodi only after a change, and verifies the
result from inside Kodi. The same rollout configures the non-secret
`mwoDevelop Profile Sync` identity and schedule per logical device. Enrollment
tokens and signing seeds are never copied between devices. A repeated
application returns `NO_CHANGE`.

Until a persistent authenticated HTTPS backend is available, the identity
profile remains deliberately `UNPAIRED` with an empty server URL. The device
E2E uses a temporary verified backend and a distinct one-time enrollment for
every device, then restores the previous identity settings and state. It must
not leave a token tied to a temporary endpoint.

Unavailable devices are reported and left unchanged. Linux/Flatpak remains
read-only until its real in-process `special://profile` path is qualified; the
tool never guesses a profile path for a write.

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

For Android TV devices without the shell utilities needed by the in-Kodi
transport, `tools/kodi_reinstall.py` also supports an explicit `adb-push`
restore mode. It stops Kodi, copies the already verified payload, lets Kodi
rebuild its databases, enables the recorded add-ons, persists the selected
skin, restarts Kodi, and validates the result over JSON-RPC.

The tools print counts and snapshot or bundle identifiers only. They never
print add-on settings, credentials, tokens, magnets, or resolved streaming
URLs.

## Clean reinstall from this host

Keep the target inventory in the ignored private file
`.kodi-private/kodi-reinstall.json`. Each entry pins the ADB serial and expected
model, snapshot, Kodi version, APK SHA-256, restore mode, and required add-ons.
It also maps restored custom add-ons to the repository that actually indexes
them, so Kodi retains automatic update ownership after rebuilding its add-on
database. The APK must also remain under `.kodi-private/`.

Preview and validate every target without changing either device:

```bash
./tools/kodi_reinstall.py
```

After reviewing the resolved model, version, ABI, and snapshot identifiers,
perform the authorized uninstall, cleanup, installation, restore, and
validation:

```bash
./tools/kodi_reinstall.py --yes
```

Limit the operation to one configured target, or repeat only the restore:

```bash
./tools/kodi_reinstall.py --target sony-tv --yes
./tools/kodi_reinstall.py --target sony-tv --restore-only --yes
```

If one add-on loses only a managed settings file, restore that exact file from
the already verified snapshot instead of replacing the whole profile:

```bash
.venv/bin/python tools/kodi_profile.py \
  --serial 192.168.1.8:5555 \
  restore-path .kodi-private/snapshots/sony-20260727T101733Z \
  --allow-kodi-upgrade \
  --allow-addon-upgrade \
  --path userdata/addon_data/plugin.video.umbrella/settings.xml
```

`restore-path` accepts only exact paths present in the verified snapshot
manifest and limits selective recovery to `userdata/`. For `addon_data`, it
also requires the snapshotted add-on to be installed at the same version;
`--allow-addon-upgrade` permits only an explicit forward move within the same
major line. The command creates a minimal archive containing those paths,
binds the result to a random operation ID and selection digest, serializes
restore operations with a device lock, and retries EventServer delivery only
until Kodi atomically acknowledges a single writer. After restarting Kodi and
allowing add-on services to load, it verifies every ordinary file by size and
SHA-256 inside Kodi before reporting success. An add-on `settings.xml` is
applied through Kodi's settings API so an active service cannot overwrite it
from stale memory, then verified by a canonical digest of the selected setting
IDs and values. If an add-on rotates or rejects an OAuth token during startup,
the strict post-restart check reports failure; refresh the source snapshot or
re-authorize that account instead of treating the stale credential as a
successful restore. A partial settings API failure is rolled back to its
pre-image. All device-side staging files are then removed; if cleanup cannot be
confirmed, the lock is retained for explicit recovery. The tool never prints
settings or credentials.

If the host process is interrupted and leaves the device lock behind, abort
and recover it explicitly (this stops Kodi before removing any staging data):

```bash
.venv/bin/python tools/kodi_profile.py \
  --serial 192.168.1.8:5555 \
  recover-lock
```

Do not run `recover-lock` while a restore that you want to finish is active.

The cleanup scope is deliberately fixed to the Kodi package and these paths:

- `/sdcard/Android/data/org.xbmc.kodi`;
- `/sdcard/Android/obb/org.xbmc.kodi`;
- `/sdcard/.kodi`.

Kodi 21.2 and 21.3 on Android TV use the same relevant profile layout:
`files/.kodi/addons/` and `files/.kodi/userdata/`. Directories such as
`media/`, `system/`, `temp/`, and versioned databases are generated by the
newly installed Kodi and are not evidence of a different Android TV profile
format.

Do not uninstall a superseded repository until its add-ons and their
`addon_data` have been backed up and a real-device migration test has passed.
Kodi may remove dependent add-ons and their user settings as part of repository
uninstallation even after their update origin has been reassigned. Prefer
leaving the old repository disabled until a verified cleanup workflow can
prove that the managed add-ons and settings survive.

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
