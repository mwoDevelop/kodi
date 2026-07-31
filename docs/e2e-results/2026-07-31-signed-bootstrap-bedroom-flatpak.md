# Signed bootstrap, Bedroom TV and Flatpak qualification

Date: 2026-07-31

## Released server path

- `kodi-profile-sync-server` 0.2.2 was merged and tagged after 21 unit tests
  and the verified-signature loopback E2E passed.
- The release workflow verified `linux/amd64` and `linux/arm/v7` for immutable
  image digest
  `sha256:11e1abac86c4ca1ec9e53106617f8bc1ef78cb3448641d315ad03f94e9b14e63`.
- QNAP preflight reported RAID `UU`, no recovery, then an integrity-checked
  69,632-byte database backup was downloaded before deployment.
- Production became ready on server 0.2.2, build
  `git:955ecee87787356d5cd7ed9490f7a42aaf175959`, database schema 2, with one
  container, one network and no Docker volume.

The bootstrap API accepts only an offline-promoter-signed assignment for an
existing non-revoked enrollment. Channel, exact active revision and sorted
administrative target tags must match server state. Released clients receive
the already supported signed `candidate` assignment shape; the server never
holds the promoter seed.

## Bedroom TV

- Kodi 21.3 and Profile Sync 0.1.8 from stable origin.
- Unique production enrollment on `home-stable` with `home` and
  `android-tv:armeabi-v7a` administrative tags.
- Signed active bootstrap accepted, exact active revision applied, signed
  success report stored, and no pending report remained.
- Post-rollout audit: 8 favourites, 7 portable WatchNixtoons2 actions, no
  missing artwork, consistent device identity, configured private CA and
  HTTPS endpoint.
- NordVPN 9.9.2-tv exposed a validated, non-bypassable VPN transport covering
  all UIDs. Umbrella 6.7.81.18 returned matching movie and TV search results
  after waking Kodi from Android TV dream mode. The first TV retry timed out
  while the device was dreaming; the same test passed after an explicit wake,
  so this was lifecycle state rather than a resolver regression.

## Linux Flatpak

Both `nuc-mwo` and `nuc-alek` passed pinned-SSH identity, owner, canonical
data-root, Kodi 21.3-Omega and x86_64 checks. Kodi's own runtime log mapped:

- `special://home` to the canonical per-account Flatpak data root;
- `special://masterprofile` and `special://profile` to that account's
  `userdata` directory;
- `special://envhome` to the exact SSH account home.

The lifecycle now validates these mappings and the log owner/type before
marking runtime paths qualified. The NUC suspended during repository staging,
became unreachable on SSH and did not wake from a standard magic packet.
Therefore no repository install, enrollment or portable-state mutation is
reported as complete for either NUC account.

## X88 Pro 20

NordVPN 9.9.2 sideload-tv still fails Android Keystore key generation with
`ProviderException` / `KeyStoreException: Unknown error`. The device exposes
no StrongBox feature and remains on a 2021 security patch. No VPN transport is
created. This is retained as a hardware/firmware limitation; no downgrade or
security bypass was applied.
