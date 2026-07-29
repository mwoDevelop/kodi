# Available-device regression

Date: 2026-07-29

## Scope

The live regression covered every currently reachable registered Kodi
consumer:

- BlueStacks1 (`SM-S901E`);
- Sony TV (`BRAVIA 4K GB ATV3`);
- X88 Pro 20 (`X88Pro20`).

Bedroom TV was unavailable over ADB. Both NUC Flatpak principals were
unavailable over SSH and are not reported as tested.

All three reachable Android devices ran Kodi 21.3 without an active VPN
transport during this pass.

## Results

Each reachable device passed:

- stable Profile Sync 0.1.6 origin, pairing, authenticated heartbeat, signed
  candidate check and the read-only no-apply invariant;
- Umbrella 6.7.81.18 search for `House of the Dragon`;
- Umbrella playback through Real-Debrid for at least 15 seconds;
- WatchNixtoons2 0.26.1 live catalogue and controlled playback for 15 seconds;
- reversible Profile Sync successful apply, injected failure, rollback,
  quarantine, exact settings restoration and journal cleanup.

Private redacted JSON reports remain below `.kodi-private/e2e` and are not
committed.

## Runner fixes discovered by live E2E

- Dismiss only the exact harmless Kodi PVR information dialog and a stale
  shutdown menu; unexpected dialogs still fail the search test.
- Use an Android key-event fallback when Kodi JSON-RPC acknowledges a modal
  action but the Android TV dialog remains open.
- Read add-on versions through Kodi when Android scoped storage hides
  `addon.xml`.
- Accept Kodi foreground focus on any Android display, which is required by
  the multi-display BlueStacks runtime.
- Include representative `premiered` metadata in direct Umbrella fixtures,
  matching normal enriched navigation.
- Send Kodi EventServer packets directly from the host for LAN ADB targets
  whose Android firmware has no `nc`; loopback/emulator targets remain
  default-deny.

The fixes affect only host-side E2E and restore tooling. No Kodi add-on payload
or stable repository artifact changed, so no add-on release was required.

## Reproducible repository verification

```text
.venv/bin/pytest -q: 166 passed
tests/e2e/run.sh: deterministic build passed; 166 passed
```
