# Rapideo private restore certification — 2026-08-04

## Scope

The clean-restore workflow gained an allow-listed private add-on adapter
registry. The first adapter reads `RAPIDEO_USER` and `RAPIDEO_PASS` from an
ignored mode-`0600` reference file, configures the official Rapideo add-on,
forces a fresh login, verifies the account endpoint and removes all temporary
Android credential material. Reports contain transport and boolean health
evidence only.

## Automated certification

- full Python suite: `317 passed`;
- CI-equivalent `tests/e2e/run.sh`: `317 passed` after two deterministic
  repository builds;
- `git diff --check`: pass;
- private adapter unit and restore integration tests: pass.

## Device evidence

| Device | Restore/configuration result | Rapideo result |
|---|---|---|
| BlueStacks1 (`SM-S901E`) | `restore-only` pass; 4,287 files; Kodi 21.3; Aeon Nox Silvo; required add-ons verified | Rapideo 1.5.0; HTTP 200 JSON login and account; fresh token present |
| Sony TV | existing profile retained; standalone idempotent adapter pass | Rapideo 1.5.0; HTTP 200 JSON login and account; fresh token present |
| X88 Pro 20 | profile/default add-on phases passed; final private phase blocked | active OpenVPN exit returned HTTP 200 `text/html` from the Rapideo login endpoint |
| Bedroom TV | Kodi transport recovered after restart; settings applied | active NordVPN path returned HTTP 200 JSON with API error 4 and no token |

No credential, token, account identity, API response body or resolved media URL
was printed or stored in this report. The two VPN-specific failures remain
explicit rollout blockers rather than being weakened to warnings.
