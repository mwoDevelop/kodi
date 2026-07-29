# QNAP upstream synchronization watchdog

This independent Container Station service polls the latest run of every
scheduled upstream workflow. It becomes unhealthy when a workflow is missing,
failed, or older than 36 hours, so a missing GitHub cron cannot hide itself.

The service uses only public GitHub API reads. It has no repository write
token, volumes, published ports, capabilities, or writable root filesystem.
Deploy only an immutable multi-architecture GHCR digest:

```bash
docker compose \
  --env-file deploy/qnap-upstream-watchdog/env.example \
  -f deploy/qnap-upstream-watchdog/compose.yaml config
```

Configure Container Station/QTS to notify on an unhealthy container. The
status document stays in a 1 MiB tmpfs and contains only workflow IDs, times,
conclusions, and repository names.
