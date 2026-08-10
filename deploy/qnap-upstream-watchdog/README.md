# QNAP upstream synchronization watchdog

For routine builds and deployments shared with the other Kodi QNAP services,
use [`tools/qnap_images.py`](../../docs/qnap-images.md).

This independent Container Station service polls the latest run of every
scheduled upstream workflow. It becomes unhealthy when a workflow is missing,
failed, or older than 36 hours, so a missing GitHub cron cannot hide itself.

The process polls GitHub every six hours; Container Station evaluates the last
persisted result every five minutes. The versioned manifest includes central
reconciliation, the accepted-provider-artifact audit, provider discovery,
Umbrella and WatchNixtoons2. See the complete
[scheduled-process catalogue](../../docs/scheduled-processes.md) for ownership,
write boundaries and verification commands.

The service uses only public GitHub API reads. It has no repository write
token, volumes, published ports, capabilities, or writable root filesystem.
Deploy only an immutable multi-architecture GHCR digest:

Run Compose against `/var/run/docker.sock`, the engine managed and displayed
by the Container Station 3 GUI. Do not use the separate
`/var/run/system-docker.sock` engine.

```bash
docker compose \
  --env-file deploy/qnap-upstream-watchdog/env.example \
  -f deploy/qnap-upstream-watchdog/compose.yaml config
```

Configure Container Station/QTS to notify on an unhealthy container. The
status document stays in a 1 MiB tmpfs and contains only workflow IDs, times,
conclusions, and repository names.
