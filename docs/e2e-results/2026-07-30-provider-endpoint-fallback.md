# MwoScrapers provider endpoint fallback

Date: 2026-07-30

## Outcome

The diagnosis confirmed a real runtime gap in MwoScrapers 0.1.6: after a
private provider endpoint was configured, a transport or protocol failure
returned an empty source list without trying the provider's public endpoint.
The endpoint default in settings was valid, but it was not a runtime fallback.

Candidate 0.1.7 fixes the gap in the shared Stremio adapter:

- a configured endpoint remains first;
- the code-owned public endpoint is the unique second candidate;
- transport, HTTP, JSON and stream-contract failures advance to the next
  candidate;
- a valid empty response is authoritative and is not duplicated;
- provider health fails only after every endpoint candidate fails.

The QNAP relay remained healthy throughout the test: one healthy container,
one Compose network and no volumes. It is still a stateless, credential-free
metadata optimization. No Real-Debrid operation passes through it.

## Provider inventory

MwoScrapers contains two original Stremio-contract adapters:

- Torrentio is enabled by default and returned 5 sources for `Sintel` plus 49
  for `Breaking Bad S01E01`;
- Comet is opt-in and its current unconfigured public endpoint returned HTTP
  403 on the host and every tested Kodi runtime.

Keeping Comet disabled is therefore correct. The
[current Comet project](https://github.com/g0ldyy/comet) expects a configured
instance and can itself integrate debrid services, which is not the passive
provider boundary used by MwoScrapers. It must not be enabled only to make the
provider count look larger.

## Exact candidate

- repository: `mwoDevelop/script.module.mwoscrapers`;
- commit: `47b4135b5b7401059ce805256c13881699f189a3`;
- version: `0.1.7`;
- candidate ZIP SHA-256:
  `f12494ee9fde346fc0f80effdc0030af42fb70ae6ff098f63c3dcc6dd87f7b39`;
- PR: `mwoDevelop/script.module.mwoscrapers#11`.

Local gates passed:

- 45 MwoScrapers tests;
- Ruff;
- add-on validation;
- two atomic candidate-rollout tests;
- deterministic repository build.

GitHub checks passed in runs `30577640978`, `30577659268` and `30577659233`,
including the exact-head malware scan, tests and relay-image build.

## Device matrix

| Device | Configured path | Configured results | Unavailable relay behavior | Playback |
| --- | --- | --- | --- | --- |
| BlueStacks1 | public | 5 / 49 | relay error, public success, 5 | movie 12.141 s; episode 12.146 s |
| Sony TV | LAN relay | 5 / 49 | relay error, public attempted but HTTP 403 | movie 12.276 s; episode 12.485 s |
| X88 Pro 20 | LAN relay | 5 / 49 | relay error, public success, 5 | movie 12.161 s; episode 12.430 s |
| Bedroom TV | unavailable | not run | not run | not run |

All six completed playback cases used Umbrella 6.7.81.18. BlueStacks and Sony
reports directly recorded `realdebrid.add_magnet` and `Played file as
resolve`. X88 Android scoped storage denied shell access to `umbrella.log`, so
an in-Kodi boolean probe read the same log and confirmed both markers without
exporting log lines, URLs, hashes or credentials.

The source fingerprints remained consistent where the existing matrix could
read Umbrella's log:

- `Sintel`: `5a6b52180d6a015e`;
- `Breaking Bad S01E01`: `6f39c1e78d9c75c4`.

## VPN limitation

Sony's NordVPN exit still receives HTTP 403 from public Torrentio. Version
0.1.7 removes the software dependency on QNAP by always attempting the public
fallback, but it cannot override an upstream decision to block a VPN address.
On that specific network route, successful searching still needs either the
healthy relay, a different VPN exit, or excluding all of Kodi from the VPN.
Android TV NordVPN offers application-level, not per-domain, split tunneling,
so excluding Kodi would also move Real-Debrid traffic outside the VPN and was
not applied.

Resolving remains independent of QNAP in every case: MwoScrapers returns
magnet metadata, then Umbrella alone submits the selected magnet to
Real-Debrid and receives the playable URL.

## Reproducible commands

Build the exact candidate using a testing lock override, then apply it with:

```bash
.venv/bin/python tools/kodi_addon_candidate_rollout.py \
  path/to/script.module.mwoscrapers-0.1.7.zip \
  --addon-id script.module.mwoscrapers \
  --version 0.1.7 \
  --serial DEVICE
```

Run the sanitized configured/public/unavailable-relay matrix with:

```bash
.venv/bin/python tools/kodi_mwoscrapers_endpoint_probe.py \
  --serial DEVICE
```

Run movie and episode playback with `tests/e2e/sony_kodi_matrix.py`.

## Publication status

The exact candidate is installed on BlueStacks1, Sony TV and X88 Pro 20.
Publication is intentionally pending because branch protection rejected an
administrative merge without one approving review from a different account
with write access. No testing/stable lock, repository add-on version or public
artifact was changed. After legal approval of PR 11, the same commit must be
published to testing, verified byte-for-byte, rolled out again from the public
repository, and only then promoted to stable.
