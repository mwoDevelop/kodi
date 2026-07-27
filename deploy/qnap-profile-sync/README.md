# QNAP profile sync container

This is the only supported backend deployment shape. It is intended for a
Container Station 3 application backed by Docker Compose.

Safety constraints:

- set `PROFILE_SYNC_IMAGE` to an immutable multi-architecture digest;
- keep the published port bound to QNAP loopback and terminate authenticated
  HTTPS in the QNAP reverse proxy;
- mount the SQLite/blob data and public-key registry from dedicated paths;
- render with an explicit Compose project name; do not add `container_name`;
- keep the root filesystem read-only and capabilities dropped;
- never use `--unsafe-accept-signatures` in this deployment;
- back up the database through the application backup operation, not by
  copying a live WAL database file.

The current QNAP remains blocked for production deployment while its RAID1 is
degraded. This Compose contract can be validated locally and in CI before the
storage gate is cleared.

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
