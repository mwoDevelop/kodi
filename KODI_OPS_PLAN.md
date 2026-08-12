# Plan uproszczenia operacji release, rollout i restore Kodi

Status: wdrożony; plan pozostaje kontraktem bram release

Data: 2026-08-11

Repo nadrzędne: `mwoDevelop/kodi`

Docelowy publiczny punkt wejścia: `tools/kodi_ops.py`

Raport niezależnego review: `docs/KODI_OPS_PLAN_REVIEW.md`

## 1. Cel

Zastąpić konieczność ręcznego składania wielu poleceń trzema operacjami na
poziomie użytkownika:

```bash
.venv/bin/python tools/kodi_ops.py release
.venv/bin/python tools/kodi_ops.py rollout
.venv/bin/python tools/kodi_ops.py restore \
  --device DEVICE --mode repair --yes
```

Obecne skrypty pozostają małymi, testowalnymi adapterami wykonawczymi. Nowy
orchestrator nie duplikuje ich logiki i nie staje się kolejną implementacją
instalacji, synchronizacji ani publikacji.

## 2. Zakres i granice

### 2.1 `release`

Operacja prowadzi zmianę od wypchniętego kodu do certyfikowanego kanału
`stable`, a po zakończonej promocji domyślnie uruchamia `rollout`. Jest to
wznawialna maszyna stanów, a nie jedno nieprzerwane wywołanie omijające review:

1. sprawdza czystość repozytoriów, obecność dokładnych commitów na
   `origin/main`, zgodność chronionych branchy i brak konfliktujących operacji;
2. wykrywa zmienione komponenty względem bieżących locków;
3. uruchamia testy komponentów oraz skan antymalware dokładnych bajtów;
4. publikuje lub potwierdza kanał `testing` i niezmienny snapshot;
5. certyfikuje dokładny snapshot najpierw na BlueStacks, potem na X88;
   certyfikacja publikuje niezmienną, wersjonowaną atestację
   `device-attestation-<attestation_id>.json`, a nie nadpisuje stałego assetu;
6. uruchamia workflow promocji, który bez ponownego budowania artefaktów
   tworzy jeden PR aktualizujący publiczny lock stable oraz, gdy zmieniły się
   obrazy, `manifests/locks/qnap-stable.json`;
7. zapisuje numer PR, Candidate-ID, snapshot ID i ważność atestacji, po czym
   kończy aktywną fazę jako `WAITING_APPROVAL`;
8. po niezależnym review i merge operator wznawia dokładny run przez
   `release --resume RUN_ID`;
9. wznowienie weryfikuje niezmienność całego PR, merge SHA, exact-head CI
   wszystkich zmienianych locków, ważność oraz SHA-256 dokładnej atestacji
   wskazanej przez promotion lock i wynik `deploy-stable`;
   orchestrator nigdy sam nie zatwierdza ani nie scala własnego PR;
10. weryfikuje publiczny indeks, ZIP-y i SHA-256, a następnie wywołuje
   `rollout` dla floty na podstawie właśnie wypromowanego stable;
11. zapisuje jeden raport łączący commit, snapshot, attestation, promocję,
   urządzenia i wyniki E2E.

Opcje kontrolne:

```bash
.venv/bin/python tools/kodi_ops.py release --dry-run
.venv/bin/python tools/kodi_ops.py release --no-promote
.venv/bin/python tools/kodi_ops.py release --no-rollout
.venv/bin/python tools/kodi_ops.py release --resume RUN_ID
```

`--no-promote` przygotowuje i certyfikuje kandydata, ale nie zmienia stable.
Po teście kandydata lub przerwaniu przed promocją canary muszą zostać
zweryfikowane jako przywrócone do produkcyjnego origin i tożsamości. Zmieniona
treść PR, zmieniony stable albo wygasła siedmiodniowa atestacja unieważniają
wznowienie i wymagają ponownej certyfikacji. Przed Etapem 4 workflow
`certify-testing.yml` musi przejść ze stałego `device-attestation.json` na
wersjonowane immutable assets, a `promote-stable.yml` musi przyjmować exact
attestation ID i digest.
Po opublikowaniu stable nie wykonuje się mutowalnego rollbacku tego samego
wydania; wycofanie wymaga nowej, audytowalnej promocji poprzedniego snapshotu.

### 2.2 `rollout`

Operacja uzgadnia infrastrukturę i wszystkie osiągalne instalacje z bieżącym
stable. Domyślna kolejność:

1. globalny preflight;
2. uzgodnienie QNAP z zatwierdzonymi digestami;
3. BlueStacks jako pierwszy canary;
4. X88 jako drugi canary;
5. Sony TV i Bedroom TV;
6. `nuc-mwo` i `nuc-alek`;
7. zbiorcze testy E2E i ponowny audyt idempotencji.

Preflight obejmuje:

- walidację `.env` i prywatnego rejestru schema 2;
- jednoznaczność logical device ID, endpointów i oczekiwanej tożsamości;
- kontrolę publicznego stable locka, indeksu repo oraz SHA-256 ZIP-ów;
- status ADB/SSH, wersję Kodi i kwalifikację ścieżek runtime;
- stan QNAP, RAID, Container Station, Profile Sync, relay i watchdoga;
- lokalną blokadę operatora oraz zdalne generation/CAS checks wykluczające
  konflikt z innym hostem, GitHub Actions i operacją QNAP;
- przypięcie `source_snapshot_id`, SHA locka i publicznych SHA-256 na cały run.

Dla każdej usługi QNAP release oblicza content hash zadeklarowanych inputów
builda. Zmiana tego hasha uruchamia build i zapis zatwierdzonego, niezmiennego
digesta. Zwykły rollout nie buduje obrazu z bieżącego checkoutu: wdraża wyłącznie
digest zapisany przez release i tylko gdy różni się on od faktycznie
uruchomionego digesta. Sam nowy commit repo nie jest powodem builda ani deployu.
Brak zmiany kończy etap jako `NO_CHANGE`.

Autorytatywnym źródłem zatwierdzonych obrazów jest wersjonowany
`manifests/locks/qnap-stable.json`, zmieniany wyłącznie przez PR i chroniony
exact-head CI. Dla każdej usługi zapisuje source repo/commit, input hash,
platformy, security report SHA-256, image digest i approval record. Rollout
przypina commit oraz SHA locka i stosuje CAS względem obserwowanego runtime.
Ignorowany `.kodi-private/qnap-images.json` pozostaje cache/evidence jednego
hosta i nigdy nie jest źródłem autoryzacji deployu.

Na każdym urządzeniu rollout uzgadnia:

- stabilne repo mwoDevelop oraz dozwolone repo oficjalne;
- Umbrella;
- moduł mwoScrapers i jego wrapper;
- WatchNixtoons2 mwoDevelop;
- mwoDevelop Profile Sync;
- Rapideo i jego jawnie przypięte zależności;
- pochodzenie dodatków oraz ich włączenie;
- logical device ID, kanał, harmonogram i tryb Profile Sync;
- przenośne favourites, akcje WatchNixtoons2 i grafiki adresowane zawartością.

Profile Sync/QNAP jest autorytatywnym kanałem rutynowej konfiguracji. Bezpośredni
portable-state pozostaje adapterem bootstrap/restore oraz awaryjną kompensacją;
orchestrator nie uruchamia obu writerów równolegle. Najpierw uzgadnia dodatek,
origin i tożsamość, następnie publikuje lub wybiera jedną przypiętą rewizję,
a na końcu wymusza i weryfikuje jej zastosowanie. Każdy managed path ma w
manifeście dokładnie jednego writera.

Sekrety, tokeny i ustawienia prywatne pozostają per urządzenie. Orchestrator
może korzystać z ignorowanych snapshotów i referencji z `.env`, lecz przekazuje
sekrety wyłącznie przez bezpieczne wejście lub referencję, nigdy w argv. Nie
kopiuje `.env`, pełnych settings ani credential payloadów do evidence, Git lub
CI. Nie kopiuje cache, baz bibliotek ani wygenerowanych plików Kodi.

Po każdym urządzeniu wykonywane są:

- kontrola inventory wersji i origin;
- Profile Sync pairing, heartbeat, podpisany kandydat i sync/no-op;
- kontrola liczby favourites i kompletności thumbnails;
- deterministyczna brama: exact SHA/origin, enablement, podpisany sync/no-op,
  gotowość backendu i kompletność managed state;
- ponawiana diagnostyka zewnętrzna: provider, VPN, resolver oraz playback;
- sanitizacja logów i zapis prywatnego raportu.

Diagnostyka zależna od zewnętrznego providera nie wyzwala rollbacku bez
klasyfikacji przyczyny. Jest obowiązkowa dla canary, zmienionego urządzenia i
restore; dla niezmienionego urządzenia wystarcza deterministyczny smoke, chyba
że operator jawnie wybierze pełną weryfikację.

Po wyczerpaniu retry awaria zależna od zewnętrznego upstreamu otrzymuje wynik
etapu `DIAGNOSTIC_FAILED`, stan runu `PARTIAL` i kod 2; dla canary zatrzymuje
kolejne fale, ale sama nie uruchamia kompensacji. Jeśli dowód wskazuje lokalną
regresję wprowadzoną przez plan (origin, credential binding, VPN/LAN policy lub
provider contract), etap ma `ERROR`, run `FAILED`, a bezpieczna kompensacja
dotyczy wyłącznie odpowiedzialnego adaptera. Nierozstrzygnięta przyczyna jest
`DIAGNOSTIC_FAILED`, nie fałszywym `PASS` ani automatycznym rollbackiem.

Opcje operatora:

```bash
.venv/bin/python tools/kodi_ops.py rollout --dry-run
.venv/bin/python tools/kodi_ops.py rollout --device sony-tv
.venv/bin/python tools/kodi_ops.py rollout --device sony-tv --device nuc-mwo
.venv/bin/python tools/kodi_ops.py rollout --resume RUN_ID
```

Bez `--device` źródłem członkostwa floty jest `KODI_SYNC_DEVICES` z `.env`.
Urządzenie niedostępne po jednoznacznym rozpoznaniu otrzymuje `DEFERRED` i nie
jest modyfikowane. Niedostępność albo błąd BlueStacks/X88 podczas pełnego
rolloutu zatrzymuje kolejne fale. Przy rolloucie jawnie ograniczonym do jednego
urządzenia `DEFERRED` kończy polecenie niezerowym kodem.

`rollout --device ...` ma zakres `scoped`: wykonuje read-only health QNAP,
mutuje wyłącznie jawnie wskazane urządzenia i nie dodaje ukrytych canary.
Wiele selektorów zachowuje kolejność floty w obrębie podanego zbioru.
`--resume` nie może być łączone z nowymi `--device`. Przed każdą mutującą falą
orchestrator ponownie odczytuje stable; zmiana kończy run jako `DRIFTED`, bez
przełączania wersji w locie ani niejawnego downgrade'u starego planu.

### 2.3 `restore`

Operacja służy nowej, wyczyszczonej albo uszkodzonej instalacji. W v1 wymaga
dokładnie jednego `--device`, jawnego `--mode repair|reinstall` oraz `--yes`
dla wyświetlonego, content-addressed planu:

1. weryfikuje fizyczną i logiczną tożsamość celu oraz fingerprint planu;
2. sprawdza target binding snapshotu i integralność APK/Flatpak source;
3. dla istniejącej instalacji tworzy oraz weryfikuje prywatny backup; jego brak
   lub błąd blokuje uninstall, a nowa instalacja raportuje `NOT_APPLICABLE`;
4. bezpośrednio przed destrukcją ponownie sprawdza tożsamość urządzenia;
5. w trybie `reinstall` odinstalowuje Kodi i czyści jego storage;
6. w trybie `repair` pomija uninstall i naprawia istniejącą instalację;
7. tylko w trybie `reinstall` instaluje Kodi właściwe dla platformy; tryb
   `repair` waliduje istniejące binaria i przechodzi bez ich reinstalacji;
8. instaluje repo i stabilny zestaw dodatków;
9. odtwarza prywatne ustawienia i credentiale przypisane tylko temu celowi;
10. enroluje Profile Sync bez kopiowania tożsamości innego urządzenia;
11. wywołuje ograniczony `rollout --device ...`;
12. przeprowadza pełne E2E i zachowuje potwierdzenie odtworzenia.

`restore --all` nie istnieje w v1. Obecny `kodi_reinstall.py` pokrywa Android;
czysta instalacja Linux/Flatpak jest nowym adapterem i przed implementacją
przechodzi osobną feasibility gate dotyczącą instalacji Flatpak, sesji
użytkownika oraz mapowania prywatnego rejestru i reinstall configu.

## 3. Architektura implementacji

Publiczny plik pozostaje cienkim parserem CLI:

```text
tools/kodi_ops.py
tools/kodi_operations/
  model.py              # typy etapu, wyniku i polityki błędów
  manifest.py           # walidacja deklaratywnego planu
  planner.py            # DAG i dry-run
  runner.py             # wykonanie, blokada, resume i cleanup
  report.py             # raport sanitizowany i prywatny dowód szczegółowy
  operations/
    release.py
    rollout.py
    restore.py
  adapters/
    github.py
    qnap.py
    android.py
    flatpak.py
    portable_state.py
    e2e.py
manifests/kodi-operations.json
```

`manifests/kodi-operations.json` opisuje kolejność fal, wymagane bramy,
dozwolone komponenty i klasy wyniku. Nie zawiera adresów prywatnych ani
sekretów. Urządzenia i endpointy nadal pochodzą z `.env` oraz
`.kodi-private/devices.json`.

Adaptery implementują wspólny kontrakt:

```text
probe(context) -> observation
plan(context, observation) -> immutable action plan
apply(context, plan) -> result
verify(context, plan, result) -> evidence
compensate(context, plan, result) -> evidence  # tylko gdy capability ją wspiera
```

Każdy adapter deklaruje capabilities, między innymi `supports_restore`,
`supports_compensation`, `supports_live_playback` i granice własnej transakcji.
Dodanie kolejnej platformy lub backendu zwykle wymaga nowego adaptera i wpisu
manifestu; operacje zależą od capabilities, a nie od rozgałęzień po nazwie
platformy. Brak wymaganej capability zatrzymuje planowanie przed mutacją.

## 4. Wykorzystanie istniejących narzędzi

| Odpowiedzialność | Istniejący adapter / kod |
|---|---|
| Inventory i tożsamość urządzeń | `kodi_devices.py`, `kodi_inventory.py`, `kodi_sync_inventory.py` |
| QNAP build/deploy/status | `qnap_images.py`, `qnap_profile_sync.py` |
| Android lifecycle i transport | `kodi_transports.py`, `kodi_lifecycle.py` |
| Stabilne dodatki mwoDevelop na Androidzie | funkcje z obecnych rolloutów kandydatów i testu Profile Sync |
| Rapideo i dodatki zewnętrzne | `kodi_default_addons.py` |
| Favourites i thumbnails | `kodi_portable_state_rollout.py` |
| Profile Sync Android | produkcyjny adapter wydzielony z `profile_sync_addon_device.py` |
| Profile Sync i wymagane dodatki Flatpak | `kodi_flatpak_profile_sync_rollout.py` |
| Pełna reinstalacja Android | `kodi_reinstall.py` |
| Testing/snapshot/certification/stable | istniejące GitHub Actions i ich artefakty |
| E2E dodatków | obecne skrypty poniżej `tests/e2e/` |

Kod produkcyjny nie powinien importować modułów z `tests/e2e`. W pierwszym
etapie wspólna logika instalacji i kontroli Profile Sync zostanie przeniesiona
do `tools/`, a testy będą wywoływać ten sam adapter.

## 5. Stan, wznowienie i współbieżność

Każde wywołanie otrzymuje losowy `run_id` i prywatny katalog:

```text
.kodi-private/kodi-ops/runs/<run_id>/
  plan.json
  state.json
  evidence/
  report.json
```

Plan zawiera dokładne commity, wersje, digesty, snapshot i listę urządzeń.
`--resume` akceptuje wyłącznie ten sam content-addressed plan. Przed pominięciem
zakończonego etapu ponownie wykonuje jego `probe` i `verify`; nie ufa samemu
lokalnemu znacznikowi sukcesu.

Stan runu rozróżnia `COMPLETE`, `PARTIAL`, `WAITING_APPROVAL`, `FAILED`,
`DRIFTED` i `RECOVERY_REQUIRED`. Wynik pojedynczego etapu to `PASS`,
`NO_CHANGE`, `DEFERRED`, `DIAGNOSTIC_FAILED`, `ROLLED_BACK`, `SKIPPED` albo
`ERROR`.
`ROLLED_BACK` nie daje sukcesu całego runu, a `NO_CHANGE` oznacza brak mutacji
zarządzanej konfiguracji, artefaktu ani deploymentu. Telemetryczny heartbeat,
read-only probe i test mogą odświeżyć obserwowalność, lecz nie zmieniają tej
klasyfikacji.

Lokalna blokada operatora jest optymalizacją, nie granicą poprawności.
GitHub concurrency/exact SHA, QNAP operation generation/CAS i identyfikatory
operacji urządzeń chronią przed drugim hostem oraz procesem cyklicznym.
Przed mutacją adapter porównuje obserwowaną generację z planem. Przerwany
proces sprząta wyłącznie własne katalogi tymczasowe i nie usuwa nieznanego
stanu.

Katalogi runów mają tryb `0700`, pliki `0600`, zapisy atomowe i odmowę pracy
przez symlink. Raport sanitizowany powstaje z allowlisty pól, nie przez regex
na stdout/stderr. Prywatne evidence nie zawiera kopii `.env`, pełnych backupów
ani credential payloadów. Manifest określa retencję runów; cleanup usuwa tylko
wygasłe, zakończone runy po sprawdzeniu właściciela i ścieżki.

## 6. Polityka błędów i rollback

- globalny preflight jest fail-closed;
- nieudany canary zatrzymuje rollout przed kolejną falą;
- orchestrator nie obiecuje globalnej ani per-device atomowości; każdy adapter
  raportuje własne granice transakcji, safe points i dostępne kompensacje;
- kompensacja urządzenia nie cofa innych urządzeń, które przeszły weryfikację;
- urządzenia niedostępne poza canary są `DEFERRED`, nie `PASS`;
- niezdrowy watchdog z listą nieudanych workflow blokuje `release`, lecz zwykły
  rollout może działać wyłącznie z czasowym waiverem wskazującym dokładny
  workflow, powód, operatora i termin ważności; stale uszkodzony watchdog albo
  brak świeżego dokumentu statusu nie podlega waiverowi;
- przed zmianą Profile Sync na QNAP wymagane są application-level backup,
  pobrana i zweryfikowana szyfrowana kopia off-NAS, poprzedni Compose/env/digest
  oraz brama kompatybilności schema;
- poprzedni obraz QNAP jest przywracany automatycznie tylko przy potwierdzonej
  backward compatibility danych; inaczej run kończy się `RECOVERY_REQUIRED`
  z instrukcją restore;
- promocja stable jest odwracana wyłącznie nową promocją podpisanego snapshotu;
- raport końcowy nie może być `COMPLETE`, jeśli wymagany etap jest `ERROR`,
  `ROLLED_BACK`, `RECOVERY_REQUIRED` albo pominięty bez ważnego odstępstwa.

## 7. Etapy implementacji

### Etap 0 — charakterystyka i kontrakty

1. Zapisać testy charakteryzujące bieżące polecenia i sanitizowane wyniki.
2. Zdefiniować schemat manifestu, planu, state i raportu.
3. Zdefiniować osobno wyniki etapów i stany całego runu, w tym
   `WAITING_APPROVAL`, `DRIFTED` oraz `RECOVERY_REQUIRED`.
4. Utworzyć fixture'y Android, Flatpak, QNAP i GitHub bez wykonywania mutacji.

Brama: brak zmian w działaniu istniejących narzędzi; pełne dotychczasowe E2E
pozostaje zielone.

### Etap 1 — planner i read-only dry-run

1. Zaimplementować parser trzech operacji i wspólne opcje.
2. Dodać rejestr adapterów i walidowany DAG.
3. Dodać lokalne i zdalne blokady/generacje, prywatny stan, allowlistowy
   raport, retencję oraz testy sentinel-secret.
4. Zaimplementować `release --dry-run`, `rollout --dry-run` oraz
   `restore --dry-run`.

Brama: dry-run wykonuje tylko planowanie i read-only probes. Może pisać
wyłącznie do własnego katalogu run-private; nie uruchamia buildów, testów
tworzących kanoniczne `.e2e/`, mutujących workflow GitHub ani operacji apply.

### Etap 2 — pełny `rollout`

1. Dodać content hash inputów obrazu i rozdzielić QNAP build w release od
   deployu zatwierdzonego digesta w rollout.
2. Dodać i chronić `manifests/locks/qnap-stable.json`; release zmienia go
   przez PR, a rollout przypina jego commit i SHA oraz odrzuca prywatny cache
   jako źródło autoryzacji deployu.
3. Wydzielić produkcyjny adapter Profile Sync Android z kodu E2E.
4. Podłączyć uzgadnianie repo, dodatków i origin na Androidzie.
5. Podłączyć Rapideo oraz jeden autorytatywny przepływ Profile Sync dla
   routine settings i portable favourites/artwork.
6. Podłączyć adapter Flatpak dla obu profili NUC.
7. Zaimplementować full/scoped semantics, fale canary, capability-based
   kompensacje, `DEFERRED`, drift stable i resume.
8. Dodać deterministyczne bramy, osobną diagnostykę zewnętrzną oraz ponowne
   wywołanie no-op.

Brama: BlueStacks i X88 muszą przejść przed pozostałymi urządzeniami; drugi
identyczny rollout nie może wykonywać niepotrzebnych instalacji ani restartów.

### Etap 3 — `restore`

Status: zakończony 2026-08-12 dla Android i Linux/Flatpak.

1. Opakować istniejący Android reinstall/restore za adapterem.
2. Wymagać trybu repair/reinstall, jednego celu, ważnego backupu i ponownej
   weryfikacji tożsamości bezpośrednio przed destrukcją.
3. Wykonać feasibility gate, a następnie dodać nowy adapter Linux/Flatpak.
4. Po odtworzeniu zawsze uruchamiać ten sam ograniczony rollout i E2E.
5. Przetestować nową instancję BlueStacks przed urządzeniem fizycznym.

Brama: test od czystej instalacji do `COMPLETE`, a następnie drugi przebieg
`NO_CHANGE`; w v1 nie istnieje restore całej floty.

Kwalifikacja Flatpak potwierdziła dwa principale na jednym hoście NUC. Dla
wspólnego systemowego Flatpaka adapter zachowuje binaria i destrukcyjnie
odtwarza wyłącznie kanoniczny katalog danych przypiętego UID. `nuc-alek` i
`nuc-mwo` przeszły backup, reset, odtworzenie, ponowne enrollment, stable
rollout, E2E i wspólny przebieg no-op. Szczegóły:
`docs/e2e-results/2026-08-12-flatpak-destructive-restore.md`.

### Etap 4 — `release`

1. Zmienić `certify-testing.yml`, aby publikował immutable
   `device-attestation-<attestation_id>.json`, oraz `promote-stable.yml`, aby
   przyjmował i zapisywał dokładne attestation ID i SHA-256.
2. Rozszerzyć jeden PR promocji o wszystkie wymagane locki publicznego repo i
   QNAP; jeden `WAITING_APPROVAL` kończy się dopiero po merge oraz exact-head
   CI całego zestawu zmian.
3. Podłączyć workflow przez exact run ID i exact head SHA.
4. Dodać wykrywanie zmienionych komponentów i oczekiwanie na wymagane checki.
5. Podłączyć testing snapshot, skan, certyfikację BlueStacks/X88 i promocję.
6. Zaimplementować `WAITING_APPROVAL`, przypięcie PR i wznowienie po merge bez
   omijania branch protection.
7. Zweryfikować ważność, ID i SHA-256 dokładnej atestacji z promotion locka,
   deploy run i publiczne bajty przed rolloutem.
8. Związać raport release z raportem podrzędnego rolloutu.

Brama: test rzeczywistego no-op release oraz kontrolowany release komponentu,
który publikuje dokładnie certyfikowane bajty.

### Etap 5 — dokumentacja i przełączenie interfejsu

1. Dodać trzy polecenia do głównego README i dokumentacji operacyjnej.
2. Pozostawić dotychczasowe skrypty udokumentowane jako adaptery/diagnostyka.
3. Nie oznaczać ich jako legacy, dopóki orchestrator nie przejdzie co najmniej
   dwóch udanych pełnych rolloutów i jednego restore.
4. Po okresie stabilizacji ograniczyć dokumentację operatora do nowego CLI.
5. Dodać sekcję „Przykłady rollout” z dry-run, full, scoped, multi-device,
   resume, kodami wyjścia, raportem, drift stable i niedostępnym celem.

## 8. Plan testów

### Testy jednostkowe

- walidacja manifestu i DAG;
- klasyfikacja zmian i kolejność fal;
- lokalne/zdalne blokady, generation checks i kolizje uruchomień;
- resume po przerwaniu każdego etapu;
- allowlistowa redakcja tokenów, credentiali, endpointów prywatnych i kluczy;
- sentinel-secret przez wyjątek, kompensację, przerwanie i resume;
- propagacja wyniku etapu, stanu runu i kodów wyjścia;
- capability-based wybór adaptera Android/Flatpak/QNAP;
- scoped/full semantics i zakaz zmiany selektorów przy resume;
- content hash inputów QNAP oraz drift stable między falami;
- klasyfikacja `DIAGNOSTIC_FAILED` wobec lokalnego `ERROR`;
- `repair` nie emituje poleceń uninstall/install, a `reinstall` wymaga
  powtórnej identyfikacji celu i ważnego backupu.

### Testy integracyjne

- fake ADB/SSH/QNAP/GitHub z zapisanym kontraktem poleceń;
- tymczasowy backend Profile Sync z podpisaną rewizją;
- niezmienne ZIP-y i błędne SHA-256;
- przerwanie oraz wznowienie po buildzie, instalacji i restarcie Kodi;
- `WAITING_APPROVAL`, zmieniony PR i wygasła atestacja;
- ponowna certyfikacja po wygaśnięciu tworzy nowy immutable asset, a promocja
  akceptuje wyłącznie dokładne ID i SHA-256 wskazane w locku;
- jeden PR promocji atomowo obejmuje wszystkie wymagane locki publicznego repo
  i QNAP; brak merge albo exact-head CI któregokolwiek locka blokuje rollout;
- niedostępny cel spoza canary oraz niedostępny canary;
- kompensacje dodatku, portable state i enrollmentu;
- QNAP z backward-compatible rollback oraz przypadkiem `RECOVERY_REQUIRED`;
- QNAP lock przechodzący przez PR/exact-head CI, CAS deployu oraz odrzucenie
  niezatwierdzonego digesta pochodzącego wyłącznie z prywatnego cache;
- rozdzielenie deterministycznej bramy od zawodnej diagnostyki upstream,
  w tym `DIAGNOSTIC_FAILED`/`PARTIAL` po wyczerpaniu retry.

### E2E na żywo

1. `rollout --dry-run` dla całej floty;
2. BlueStacks: pełny rollout i powtórny `NO_CHANGE`;
3. X88: pełny rollout, VPN aktywny, Rapideo i resolver;
4. Sony TV i Bedroom TV: favourites/thumbnails, Rapideo, resolver i VPN;
5. oba profile NUC: Flatpak, izolacja kont, Profile Sync i `NO_CHANGE`;
6. QNAP: status, deploy przypiętego digesta, backup/health i no-op;
7. test kontrolowanego przerwania oraz `--resume`;
8. pełne stare E2E repozytorium;
9. kontrolowany release testing -> certification -> stable -> rollout;
10. końcowa kontrola procesów cyklicznych i watchdoga.

Hermetyczny `tests/e2e/run.sh` pozostaje bramą build + pytest, ale nie jest
dowodem live E2E. Capability matrix określa per platforma bramy `BLOCKING`
(inventory, origin, exact SHA, enablement, signed sync/no-op, readiness) oraz
`DIAGNOSTIC_RETRIED` (provider, VPN, resolver, playback). Pełne live E2E jest
obowiązkowe dla canary, zmienionych celów i restore.

## 9. Plan dokumentacji i przykłady wywołań

Główne `README.md` ma prowadzić do nowej sekcji operacyjnej
`docs/kodi-operations.md`. Dokumentacja pokazuje najpierw jedno polecenie
wysokiego poziomu, a dopiero w części diagnostycznej mapowanie na adaptery.

### 9.1 Pełny plan bez mutacji

```bash
.venv/bin/python tools/kodi_ops.py rollout --dry-run
```

Zakres: read-only health QNAP, inventory całej floty, przypięcie stable i
wyświetlenie obu canary oraz kolejnych fal. Nie uruchamia buildów, publikacji,
apply, restartów ani testów zapisujących kanoniczne `.e2e/`. Raport trafia do
`.kodi-private/kodi-ops/runs/<run_id>/report.json`.

### 9.2 Pełny rollout

```bash
.venv/bin/python tools/kodi_ops.py rollout
```

Zakres: deploy wyłącznie zatwierdzonych digestów QNAP, BlueStacks, X88,
pozostałe Android TV, a następnie oba profile NUC. Oba canary są obowiązkowe.
Oczekiwany wynik urządzenia to `PASS` po zmianie albo `NO_CHANGE`; niedostępny
cel poza canary daje `DEFERRED` i stan runu `PARTIAL`.
Po wyczerpaniu retry zewnętrzna diagnostyka daje `DIAGNOSTIC_FAILED`, stan
`PARTIAL` i kod 2; na BlueStacks lub X88 zatrzymuje dalsze fale.

### 9.3 Scoped rollout jednego urządzenia

```bash
.venv/bin/python tools/kodi_ops.py rollout --device sony-tv
```

Zakres: read-only health QNAP i mutacja wyłącznie `sony-tv`. Nie dodaje
BlueStacks ani X88 jako ukrytych celów. Niedostępny Sony kończy run jako
`PARTIAL` z niezerowym kodem.
Wyczerpana diagnostyka upstream również daje `DIAGNOSTIC_FAILED`, `PARTIAL`
i kod 2; nie uruchamia automatycznej kompensacji bez dowodu lokalnej regresji.

### 9.4 Scoped rollout kilku urządzeń

```bash
.venv/bin/python tools/kodi_ops.py rollout \
  --device sony-tv \
  --device nuc-mwo
```

Zakres: wyłącznie jawnie podany zbiór, uporządkowany zgodnie z kolejnością
floty. QNAP pozostaje read-only, a brak jednego celu nie jest przedstawiany
jako pełny sukces drugiego.
`DIAGNOSTIC_FAILED` na dowolnym celu pozostaje widoczne w raporcie i daje
`PARTIAL`/kod 2; jeśli wskazany zbiór zawiera canary, jego błąd zatrzymuje
następne cele tego scoped runu.

### 9.5 Wznowienie dokładnego planu

```bash
.venv/bin/python tools/kodi_ops.py rollout --resume RUN_ID
```

Wznowienie korzysta z zapisanych selektorów, snapshotu, locka i digestów.
Nie wolno dołączać nowych `--device`. Zmieniony stable lub generation kończy
run jako `DRIFTED`; operator tworzy nowy dry-run zamiast wymuszać stare wersje.

### 9.6 Release z ręcznym approval

```bash
.venv/bin/python tools/kodi_ops.py release
# Po niezależnym review i merge utworzonego PR:
.venv/bin/python tools/kodi_ops.py release --resume RUN_ID
```

Pierwsze polecenie może poprawnie zakończyć aktywną fazę jako
`WAITING_APPROVAL`. Drugie weryfikuje PR, atestację, deploy stable i dopiero
wtedy uruchamia podrzędny pełny rollout.

### 9.7 Restore jednego celu

```bash
.venv/bin/python tools/kodi_ops.py restore \
  --device x88pro20 \
  --mode reinstall \
  --yes
```

Dokumentacja pokazuje wcześniej odpowiadający mu `--dry-run`, fingerprint
planu, lokalizację backupu i warunek fail-closed. Nie zawiera przykładu
`restore --all`, ponieważ taki interfejs nie istnieje w v1.

### 9.8 Wyniki i kody wyjścia

| Kod | Stan runu | Znaczenie |
|---:|---|---|
| 0 | `COMPLETE` | wszystkie wymagane etapy to `PASS`/`NO_CHANGE` |
| 2 | `PARTIAL` | co najmniej jeden `DEFERRED` lub `DIAGNOSTIC_FAILED` |
| 3 | `WAITING_APPROVAL` | wymagany niezależny review/merge; run można wznowić |
| 4 | `DRIFTED` | stable, PR albo generation różni się od planu |
| 5 | `FAILED` | brama lub wymagany etap zakończyły się błędem |
| 6 | `RECOVERY_REQUIRED` | automatyczna kompensacja nie jest bezpieczna |

Przy każdym przykładzie dokumentacja podaje zakres mutacji, obecność canary,
oczekiwane wyniki, kod wyjścia, lokalizację raportu, reakcję na niedostępny
cel i drift stable. Dokumentacja diagnostyczna pokazuje także, jak z `run_id`
odnaleźć exact GitHub run, snapshot, QNAP digest i prywatne evidence bez
ujawniania sekretów.

## 10. Kryteria pełnego release orchestratora

1. Jedno `rollout` doprowadza całą osiągalną flotę do stable bez ręcznego
   wywoływania skryptów podrzędnych.
2. Drugi rollout zwraca `NO_CHANGE` dla każdego osiągalnego celu.
3. BlueStacks i X88 są obowiązkowymi canary i zatrzymują kolejne fale po
   błędzie.
4. Android i Flatpak mają ten sam kontrakt raportu, mimo różnych adapterów.
5. QNAP buduje obraz tylko po zmianie content hasha inputów i wdraża wyłącznie
   zatwierdzony digest różny od uruchomionego.
6. `release` respektuje `WAITING_APPROVAL` i publikuje te same bajty, które
   przeszły ważną certyfikację; promotion lock wskazuje immutable attestation
   ID i SHA-256, więc ponowna certyfikacja nie nadpisuje wcześniejszego dowodu.
   Jeden PR promocji obejmuje wszystkie wymagane locki repo i QNAP, a rollout
   czeka na merge i exact-head CI całego zestawu.
7. Android `restore` przechodzi od czystej instalacji do pełnego E2E na nowym
   BlueStacks; Flatpak restore ma osobną zaliczoną feasibility gate i E2E.
8. Wznowienie nie powtarza zweryfikowanych mutacji i wykrywa drift.
9. Żaden sanitizowany raport, log CI ani plik Git nie zawiera sekretów.
10. Dotychczasowe testy pozostają zielone, a adaptery można nadal uruchamiać
    osobno do diagnostyki.
11. Dokumentacja prowadzi operatora przez trzy polecenia, nie przez ręczną
    sekwencję kilkunastu narzędzi, i zawiera zweryfikowane przykłady rollout.
12. Żaden PR utworzony przez run nie pozostaje w nieznanym stanie, a każdy
   publiczny artefakt ma zweryfikowane pochodzenie; czyste worktree jest
   sprawdzanym precondition, nie obietnicą globalnego cleanupu.
13. QNAP wdraża tylko digest z zatwierdzonego, wersjonowanego locka, nigdy z
    lokalnego cache ani z bieżącego checkoutu operatora.
14. Zewnętrzny błąd diagnostyczny i lokalna regresja mają odrębne wyniki,
    wpływ na dalsze fale oraz udokumentowane kody wyjścia.

## 11. Proponowane decyzje do akceptacji

1. Publiczne CLI ma dokładnie trzy operacje: `release`, `rollout`, `restore`.
2. `release` zatrzymuje się na niezależny approval PR, a po wznowieniu i udanej
   promocji domyślnie uruchamia `rollout`.
3. BlueStacks i X88 są obowiązkowymi canary w tej kolejności.
4. Pozostałe niedostępne urządzenia mogą zostać `DEFERRED`; jawnie wskazany cel
   niedostępny kończy polecenie błędem.
5. `rollout` obejmuje QNAP, dodatki, Profile Sync, favourites/thumbnails i E2E,
   ale nie wykonuje reinstalacji Kodi.
6. Scoped rollout mutuje tylko jawnie wskazane urządzenia; QNAP jest wtedy
   read-only i nie ma ukrytych canary.
7. `restore` jest jedyną publiczną operacją wykonującą uninstall/cleanup,
   przyjmuje jeden cel i nie oferuje `--all` w v1.
8. Sekrety pozostają niewersjonowane i per urządzenie; uproszczenie CLI nie
   zmienia tej granicy.
9. Istniejące skrypty pozostają adapterami i nie są usuwane w pierwszym
   wydaniu orchestratora.
10. Zwykły rollout nie buduje obrazów QNAP; build i zapis zatwierdzonego
    digesta należą do release.
11. Zewnętrzny provider/VPN/playback są diagnostyką ponawianą i klasyfikowaną,
    a nie automatycznym dowodem wymagającym rollbacku konfiguracji.
12. Atestacje urządzeń są immutable i wersjonowane; promotion lock wiąże
    dokładne ID i SHA-256, a wygaśnięcie wymaga nowej certyfikacji.
13. `manifests/locks/qnap-stable.json` jest jedynym źródłem zatwierdzonych
    digestów QNAP; `.kodi-private/qnap-images.json` jest wyłącznie cache.

## 12. Historyczny szacunek realizacji

- Etap 0–1: 2–3 dni;
- Etap 2: 3–5 dni;
- Etap 3 Android: 1–2 dni;
- feasibility i implementacja restore Flatpak: zakończone;
- Etap 4: 2–3 dni;
- Etap 5 i pełna stabilizacja: 1–2 dni.

Łącznie: około 11–19 dni pracy implementacyjnej i testowej. Osobno należy
liczyć czas kalendarzowy oczekiwania na urządzenia, niezależny review,
ważność atestacji i GitHub Actions. Zakres nie wymaga przepisania działających
adapterów ani zmiany wersji `repository.mwodevelop`.
