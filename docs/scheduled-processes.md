# Procesy cykliczne

To jest katalog operacyjny automatyzacji cyklicznej projektu mwoDevelop Kodi.
Kanoniczny katalog obserwacyjny znajduje się w
`manifests/control-plane-schedules.json`; CI porównuje go z cronami workflow i
`manifests/upstream-watchdog.json`. Ten dokument opisuje ich właścicieli, skutki,
granice awarii i monitoring.

Wszystkie wyrażenia cron GitHub używają czasu UTC. GitHub może rozpocząć zaplanowane
workflow później niż wskazana minuta, dlatego harmonogram nie stanowi SLA. Każdy
workflow obsługuje również `workflow_dispatch`, umożliwiający kontrolowane ponowienie.

## GitHub Actions

| UTC | Repozytorium | Workflow | Cel | Granica zapisu |
| --- | --- | --- | --- | --- |
| 03:10 codziennie | `mwoDevelop/kodi` | `publish-pages.yml` | Odświeża jeden atomowy payload stable, testing i publicznego statusu Umbrelli. | To jedyny writer GitHub Pages; dokładne komponenty pochodzą z locków i cały payload przechodzi wspólną bramę malware. |
| co 15 minut | `mwoDevelop/kodi` | `approve-umbrella-update.yml` | Sprawdza ścisłą allowlistę PR aktualizującego wyłącznie lock Umbrelli. | Domyślnie obserwacyjny. Mutacja wymaga `UMBRELLA_AUTO_MERGE_ENABLED=true` i osobnej App bez bypassu rulesetów. |
| co 30 minut | `mwoDevelop/kodi` | `approve-umbrella-promotion.yml` | Sprawdza PR stable związany z dokładnym snapshotem, hermetyczną atestacją i niezmienionym lockiem QNAP. | Forward rollback nigdy nie kwalifikuje się do automatycznego approval; normalna promocja używa tej samej chronionej App i native auto-merge. |
| 04:20 codziennie | `mwoDevelop/kodi` | `reconcile-upstreams.yml` | Wykrywa stan wszystkich zarządzanych komponentów i przygotowuje dokładnego kandydata na lock kanału testing. | Ogólny kandydat trafia na `automation/testing-lock` i wymaga review. |
| 04:35 codziennie | `mwoDevelop/kodi` | `reconcile-upstreams.yml` w trybie komponentowym | Przygotowuje lock zmieniający wyłącznie `plugin.video.umbrella`. | PR `automation/testing-lock-plugin-video-umbrella` może otrzymać automatyczne approval dopiero po pełnej weryfikacji allowlisty i CI. |
| 04:29 codziennie | `mwoDevelop/kodi` | `check-youtube-upstream.yml` | Pobiera oficjalny ZIP YouTube z mirroru Kodi, materializuje jego drzewo i porównuje wersję, hash oraz zależności z kwalifikacją. | ZIP i rozpakowane pliki przechodzą wspólną bramę malware. Zmiana może utworzyć PR `automation/youtube-upstream`, ale nie jest automatycznie scalana, promowana ani publikowana przez mwoDevelop. |
| 04:23 codziennie | `mwoDevelop/script.module.mwoscrapers` | `check-provider-upstreams.yml` | Pobiera zaakceptowane niezmienne artefakty Coco i Viper, weryfikuje przypięte digesty, bezpiecznie materializuje zawartość i skanuje dokładne ZIP-y oraz pliki wspólną bramą antymalware. | Tylko do odczytu. Weryfikacja pokrycia wymaga zgodności liczby archiwów, plików i bajtów z raportem skanera. Workflow przesyła artefakt audytu przechowywany przez 14 dni i nigdy nie zmienia gałęzi. Niedostępny artefakt, niezgodność digestu, niepełne pokrycie lub błąd skanowania powodują błąd workflow. |
| 04:35 codziennie | `mwoDevelop/ch.repo` | `mwodevelop-watchnixtoons2-update.yml` | Wykrywa upstream WatchNixtoons2, materializuje i skanuje izolowanego kandydata, a następnie go testuje. | Zweryfikowana zmiana może zaktualizować `automation/watchnixtoons2-upstream` i otworzyć PR wymagający review. Nie publikuje repozytorium Kodi. |
| 04:41 codziennie | `mwoDevelop/script.module.mwoscrapers` | `discover-provider-upstreams.yml` | Obserwuje najnowsze źródła providerów i utrzymuje stan review dotyczący wyłącznie pochodzenia. | Zmieniona obserwacja może zaktualizować `automation/provider-provenance` i otworzyć PR wymagający review. Nie importuje ani nie wykonuje kodu providera. |
| 04:50 codziennie | `mwoDevelop/umbrellaplug.github.io` | `propose-upstream-update.yml` | Odtwarza stos poprawek downstream Umbrella na dokładnym commitcie upstream, skanuje kandydata i go testuje. | Zweryfikowana zmiana może zaktualizować `automation/umbrella-upstream` i otworzyć PR wymagający review. Chronione ścieżki muszą pozostać niezmienione. |
| co 15 minut | `mwoDevelop/umbrellaplug.github.io` | `approve-upstream-update.yml` | Sprawdza dokładny PR odtwarzający fork Umbrelli, jego Candidate-ID, stos patchy i zielone checki. | Domyślnie obserwacyjny. Mutacja wymaga chronionego Environment, dedykowanej App i `UMBRELLA_AUTO_MERGE_ENABLED=true` również w repozytorium forka. |
| 05:03 codziennie | `mwoDevelop/script.module.mwoscrapers` | `probe-provider-health.yml` | Sprawdza publiczne kontrakty wszystkich kwalifikowanych providerów na co najmniej dwóch kontrolowanych filmach i dwóch odcinkach. | Tylko do odczytu. Wynik schema 2 rozróżnia błędy transportu, kontraktu, deadline i pusty wynik po filtracji; quorum chroni przed uznaniem pojedynczego braku tytułu za awarię providera. Artefakt nie zapisuje nazw źródeł, magnetów, hashy ani URL-i treści. |

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

Żaden cykliczny workflow poza ściśle ograniczoną ścieżką Umbrelli nie scala PR ani
nie promuje `testing` do `stable`. Automatyka nigdy nie zmienia poświadczeń
Real-Debrid ani konfiguracji użytkownika Kodi. Szczegółowy kontrakt wyjątku opisuje
[automatyczny release Umbrelli](umbrella-automated-release.md).

## Monitorowanie na QNAP

`qnap-upstream-watchdog` działa w Container Station i odpytuje GitHub co 15 minut.
Monitorowana lista workflow jest wersjonowana w `manifests/upstream-watchdog.json`.
Workflow jest niezdrowy, gdy brakuje ostatniego uruchomienia, zakończyło się ono
błędem lub przekracza indywidualny próg `stale_after_seconds`. Dla procesów co
15 minut jest to 1 godzina, co 30 minut — 2 godziny, a dla dziennych — 36 godzin.
Stan obserwatora jest jednak rozdzielony od wyniku obserwowanych workflow:
`observer_ready` i `collection_state=READY|PARTIAL|ERROR` opisują zdolność zebrania
pełnego, świeżego katalogu, natomiast `monitored_state=HEALTHY|FAILED|UNKNOWN`
opisuje same procesy. Healthcheck kontenera sprawdza gotowość obserwatora i
integralność dokumentu, dlatego poprawnie działający watchdog pozostaje zdrowym
kontenerem również wtedy, gdy raportuje `monitored_state=FAILED`. QTS/Container
Station może dzięki temu odróżnić awarię sondy od alarmu domenowego.

Obserwacja rozdziela dwa fakty. Najnowszy przebieg `schedule` dowodzi, że natywny
cron GitHub nadal jest uruchamiany. Jeżeli jego wynik przekroczy jawny próg z
`manifests/upstream-watchdog.json`, watchdog może wykonać wyłącznie allowlistowany
`workflow_dispatch` na `main`. Udany, nowszy przebieg naprawczy jest prezentowany
w panelu jako `REMEDIATED`; kolejne opuszczone okna ponownie otworzą alert. Pole
`run_event=workflow_dispatch` zachowuje pochodzenie i nie pozwala pomylić fallbacku
z natywnym harmonogramem.

Watchdog ma uwierzytelniony dostęp do GitHub API, aby nie
dzielić anonimowego limitu `60/h` dla adresu wyjściowego QNAP. Token jest wstrzykiwany
z prywatnych referencji podczas wdrożenia i nie trafia do repozytorium ani raportu
statusu. Jedyną operacją zapisu jest `actions:write` potrzebne do wywołania
`workflow_dispatch` dla dokładnej listy wersjonowanego manifestu; watchdog nie może
zmienić gałęzi, PR, release ani artefaktu upstream. Workflow nadal wykonuje własne
kontrole uprawnień, dokładnego SHA i bramek środowiska, a automatyczne merge Umbrelli
pozostaje wyłączone bez `UMBRELLA_AUTO_MERGE_ENABLED=true`. Pomyślne odkrycie nie maskuje
błędu audytu zaakceptowanych artefaktów; oba workflow mwoScrapers są
monitorowane niezależnie.

Pozostałe healthchecki kontenerów QNAP sprawdzają dostępność usług, a nie
harmonogramów aktualizacji:

| Usługa | Interwał | Sonda |
| --- | --- | --- |
| Backend Profile Sync | 30 sekund | lokalny endpoint gotowości HTTPS wewnątrz kontenera |
| Read-only Control Plane | 30 sekund | loopback `/ready`; stan może być `degraded`, gdy zredagowany ostatni poprawny odczyt nadal jest dostępny |
| Przekaźnik providerów mwoScrapers | 30 sekund | lokalny endpoint `/health` wewnątrz kontenera |
| Watchdog upstream | 5 minut | ostatnia utrwalona ocena workflow GitHub |
| Secret Broker | 30 sekund | mTLS `/ready`, klucz główny i integralność SQLite |

Control Plane odświeża co 60 sekund read-only widoki Profile Sync, Secret Brokera,
watchdoga przez prywatne mTLS i zbiorczy stan GitHub, a szczegóły 11 harmonogramów
co 15 minut. Heartbeat procesu Profile Sync urządzeń wylicza z najnowszej generacji
enrollmentu każdego logicznego urządzenia, więc stare generacje nie tworzą
fałszywego alertu. Odczyty GitHub Control Plane i Watchdoga używają tego samego
zweryfikowanego tokena read-only, ale osobnych kopii pliku sekretu w katalogach
wdrożeniowych; panel nie polega na anonimowym limicie API. Błąd źródła nie usuwa ostatniego
poprawnego payloadu: zapisuje kod błędu, przechodzi w `degraded` i dopisuje
zdarzenie do łańcucha audytu. Ten collector nie jest procesem aktualizacji i nie
ma endpointu mutującego, klucza assignmentów ani dostępu do socketa Dockera.
Dashboard mTLS rozdziela `scheduler_status`, `run_result` i `freshness`; jego
cykliczne odczyty nie powiększają tamper-evident audit chain. Katalog określa
osobne progi `missed_windows_warning` i `missed_windows_failure` na podstawie
liczby opuszczonych wystąpień crona. Alerty z bezpośredniego odczytu GitHub i
Watchdoga są deduplikowane po repozytorium, workflow i identyfikatorze
zaplanowanego uruchomienia.

## Klienci Kodi Profile Sync

`service.mwodevelop.profilesync` jest oddzielnym procesem cyklicznym na urządzeniu.
Standardowy profil domowy czeka 15 sekund po uruchomieniu Kodi i sprawdza podpisane
przypisanie `home-stable` co sześć godzin. Rejestracja dla konkretnego urządzenia,
tokeny, materiał podpisujący i ostatnio zastosowana rewizja pozostają lokalne i
są wyłączone z payloadu synchronizowanego profilu.

Profile Sync nie instaluje kodu dodatku, nie uruchamia GitHub workflow, nie promuje
kanału repozytorium ani nie używa przekaźnika providerów. Dlatego jego backend i
harmonogram są monitorowane niezależnie od synchronizacji upstream.

Od wersji 1.1.2 przejściowe błędy transportu, timeout, HTTP 429 i 5xx są
ponawiane z utrwalonym backoffem 1/5/15/30 minut i jitterem. Błędy autoryzacji,
konfiguracji oraz kontraktu są terminalne do czasu zmiany ich odcisku. Telemetria
rozróżnia próbę, udany heartbeat i udany pełny cykl, nie zapisując sekretów.

W tym samym cyklu Agent może pobrać krótkotrwałą kopertę HPKE z Profile Sync.
Profile Sync uzyskuje ją z Secret Brokera przez prywatne mTLS; Control Plane sprawdza
gotowość Brokera co 60 sekund. Nie jest to zadanie GitHub ani automatyczna rotacja
credentiali: lifecycle secret setu wymaga jawnej operacji administracyjnej.

## Procesy ręczne i sterowane zdarzeniami

Buildy, CI, testy antymalware, publikacja testing, kwalifikacja hermetyczna i promocja
stable są przede wszystkim sterowane zdarzeniami. Cykl Umbrelli może przejść te etapy
automatycznie, ale każdy etap zachowuje kontrolę dokładnego SHA, snapshotu i atestacji.
Pozostałe komponenty wymagają dotychczasowego ręcznego review lub jawnego
`workflow_dispatch`.

## Weryfikacja operacyjna

Sprawdź najnowsze zaplanowane uruchomienia bez polegania na historycznym raporcie
wydania:

```bash
gh run list --repo mwoDevelop/kodi \
  --workflow reconcile-upstreams.yml --event schedule --limit 1
gh run list --repo mwoDevelop/kodi \
  --workflow approve-umbrella-update.yml --event schedule --limit 1
gh run list --repo mwoDevelop/kodi \
  --workflow publish-pages.yml --event schedule --limit 1
gh run list --repo mwoDevelop/kodi \
  --workflow check-youtube-upstream.yml --event schedule --limit 1
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
gh run list --repo mwoDevelop/umbrellaplug.github.io \
  --workflow approve-upstream-update.yml --event schedule --limit 1
```

W przypadku wdrożonego watchdoga sprawdź `/run/watchdog/status.json` wewnątrz kontenera
`qnap-upstream-watchdog-upstream-watchdog-1`. Zdrowy kontener stanowi dowód wyłącznie
dla workflow obecnych w wersjonowanym manifeście watchdoga.

Ten sam, zredagowany dokument jest dostępny dla Control Plane pod prywatnym endpointem
`https://upstream-watchdog:9445/v1/status`. Endpoint nie ma portu opublikowanego do
LAN i wymaga dedykowanego certyfikatu klienta mTLS.

Dodając lub usuwając zaplanowane upstream workflow, zaktualizuj razem:

1. jego plik workflow i cron;
2. ten dokument katalogowy;
3. `manifests/control-plane-schedules.json`;
4. `manifests/upstream-watchdog.json` (progi per workflow muszą być identyczne);
5. testy katalogu/watchdoga i niezmienne obrazy QNAP;
6. aktywne wdrożenie QNAP, a następnie funkcjonalną kontrolę stanu.

Raporty historyczne poniżej `docs/e2e-results/` opisują podaną datę certyfikacji i nie
mogą być traktowane jako bieżący stan operacyjny.
