# Procesy cykliczne

To jest katalog operacyjny automatyzacji cyklicznej projektu mwoDevelop Kodi. Pliki
workflow i manifesty Compose pozostają wykonywalnymi źródłami prawdy; ten dokument
opisuje w jednym miejscu ich właścicieli, skutki, granice awarii i monitoring.

Wszystkie wyrażenia cron GitHub używają czasu UTC. GitHub może rozpocząć zaplanowane
workflow później niż wskazana minuta, dlatego harmonogram nie stanowi SLA. Każdy
workflow obsługuje również `workflow_dispatch`, umożliwiający kontrolowane ponowienie.

## GitHub Actions

| UTC | Repozytorium | Workflow | Cel | Granica zapisu |
| --- | --- | --- | --- | --- |
| 04:20 codziennie | `mwoDevelop/kodi` | `reconcile-upstreams.yml` | Wykrywa stan wszystkich zarządzanych komponentów i przygotowuje dokładnego kandydata na lock kanału testing. | Discovery jest tylko do odczytu. Zmieniony lock jest proponowany na `automation/testing-lock`; nigdy nie jest automatycznie scalany ani promowany. |
| 04:23 codziennie | `mwoDevelop/script.module.mwoscrapers` | `check-provider-upstreams.yml` | Pobiera zaakceptowane niezmienne artefakty Coco i Viper, weryfikuje przypięte digesty, bezpiecznie materializuje zawartość i skanuje dokładne ZIP-y oraz pliki wspólną bramą antymalware. | Tylko do odczytu. Weryfikacja pokrycia wymaga zgodności liczby archiwów, plików i bajtów z raportem skanera. Workflow przesyła artefakt audytu przechowywany przez 14 dni i nigdy nie zmienia gałęzi. Niedostępny artefakt, niezgodność digestu, niepełne pokrycie lub błąd skanowania powodują błąd workflow. |
| 04:35 codziennie | `mwoDevelop/ch.repo` | `mwodevelop-watchnixtoons2-update.yml` | Wykrywa upstream WatchNixtoons2, materializuje i skanuje izolowanego kandydata, a następnie go testuje. | Zweryfikowana zmiana może zaktualizować `automation/watchnixtoons2-upstream` i otworzyć PR wymagający review. Nie publikuje repozytorium Kodi. |
| 04:41 codziennie | `mwoDevelop/script.module.mwoscrapers` | `discover-provider-upstreams.yml` | Obserwuje najnowsze źródła providerów i utrzymuje stan review dotyczący wyłącznie pochodzenia. | Zmieniona obserwacja może zaktualizować `automation/provider-provenance` i otworzyć PR wymagający review. Nie importuje ani nie wykonuje kodu providera. |
| 04:50 codziennie | `mwoDevelop/umbrellaplug.github.io` | `propose-upstream-update.yml` | Odtwarza stos poprawek downstream Umbrella na dokładnym commitcie upstream, skanuje kandydata i go testuje. | Zweryfikowana zmiana może zaktualizować `automation/umbrella-upstream` i otworzyć PR wymagający review. Chronione ścieżki muszą pozostać niezmienione. |
| 05:03 codziennie | `mwoDevelop/script.module.mwoscrapers` | `probe-provider-health.yml` | Sprawdza publiczne kontrakty wszystkich kwalifikowanych providerów na kontrolowanym filmie i odcinku. | Tylko do odczytu. Artefakt przechowuje wyłącznie status, czas i liczbę wyników; nie zapisuje nazw źródeł, magnetów, hashy ani URL-i treści. |

Audyt providerów i ich discovery są celowo rozdzielone:

- audyt 04:23 dowodzi, że każdy już zaakceptowany artefakt jest nadal możliwy do
  pobrania, identyczny bajtowo i czysty w skanowaniu;
- discovery 04:41 obserwuje nowy stan upstream i może zgłosić lub zaproponować
  aktualizację pochodzenia bez akceptowania nowych bajtów wykonywalnych.

Magneto nie jest aktywnym źródłem audytu. Jego przypięty artefakt został usunięty
upstream, dlatego obserwację wycofano 12 sierpnia 2026 r. i zachowano wyłącznie jako
rekord historyczny w `.upstream/retired-observations.json` repozytorium mwoScrapers.
Poprzednie błędy pobrania Magneto były prawidłowym zachowaniem fail-closed, a nie
awarią skanera; aktywny cykl obejmuje obecnie dokładnie Coco i Viper.

Żaden cykliczny workflow nie scala PR, nie promuje `testing` do `stable`, nie zmienia
poświadczeń Real-Debrid ani nie zapisuje konfiguracji użytkownika Kodi.

## Monitorowanie na QNAP

`qnap-upstream-watchdog` działa w Container Station i odpytuje GitHub co sześć godzin.
Monitorowana lista workflow jest wersjonowana w `manifests/upstream-watchdog.json`.
Workflow jest niezdrowy, gdy brakuje ostatniego uruchomienia, zakończyło się ono błędem
lub jest starsze niż 36 godzin. Healthcheck kontenera odczytuje wynik co pięć minut, a
QTS/Container Station odpowiada za powiadomienie zewnętrzne.

Watchdog ma wyłącznie publiczny dostęp GitHub do odczytu. Nie może ponowić workflow,
zmienić gałęzi ani naprawić artefaktu upstream. Pomyślne odkrycie nie maskuje
błędu audytu zaakceptowanych artefaktów; oba workflow mwoScrapers są
monitorowane niezależnie.

Pozostałe healthchecki kontenerów QNAP sprawdzają dostępność usług, a nie
harmonogramów aktualizacji:

| Usługa | Interwał | Sonda |
| --- | --- | --- |
| Backend Profile Sync | 30 sekund | lokalny endpoint gotowości HTTPS wewnątrz kontenera |
| Przekaźnik providerów mwoScrapers | 30 sekund | lokalny endpoint `/health` wewnątrz kontenera |
| Watchdog upstream | 5 minut | ostatnia utrwalona ocena workflow GitHub |

## Klienci Kodi Profile Sync

`service.mwodevelop.profilesync` jest oddzielnym procesem cyklicznym na urządzeniu.
Standardowy profil domowy czeka 15 sekund po uruchomieniu Kodi i sprawdza podpisane
przypisanie `home-stable` co sześć godzin. Rejestracja dla konkretnego urządzenia,
tokeny, materiał podpisujący i ostatnio zastosowana rewizja pozostają lokalne i
są wyłączone z payloadu synchronizowanego profilu.

Profile Sync nie instaluje kodu dodatku, nie uruchamia GitHub workflow, nie promuje
kanału repozytorium ani nie używa przekaźnika providerów. Dlatego jego backend i
harmonogram są monitorowane niezależnie od synchronizacji upstream.

## Procesy ręczne i sterowane zdarzeniami

Buildy, CI, testy antymalware, publikacja testing, certyfikacja, promocja stable i
workflow wdrożeniowe celowo nie są cykliczne. Uruchamiają się po pushu, przez pull
request lub jawne `workflow_dispatch` i zachowują własne bramy review oraz kontrolę
dokładnego head SHA.

## Weryfikacja operacyjna

Sprawdź najnowsze zaplanowane uruchomienia bez polegania na historycznym raporcie
wydania:

```bash
gh run list --repo mwoDevelop/kodi \
  --workflow reconcile-upstreams.yml --event schedule --limit 1
gh run list --repo mwoDevelop/script.module.mwoscrapers \
  --workflow check-provider-upstreams.yml --event schedule --limit 1
gh run list --repo mwoDevelop/script.module.mwoscrapers \
  --workflow discover-provider-upstreams.yml --event schedule --limit 1
gh run list --repo mwoDevelop/script.module.mwoscrapers \
  --workflow probe-provider-health.yml --event schedule --limit 3
gh run list --repo mwoDevelop/ch.repo \
  --workflow mwodevelop-watchnixtoons2-update.yml --event schedule --limit 1
gh run list --repo mwoDevelop/umbrellaplug.github.io \
  --workflow propose-upstream-update.yml --event schedule --limit 1
```

W przypadku wdrożonego watchdoga sprawdź `/run/watchdog/status.json` wewnątrz kontenera
`qnap-upstream-watchdog-upstream-watchdog-1`. Zdrowy kontener stanowi dowód wyłącznie
dla workflow obecnych w wersjonowanym manifeście watchdoga.

Dodając lub usuwając zaplanowane upstream workflow, zaktualizuj razem:

1. jego plik workflow i cron;
2. ten dokument katalogowy;
3. `manifests/upstream-watchdog.json`;
4. testy watchdoga i niezmienny obraz watchdoga QNAP;
5. aktywne wdrożenie QNAP, a następnie funkcjonalną kontrolę stanu.

Raporty historyczne poniżej `docs/e2e-results/` opisują podaną datę certyfikacji i nie
mogą być traktowane jako bieżący stan operacyjny.
