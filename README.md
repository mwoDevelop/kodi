# mwoDevelop Kodi repository

Reproducible publisher for the `mwoDevelop` Umbrella fork and MwoScrapers.

## Build

```bash
python3 tools/build_repo.py --output dist
python3 -m pytest
```

The build is deterministic: the component commits, channel manifest, file
contents, and fixed ZIP metadata completely define `dist/`.

## Install testing

Install `repository.mwodevelop.testing-1.0.0.zip` from:

<https://mwodevelop.github.io/kodi/repository.mwodevelop.testing-1.0.0.zip>

The testing repository contains `plugin.video.umbrella` and
`script.module.mwoscrapers`. The stable repository is intentionally empty
until the BlueStacks and clean-profile E2E gates pass.

## Reproducible E2E

```bash
tests/e2e/run.sh
```

or in an isolated container:

```bash
tests/e2e/run-docker.sh
```

The scenario performs two independent builds, compares every byte, serves the
repository over HTTP, downloads and installs both add-ons into a temporary Kodi
profile, validates the provider contract, and compiles the downstream resolver.
