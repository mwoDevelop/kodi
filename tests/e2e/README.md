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

Verify the public file-source URL through Kodi's own HTTP directory and ZIP
engines:

```bash
python tests/e2e/kodi_http_source.py \
  --adb /home/mwo/android-sdk/platform-tools/adb \
  --serial emulator-5554
```

The check fails unless Kodi lists `repository.mwodevelop-1.0.0.zip`, downloads
and opens that archive, finds the `repository.mwodevelop` root, and reads its
`addon.xml` manifest.

## WatchNixtoons2 on BlueStacks1

Install `WatchNixtoons2 (mwoDevelop)` from the stable repository through Kodi's
GUI. Open `Latest Releases`, record the item count and available qualities,
play a selected quality for a controlled interval, then stop playback. Validate
the stable ownership, cleanup state, deterministic artifact, and Kodi media
pipeline with:

```bash
python tests/e2e/watchnixtoons2_bluestacks.py \
  --adb /home/mwo/android-sdk/platform-tools/adb \
  --serial emulator-5554 \
  --catalog-items 16 \
  --qualities 480 720 1080 \
  --quality 720 \
  --observed-seconds 25 \
  --result docs/e2e-results/2026-07-25-bluestacks1-watchnixtoons2.json
```

The verifier is read-only on the Kodi profile. It fails unless the mwoDevelop
add-on is enabled and owned by the stable repository, the legacy add-on and
testing repository are absent, and the latest matching playback log contains
input stream, demuxer, audio decoder, and clean player-close markers.

## Sony Android TV / Kodi 21.2

Use an isolated ADB server when another local Android client keeps replacing
the default server:

```bash
/home/mwo/android-sdk/platform-tools/adb -P 5038 start-server
/home/mwo/android-sdk/platform-tools/adb -P 5038 connect 192.168.1.12:5555
export ADB_SERVER_SOCKET=tcp:localhost:5038
```

The Umbrella matrix drives real Kodi search and selection screens, observes the
player, and stores redacted Kodi and Umbrella resolver diagnostics:

```bash
.venv/bin/python tests/e2e/sony_kodi_matrix.py \
  --adb /home/mwo/android-sdk/platform-tools/adb \
  --serial 192.168.1.12:5555 \
  --host 127.0.0.1 \
  --jsonrpc-port 19090 \
  --event-host 192.168.1.12 \
  --observe-seconds 15 \
  --result docs/e2e-results/sony-umbrella-matrix.json
```

For the deterministic WatchNixtoons2 playback test, first select `Auto Play
Highest Quality` in the add-on's Playback Method setting. The runner validates
the live `Latest Releases` catalogue and a known episode through Kodi's media
pipeline:

```bash
.venv/bin/python tests/e2e/sony_watchnixtoons2.py \
  --adb /home/mwo/android-sdk/platform-tools/adb \
  --serial 192.168.1.12:5555 \
  --host 192.168.1.12 \
  --observe-seconds 15 \
  --result docs/e2e-results/sony-watchnixtoons2.json
```

Both reports omit credentials, magnets, and resolved media URLs.

The focused search regression opens Umbrella's real virtual keyboard, submits a
term, and verifies that Kodi receives a matching directory result. It fails
immediately if a stale `source_progress` modal is still blocking the UI:

```bash
.venv/bin/python tests/e2e/umbrella_search_e2e.py \
  --adb /home/mwo/android-sdk/platform-tools/adb \
  --serial 192.168.1.12:5555 \
  --host 127.0.0.1 \
  --jsonrpc-port 19090 \
  --term Sintel \
  --result docs/e2e-results/sony-umbrella-search.json
```

## BlueStacks1 / Kodi 21.3

BlueStacks may expose Kodi's JSON-RPC only on the guest loopback interface.
Forward it through the exact `BlueStacks1` ADB target and send EventServer
commands from inside that same guest:

```bash
export ADB_SERVER_SOCKET=tcp:localhost:5038
/home/mwo/android-sdk/platform-tools/adb -s 127.0.0.1:5555 forward tcp:19090 tcp:9090

.venv/bin/python tests/e2e/sony_kodi_matrix.py \
  --adb /home/mwo/android-sdk/platform-tools/adb \
  --serial 127.0.0.1:5555 \
  --host 127.0.0.1 \
  --jsonrpc-port 19090 \
  --event-via-adb \
  --direct-play \
  --case sintel \
  --observe-seconds 15 \
  --result docs/e2e-results/bluestacks1-umbrella-matrix.json
```

The ADB port is dynamic; confirm that `127.0.0.1:5555` still identifies the
`Rvc64`/`BlueStacks1` instance before running the command. JSON-RPC access must
also be enabled in Kodi for the duration of the test and restored afterwards.

The same focused search check uses the forwarded JSON-RPC endpoint in
BlueStacks:

```bash
.venv/bin/python tests/e2e/umbrella_search_e2e.py \
  --adb /home/mwo/android-sdk/platform-tools/adb \
  --serial 127.0.0.1:5555 \
  --host 127.0.0.1 \
  --jsonrpc-port 19090 \
  --term Sintel \
  --result docs/e2e-results/bluestacks1-umbrella-search.json
```
