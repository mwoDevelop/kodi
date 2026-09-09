# 9.09.2026 — Realizacja planu pozostałych zadań

Plan: [REMAINING_OPS_PLAN_2026-09-09.md](../REMAINING_OPS_PLAN_2026-09-09.md).
Review: [REMAINING_OPS_PLAN_REVIEW_2026-09-09.md](../REMAINING_OPS_PLAN_REVIEW_2026-09-09.md).

## Wyniki

| Krok | Wynik |
|---|---|
| A NUC `flatpak_scope` | **DONE** — PR [#366](https://github.com/mwoDevelop/kodi/pull/366) squash `d409ed8`. Live `kodi_inventory` `nuc-alek`/`nuc-mwo`: Kodi 21.3-Omega, `runtime_paths_qualified`, bez enumeracji Edge. |
| B Gateway 0.3.4 | **DONE bez redeploy** — SHA `gateway.cgi` i `KodiCPGateway.sh` = QNAP. PR [#367](https://github.com/mwoDevelop/kodi/pull/367) scalony. |
| C Cron Umbrella | **DIAGNOZA** — `approve-umbrella-promotion.yml` wrócił native `schedule` 10:04Z SUCCESS. `approve-upstream-update.yml` nadal rzadki native cron; watchdog `RETRY_BUDGET_EXHAUSTED`. Jeden ręczny dispatch 34339010861 SUCCESS (brak PR do approve). Budżetu retry nie resetowano. |
| D Bedroom | **CZĘŚCIOWY** — ADB OK, playback nieaktywny, dry-run PASS `scope=scoped`. Apply: YouTube ACCOUNT_READY, OpenSubtitles.com PASS, `.org` `VIP_REQUIRED` + kwarantanna, mwoScrapers 0.2.2, Profile Sync assigned **active** `63a8026e…` (nie kandydat), portable CONVERGED 7 favourites, NordVPN compliant. **Rapideo** nadal `JSON`/`HTML` na `/account` przez tunel Kodi (Sony JSON OK). Pełny `kodi_ops.py rollout --device bedroom-tv` = FAILED na adapterze rapideo. Kodi zostawione uruchomione; UI wrócone na launcher. |
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
