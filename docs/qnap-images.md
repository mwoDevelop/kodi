# QNAP image build and deployment

`tools/qnap_images.py` is the single host entry point for the three Kodi
Container Station applications:

- `profile-sync`;
- `provider-relay`;
- `upstream-watchdog`.

It dispatches repository-owned GitHub Actions builds, pushes multi-architecture
images to GHCR, verifies the required manifest platforms, records immutable
digest references under the Git-ignored `.kodi-private/qnap-images.json`, and
deploys only those digests. The build refuses a dirty or unpushed source
repository, so an image always maps to an exact Git commit.

## Common commands

Inspect the running QNAP containers without changing them:

```bash
python tools/qnap_images.py status
```

Preview all builds without logging into GHCR or invoking Docker:

```bash
python tools/qnap_images.py build all --dry-run
```

Build and push all images through GitHub Actions, then deploy their recorded
immutable digests:

```bash
python tools/qnap_images.py build all
python tools/qnap_images.py deploy all
```

The combined form is:

```bash
python tools/qnap_images.py update all
```

The GitHub Actions publisher is the default. It avoids distributing a local
long-lived `write:packages` token and waits for every workflow to finish before
resolving and recording its GHCR digest. An explicitly authenticated local
Buildx build remains available when needed:

```bash
python tools/qnap_images.py build all --publisher local
```

Replace `all` with one or more names for a partial operation:

```bash
python tools/qnap_images.py update upstream-watchdog
python tools/qnap_images.py build profile-sync provider-relay
```

The default Profile Sync server checkout is the sibling directory
`../kodi-profile-sync-server`. Override it explicitly when necessary:

```bash
python tools/qnap_images.py \
  --profile-sync-repository /path/to/kodi-profile-sync-server \
  build profile-sync
```

## Safety boundary

- `build` requires clean source repositories whose exact commits are the heads
  of pushed `origin` branches, plus an authenticated `gh` CLI;
- the default publisher uses short-lived repository `GITHUB_TOKEN` credentials
  inside Actions; the optional local publisher passes GHCR credentials to
  `docker login` over stdin and never writes them to the image-state file;
- Buildx publishes immutable multi-platform manifests and the script verifies
  their required `linux/amd64`, `linux/arm/v7` and, for the watchdog,
  `linux/arm64` entries;
- Profile Sync deployment retains the existing RAID, TLS, key-registry,
  backup and readiness gates;
- provider relay deployment retains the stateless Compose policy and live
  provider probe;
- watchdog deployment validates its hardened Compose policy and rolls the
  previous Compose files back if the new container cannot publish a complete
  five-workflow status document;
- the watchdog may be operational but intentionally `unhealthy` when one of
  the monitored GitHub workflows has failed. Deployment does not hide that
  upstream failure.

All three applications use `/var/run/docker.sock`, the engine managed by the
Container Station GUI. The script never targets QNAP `system-docker`.
