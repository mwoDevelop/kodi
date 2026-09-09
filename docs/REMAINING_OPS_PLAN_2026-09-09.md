# Plan pozostałych zadań operacyjnych — 9 września 2026

Weryfikacja na żywo: **2026-09-09T09:51Z**. Zaktualizowano po
[niezależnym review](REMAINING_OPS_PLAN_REVIEW_2026-09-09.md).
Realizacja: [2026-09-09-remaining-ops.md](e2e-results/2026-09-09-remaining-ops.md).
Nie jest raportem E2E.

Powiązane zapisy: [odbiór stable 9.09](e2e-results/2026-09-09-stable-and-pr-observation.md),
[migracja NUC `--user`](e2e-results/2026-09-09-nuc-flatpak-user-migration.md),
[plan Copilota](COPILOT_PR_AUTOMATION_PLAN.md),
[operacje Kodi](kodi-operations.md),
[procesy cykliczne](scheduled-processes.md).

Kanoniczna jest **kolejność wykonania** poniżej. Numery handoveru (#1–#7)
są tylko mapą; nie używać ich jako kroków sesji.

## Werdykt aktualności (handover → wykonanie)

| Handover | Werdykt 09:51Z | Krok wykonania |
|---|---|---|
| #1 PR NUC | **AKTUALNY** — `1493a8f` nie jest w `origin/main` (`005a9e7`) | Krok A |
| #2 Gateway 0.3.4 | **AKTUALNY, INNY ZAKRES** — QNAP już ma 0.3.4; Git HEAD 0.3.2 | Krok B |
| #3 Bedroom ADB | **AKTUALNY, ADB JEST** — `192.168.1.20:5555` device, Kodi 21.3 działa | Krok D (nie czeka na A–C) |
| #4 Kandydat `3c3391bf…` | **AKTUALNY** — candidate ≠ active; 9 assignmentów = active | Krok E, tylko odczyt |
| #5 Copilot `observe` | **POZA IMPLEMENTACJĄ** | Ograniczenie, nie krok |
| #6 OpenSubtitles.org `VIP_REQUIRED` | **LIMIT KONTA** | Obserwacja w raporcie Bedroom |
| #7 Cron Umbrella | **WĘŻSZY** — promotion i umbrellaplug approve-upstream unhealthy | Krok C, nie brama |

## Kolejność wykonania

Kroki A, B, C, D są **równoległe tam, gdzie nie dzielą drzewa git**.
Bedroom (D) **nie czeka** na merge NUC, deploy Gateway ani native cron.

| Krok | Praca | Drzewo git |
|---|---|---|
| A | PR narzędzi `flatpak_scope` + live inventory NUC | czyste worktree od `origin/main`, cherry-pick tylko `1493a8f` |
| B | Uzgodnić źródło Gateway 0.3.4 z bajtami na QNAP | osobny branch; nie ten sam commit co A |
| C | Diagnoza dwóch opóźnionych cronów | odczyt GitHub/watchdog; native schedule = sukces późniejszy |
| D | Scoped rollout `bedroom-tv` | HEAD z `flatpak_scope` (np. `1493a8f`), **bez** uncommitted Gateway w indeksie |
| E | Odczyt kandydata Profile Sync, potem STOP | bez CAS bez zgody właściciela |

Lokalny checkout `fix/qnap-compose-readiness-20260909` ma niecommitowany Gateway.
Nie commitować z tej gałęzi. Copilot i zakup VIP OpenSubtitles są poza zakresem.

---

## Krok A — PR NUC `flatpak_scope`

**Cel.** Narzędzia floty walidują `flatpak_scope: user`, żeby inwentarz
`nuc-alek` nie enumerował `/var/lib/flatpak/app/` (ACL Edge).

**Nie przenosi** prywatnego `.kodi-private/devices.json` (gitignore). Inventory
zostaje lokalne; trzeba je mieć przy probe.

**Zakres.**

1. Worktree od `origin/main`. Cherry-pick **tylko** `1493a8f` (nie `57d8092`,
   nie Gateway).
2. Testy: `tests/test_kodi_devices.py`, `tests/test_kodi_flatpak_restore.py`,
   `tests/test_kodi_transports.py`.
3. PR na `main`. Sukces minimalny: PR + zielone exact-head CI. Merge jest
   dodatkowy, jeśli ruleset na to pozwoli; zablokowany merge nie zatrzymuje D.
4. Po narzędziach z `flatpak_scope` na używanym HEAD: live
   `kodi_inventory` / probe `nuc-alek` i `nuc-mwo`. Wymagane: inwentarz
   przechodzi, Kodi 21.3, `runtime_paths_qualified`, brak enumeracji
   systemowego Flatpak. **Nie** robić pełnego apply NUC — migracja już PASS.
5. Nie resetować ACL Edge.

**Sukces minimalny.** Otwarty PR z samym `1493a8f` i zielonym CI.
**Sukces dodatkowy.** Merge do `origin/main`.
**Dowód hosta.** Live probe obu kont NUC, nie sam dry-run.

## Krok B — Gateway 0.3.4: Git = produkcja albo STOP

**Cel.** Git opisuje to, co stoi na QNAP. Nie instalować od zera.

**Stan.** QNAP: `Version=0.3.4`, `Enable=TRUE`,
`Service_Program=KodiCPGateway.sh`. Git HEAD: 0.3.2. Working tree ma
niecommitowany kandydat źródła.

`status` / `verify()` sprawdzają pola `qpkg.conf` i tryby plików, **nie** SHA
`gateway.cgi` / `KodiCPGateway.sh`. Zgodna wersja nie wystarczy.

**Zakres.**

1. Porównać SHA zainstalowanych na QNAP `www/gateway.cgi`,
   `KodiCPGateway.sh` (i innych plików pakietu) z lokalnym źródłem.
2. Zgodność bajtów → commit źródła 0.3.4 + testy, **bez deploy**.
3. Różnica bajtów → STOP. Nie udawać, że git = produkcja; nie `deploy`
   „dla pewności”.
4. Osobny branch od `origin/main`. Nie mieszać z krokiem A.
5. Nie commitować sekretów operatora, `*.qpkg`, kluczy `QPKG_SIGNING_DIR`.

**Sukces.** Źródło w PR/main odpowiada zainstalowanym bajtom albo jawny STOP
z listą różnic. Skrót „Kodi admin” nadal po HTTPS QTS; brak publicznego `:19444`.

## Krok C — Cron Umbrella: diagnoza teraz, native później

**Cel.** Wyjaśnić, czemu dwa schedule’e są starsze niż `max_age`, bez podnoszenia
progów i bez pętli dispatchy.

**Stan 09:51Z**

| Workflow | Wiek | Próg | Stan |
|---|---:|---:|---|
| `approve-umbrella-update.yml` | 1225 s | 4500 | healthy |
| `approve-umbrella-promotion.yml` | 16280 s | 8100 | **unhealthy** (ostatni SUCCESS) |
| `approve-upstream-update.yml` | 13198 s | 4500 | **unhealthy** (ostatni SUCCESS) |

**Zakres sesji.** Czy `schedule` w ogóle startuje (Actions, concurrency, billing)?
Co najwyżej **jeden** `workflow_dispatch` na unhealthy workflow, tylko gdy brak
aktywnej próby i cooldown na to pozwala. Nie resetować budżetu retry.

**Nie jest bramą** dla A/B/D. Native `schedule` poniżej progu to sukces
**późniejszy**, poza jedną sesją jeśli GitHub nie odpali crona.

**Sukces sesji.** Zapisana przyczyna (nie startuje / startuje za rzadko /
watchdog nie dispatchuje) i ewentualnie jeden uzasadniony dispatch.
**Sukces operacyjny (później).** Oba workflow < `max_age` po evencie `schedule`.

## Krok D — Bedroom TV, scoped, bez ucinania odtwarzania

**Cel.** Przywrócić Bedroom do kontraktu floty. Ostatni PASS: 3.09.
DEFERRED od 5.09 z powodu ADB — ta blokada **nie obowiązuje**.

**Stan 09:51Z.** ADB połączone, model zgodny, Kodi 21.3 **uruchomione**.
Nie czekać na A–C. Narzędzia muszą akceptować `flatpak_scope` w inventory
(obecny `1493a8f` wystarczy; merge A nie jest bramą).

**Zakres.**

1. JSON-RPC `Player.GetActivePlayers` / `GetItem`. Jeśli odtwarza →
   **nie apply**. Wynik `DEFERRED` / `playback_active`. Dry-run bez mutacji
   jest dozwolony.
2. Tylko:
   `.venv/bin/python tools/kodi_ops.py rollout --device bedroom-tv --dry-run`
   potem, jeśli player pusty, to samo bez `--dry-run`.
3. Zakaz `rollout` bez `--device` i `--resume` pełnej floty (converge
   fail-closed na kandydacie `3c3391bf…` i nie dochodzi do Bedroom).
4. Po dry-run: w planie `scope=scoped`, brak kroku `profile-sync`.
5. Nie kopiować enrollmentu ani userdata. Nie ruszać kandydata Profile Sync.
6. Po teście zostawić Kodi **uruchomione** (stan sprzed).
7. OpenSubtitles.org jako `VIP_REQUIRED` nie jest failure, o ile `.com` PASS.

Jeśli `ensure_kodi_ready` / instalacje dodatków robią `am force-stop` bez
kontroli playera, to błąd narzędzi — poprawić i przetestować, zamiast
omijać ręcznie przy każdym apply.

**Sukces.** `device:bedroom-tv` PASS, albo jawny DEFERRED (`playback_active`
lub inna prawdziwa przyczyna, nie „brak ADB”).

## Krok E — Kandydat Profile Sync: odczyt i STOP

**Stan.** `home-stable` generation 7:

- candidate `sha256:3c3391bf5a67880e732ce0d8489589c1b8407ac70adaddb43c71857bcf744430`
- active `sha256:63a8026e6454713ebbd18e9cdd9660e194ad99e0f90e224819922a963a72e6dc`
- 9 assignmentów = active

Różnica: `umbrella.preferences` / hash polityki, nie ZIP-y. Favourites:
eksport 7 vs aktywna rewizja 8.

**Zakres sesji.** Odczyt diffu (bez sekretów w raporcie publicznym).
**STOP.** Bez zgody właściciela: zero `PUT` / `DELETE` / `promote`.
Zostawienie kandydata z notatką jest ważnym sukcesem.

## Poza implementacją tej sesji

- Copilot: zostawić `MWOSCRAPERS_COPILOT_MODE=observe`. Nie review/merge #29
  jako „domknięcie planu”. Nie `advisory`/`on`.
- OpenSubtitles.org: nie kupować VIP, nie usuwać `.org`, nie osłabiać asercji.
  Tylko potwierdzić w raporcie Bedroom.
- ACL Edge, locki stable, wersja repo Kodi, ZeroTier, qnap-download-search.
- Pełny apply NUC. Ponowny deploy Gateway przy zgodnych bajtach.
- Podnoszenie `max_age_seconds` watchdoga.

## Polecenia (z właściwego drzewa)

```bash
# A — worktree od origin/main
.venv/bin/python tools/kodi_inventory.py nuc-alek
.venv/bin/python tools/kodi_inventory.py nuc-mwo

# D — tylko scoped, po sprawdzeniu playera
.venv/bin/python tools/kodi_ops.py rollout --device bedroom-tv --dry-run

# B
.venv/bin/python tools/qnap_control_plane_gateway.py status

# C
gh run list --repo mwoDevelop/kodi --workflow approve-umbrella-promotion.yml --limit 5
gh run list --repo mwoDevelop/umbrellaplug.github.io --workflow approve-upstream-update.yml --limit 5
```
