# mwoDevelop Kodi repository

Reproducible publisher for the `mwoDevelop` Umbrella fork, MwoScrapers, and
WatchNixtoons2.

## Build

```bash
python3 tools/build_repo.py --output dist
python3 -m pytest
```

The build is deterministic: independent stable/testing locks, component
commits, file contents, and fixed ZIP metadata completely define `dist/`.

## Install stable

Add this address as a Kodi file source:

<https://mwodevelop.github.io/kodi/repo>

Then use `Add-ons -> Install from zip file`, open that source and install
`repository.mwodevelop-1.0.0.zip`.

The repository ZIP is also available directly from:

<https://mwodevelop.github.io/kodi/repository.mwodevelop-1.0.0.zip>

Open `mwoDevelop Add-ons`, then install Umbrella only. Kodi automatically
installs the MwoScrapers module as its required technical dependency.
`MwoScrapers Manager` is an optional, separately installable Program add-on
that opens provider settings and reports their enabled/disabled state.

## Install testing

Install `repository.mwodevelop.testing-1.0.0.zip` from:

<https://mwodevelop.github.io/kodi/repository.mwodevelop.testing-1.0.0.zip>

Use testing only for release candidates. The channel contains Umbrella, the
technical `script.module.mwoscrapers` dependency, and the separately visible
`script.mwoscrapers` manager. WatchNixtoons2 release candidates are published
here for side-by-side playback testing before promotion to stable.

## Reproducible E2E

```bash
tests/e2e/run.sh
```

or in an isolated container:

```bash
tests/e2e/run-docker.sh
```

The scenario performs two independent builds, compares every byte, serves the
repository over HTTP, installs Umbrella and recursively resolves MwoScrapers
from the repository metadata, validates the provider contract, and compiles the
downstream resolver.

## Private Kodi configuration

`tools/kodi_profile.py` exports and restores installed add-ons, their settings
and credentials, and the selected skin while excluding caches and generated
databases. Unencrypted snapshots are restricted to the Git-ignored
`.kodi-private/` directory.

`tools/kodi_reinstall.py` adds a dry-run-first host workflow for a verified
uninstall, Kodi storage cleanup, ABI-matched APK installation, snapshot
restore, and live add-on/skin validation.

The private device inventory accepts legacy schema 1 and schema 2. Migrate it
atomically after a dry run, marking emulators explicitly:

```bash
python3 tools/kodi_devices.py migrate-registry \
  --platform bluestacks1=android-emulator
python3 tools/kodi_devices.py migrate-registry \
  --platform bluestacks1=android-emulator \
  --yes
```

Read-only platform inventory resolves the neutral transport and Kodi lifecycle
without printing endpoints, usernames, home paths or private references:

```bash
python3 tools/kodi_inventory.py bluestacks1 \
  --adb /home/mwo/android-sdk/platform-tools/adb \
  --adb-server-port 5038
```

See [Private Kodi profile snapshots](docs/kodi-private-profile.md) for the
security boundary, exact contents, commands, and reproducible device checks.
