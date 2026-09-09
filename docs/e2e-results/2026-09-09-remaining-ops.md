# 9.09.2026 — Realizacja planu pozostałych zadań

Plan: [REMAINING_OPS_PLAN_2026-09-09.md](../REMAINING_OPS_PLAN_2026-09-09.md).
Review: [REMAINING_OPS_PLAN_REVIEW_2026-09-09.md](../REMAINING_OPS_PLAN_REVIEW_2026-09-09.md).

## Wyniki

| Krok | Wynik |
|---|---|
| A NUC `flatpak_scope` | **DONE** — PR [#366](https://github.com/mwoDevelop/kodi/pull/366) squash `d409ed8`. Live `kodi_inventory` `nuc-alek`/`nuc-mwo`: Kodi 21.3-Omega, `runtime_paths_qualified`, bez enumeracji Edge. |
| B Gateway 0.3.4 | **DONE bez redeploy** — SHA `gateway.cgi` i `KodiCPGateway.sh` = QNAP. PR [#367](https://github.com/mwoDevelop/kodi/pull/367) scalony. |
| C Cron Umbrella | **DIAGNOZA** — `approve-umbrella-promotion.yml` wrócił native `schedule` 10:04Z SUCCESS. `approve-upstream-update.yml` nadal rzadki native cron; watchdog `RETRY_BUDGET_EXHAUSTED`. Jeden ręczny dispatch 34339010861 SUCCESS (brak PR do approve). Budżetu retry nie resetowano. |
| D Bedroom | **CZĘŚCIOWY** — ADB OK, playback nieaktywny, dry-run PASS `scope=scoped`. Apply: YouTube ACCOUNT_READY, OpenSubtitles.com PASS, `.org` `VIP_REQUIRED` + kwarantanna, mwoScrapers 0.2.2, Profile Sync assigned **active** `63a8026e…` (nie kandydat), portable CONVERGED 7 favourites, NordVPN compliant. **Rapideo** nadal `JSON`/`HTML` na `/account` przez tunel Kodi (Sony JSON OK). Pełny `kodi_ops.py rollout --device bedroom-tv` = FAILED na Rapideo.

### Rapideo Bedroom — diagnoza

To **nie jest błąd parsera JSON ani inny `base_url`**. Addon 1.5.0 i
`https://www.rapideo.pl/api/rest` są identyczne na Bedroom i Sony. DNS w Kodi
w obu przypadkach: `51.38.140.112`. Serwer: `FileSolutions/4.0`.

Bedroom przez tunel Kodi/Nord dostaje HTML 200 z tytułem
**„403 – Dostęp tymczasowo ograniczony”** (WAF Rapideo). Sony dostaje JSON
(`Authtoken invalid` / konto OK). Egress Kodi: Bedroom `37.209.128.65`
(Netia/Plus, Łódź), Sony `83.4.84.222` (Orange, Kraków). Host operatorski
dostaje JSON.

Decyzja: **konfiguracja wyjścia NordVPN na Bedroom**, nie generyczna zmiana
API. Split-tunnel jest per-aplikacja — nie da się wyłączyć VPN tylko dla
`rapideo.pl` wewnątrz Kodi. Kod tylko klasyfikuje tę stronę WAF jako
`ACCESS_RESTRICTED` zamiast `JSONDecodeError`.

Odblokowanie Bedroom: w NordVPN na Streamerze wybrać inny serwer (np. taki,
którego egress Rapideo akceptuje; Sony/Orange działa). Potem ponowić
`kodi_rapideo_configure.py` / scoped rollout. |
| E Kandydat Profile Sync | **STOP** — candidate nadal `3c3391bf…`, active `63a8026e…`. Bedroom dostał active. Bez promote/DELETE. |
| Copilot | bez zmian, `observe` |
| OpenSubtitles.org | potwierdzone `VIP_REQUIRED` na Bedroom; `.com` default |

## Poprawki narzędzi (PR #368)

- Android mutate: `DEFERRED` przy `Player.GetActivePlayers`.
- Rapideo: export tokenu wydawcy, retry, ponowne logowanie gdy `/account` nie jest JSON.

## Świadomie nie zrobione

- Promocja kandydata `3c3391bf…`
- Reset budżetu watchdoga / podniesienie `max_age`
- VIP OpenSubtitles.org
- Copilot approvals
- Redeploy QPKG 0.3.4
