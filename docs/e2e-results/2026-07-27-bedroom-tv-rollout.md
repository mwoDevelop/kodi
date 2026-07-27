# Bedroom TV rollout checkpoint

Date: 2026-07-27

Target: private registry device `bedroom-tv` (Google TV Streamer, Android 14,
ARMv7 Kodi userspace).

## Completed

- read-only lifecycle inventory passed on Kodi 21.2;
- a private rollback snapshot was created before mutation;
- Kodi was upgraded to 21.3;
- the verified Sony Android TV snapshot was restored through the in-process
  Kodi restore path (4,277 managed files);
- Aeon Nox Silvo was activated;
- `repository.mwodevelop` 1.0.0, Umbrella 6.7.81.14, MwoScrapers 0.1.3,
  the MwoScrapers wrapper 0.1.1 and WatchNixtoons2 0.25.2 were present with
  the expected stable origin.

## Live defects found

1. A corrupt legacy `plugin.video.pov/addon.xml` containing only zero bytes
   prevented snapshot inventory. The host exporter now preserves corrupt
   payload bytes for rollback but does not mark such an add-on as safe to
   re-enable.
2. Android 14 did not permit the direct ADB profile path before Kodi first
   created it. The target now uses the supported in-process restore mode.
3. Google TV can freeze a background Kodi process when HDMI/ambient mode takes
   focus. Device E2E must wake the target and keep Kodi foregrounded.
4. The first playback checks stopped before provider resolution because a
   fresh restore has an empty Umbrella cache version marker. Umbrella
   6.7.81.15 treats that legacy marker as version zero and is published to
   testing; stable remains on 6.7.81.14 until the device rerun passes.
5. Device automation now prefers Kodi JSON-RPC for builtins and retains
   EventServer only as a fallback, avoiding a blocking Android `nc`.

## Host and publication evidence

- all 116 root repository E2E tests passed;
- Umbrella's 40 downstream tests and deterministic 27-patch reconstruction
  passed;
- the testing publication workflow completed successfully:
  <https://github.com/mwoDevelop/kodi/actions/runs/30299301112>;
- the public testing index exposes Umbrella 6.7.81.15 and
  `service.mwodevelop.profilesync` 0.1.6.

## Reproducible continuation

After Bedroom TV is powered on and ADB is authorized:

```bash
cd /home/mwo/projects/kodi

PYTHONPATH=. .venv/bin/python \
  tests/e2e/profile_sync_addon_device.py \
  --device bedroom-tv \
  --adb /home/mwo/android-sdk/platform-tools/adb \
  --adb-server-port 5037 \
  --server-repository /home/mwo/projects/kodi-profile-sync-server \
  --result .kodi-private/e2e/bedroom-tv-profile-sync-0.1.6.json
```

Then install/update Umbrella 6.7.81.15 from the testing channel and rerun at
least one movie and one episode through the resolver matrix. Promote to stable
only after the service log has no fresh-cache `ValueError` and both cases
reach controlled playback.

## Deferred target

`mwonuc` did not accept TCP/22 during this checkpoint. Its private registry
entries and per-account SSH keys cannot be safely qualified or rolled out
until the host is reachable; no NUC mutation was attempted.
