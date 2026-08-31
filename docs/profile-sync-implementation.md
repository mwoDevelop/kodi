# Stan wdrożenia Profile Sync

Data: 2026-08-31

To jest chronologiczny zapis wdrożenia, a nie strona statusu na żywo. Poniższe
stwierdzenia dotyczące wersji opisują bramę osiągniętą w zarejestrowanym dniu. Bieżący
wydany klient jest zdefiniowany przez `manifests/locks/stable.json`; użyj `python
tools/qnap_images.py status` i kontroli urządzenia udokumentowanych w
`docs/kodi-private-profile.md` pod kątem stanu działania. Mapa dokumentacji znajduje się
w `docs/README.md`.

## Zaimplementowano

### Przyrost 2026-08-31: stan odtwarzania

- Profile Sync 1.3.0 ma osobny, pięciominutowy cykl playback i lokalny journal
  SQLite; awaria sieci nie usuwa zdarzenia;
- WatchNixtoons2 0.30.0 przekazuje wyłącznie wersjonowany namespace,
  deterministyczny hash strony odcinka i dokładną ścieżkę `plugin://`;
- serwer 0.9.0 nadaje rewizje LWW, odrzuca stary `based_on_revision`, obsługuje
  idempotentny replay i trzyma tombstone `unwatched`;
- funkcja jest domyślnie wyłączona per enrollment; włączenie wymaga capability
  `playback-state-lww-v1` i hostowej komendy `set-playback-state`;
- Umbrella nadal korzysta z Trakt, a YouTube z historii konta. Profile Sync
  wymusza politykę i raportuje wyłącznie zredagowane booleany;
- Fen Light oraz YouTube2KodiLibrary są wycofane i usuwane przez preflight
  Android bez adaptera historii;
- Rapideo pozostaje fail-closed do czasu wydzielenia stabilnej trasy opartej na
  `file.id`; nazwa i rozmiar pliku nie są dopuszczalną tożsamością.

Powtarzalny test backendu obejmujący HTTP, idempotencję i konwergencję:

```bash
cd /home/mwo/projects/kodi-profile-sync-server
PYTHONPATH=src /home/mwo/projects/kodi/.venv/bin/python \
  tests/e2e/verified_loopback.py
```

- `manifests/devices.schema.json` z walidacją kompatybilnego schematu 1/2 i zredagowanym
  przykładem schematu 2 Android/Flatpak;
- moduł ładujący inwentarz urządzeń prywatnych normalizujący schemat 1/2 do wewnętrznego
  modelu v2;
- idempotentna, atomowa migracja rejestru 1 -> 2 z prywatną kopią zapasową i
  potwierdzeniem punktu końcowego odpowiadającego bajtom;
- nieprzejrzyste identyfikatory głównych kont, jawna platforma, fizyczne grupowanie
  hostów i dokładnie jeden neutralny transport ADB/SSH;
- oddzielne kontrakty `AdbTransport`/`SshTransport` i
  `AndroidKodiLifecycle`/`FlatpakKodiLifecycle`;
- `tools/kodi_inventory.py` tylko do odczytu ze zredagowanymi danymi wyjściowymi;
- przypięte klucze hosta SSH, sprawdzanie trybu klucza prywatnego, wyłączone
  przekazywanie agentów, sprawdzanie poprawności UID/domu/właściciela i odrzucanie
  ucieczki dowiązania symbolicznego;
- Zapasy cyklu życia Android zostały zakwalifikowane na żywo w BlueStacks, Sony TV,
  Bedroom TV i X88 Pro 20;
- schemat 1 -> 2 zainstaluj ponownie migrację z prywatną kopią zapasową;
- zainstaluj ponownie rozwiązanie konfiguracji poprzez `logical_device_id`;
- polityka profilu schematu 2 z oddzielnymi `disaster_recovery` i `routine`;
- semantyczny eksport procedury z domyślną odmową dla rdzenia Kodi i wybranych ustawień
  Umbrella;
- wpisane wartości, deterministyczny identyfikator wersji i wykluczenie sekretu;
- lokalny serwer transakcyjny SQLite w osobnej kasie `kodi-profile-sync-server`;
- kandydat na CAS, idempotencja, przydziały kanaryjskie i awans oparty na raportach;
- Programowanie HTTP oparte wyłącznie na pętli zwrotnej;
- po stronie hosta `tools/profile_sync_admin.py`;
- natywny Ed25519 zakwalifikowany w Kodi na BlueStacks x86 i Sony ARMv7;
- jednorazowe parowanie, rejestracja/token/klucz i puls dla każdej instalacji;
- oddzielne repozytorium `service.mwodevelop.profilesync` ze sprawdzaniem tylko do
  odczytu;
- deterministyczna publikacja dodatku serwisowego w zamku testing;
- urządzenie E2E dla dodatku 0.1.4 na BlueStacks x86 i Sony ARMv7, w tym pochodzenie
  repozytorium testing, parowanie, uwierzytelniony puls, podpisana kontrola kandydata i
  niezmiennik bez zastosowania w trybie tylko do odczytu;
- pobieranie uwierzytelnionej, niezmiennej wersji na serwer;
- dodatek 0.1.5 testing Candidate z adapterem Umbrella z domyślną odmową, prywatnym
  dziennikiem przed zapisem, odzyskiwaniem przy uruchamianiu, sprawdzaniem stanu,
  rollback i kwarantanną wersji; urządzenie zastosuj E2E jest nadal w toku;
- dodatek 0.1.5 regresja tylko do odczytu przekazywana na BlueStacks i Sony po
  sprawdzeniu rzeczywistego cyklu życia wyłączania/włączania usług;
- dodatek 0.1.6 testing Candidate odczytuje schemat 2 i stosuje podpisany schemat 3
  warstwy wybrane ze znaczników docelowych powiązanych z serwerem; Bedroom TV przeszedł
  pomyślnie instalację repozytorium testing, parowanie, uwierzytelniony puls,
  weryfikację podpisanego kandydata i niezmiennik bez zastosowania w trybie tylko do
  odczytu;
- X88 Pro 20 przeszedł pomyślnie czyste przywracanie Kodi 21.3 i weryfikację pochodzenia
  stable. Wszystkie modele BlueStacks, Sony TV i X88 Pro 20 przeszły pomyślnie parowanie
  Profile Sync 0.1.6/tylko do odczytu E2E i odwracalne zastosowanie w procesie,
  obejmujące pomyślne zastosowanie, wstrzyknięty błąd, rollback, kwarantannę,
  czyszczenie dziennika i przywracanie zarządzanych ustawień z dokładnością do bajtów;
- QNAP Container Station Utwórz kontrakt z bramką obrazu ARMv7;
- Preflight na żywo QNAP potwierdzający Container Station 3, Docker 26, Compose 2,
  `overlay2`, wystarczającą pojemność i dostępny obraz podstawowy Python 3.11 ARMv7;
- niezmienny manifest serwera 0.1.0 GHCR kwalifikowany dla `linux/amd64` i
  `linux/arm/v7`;
- izolowany dym QNAP 6A z `/ready`, schemat bazy danych 2, ponowne uruchomienie procesu,
  kontrolowana niedostępność/odzyskiwanie i zerowe pozostałe zasoby Compose;
- produkcyjny cykl życia QNAP ze stałym zarządzanym katalogiem głównym, zdrową bramą
  RAID, wymuszaniem niezmiennego obrazu, przypiętym kluczem hosta SSH, zweryfikowanym
  protokołem TLS 1.2+ i ograniczonymi mocowaniami zabezpieczeń tylko do odczytu;
- kopia zapasowa SQLite online, pobieranie atomowe poza NAS, szyfrowanie AES-256-GCM i
  pomyślne odszyfrowanie oraz przywracanie integralności SQLite;
- oddzielny adapter stanu przenośnego `kodi.favourites` dla treści użytkownika, których
  nie wolno osadzać w wersjach ustawień procedur semantycznych;
- deterministyczne generowanie pakietów z dokładną inwentaryzacją, walidacja plików
  ograniczonych/XML, weryfikacja grafiki adresowanej do treści oraz
  zastosowanie/odzyskiwanie transakcyjne;
- migracja ulubionych akcji ze starszego WatchNixtoons2 do identyfikatora dodatku
  mwoDevelop;
- Autorytatywne członkostwo w synchronizacji oparte na `.env`, wydawcy i punkty końcowe
  sieci, z tożsamością logiczną i oczekiwanym sprzętem przechowywanym w rejestrze
  prywatnym;
- powtarzalne wdrożenie Android z audytem w Kodi, rezerwami JSON-RPC/EventServer,
  dowodem konwergencji po zastosowaniu i idempotencją `NO_CHANGE`;
- profile tożsamości Profile Sync dla poszczególnych urządzeń pochodzące z `.env` i
  rejestru logicznego, bez klonowania tokenów rejestracji lub podpisywania nasion;
- urządzenie zachowujące tożsamość Oczyszczanie E2E: tymczasowe parowanie
  zweryfikowane-backend przywraca poprzednie ustawienia i stan zamiast wygaszać profil.

## Stan prywatny

Utworzono migrację:

```text
.kodi-private/devices.json
.kodi-private/devices.json.schema1.bak
.kodi-private/kodi-reinstall.json
.kodi-private/kodi-reinstall.json.schema1.bak
.kodi-private/routine/bluestacks1.json
.kodi-private/portable-state/<bundle-sha256>.zip
```

Wszystkie pliki pozostają ignorowane przez Git. Tryb `0600` `.env` zawiera dodatkowo
klucze hosta ADB/SSH `KODI_SYNC_PUBLISHER`, `KODI_SYNC_DEVICES` i per-urządzenie
logiczne. Przechowuje także kanał Profile Sync, opóźnienie uruchamiania, interwał i
politykę tylko do odczytu. Wartości te nie są zapisywane w publicznych urządzeniach ani
na wyjściu testowym.

## Powtarzalne kontrole

Główne repozytorium:

```bash
.venv/bin/pytest -q
python tools/kodi_devices.py validate
python tools/kodi_inventory.py bluestacks1 \
  --adb /home/mwo/android-sdk/platform-tools/adb \
  --adb-server-port 5038
python tools/kodi_routine_profile.py \
  <private-snapshot>/payload \
  .kodi-private/routine/bluestacks1.json \
  --kodi-major 21
PYTHONPATH=. .venv/bin/python tools/profile_sync_portable_release.py converge \
  --routine-settings .kodi-private/umbrella/settings.xml \
  --canary bluestacks1 \
  --canary x88pro20
PYTHONPATH=. .venv/bin/python \
  tests/e2e/profile_sync_foundation_device.py
.venv/bin/python tools/kodi_portable_state_rollout.py audit \
  --result .kodi-private/e2e/portable-state-audit.json
.venv/bin/python tools/kodi_portable_state_rollout.py sync \
  --result .kodi-private/e2e/portable-state-sync.json
```

Opcjonalne `--routine-settings` nie publikuje źródłowego XML ani sekretów.
Eksportuje z niego wyłącznie identyfikatory jawnie dopuszczone przez
`manifests/kodi-profile-policy.json`, składa je z aktywną rewizją i portable
favourites, a następnie używa tego samego podpisanego candidate/promote i kopii
QNAP. Brak różnicy kończy się `NO_CHANGE`.

Repozytorium serwera:

```bash
PYTHONPATH=src ../kodi/.venv/bin/pytest -q
PYTHONPATH=src ../kodi/.venv/bin/python \
  tests/e2e/verified_loopback.py
PYTHONPATH=src ../kodi/.venv/bin/python -m profile_sync_server.http \
  --database /tmp/mwo-profile-sync-smoke.sqlite \
  --port 18765 \
  --unsafe-accept-signatures
curl --fail http://127.0.0.1:18765/health
```

Możliwości kryptograficzne Kodi:

```bash
PYTHONPATH=. .venv/bin/python \
  tests/e2e/profile_sync_crypto_spike.py
```

Dodatek Kodi na obu zarejestrowanych urządzeniach:

```bash
PYTHONPATH=. .venv/bin/python \
  tests/e2e/profile_sync_addon_device.py \
  --device bluestacks1 \
  --device sony-tv \
  --result docs/e2e-results/2026-07-27-profile-sync-addon-devices.json
```

Test budzi Kodi przed instalacją GUI, w razie potrzeby ładuje repozytorium testing i
uruchamia pojedynczą sondę in-Kodi. Sonda ujawnia tylko status, identyfikator
rejestracji i wartości logiczne dotyczące tajnej obecności; wartości początkowe tokenu i
podpisu nigdy nie opuszczają Kodi.

## Status wydania i świadomie pozostawione blokery

Backend produkcyjny jest aktywny na QNAP przy użyciu niezmiennego obrazu
wieloarchitekturowego serwera 0.2.2, dedykowanego prywatnego urzędu certyfikacji i
zweryfikowanego protokołu TLS. Raporty wstępnej inspekcji na żywo RAID `[UU]` bez
trwającego odzyskiwania. Ostateczna kopia zapasowa po wdrożeniu poza serwerem NAS
przeszła uwierzytelnione odszyfrowanie w pamięci i `PRAGMA integrity_check=ok` na
schemacie 2 z trzema aktywnymi rejestracjami urządzeń.

Profile Sync 0.1.8 przeszedł certyfikację dokładnej migawki na BlueStacks i X88, w tym
przypisanie z podpisem produkcyjnym, zastosowanie transakcyjne, podpisany raport i
rollback. Ten sam certyfikowany ZIP był promowany bez przebudowy, a jego publiczne
podsumowanie stable jest zapisane w raporcie wydania. Następnie firma Sony przeszła
kontrolę pochodzenia stable, izolowanego przypisania i kontroli rollback i otrzymała
własną rejestrację produkcyjną. Tokeny klienta i nasiona podpisywania pozostały lokalne
na urządzeniu.

Już aktywna wersja jest celowo zwracana jako `ACTIVE_UNVERIFIED` do nowo
zarejestrowanego klienta, ponieważ backend nie przechowuje klucza promotora offline i
dlatego nie może wygenerować nowego podpisanego przypisania dla każdego urządzenia.
Serwery 0.2.2 i `tools/profile_sync_admin.py bootstrap-active` udostępniają teraz
sprawdzoną ścieżkę ładowania początkowego: host podpisuje się w trybie offline, podczas
gdy serwer ogranicza dokładną rejestrację, kanał, administracyjne znaczniki docelowe i
wersję do bieżącego aktywnego stanu. Przechowywany dokument pozostaje podpisanym,
kompatybilnym z klientem zadaniem kandydata. Ufanie odpowiedzi TLS jako niepodpisanemu
przypisaniu pozostaje zabronione.

Obsługa hosta Linux/Flatpak wykorzystuje te same bramki fail-closed. Oddzielne przypięte
tożsamości SSH wybierają każdego użytkownika systemu Unix; sonda cyklu życia weryfikuje
UID/home, wersję Kodi i ABI oraz kwalifikuje `special://home` plus `special://profile`
na podstawie bieżącego dziennika wykonawczego Kodi. Następnie należy zatrzymać Kodi
przed rozpoczęciem dostawienia. `tools/kodi_flatpak_profile_sync_rollout.py` nie
rozpakowuje dodatków ani nie edytuje bazy danych dodatków przez SSH. Po tym, jak bieżący
dziennik Kodi wykaże, że EventServer jest gotowy, ograniczony `RunScript(...)` wywołuje
instalator transakcyjny wewnątrz Kodi, który wykonuje rollback, `UpdateLocalAddons`,
włączenie i oczyszczony znacznik wyniku. Przed zastosowaniem profilu uzgadnia dokładne
wersje blokad stable Umbrella, mwoScrapers, jego opakowania i interfejsy API
repozytorium WatchNixtoons2 do Kodi. Profile Sync 1.0.3 wybiera Android BoringSSL lub
Linux OpenSSL EVP bez zmiany formatu przewodu/klucza Ed25519. Pomyślne powtórzenie
powoduje ponowne sprawdzenie tych pinów, użycie trybu tylko synchronizacji i musi
zachować tę samą zastosowaną wersję bez oczekującego raportu.

Nieosiągalny NUC jest nadal zgłaszany jako `UNAVAILABLE` i pozostaje niezmieniony. Dwie
rejestracje kont, tokeny, klucze do podpisu, rachunki za instalację i dowody pozostają
niezależne w ramach ignorowanego prywatnego katalogu. Urządzenia Android nie potrzebują
bramy cyklu życia SSH, ponieważ ich adapter działa już w Kodi i tam rozwiązuje
`special://profile`.

Profile tożsamości Android korzystają z unikalnego `logical_device_id`, rejestracji,
kanału i harmonogramu. Na żywo 31.07.2026 E2E na BlueStacks, Sony TV i X88 Pro 20
przeszło unikalne parowanie produkcyjne, uwierzytelniony puls, odkrycie podpisanego
przypisania, zastosowane zostały pomyślne ustawienia, wstrzyknięty błąd rollback,
oczyszczenie dziennika i przywrócenie ustawień z dokładnością do bajtów za pośrednictwem
uwierzytelnionego produkcyjnego punktu końcowego HTTPS.

Bedroom TV przeszedł workflow w stosunku do wersji produkcyjnej 0.2.2: stable Profile
Sync 0.1.8 w połączeniu z unikalną rejestracją, zaakceptował bootstrap podpisany
offline, zastosował i zgłosił dokładną aktywną wersję oraz zachował kompletny profil
przenośny z grafiką WatchNixtoons2. Obydwa podmioty główne NUC mają niezależnie
kwalifikowane mapowania środowiska wykonawczego Kodi Flatpak 21.3. Ich instalacja
produkcyjna i parowanie pozostają aktywną bramą E2E, gdy host fizyczny jest
nieosiągalny; wsparcie na poziomie źródła nie jest zgłaszane jako certyfikacja
urządzenia.

Schemat wersji 3 i administracyjnie powiązane znaczniki zgodności są teraz
zaimplementowane w generatorze, serwerze i dodatku. Certyfikacja Linux/Flatpak nadal
wymaga zarejestrowanej pomyślnej instalacji i ponownej synchronizacji dla obu podmiotów
głównych NUC; żadne z nich nie jest zgłaszane jako zaliczone, gdy punkt końcowy jest
nieosiągalny.

## Odporność cyklu klienta od wersji 1.1.2

Klient klasyfikuje timeouty, błędy transportu, HTTP 429 oraz 5xx jako przejściowe
i ponawia cykl z utrwalonym backoffem 1/5/15/30 minut oraz jitterem. HTTP 401/403,
błędy konfiguracji i kontraktu pozostają terminalne do chwili zmiany ich
bezpiecznego odcisku. Stan przetrwa restart Kodi, chroni przed cofnięciem zegara i
nie tworzy pętli restartów. Utrwalona telemetria rozdziela `last_attempt`,
`last_heartbeat_success`, `last_cycle_success`, liczbę kolejnych błędów, przyczynę
oraz następny termin próby; nie zawiera tokenów ani credentiali.

## Obserwowalność procesu od wersji 1.2.0

Uwierzytelniony heartbeat zawiera opcjonalny `process_observation` schematu 1.
Klient wysyła wyłącznie jawnie dozwolone znaczniki czasu, interwał, wynik,
licznik kolejnych błędów i stały kod błędu. Serwer odrzuca dodatkowe pola,
nieprawidłowe typy oraz wartości spoza kontraktu, zapisuje kanoniczny JSON i
udostępnia go tylko w prywatnym widoku integracyjnym mTLS. Token enrollmentu,
klucze, treści i credentiale nie należą do tego dokumentu.

Control Plane używa tej obserwacji do wyliczenia ostatniej próby, sukcesu oraz
następnego terminu na tych samych zasadach co dla GitHub Actions i QNAP Watchdog.
Heartbeat starszego klienta pozostaje ważny; dopóki nie pojawi się telemetria 1.2.0,
panel wylicza kompatybilny widok z czasu ostatniego heartbeat i interwału katalogu.

## Warstwowe rewizje rutynowe

Schemat 2 pozostaje czytelny i eksportuje tylko przenośny wspólny podzbiór. Schemat 3
zawiera tablicę `base.adapters` i tablicę `layers` uporządkowaną kanonicznie. Warstwy
klas wybrane przez `all_target_tags` poprzedzają warstwy wybrane przez
`logical_device_id`. Tagi docelowe są przypisywane podczas rejestracji po stronie
serwera i muszą być zgodne z podpisanym przypisaniem kandydata; obserwacje pulsu nigdy
nie wybierają warstwy.

Wygeneruj schemat 3 jawnie:

```bash
python tools/kodi_routine_profile.py \
  /path/to/kodi/profile \
  /path/to/revision.json \
  --kodi-major 21 \
  --revision-schema 3
```
