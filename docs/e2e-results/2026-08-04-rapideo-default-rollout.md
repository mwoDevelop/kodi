# Rapideo default add-on rollout — 2026-08-04

The official Rapideo repository `1.0.4`, Rapideo plug-in `1.5.0`, and the Kodi
mirror build of `script.module.xbmcswift2` `19.0.7` were reconciled on the four
available Android Kodi installations: BlueStacks1, X88 Pro 20, Sony TV, and
Bedroom TV.

Evidence:

- every downloaded archive matched its pinned SHA-256 and `addon.xml` identity;
- repository and plug-in add-ons were enabled on all four devices;
- Rapideo was assigned to `repository.rapideo_pl`, while xbmcswift2 was assigned
  to Kodi's built-in `repository.xbmc.org`;
- `Files.GetDirectory(plugin://plugin.video.rapideo_pl/)` returned three root
  menu items on every device without a Python error;
- a repeated X88 reconciliation reported all three managed add-ons as
  `unchanged`;
- X88 was restored from verified snapshot
  `ae3be132353673c4184874a8022eb99bf3b1b8a82946771d144cfec04b9bcdb4`
  after a legacy ADB-owned orphan directory was found.

The two registered Linux Flatpak profiles could not be audited or changed in
this run because their pinned SSH transport returned exit code 255. This is an
availability exception, not a successful rollout claim.

## Final convergence

The X88 clean-profile repair restored an older stable snapshot, so the final
matrix audit also reconciled the current stable Umbrella `6.7.81.20`,
mwoScrapers `0.1.10`, WatchNixtoons2 `0.26.1`, and Profile Sync `1.0.1`.
Profile Sync received a new one-time production enrollment and an
offline-signed bootstrap assignment for the active `home-stable` revision. The
first sync applied it and the repeat sync returned `NO_CHANGE` with no pending
report.

With the X88 always-on OpenVPN tunnel validated, public Torrentio returned HTTP
403 while public Comet returned 132 sanitized source records. Both providers
remain enabled, so the working provider is retained instead of treating the
Torrentio VPN policy as an empty-search result. Umbrella then resolved and
played the open Sintel test asset for 10 seconds through Real-Debrid; resolver
startup took 52.886 seconds. The BlueStacks and X88 Real-Debrid probes both
reported a premium account and the expected code-37 `disabled_endpoint`
mapping as healthy.

The final four-device portable-state audit reported the same eight favourites,
seven portable WatchNixtoons2 entries, no missing artwork, Profile Sync `1.0.1`
and `NO_CHANGE` on BlueStacks1, X88 Pro 20, Sony TV, and Bedroom TV. All four
also use Umbrella `6.7.81.20` from `repository.mwodevelop`, Rapideo `1.5.0` from
`repository.rapideo_pl`, and xbmcswift2 `19.0.7` from
`repository.xbmc.org`.
