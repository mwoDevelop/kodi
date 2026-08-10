# QNAP profile sync container

For routine builds and deployments shared with the other Kodi QNAP services,
use [`tools/qnap_images.py`](../../docs/qnap-images.md). The commands below
remain the lower-level Profile Sync lifecycle and recovery interface.

This is the only supported backend deployment shape. It is intended for a
Container Station 3 application backed by Docker Compose.

The host lifecycle targets `/var/run/docker.sock`, the Docker engine managed
and displayed by the Container Station 3 GUI. Do not deploy this project to
the separate `/var/run/system-docker.sock` engine.

Safety constraints:

- set `PROFILE_SYNC_IMAGE` to an immutable multi-architecture digest;
- bind the published port to one explicit LAN address and serve verified TLS
  directly from the container;
- mount the SQLite/blob data and public-key registry from dedicated paths;
- mount the TLS certificate and private key read-only; clients must trust the
  dedicated private CA instead of disabling certificate verification;
- render with an explicit Compose project name; do not add `container_name`;
- keep the root filesystem read-only and capabilities dropped;
- never use `--unsafe-accept-signatures` in this deployment;
- back up the database through the application backup operation, not by
  copying a live WAL database file.

The host lifecycle refuses production deployment unless all RAID members are
online, no rebuild is running, the image is pinned by digest, the SSH host key
is pinned and all private files have restrictive permissions.

Deploy and verify production through the confined host lifecycle:

```bash
python tools/qnap_profile_sync.py --references .env deploy-production \
  --image ghcr.io/mwodevelop/kodi-profile-sync-server@sha256:<digest> \
  --host-ip 192.0.2.39 \
  --key-registry /private/key-registry.json \
  --tls-certificate /private/server.crt \
  --tls-key /private/server.key \
  --ca-certificate /private/ca.crt
python tools/qnap_profile_sync.py --references .env verify-production \
  --host-ip 192.0.2.39 --ca-certificate /private/ca.crt
```

Create an online SQLite backup and copy it off the NAS. Interrupted downloads
can be resumed without recreating or overwriting the server-side backup:

```bash
python tools/qnap_profile_sync.py --references .env backup-production \
  --backup-id production-20260731 --output /private/production.sqlite
python tools/qnap_profile_sync.py --references .env \
  download-production-backup \
  --backup-id production-20260731 --output /private/production.sqlite
```

Encrypt the off-NAS copy with a separate mode-`0600`, 32-byte key and perform
a decrypt plus SQLite integrity drill before considering the backup complete:

```bash
python tools/profile_sync_backup.py encrypt \
  --input /private/production.sqlite \
  --output /private/production.sqlite.mwobak \
  --key-file ~/.config/mwodevelop/profile-sync-backup.key
python tools/profile_sync_backup.py decrypt \
  --input /private/production.sqlite.mwobak \
  --output /tmp/profile-sync-restore.sqlite \
  --key-file ~/.config/mwodevelop/profile-sync-backup.key
sqlite3 /tmp/profile-sync-restore.sqlite 'PRAGMA integrity_check;'
```

Validate production policy without starting a container:

```bash
python tools/qnap_compose_policy.py \
  --mode production \
  --allow-placeholder \
  --env-file deploy/qnap-profile-sync/env.example
```

Validate the isolated smoke overlay:

```bash
python tools/qnap_compose_policy.py \
  --mode smoke \
  --allow-placeholder \
  --env-file deploy/qnap-profile-sync/smoke.env.example
```

The smoke environment is a template only. A run must replace the image with
an immutable 64-hex digest and use a new one-time directory outside
`/share/ProfileSync`. Smoke data, key registry, project, port and tunnels must
be removed after the test.
