# mwoDevelop Kodi repository

Reproducible publisher for the `mwoDevelop` Umbrella fork and MwoScrapers.

## Build

```bash
python3 tools/build_repo.py --output dist
python3 -m pytest
```

The build is deterministic: independent stable/testing locks, component
commits, file contents, and fixed ZIP metadata completely define `dist/`.

## Install stable

Install `repository.mwodevelop-1.0.0.zip` from:

<https://mwodevelop.github.io/kodi/repository.mwodevelop-1.0.0.zip>

Open `mwoDevelop Add-ons`, then install Umbrella only. Kodi automatically
installs MwoScrapers as its required technical dependency.

## Install testing

Install `repository.mwodevelop.testing-1.0.0.zip` from:

<https://mwodevelop.github.io/kodi/repository.mwodevelop.testing-1.0.0.zip>

Use testing only for release candidates. Both channel indexes contain
`plugin.video.umbrella` and `script.module.mwoscrapers`, but the user-facing
installation remains Umbrella only.

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
