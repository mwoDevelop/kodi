# QNAP profile sync container

This is the only supported backend deployment shape. It is intended for a
Container Station 3 application backed by Docker Compose.

Safety constraints:

- set `PROFILE_SYNC_IMAGE` to an immutable multi-architecture digest;
- keep the published port bound to QNAP loopback and terminate authenticated
  HTTPS in the QNAP reverse proxy;
- mount the SQLite/blob data and public-key registry from dedicated paths;
- keep the root filesystem read-only and capabilities dropped;
- never use `--unsafe-accept-signatures` in this deployment;
- back up the database through the application backup operation, not by
  copying a live WAL database file.

The current QNAP remains blocked for production deployment while its RAID1 is
degraded. This Compose contract can be validated locally and in CI before the
storage gate is cleared.
