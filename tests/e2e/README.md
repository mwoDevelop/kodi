# Reproducible E2E

Run from any directory:

```bash
/home/mwo/projects/kodi/tests/e2e/run.sh
```

The script:

1. removes only `/home/mwo/projects/kodi/.e2e`;
2. builds two complete repository snapshots;
3. compares them recursively;
4. starts a temporary local HTTP repository;
5. downloads and extracts MwoScrapers and Umbrella like a Kodi profile;
6. loads the external provider registry;
7. compiles the isolated downstream resolver files;
8. executes repository structure, dependency, provenance, and ZIP safety tests.

Container form:

```bash
/home/mwo/projects/kodi/tests/e2e/run-docker.sh
```

The container wrapper requires a running Docker daemon. CI uses the native
script in a fresh GitHub runner, which provides the same clean-filesystem
property without requiring Docker-in-Docker.
