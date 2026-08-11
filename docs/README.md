# Indeks dokumentacji

Ta strona jest punktem wejścia nawigacji po dokumentacji projektowej. Dokumenty są
pogrupowane według przeznaczenia, tak aby aktualnych instrukcji obsługi nie mylić z
datowanymi planami lub dowodami z testów.

Wróć do [głównego README](../README.md), aby zapoznać się z poleceniami instalacji i
kompilacji.

## Aktualne instrukcje operatora

| Obszar | Dokument | Cel |
|---|---|---|
| Repozytorium Kodi | [Główny plik README](../README.md) | Zainstaluj stable/testing, zbuduj repozytorium i uruchom jego odtwarzalne E2E |
| Profile prywatne | [Prywatne migawki profilu Kodi](kodi-private-profile.md) | Tworzenie kopii zapasowych, przywracanie, tożsamość urządzenia, stan przenośny i granice bezpieczeństwa |
| Automatyzacja cykliczna | [Procesy cykliczne](scheduled-processes.md) | Workflow cron GitHub, watchdog QNAP, częstotliwość Profile Sync i weryfikacja na żywo |
| Kontenery QNAP | [Cykl życia obrazu QNAP](qnap-images.md) | Twórz, publikuj, wdrażaj i sprawdzaj trzy obrazy Container Station |
| E2E | [Przewodnik po testach E2E](../tests/e2e/README.md) | Testowe punkty wejścia i wymagania środowiskowe |
| Upstream Sync E2E | [Scenariusze synchronizacji upstream](../tests/e2e/upstream_sync/README.md) | Powtarzalne fixture i scenariusze aktualizacji |

Szczegóły wdrożenia specyficzne dla komponentu:

- [Serwer Profile Sync](../deploy/qnap-profile-sync/README.md)
- [przekaźnik providerów](../deploy/qnap-provider-relay/README.md)
- [watchdog synchronizacji upstream](../deploy/qnap-upstream-watchdog/README.md)

## Zapisy architektury i implementacji

Dokumenty te wyjaśniają decyzje projektowe i historię realizacji. Ich datowane
sekcje statusu nie są bieżącymi raportami o stanie systemu.

| Obszar | Dokument |
|---|---|
| Repozytorium, forki i architektura dostawców | [Plan architektury projektu](../PLAN.md) |
| Synchronizacja profilu i urządzenia | [Plan Profile Sync](../PROFILE_SYNC_PLAN.md) |
| Dziennik wdrożenia Profile Sync | [Zapis stanu realizacji](profile-sync-implementation.md) |
| Synchronizacja upstream | [Plan synchronizacji upstream](../UPSTREAM_SYNC_PLAN.md) |
| Bramka bezpieczeństwa upstream | [Projekt skanowania w poszukiwaniu złośliwego oprogramowania](UPSTREAM_MALWARE_SCANNING_PLAN.md) |
| Usunięcie zgodności legacy | [Plan usunięcia kodu legacy](../LEGACY_REMOVAL_PLAN.md) |
| Cykl życia formatów | [Schematy bieżące i legacy](schema-lifecycle.md) |
| Wstępny rekonesans repozytorium | [Rekord etapu 0](ETAP0.md) |
| Początkowa linia bazowa upstream | [Wartość bazowa upstream z 25.07.2026 r.](upstream-sync-baseline-2026-07-25.md) |

## Recenzje i zapisy decyzji

- [Review planu usunięcia kodu legacy](LEGACY_REMOVAL_PLAN_REVIEW.md)
- [Review architektury Profile Sync](PROFILE_SYNC_PLAN_REVIEW.md)
- [Review Profile Sync na QNAP](PROFILE_SYNC_QNAP_PLAN_REVIEW.md)
- [Review Profile Sync na NUC/Flatpak](PROFILE_SYNC_NUC_PLAN_REVIEW.md)
- [Review architektury Upstream Sync](UPSTREAM_SYNC_PLAN_REVIEW.md)
- [Review pełnego wydania Upstream
  Sync](UPSTREAM_SYNC_FULL_RELEASE_REVIEW_2026-07-29.md)

## Dowody z testów i wdrożenia

[Indeks dowodów E2E](e2e-results/README.md) zawiera listę datowanych raportów
dotyczących urządzeń, wydań i wdrożeń. Raport potwierdza stan zaobserwowany w
zarejestrowanym czasie; nie potwierdza aktualnego stanu urządzenia ani usługi.

## Źródła prawdy

| Pytanie | Autorytatywne źródło |
|---|---|
| Co jest opublikowane w stable lub testing? | `manifests/locks/stable.json` i `manifests/locks/testing.json` |
| Które drzewo źródłowe tworzy każdy dodatek? | `manifests/components.json` |
| Które zadania są zaplanowane? | `.github/workflows/` plus [Zaplanowane procesy](scheduled-processes.md) |
| Który digest obrazu QNAP jest wdrożony? | ignorowany `.kodi-private/qnap-images.json` oraz `python tools/qnap_images.py status` |
| Które urządzenia i endpointy są zarządzane? | ignorowane `.env` i `.kodi-private/devices.json` |
| Czy określone wdrożenie zakończyło się powodzeniem? | jego datowany raport w [dowodach E2E](e2e-results/README.md) |

Utrzymywane drzewa źródeł komponentów to [fork Umbrella](../umbrella/),
[MwoScrapers](../mwoscrapers/), [fork WatchNixtoons2](../watchnixtoons2/) i
[dodatek Profile Sync](../profile-sync-addon/). Każde z nich jest submodułem Git z
własnym plikiem README na poziomie komponentu i historią wydań.

Prywatnych plików i danych uwierzytelniających nie wolno nigdy kopiować do dokumentacji,
commitów, artefaktów kompilacji ani raportów zgłoszeń.

## Konserwacja dokumentacji

- Umieszczaj aktualne procedury w instrukcjach operacyjnych i linkuj je z tej strony.
- Zachowuj plany projektowe i review jako zapisy decyzji; nie używaj ich jako
  dashboardów bieżącego stanu.
- Umieszczaj datowane wyniki w `docs/e2e-results/` i dodawaj je do indeksu.
- Nie powielaj w tekście numerów wydanych wersji. Zamiast tego linkuj lock kanału.
- Uruchom `python -m pytest tests/test_documentation.py` po zmianie plików Markdown.
