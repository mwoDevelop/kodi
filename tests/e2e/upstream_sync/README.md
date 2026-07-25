# Upstream synchronization E2E

Run from any directory:

```bash
/home/mwo/projects/kodi/tests/e2e/upstream_sync/run.sh
```

The test performs two independent live discovery passes and requires the
second pass to be byte-identical and `noop`. It then reconstructs Umbrella and
WatchNixtoons2 from their accepted upstream identities, audits every provider
observation, runs all component tests, materializes the exact stable/testing
locks into a fresh checkout, builds the Kodi repository twice and confirms
that the stable lock was not modified.

Reports are written to `.e2e/upstream-sync/`. The script has no write token and
does not create branches, pull requests or releases.
