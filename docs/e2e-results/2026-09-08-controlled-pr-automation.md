# Kontrolowana akceptacja PR — odbiór częściowy

8 września 2026. Status: implementacja i konfiguracja gotowe; bootstrap i test
pozytywnego merge **BLOCKED** do decyzji właściciela o ścieżce review.

## Zrealizowane

- Plan, niezależne review planu i implementacji, zastosowane poprawki:
  [plan](../CONTROLLED_PR_AUTOMATION_PLAN.md),
  [review](../CONTROLLED_PR_AUTOMATION_PLAN_REVIEW.md).
- [mwoScrapers PR #33](https://github.com/mwoDevelop/script.module.mwoscrapers/pull/33):
  kwalifikacja zdarzeniowa, izolacja kandydata, review polityki i merge bez
  `--admin`, ścisłe przepisy przejrzanego kodu i provenance, ręczny reconcile.
- Skrypt `tools/github_pr_automation.py`: dry-run, prywatny backup 0600,
  kontrola niezmienności zastanej konfiguracji, apply/readback i idempotencja.
- Wdrożone ustawienia repo: auto-merge dostępny, wymagane `test` i
  `malware-scan`, nadal **1 approval**, aktualna baza i dismiss stale reviews.
  Pierwsze wywołanie `APPLIED`, drugie `NO_CHANGE`; inni aktorzy/reguły bez zmian.
- Przejrzano staged paths i dodane linie pod kątem sekretów przed commitem.
  Pliki prywatne i zastane zmiany QTS Gateway nie należą do tego commitu.

## Dowody testów

| Próba | Wynik |
|---|---|
| Lokalna regresja mwoScrapers i polityki | 125 PASS; ruff i validate_addon PASS |
| Lokalna pełna regresja Kodi | 828 PASS; ostrzeżenie o celowo zdublowanym ZIP w teście negatywnym |
| PR #31, tryb bez zmian | BLOCKED / MANUAL_REQUIRED — edycja workflow |
| PR #32, tryb bez zmian | ELIGIBLE; dokładny head `028d6d695922f61237022b7549990cbbab27d736`, base `357c1e6df7d8414768a69ba8108fe84b44ef5804` |
| PR #32, kwalifikacja bubblewrap | PASS: regresje bazy, kandydata, live health 6 providerów; bez tokenu i bez zapisywalnego drzewa źródeł |
| PR #32, approve bez apply | DRY_RUN, bez review/merge/dispatch |
| Negatywne testy kodu | Rebinding, eval, importy/dekoratory/defaults testów, dynamiczny endpoint i encoding — blokowane |
| Cykl życia review | Timeout, zmieniona baza, błąd komendy/odpowiedzi POST wycofują własny approval; wyścig z merge wykonuje followup; ludzkie reviews zachowane |
| GitHub ustawienia repo | APPLIED, odczyt zgodny, kolejne apply NO_CHANGE |
| QNAP | 7 kontenerów running/healthy; niezależny stan monitorowanych zadań nadal FAILED |
| Control Plane API/mTLS | refresh HTTP 200; 11/12 GitHub OK, health mwoScrapers FAILED, watchdog propaguje ten błąd |
| BlueStacks / X88 | Oba osiągalne, Kodi 21.3 uruchomione, ścieżki runtime zakwalifikowane; nowy ZIP jeszcze niewdrożony |
| Bedroom TV | DEFERRED — ADB niedostępne; panel zasadnie FLEET_ASSIGNMENT_PENDING |

Uwaga: powyższy lokalny dry-run korzysta z nowego validatora, nie dowodzi jeszcze
działania bota na chronionym `main`. Ten test wymaga zakończenia bootstrapu.

## Gotowy artefakt cutoveru tygodniowego

Zbudowano przez istniejący `qnap_images.build_with_actions`, nie ad hoc:

- [build 34235470320](https://github.com/mwoDevelop/kodi/actions/runs/34235470320), SUCCESS;
- źródło `c52e8e08018741acc9ae232e0f14bd36f9fe9fec`;
- obraz `ghcr.io/mwodevelop/kodi-upstream-watchdog@sha256:db5513a0334969dbb3671da6cf32b9621fd0172ec78e0cdb0f1f3d5b771760c3`;
- manifest platform: amd64, arm64, arm/v7 — PASS;
- smoke obrazu bez sieci, read-only, bez capabilities — PASS: 12 workflow,
  audit/discovery `max_age_seconds=610200`.

Obraz **nie został wdrożony**, ponieważ PR #31 nadal definiuje zmianę przyszłą.
Produkcja musi mieć harmonogram i monitoring o tej samej kadencji. Samo istnienie
obrazu nie zmienia stable locka ani nie oznacza zakończonego deployu.

## Pozostałe kroki i blokada

1. Dokończyć CI/review #33. Bootstrap #31 i #33 wymaga drugiego uprawnionego
   reviewera albo wyraźnej zgody na jednorazowy istniejący owner bypass.
   Pytanie skierowano do użytkownika; brak odpowiedzi nie jest zgodą.
2. Scalić #31 w jednym oknie z Kodi #360, tygodniowym manifestem Control Plane
   i gotowym obrazem watchdoga; sprawdzić readback i ponowny deploy NO_CHANGE.
3. Zaktualizować bazę #32, ponowić CI i sandbox, sprawdzić workflow dry-run,
   dopiero potem włączyć flagę i potwierdzić review bota/merge bez bypassu.
4. Potwierdzić health `main`, ponowienie reconcile, status watchdoga i panelu.
5. Zbudować pakiet i przeprowadzić testy nowego dodatku na BlueStacks, potem X88;
   stable/publikacja/rollout są oddzielne od automatycznej akceptacji PR.

Nie usuwano rejestru prób watchdoga. Historyczny zatrzask `BILLING_BLOCKED`
pozostaje do świeżego sukcesu produkcyjnej gałęzi; najnowszy run
`34221782367` faktycznie wykonał kod i zakończył się `FILTERED_EMPTY` PirateBay,
nie odmową uruchomienia runnera. Zielona gałąź kandydata nie kasuje tej historii.
