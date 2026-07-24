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
5. starts with Umbrella only and resolves MwoScrapers recursively from its
   required Kodi dependencies;
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

## BlueStacks1 / Kodi 21.3

Build `dist`, connect ADB to the `BlueStacks1` instance, then prepare a
recoverable device test:

```bash
python tests/e2e/bluestacks_e2e.py \
  --phase prepare \
  --adb /path/to/platform-tools/adb \
  --backup-dir .device-backups/bluestacks1-$(date +%Y%m%d-%H%M%S)
```

The clean dependency test requires Umbrella and MwoScrapers to be absent before
`prepare`; the script records that state after backing up the existing profile.
Install the copied repository ZIP and only Umbrella through Kodi's own add-on
manager, as printed by the script. Then validate installed IDs, versions,
their owning repository (`origin` in Kodi's add-on database), automatic
MwoScrapers installation, and the Kodi log:

```bash
python tests/e2e/bluestacks_e2e.py \
  --phase verify \
  --adb /path/to/platform-tools/adb \
  --backup-dir .device-backups/bluestacks1-YYYYMMDD-HHMMSS \
  --result docs/e2e-results/bluestacks1.json
```

The testing repository is expected by default. To exercise the production
channel, pass `--expected-origin repository.mwodevelop` to both `prepare` and
`verify`. This also selects the stable repository ZIP and fails if either
component remains attached to the testing channel.

After a controlled Sintel search, source selection, at least 30 seconds of
playback, and stopping Kodi's player, validate the media pipeline from the
redacted-safe log markers:

```bash
python tests/e2e/bluestacks_e2e.py \
  --phase playback \
  --adb /path/to/platform-tools/adb \
  --backup-dir .device-backups/bluestacks1-YYYYMMDD-HHMMSS \
  --result docs/e2e-results/bluestacks1.json \
  --sources 5 \
  --observed-seconds 30
```

This intentional three-phase design respects Android scoped storage and tests
the real Kodi repository path instead of injecting files into Kodi's profile.
