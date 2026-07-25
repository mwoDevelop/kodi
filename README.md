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

Install `repository.mwodevelop-1.0.0.zip` from:

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
