# Plan synchronizacji profili, urządzeń i aktualizacji Kodi

Status: plan po niezależnym review, gotowy do realizacji etapowej

Data: 2026-07-27

Repo nadrzędne: `mwoDevelop/kodi`

Lokalizacja robocza: `/home/mwo/projects/kodi`

Dokument powiązany: `UPSTREAM_SYNC_PLAN.md`

Raport review: `docs/PROFILE_SYNC_PLAN_REVIEW.md`

Stan realizacji 2026-07-27:

- Etap 1: zrealizowany lokalnie i pokryty testami;
- Etap 2: zrealizowany pierwszy bezpieczny zakres routine export;
- Etap 3: zrealizowany transakcyjny store, loopback API development oraz
  przenośny Ed25519 na Kodi x86/ARMv7 i serwerze;
- Etap 4: utworzone osobne repo i fundament dodatku, pairing/check w realizacji;
- Etapy 5–8: nierozpoczęte;
- produkcyjny QNAP nadal zablokowany przez warunki Etapu 0.

## 1. Cel

Zbudować bezpieczny i odtwarzalny system, który:

1. przechowuje prywatny rejestr lokalnych urządzeń Kodi i ich endpointów;
2. pozwala jednej instalacji Kodi pełnić rolę publikującego profil;
3. wersjonuje profile użytkownika na QNAP i umożliwia rollback;
4. synchronizuje zatwierdzony profil do pozostałych instalacji przy starcie
   Kodi i cyklicznie;
5. przywraca dodatki, ustawienia, skórkę i docelowo także poświadczenia, bez
   kopiowania cache i wygenerowanych baz;
6. pozostawia GitHub jako control plane kodu, forków i wydań dodatków;
7. nie pozwala, aby uszkodzona lub niezatwierdzona konfiguracja automatycznie
   rozeszła się na wszystkie urządzenia;
8. pozwala sprawdzić dokładnego kandydata na wybranych urządzeniach bez zmiany
   globalnego `active`;
9. zachowuje obecny awaryjny workflow hosta oparty o prywatne snapshoty i ADB.

## 2. Decyzja architektoniczna

Wybrany zostaje wariant hybrydowy:

```text
GitHub
  discovery upstreamów -> PR -> testing -> ręczne stable
                                      |
                                      v
                         repository.mwodevelop

Kodi publisher
  eksport profilu -> candidate -------+
                                      |
                                      v
                         QNAP profile-sync API
                         - rejestr urządzeń
                         - wersje profilu
                         - active channel
                         - historia i audyt
                                      |
                         pull przy starcie / cyklicznie
                                      |
                                      v
                          pozostałe instalacje Kodi
```

QNAP jest brokerem i magazynem, ale nie zastępuje GitHub Actions ani
repozytorium Kodi. Instalacja określana jako publisher nie wystawia usługi P2P;
publikuje kandydatów do QNAP. Konsumenci sami pobierają aktywną wersję.

Backend na QNAP jest dostarczany wyłącznie jako kontener zarządzany przez
Container Station/Docker Compose. QPKG, instalacja Pythona bezpośrednio w QTS
i ręcznie utrzymywany proces systemowy nie są ścieżkami wdrożeniowymi. Obraz
jest wieloarchitekturowy, a wariant `linux/arm/v7` jest obowiązkową bramą CI.

Bezpośrednia synchronizacja P2P zostaje odrzucona jako mechanizm podstawowy,
ponieważ wymaga jednoczesnej dostępności obu urządzeń, wystawienia bezpiecznego
API zapisu na każdym Kodi, rozwiązywania adresów i konfliktów oraz nie zapewnia
naturalnej historii zmian.

Zwykły udział SMB również nie jest docelowym API. Istniejący AddonSync może
służyć jako materiał porównawczy, ale jego model oparty o współdzielony katalog
i timestampy nie pokrywa transakcyjnego przywracania dodatków, skórki,
repozytorium, wersji ani sekretów.

## 3. Zasady nienaruszalne

1. Kod dodatków jest instalowany i aktualizowany wyłącznie przez
   `repository.mwodevelop` lub oficjalne repo Kodi.
2. Routine profile sync nie kopiuje katalogów z kodem dodatków.
3. Pełny snapshot disaster recovery może zawierać kod, ale pozostaje ścieżką
   awaryjną obsługiwaną przez obecny skrypt hosta.
4. `stable` dodatków i `active` profilu nigdy nie są promowane automatycznie w
   MVP.
5. Sekrety nie trafiają do Git, obrazu kontenera, logów, raportów CI ani
   publicznego repo Kodi.
6. IP nie jest tożsamością urządzenia. Tożsamość logiczną opisuje stabilny
   `logical_device_id`, a konkretną instalację `enrollment_id` i
   `enrollment_generation` z własnym kluczem/tokenem.
7. Każda rewizja profilu jest niemutowalna i adresowana przez digest.
8. Zastosowanie profilu jest crash-resilient i kompensacyjne: staging,
   walidacja, lokalny backup, journal, apply, health check i rollback w
   granicach możliwości adaptera.
9. Rozszerzenie systemu o kolejną klasę plików, kanał lub typ urządzenia ma
   wymagać wpisu w manifeście albo nowego adaptera, a nie warunków zależnych od
   nazw Sony, BlueStacks, Umbrella lub WatchNixtoons2.
10. Istniejący `.env` z kontem administracyjnym QNAP służy tylko operacjom
    wdrożeniowym z hosta. Nie jest przekazywany klientom Kodi.
11. Routine sync jest `default-deny`: nieznane pliki i ustawienia nie są
    eksportowane ani stosowane.
12. `enrollment_id`, token i klucz podpisujący klienta synchronizacji są
    zawsze device-local i nigdy nie należą do profilu.
13. Uprawnienia `promote` i `admin` nie trafiają do codziennego dodatku Kodi.
    Promocję wykonuje narzędzie hostowe lub oddzielny interfejs administracyjny.
14. Rollback profilu cofa konfigurację. Nie obiecuje downgrade'u kodu dodatków.

## 4. Stan początkowy

### 4.1 Kodi i urządzenia

Obecnie prywatne endpointy są częściowo przechowywane w:

```text
.kodi-private/kodi-reinstall.json
```

Znane cele:

- BlueStacks1, model `SM-S901E`;
- Sony Android TV, model `BRAVIA 4K GB ATV3`;
- QNAP TS-x31P2.

Rzeczywiste adresy pozostają wyłącznie w `.kodi-private`.

Istnieją:

- prywatne snapshoty profili;
- `tools/kodi_profile.py`;
- `tools/kodi_reinstall.py`;
- polityka `manifests/kodi-profile-policy.json`;
- testy urządzeń i repozytorium Kodi.

### 4.2 Aktualizacje kodu

`mwoDevelop/kodi` ma już oddzielny control plane:

- `manifests/upstreams.json`;
- codzienny `reconcile-upstreams.yml`;
- kanały `testing` i `stable`;
- deterministyczne snapshoty;
- ręczną promocję stable;
- obowiązkowy E2E przed publikacją.

Ten mechanizm pozostaje źródłem prawdy dla kodu. Profile użytkownika nie mogą
go mutować ani omijać.

### 4.3 QNAP

Rozpoznany QNAP:

- model TS-x31P2, ARMv7;
- 8 GB RAM;
- QTS 5.2.9;
- Container Station 3.1.2;
- Docker 26.1.4;
- Docker Compose 2.27.1;
- dostępne snapshoty QTS.

Live preflight 2026-07-27 potwierdził:

- host `armv7l`, 4 CPU i około 8 GB RAM;
- działający daemon Docker `26.1.4-qnap2` na zarządzanym przez Container
  Station sockecie;
- storage driver `overlay2`;
- około 1,8 TB wolnego miejsca na wolumenie Container Station;
- dostępność oficjalnego obrazu bazowego Python 3.11 dla `linux/arm/v7`;
- obsługę aplikacji Docker Compose w Container Station.

Wniosek: kontenerowy backend jest technicznie wykonalny na tym modelu.
Produkcję blokuje stan danych, nie runtime kontenerowy.

Twardy blocker produkcyjny:

```text
md1: RAID1 [2/1] [U_]
state: clean, degraded
```

Brakuje drugiego członu RAID1. Do czasu odbudowania RAID i potwierdzenia
zewnętrznego backupu na QNAP można uruchamiać jedynie jednorazowe, odtwarzalne
smoke bez trwałych istotnych danych. Nie może być magazynem deweloperskim,
produkcyjnym ani jedyną kopią profili lub sekretów.

## 5. Zakres

### 5.1 W zakresie docelowym

- prywatny rejestr urządzeń;
- usługa synchronizacji uruchamiana na QNAP;
- dodatek Kodi `service.mwodevelop.profilesync`;
- publikowanie wersji `candidate`;
- ręczna promocja `candidate -> active`;
- pull przy starcie i cyklicznie;
- wersjonowanie, rollback i audyt;
- ustawienia dodatków;
- ustawienia przenośne Kodi;
- lista wymaganych dodatków i wersji;
- wybrana skórka;
- opcjonalne ustawienia skórki w overlayach urządzeń;
- zaszyfrowany backup sekretów;
- podpisane rewizje i podpisane zmiany aktywnego wskaźnika;
- przypięcie kandydata do wybranych urządzeń canary;
- testy BlueStacks i Sony;
- integracja z istniejącym repo mwoDevelop;
- backup QNAP poza macierzą, gdy storage będzie zdrowy.

### 5.2 Poza MVP

- bezpośrednie P2P między Kodi;
- automatyczna promocja profilu do `active`;
- automatyczna promocja kodu do `stable`;
- synchronizacja bibliotek multimediów;
- synchronizacja cache, miniaturek i baz Kodi;
- publiczne wystawianie QNAP API do Internetu;
- automatyczne rozwiązywanie rozbieżnych zmian z wielu publisherów;
- zastępowanie routera lub DHCP własnym discovery;
- natywna aplikacja QPKG;
- obsługa wielu profili użytkownika Kodi;
- automatyczny downgrade dodatków podczas rollbacku profilu;
- bezpośrednia podmiana dowolnych plików innych dodatków przez usługę Kodi.

## 6. Struktura projektu

Docelowy podział:

```text
kodi/
├── manifests/
│   ├── kodi-profile-policy.json
│   ├── devices.schema.json
│   └── profile-sync.schema.json
├── deploy/
│   └── qnap-profile-sync/
│       ├── compose.yaml
│       ├── README.md
│       └── env.example
├── tools/
│   ├── kodi_devices.py
│   ├── kodi_profile.py
│   ├── kodi_reinstall.py
│   └── profile_sync_admin.py
├── profile-sync-addon/             # osobne repo/submoduł
└── .kodi-private/
    ├── devices.json
    ├── kodi-reinstall.json
    ├── qnap-profile-sync.env
    ├── profile-sync-admin/
    └── snapshots/
```

Rekomendowane osobne repozytoria:

- `mwoDevelop/service.mwodevelop.profilesync`;
- `mwoDevelop/kodi-profile-sync-server`.

Repo `mwoDevelop/kodi` integruje wersje komponentów i publikuje dodatek, ale
nie zawiera implementacji serwera. Dodatek jest osobnym repo/submodułem,
otrzymuje wpis w `manifests/components.json` i obu lockach oraz jest budowany
przez ten sam deterministyczny pipeline co pozostałe dodatki. Serwer nie jest
submodułem: `compose.yaml` wskazuje jego obraz przez niezmienny digest.

Dodanie `service.mwodevelop.profilesync` nie zmienia wersji
`repository.mwodevelop`; komponent jest po prostu kolejną pozycją w
generowanym indeksie repozytorium.

## 7. Rejestr urządzeń

Rzeczywisty rejestr:

```text
.kodi-private/devices.json
```

Plik jest ignorowany przez Git. Wersjonowane będą wyłącznie:

- `manifests/devices.schema.json`;
- przykład bez prawdziwych adresów;
- testy walidatora.

Proponowany dokument:

```json
{
  "schema": 1,
  "devices": {
    "sony-living-room": {
      "roles": ["consumer"],
      "expected": {
        "model": "BRAVIA 4K GB ATV3",
        "kodi_major": 21,
        "abi": ["armeabi-v7a"]
      },
      "endpoints": {
        "adb": "<private-sony-ip>:5555",
        "jsonrpc": "http://<private-sony-ip>:9090"
      },
      "profile_channel": "home-stable"
    },
    "bluestacks-master": {
      "roles": ["publisher", "consumer"],
      "expected": {
        "model": "SM-S901E",
        "kodi_major": 21
      },
      "endpoints": {
        "adb": "<private-bluestacks-adb-endpoint>"
      },
      "profile_channel": "home-stable"
    }
  }
}
```

`kodi-reinstall.json` zostanie zmigrowany do referencji:

```json
{
  "logical_device_id": "sony-living-room"
}
```

Endpointy operacyjne nie będą duplikowane. Narzędzie hosta rozwiązuje
`logical_device_id`, sprawdza model i dopiero potem wykonuje ADB.

Dla urządzeń fizycznych zalecane są rezerwacje DHCP. QNAP rejestruje także
`last_seen`, ostatni obserwowany adres i wersję klienta, ale nie traktuje
adresu jako poświadczenia.

Rejestry mają różne, jawne role:

- `.kodi-private/devices.json` jest administracyjnym inventory hosta dla ADB,
  JSON-RPC i operacji reinstall/restore;
- rejestr QNAP przechowuje enrollment, klucze publiczne, role, capabilities i
  heartbeat klienta, ale nie przechowuje endpointów ADB;
- `logical_device_id` jest stabilnym aliasem urządzenia, natomiast każda
  ponowna instalacja tworzy nowe `enrollment_id`, podniesioną
  `enrollment_generation`, token i klucz podpisujący;
- token, klucz i enrollment nie są kopiowane ze snapshotu. Po czystej
  reinstalacji urządzenie jest ponownie parowane;
- overlay jest wiązany przede wszystkim z `device_class` i capabilities.
  Wyjątek per `logical_device_id` wymaga jawnego wpisu.

## 8. Model profilu

Obecna polityka zostanie rozszerzona, a nie zastąpiona konkurencyjnym plikiem.
Schema v2 definiuje dwa rozłączne scope'y:

- `disaster_recovery`: zachowuje kompatybilność schema 1, kod dodatków i
  hostowy restore zatrzymanego Kodi;
- `routine`: nowy profil default-deny bez kodu dodatków i bez nieznanych pól.

W scope `routine` sama klasyfikacja ścieżki nie wystarcza. `settings.xml` może
zawierać jednocześnie preferencje i tokeny, dlatego polityka działa na dwóch
poziomach:

- `portable`: bezpieczna między urządzeniami;
- `device_overlay`: zależna od urządzenia, rozdzielczości lub platformy;
- `secret`: poświadczenia i tokeny;
- `device_local`: enrollment, endpointy i stan klienta;
- `excluded`: cache i dane generowane.

Adaptery semantyczne eksportują i stosują wyłącznie jawnie dozwolone klucze:

- adapter ustawień core używa wspieranego JSON-RPC
  `Settings.SetSettingValue`;
- adapter dodatku zna dozwolone ID ustawień i ich typy;
- adapter skórki używa wspieranego API/builtin albo oznacza zmianę jako
  wymagającą hostowego restore;
- adapter plikowy jest dopuszczony tylko dla całego pliku o jednolitej klasie
  i jawnie zarządzanej ścieżce.

Nieznany adapter, klucz, typ albo wersja schematu kończy się przed mutacją.
`service.mwodevelop.profilesync`, jego token, klucz, `enrollment_id`, journal
oraz lokalny backup są zawsze `device_local`.

Routine profile revision zawiera:

- wymagane repozytoria;
- ID i oczekiwane wersje dodatków;
- aktywną skórkę;
- ustawienia przenośne;
- ustawienia dodatków;
- overlaye wybranych urządzeń;
- zgodność z Kodi major i ABI;
- digest polityki;
- digest każdego pliku.

Manifest przechowuje również:

- wersję adaptera i zakres kompatybilnych wersji dodatku;
- deklarację własności zarządzanych kluczy/ścieżek;
- jawne tombstones dla usunięć.

Usunięcie dotyczy tylko elementu wcześniej zarządzanego przez ten sam adapter.
Brak elementu w profilu nie oznacza zgody na skasowanie niezarządzanych danych.
Kolejność nakładania jest deterministyczna:

```text
portable -> device_class overlay -> logical_device overlay
```

Nie zawiera:

- kodu dodatków;
- `Addons*.db`;
- `Textures*.db`;
- miniaturek;
- artwork cache;
- logów;
- provider cache;
- search/history cache;
- pakietów ZIP;
- plików tymczasowych.

Pełny snapshot disaster recovery pozostaje osobnym formatem i jest obsługiwany
przez istniejące narzędzia hosta.

MVP obsługuje wyłącznie domyślny profil Kodi. Wykrycie dodatkowych profili
powoduje raport `UNSUPPORTED_MULTI_PROFILE` bez mutacji.

## 9. Wersjonowanie

Rewizja zawiera wyłącznie niemutowalną treść. `candidate`, `active`, canary,
promocja i rollback są osobnymi wskaźnikami albo zdarzeniami i nie należą do
manifestu rewizji.

Przykładowa rewizja:

```json
{
  "schema": 2,
  "revision_id": "sha256:...",
  "base_revision": "sha256:...",
  "publisher_enrollment_id": "enr:...",
  "created_utc": "...",
  "kodi_major": 21,
  "policy_sha256": "...",
  "repository_index_sha256": "...",
  "files": {},
  "addons": {},
  "overlays": {},
  "signature": {}
}
```

`revision_id` jest SHA-256 kanonicznej części identity manifestu. Czas,
podpisy, raporty i stan kanału nie wchodzą do identity. JSON jest
kanonikalizowany jednym wersjonowanym algorytmem, a digest blobu jest liczony
po surowych bajtach. Testy golden vectors w Pythonie serwera i Kodi muszą
dawać identyczny wynik.

`repository_index_sha256` jest dowodem, względem którego profil został
zakwalifikowany, a nie żądaniem trwałego cofnięcia całego repo do tego indeksu.
Klient egzekwuje origin i kompatybilne constraints. Promoter sprawdza, że
wymagany kod jest nadal dostępny w aktualnym publicznym stable.

Serwer przechowuje:

- niemutowalne manifesty;
- content-addressed blobs;
- wskaźnik `candidate`;
- wskaźnik `active`;
- przypisania canary `enrollment_id -> exact revision`;
- historię promocji i rollbacków;
- wynik health checków klientów.

Na kanał przypada najwyżej jeden nierozstrzygnięty candidate. Operacje mają
oddzielne warunki compare-and-swap:

```text
publish:
  expected_candidate_head == current_candidate_head
  base_revision == current_active

promote:
  expected_active_revision == current_active
  candidate_revision == current_candidate

rollback:
  expected_active_revision == current_active
  target_revision istnieje i jest kompatybilna
```

Każde żądanie mutujące ma `idempotency_key`, a serwer zwraca poprzedni wynik
dla bezpiecznego retry. Promocja lub rollback tworzą nowe, podpisane zdarzenie
z monotonicznym `channel_generation` i `previous_event_digest`; nie modyfikują
rewizji. Klient odrzuca starszą generację, chyba że otrzyma jawne, podpisane
zdarzenie rollbacku o wyższej generacji. Enrollment bundle zawiera podpisany
checkpoint bieżącego kanału, aby nowy klient nie zaakceptował replay starego,
choć poprawnie podpisanego zdarzenia.

Canary assignment i jego unassign/revocation są podpisanymi zdarzeniami
promotera. Raport klienta podpisuje klucz konkretnego enrollmentu. Oba
dokumenty zawierają co najmniej kanał, exact revision, `logical_device_id`,
`enrollment_id`, `enrollment_generation`, nonce, generację i czas. Promocja
sprawdza podpisane raporty przypisane do exact revision, a nie sam status w
SQLite.

Jeśli warunek CAS się nie zgadza, operacja zostaje odrzucona. Zapobiega to
nadpisaniu zmian przez dwa mastery i promocji innego kandydata niż sprawdzony.
W MVP tylko jedno urządzenie ma uprawnienie `publish` dla kanału.
Publisher może supersedować wyłącznie własnego kandydata przy poprawnym
`expected_candidate_head`; zmienia to candidate head i unieważnia wcześniejsze
raporty canary oraz approvals, ale zachowuje wpis audytowy poprzednika.

## 10. Usługa QNAP

Usługa zostanie dostarczona jako przypięty digestem obraz wieloarchitekturowy
z obowiązkowym wariantem:

```text
linux/arm/v7
```

MVP to pojedynczy lekki kontener:

- HTTP API;
- SQLite;
- katalog blobów;
- health endpoint;
- migracje schematu;
- redagowane logi.

Warstwa zapisu używa protokołu:

1. utworzenie upload session z limitem rozmiaru i TTL;
2. zapis blobów do tymczasowego obszaru;
3. weryfikacja rozmiaru i SHA-256;
4. atomowe finalize manifestu w transakcji SQLite;
5. dopiero po commit rewizja może zostać kandydatem.

SQLite działa w WAL z jednym writerem i ustawionym `busy_timeout`. Finalize,
promocja, rollback i zapis idempotency key są transakcjami. Osierocone uploady
mają TTL. GC używa lease/grace period i nie usuwa blobu trwającego downloadu.
Backup SQLite jest wykonywany przez SQLite Backup API albo po kontrolowanym
zatrzymaniu kontenera; zwykłe kopiowanie aktywnego pliku DB nie jest uznawane
za spójny backup.

Nie jest wymagany PostgreSQL ani wielokontenerowa infrastruktura. Compose
pozostaje deklaratywnym kontraktem wdrożenia i umożliwia późniejsze dodanie
reverse proxy lub zewnętrznej bazy bez zmiany dodatku Kodi.

Przykładowe zasoby:

```text
POST /v1/pair
POST /v1/devices/heartbeat
POST /v1/channels/{channel}/candidates
POST /v1/channels/{channel}/assignments
POST /v1/channels/{channel}/promote
POST /v1/channels/{channel}/rollback
GET  /v1/enrollments/{enrollment_id}/assignment
GET  /v1/revisions/{revision_id}
GET  /v1/blobs/{sha256}
POST /v1/reports
GET  /health
```

Trwałe dane są montowane z dedykowanego udziału QNAP. Nic ważnego nie jest
przechowywane wewnątrz warstwy kontenera ani katalogu QPKG.

Aktualizacja serwera jest kontrolowaną operacją hostową:

1. spójny backup DB i manifestu blobów;
2. preflight migracji na kopii;
3. pull obrazu po konkretnym digest;
4. uruchomienie migracji i health check;
5. rollback do poprzedniego digestu i kompatybilnej kopii DB po błędzie.

Nie stosujemy Watchtower, ruchomych tagów ani automatycznego wdrożenia po
samym zbudowaniu obrazu.

## 11. Dodatek Kodi

ID:

```text
service.mwodevelop.profilesync
```

Jeden dodatek udostępnia:

- rozszerzenie `xbmc.service`;
- ustawienia;
- UI `Sync now`;
- pairing;
- publikację candidate dla publishera;
- pobranie przypisanego kandydata dla urządzenia canary;
- status ostatniej synchronizacji;
- raport kompatybilności.

Promocja, rollback, revocation i zarządzanie rolami należą do
`tools/profile_sync_admin.py` lub osobnego admin UI i nie są funkcjami
codziennego klienta Kodi.

Stan klienta:

```text
UNPAIRED
  -> IDLE
  -> CHECKING
  -> DOWNLOADING
  -> STAGED
  -> WAITING_FOR_ADDONS
  -> PENDING_RESTART
  -> APPLYING
  -> HEALTH_CHECK
  -> APPLIED
  -> ROLLED_BACK | QUARANTINED | ERROR
```

Dodatek nigdy nie stosuje wartości przed:

- walidacją adaptera, klucza i ścieżki;
- sprawdzeniem rozmiaru;
- weryfikacją SHA-256;
- weryfikacją podpisu rewizji i zdarzenia kanału;
- sprawdzeniem wersji Kodi;
- sprawdzeniem wersji dodatku, którego ustawienia dotyczą;
- utworzeniem lokalnej kopii poprzedniego stanu.

Oficjalne zasady dodatków Kodi nie pozwalają dodatkom bezwarunkowo modyfikować
danych innych dodatków. Ponieważ ten komponent będzie dystrybuowany prywatnym
repo, technicznie może mieć szersze możliwości, ale użytkownik musi jawnie
włączyć każdy adapter ingerujący poza profilem własnego dodatku. Preferowane są
wspierane API. Bezpośrednia podmiana obcego `settings.xml` nie jest generycznym
mechanizmem MVP.

Transakcja klienta jest `crash-resilient` i kompensacyjna, a nie globalnie
atomowa. Kodi i dodatki mogą utrzymywać stan w pamięci, a usługa nie cofnie
zmiany, która uniemożliwi start samego Kodi. Dlatego:

- każdy etap ma fsyncowany journal i lokalny backup;
- adapter deklaruje `hot_apply`, `next_start` albo `host_only`;
- `next_start` nadal używa wyłącznie wspieranego API po uruchomieniu usługi.
  Zmiana wymagająca zapisu przed inicjalizacją właściciela jest `host_only`;
- po trzech nieudanych startach rewizja trafia do kwarantanny;
- klient nie tworzy automatycznej pętli restartów;
- zmiany `host_only` są raportowane i pozostawiane obecnemu workflow ADB;
- rollback kodu dodatku nie jest częścią tej transakcji.

## 12. Kolejność synchronizacji klienta

Po starcie lub ręcznym wywołaniu:

1. Sprawdź pairing i ważność tokenu.
2. Wyślij heartbeat z `logical_device_id`, `enrollment_id`,
   `enrollment_generation`, modelem, ABI, wersją Kodi i wersją dodatku.
3. Poczekaj na gotowość sieci bez blokowania startu Kodi i respektuj
   `xbmc.Monitor.abortRequested()`.
4. Pobierz podpisane assignment: globalny `active` albo exact candidate
   przypisany temu canary.
5. Odrzuć starszą generację, nieprawidłowy podpis lub niezgodny kanał.
6. Jeśli rewizja jest już zastosowana, zakończ bez zmian.
7. Pobierz i zweryfikuj manifest.
8. Sprawdź zgodność urządzenia, polityki, adapterów i repo stable.
9. Jeśli brak wymaganej wersji dodatku, wykonaj jeden wymuszony
   `UpdateAddonRepos` niezależnie od okresowego limitu.
10. Zainstaluj lub zaktualizuj wymagane dodatki przez repo Kodi i asynchronicznie
    czekaj na potwierdzenie wersji oraz `installed.origin`.
11. Jeśli origin jest inny niż oczekiwany albo wymagany kod nie istnieje w
    stable, zakończ bez mutacji. Active nie może wymagać kanału testing.
12. Jeśli aktualizuje się `service.mwodevelop.profilesync`, przerwij apply i
    wznów go dopiero po przeładowaniu nowej wersji klienta.
13. Poczekaj na bezpieczne okno: brak playbacku, dialogu ustawień i trwającej
    aktualizacji dodatków.
14. Pobierz bloby do stagingu i zweryfikuj kompletność oraz digests.
15. Zastosuj `hot_apply` wyłącznie przez zakwalifikowane adaptery.
16. Zapisz `next_start` jako pending; nie wymuszaj restartu Androida w MVP.
17. Zmiany `host_only` pokaż jako niezastosowane.
18. Zweryfikuj aktywną skórkę, dodatki i podstawowe JSON-RPC.
19. Wyślij raport sukcesu albo wykonaj kompensacyjny rollback konfiguracji.

Każdy raport zawiera `assignment_kind: active|candidate`, exact revision i
podpis enrollmentu. Stan `APPLIED` oznacza zastosowanie assignmentu, a nie
globalną promocję rewizji do `active`.

Jeśli QNAP jest niedostępny, klient pozostawia lokalną konfigurację bez zmian i
próbuje ponownie z backoffem. Niedostępność serwera nie może blokować startu
Kodi.

Profil deklaruje kompatybilne ograniczenia wersji i origin, nie automatyczny
downgrade. Raport rollbacku rozróżnia co najmniej:

```text
CONFIG_ROLLED_BACK
CONFIG_ROLLED_BACK_CODE_ADVANCED
ROLLBACK_REQUIRES_HOST
```

## 13. Publikacja przez publishera

MVP:

- publikacja tylko ręczna;
- nowa rewizja zawsze trafia jako `candidate`;
- kandydat pokazuje diff logiczny;
- admin przypina exact candidate do wybranych urządzeń canary;
- test candidate nie zmienia globalnego `active`;
- promocja do `active` jest osobną podpisaną akcją hostową;
- promocja wymaga raportu sukcesu z czystego BlueStacks oraz urządzenia klasy
  Sony albo jawnego, audytowanego waivera;
- poprzedni `active` pozostaje dostępny do rollbacku.

Późniejsza automatyzacja:

- detekcja rzeczywistej zmiany profilu;
- debounce co najmniej 15 minut;
- najwyżej jeden automatyczny candidate na dobę;
- brak automatycznej promocji;
- brak publikacji, gdy profil jest niezgodny, Kodi kończy pracę albo trwa
  aktualizacja dodatków.

## 14. Bezpieczeństwo

### 14.1 Sieć i uwierzytelnienie

- API dostępne tylko z LAN/VPN;
- brak publicznego port-forwardingu;
- HTTPS przez QNAP reverse proxy;
- pairing kodem jednorazowym wygenerowanym przez admin CLI, z krótkim TTL,
  limitem prób i jednorazowym użyciem;
- osobny token każdego urządzenia;
- token przechowywany po stronie serwera jako hash;
- osobny enrollment signing keypair; klucz prywatny pozostaje device-local, a
  publiczny służy do proof-of-possession i weryfikacji raportów;
- role `read`, `publish`, `promote`, `admin`;
- zwykły consumer otrzymuje tylko `read`, a publisher oddzielnie `publish`;
- `promote` i `admin` pozostają poza Kodi;
- możliwość unieważnienia pojedynczego urządzenia;
- limit rozmiaru i częstotliwości uploadu;
- ochrona przed path traversal i symlinkami.

Bootstrap zaufania jest jawny. Produkcja używa lokalnej nazwy DNS i
certyfikatu zaufanego przez Android albo fingerprintu certyfikatu
zweryfikowanego poza kanałem QNAP podczas pairing. `verify=False` i trwały
plain HTTP są zabronione; HTTP jest dozwolony tylko na loopback w testach.

Każda rewizja jest podpisana kluczem publishera przypisanym do kanału. Każde
zdarzenie promote/rollback jest podpisane osobnym kluczem promotera i zawiera
monotoniczną generację kanału. Klient przypina publiczne klucze podczas
kontrolowanego enrollmentu i sprawdza podpis, kanał, schema, policy digest oraz
generację przed pobraniem payloadu. SHA-256 blobów chroni integralność
transportu, ale sam nie zastępuje podpisu.

### 14.2 Sekrety

Klucz podpisujący enrollment z MVP nie jest kluczem szyfrowania sekretów.
Jego przenośna implementacja kryptograficzna na Kodi ARMv7/x86 jest bramą MVP,
ale nie wymaga sprzętowej ochrony Android Keystore.

Etap 1:

- routine sync nie automatyzuje sekretów;
- pełny snapshot z sekretami pozostaje w `.kodi-private`;
- plaintext snapshot nie jest wysyłany na QNAP;
- opcjonalna kopia na QNAP jest szyfrowana na hoście przed uploadem kluczem,
  którego nie przechowuje QNAP;
- przywracanie sekretów odbywa się obecnym skryptem hosta.

Etap 2:

- osobny per-device encryption keypair;
- publiczny klucz szyfrowania urządzenia przechowywany na serwerze;
- losowy klucz danych dla rewizji;
- envelope encryption klucza danych osobno dla każdego urządzenia;
- QNAP przechowuje wyłącznie ciphertext;
- dodatek odszyfrowuje lokalnie po kwalifikacji biblioteki na ARMv7 i x86.

Przed implementacją etapu 2 obowiązuje feasibility gate dla bezpiecznego
przechowywania encryption key na Kodi/Android. Spike sprawdza Android Keystore
lub równoważny mechanizm, trwałość po restarcie, zachowanie po reinstalacji,
revocation, ARMv7/x86 oraz gwarancję, że klucz nie trafia do snapshotu.
Jeżeli nie ma przenośnej bezpiecznej implementacji, automatyczny restore
sekretów pozostaje poza zakresem, a hostowy encrypted backup jest rozwiązaniem
docelowym.

Synchronizator nie tworzy dodatkowych kopii plaintextu na QNAP, w stagingu,
journalu ani niesekretnym backupie rollback. Plaintext może jednak pozostać w
docelowym magazynie `userdata/addon_data`, jeżeli Umbrella/Real-Debrid wymaga
go do działania. MVP jawnie nie zapewnia ochrony at-rest docelowych ustawień
Kodi; chroni transport, kopie synchronizatora i dostęp do urządzenia.

Automatyczna synchronizacja sekretów nie zostanie włączona, dopóki testy nie
potwierdzą:

- braku plaintextu na QNAP;
- braku sekretów w logach;
- poprawnej rotacji i revocation;
- działania na Sony ARMv7 i BlueStacks x86;
- bezpiecznego rollbacku.

## 15. Harmonogramy

| Warstwa | Trigger | Akcja |
|---|---|---|
| upstream discovery | codziennie 04:20 | raport i propozycja zmian |
| kod testing | merge zaakceptowanego PR | deterministyczny build i publikacja |
| kod stable | ręcznie | promocja tych samych bajtów |
| repo Kodi klienta | native updater Kodi | synchronizator wymusza jeden refresh tylko przy niespełnionej zależności |
| profile consumer | start Kodi | sprawdzenie assignment |
| profile consumer | co 6 h z jitterem | sprawdzenie assignment |
| publisher MVP | ręcznie | candidate |
| publisher później | maks. raz/dobę po zmianie | candidate |
| snapshot QNAP | po naprawie RAID | Smart Versioning |
| backup poza QNAP | po naprawie RAID, codziennie | HBS lub równoważny backup |

Synchronizacja profili nie uruchamia `reconcile-upstreams` i nie modyfikuje
locków kodu.

Sprawdzenie przy starcie jest nieblokujące. Apply czeka na bezpieczne okno i
ma twarde timeouty; aktywny playback albo brak LAN przez VPN powoduje
odroczenie, a nie przerwanie pracy Kodi.

## 16. Etapy realizacji

### Etap 0: storage i warunki bezpieczeństwa

1. Przywrócić RAID1 QNAP do `[UU]`.
2. Potwierdzić stan przez `/proc/mdstat`, `mdadm` i `qcli_storage`.
3. Skonfigurować drugi backup poza tą macierzą.
4. Potwierdzić restore testowy niewrażliwego pliku.
5. Dopiero wtedy dopuścić QNAP jako magazyn produkcyjny.

Registry, schema, serwer na hoście, dodatek i lokalne E2E mogą powstawać
równolegle z naprawą storage. Zablokowane jest wyłącznie wdrożenie produkcyjne
i przechowywanie istotnych danych na QNAP. Zdegradowany QNAP nie jest
środowiskiem trwałego development storage.

### Etap 1: rejestr urządzeń

1. Dodać `manifests/devices.schema.json`.
2. Dodać przykład bez prawdziwych adresów.
3. Utworzyć prywatny `.kodi-private/devices.json`.
4. Zmigrować `kodi-reinstall.json` do `logical_device_id`.
5. Dodać `tools/kodi_devices.py`.
6. Zachować walidację modelu, ABI i wersji przed każdą mutacją.

### Etap 2: model profilu v2

1. Rozszerzyć istniejącą politykę o klasy danych.
2. Zdefiniować schemat manifestu rewizji.
3. Oddzielić routine profile od disaster-recovery snapshot.
4. Dodać diff logiczny bez ujawniania wartości sekretów.
5. Dodać semantyczne adaptery per setting z default-deny.
6. Dodać ownership, tombstones i deterministyczną kolejność overlayów.
7. Dodać eksport deterministyczny i content-addressed blobs.
8. Zachować zgodność odczytu snapshotów schema 1 jako osobnego scope
   disaster recovery.

### Etap 3: serwer lokalny

1. Wykonać MVP crypto spike: enrollment signing, weryfikacja podpisów i
   golden vectors na Kodi ARMv7/x86. **Zrealizowane.**
2. Utworzyć osobne repo serwera.
3. Zaimplementować immutable revisions, channels i CAS.
4. Dodać idempotency keys, upload sessions i spójność SQLite/blob store.
5. Dodać pairing, tokeny, role i revocation.
6. Dodać podpisy rewizji, assignmentów, raportów oraz zdarzeń kanału.
7. Dodać SQLite migrations, backup API i bezpieczny GC.
8. Dodać redakcję logów.
9. Dodać minimalny Dockerfile, health check i CI budujące obrazy
   `linux/amd64` oraz `linux/arm/v7`; publikować manifest wieloarchitekturowy
   i przypinać wdrożenie po digescie, nie ruchomym tagu.
10. Uruchomić integrację lokalnie bez QNAP.

### Etap 4: dodatek Kodi

1. Utworzyć `service.mwodevelop.profilesync`.
2. Dodać pairing i heartbeat.
3. Dodać weryfikację TLS, podpisów i generacji kanału.
4. Dodać active/canary assignment, check/download/staging.
5. Dodać zarządzanie wymaganymi dodatkami przez repo Kodi.
6. Dodać jawnie włączane adaptery dla ustawień niesekretnych.
7. Dodać crash-resilient journal, pending next-start i kwarantannę.
8. Dodać health report i kompensacyjny rollback konfiguracji.
9. Dodać admin CLI poza Kodi.
10. Opublikować wyłącznie w `testing`.

### Etap 5: E2E ustawień niesekretnych

1. BlueStacks jako publisher.
2. Czysta dodatkowa instancja BlueStacks jako consumer.
3. Sony jako consumer.
4. Candidate przypięty tylko do czystego BlueStacks i apply.
5. Po sukcesie exact candidate przypięty tylko do Sony i apply.
6. Dopiero po obu raportach promocja, startowy pull i apply.
7. Potwierdzenie aktywnej skórki lub jawnego `host_only`.
8. Potwierdzenie repo origin dodatków.
9. Deterministyczny test adapterów z lokalnym fake add-on/API.
10. Umbrella search bez credentiali albo z oczekiwanym brakiem autoryzacji.
11. RD playback wyłącznie na consumerze pre-provisioned hostowym restore i
    oznaczony jako test zależny od zewnętrznej usługi.
12. WatchNixtoons2 katalog i playback jako uzupełniający live smoke.
13. Uszkodzony digest/podpis/path: zero mutacji.
14. Poprawny technicznie, lecz wadliwy profil: health failure i rollback.
15. Test niedostępnego QNAP i VPN bez uszkodzenia Kodi.

### Etap 6: QNAP

1. Utworzyć dedykowany udział danych.
2. Wdrożyć jako aplikację Container Station z Docker Compose i digestem
   obrazu; nie instalować backendu bezpośrednio w QTS ani jako QPKG.
3. Ograniczyć port do LAN.
4. Skonfigurować HTTPS.
5. Skonfigurować health check i restart policy.
6. Wykonać runtime smoke ARMv7, migrację SQLite i TLS z obu klientów Kodi.
7. Skonfigurować kontrolowany update/rollback obrazu po digescie.
8. Skonfigurować retencję aplikacyjną.
9. Skonfigurować snapshoty QTS.
10. Skonfigurować backup poza QNAP.
11. Wykonać restore drill.

### Etap 7: zaszyfrowane sekrety

1. Wybrać bibliotekę po spike na ARMv7/x86.
2. Zakwalifikować bezpieczne przechowywanie klucza na Androidzie.
3. Zaimplementować device keys i envelope encryption.
4. Dodać rotację i unieważnianie.
5. Dodać testy braku plaintextu w stagingu, journalu, backupie i logach.
6. Dodać ręczny restore sekretów w dodatku.
7. Wykonać autonomiczny RD restore/playback E2E.
8. Dopiero po stabilizacji rozważyć automatyczny restore.

### Etap 8: stabilizacja i wydanie

1. Audyt bezpieczeństwa.
2. Niezależne review implementacji względem niniejszego planu.
3. Pełny lokalny E2E.
4. CI bez sekretów.
5. Canary na BlueStacks.
6. Canary na Sony.
7. Publikacja do testing.
8. Okres obserwacji.
9. Ręczna promocja do stable.

## 17. Testy

### 17.1 Unit

- walidacja rejestru urządzeń;
- bezpieczne rozwiązywanie `logical_device_id`;
- klasyfikacja plików polityki;
- deterministyczny manifest;
- golden vectors kanonikalizacji i podpisów;
- podpisane assignmenty i raporty enrollmentu;
- SHA-256 i inventory;
- osobne CAS publish/promote/rollback i idempotency keys;
- role i tokeny;
- default-deny per setting, ownership i tombstones;
- deterministyczne overlaye;
- path traversal;
- limit rozmiaru;
- migracje SQLite;
- redakcja logów;
- state machine klienta;
- kompensacyjny rollback i kwarantanna.

### 17.2 Integration

- API + SQLite + blob store;
- restart kontenera w trakcie uploadu;
- restart kontenera przy finalize, promote i GC;
- ponowienie idempotentnego uploadu;
- przerwany download;
- równoległe publikacje;
- unieważniony token;
- wersja klienta niezgodna z manifestem;
- zły podpis, starsza generacja i niezgodna wersja API/schema;
- disk full oraz crash injection w każdej fazie apply;
- aktualizacja klienta w trakcie apply;
- build `linux/arm/v7`;
- runtime smoke na rzeczywistym QNAP ARMv7;
- odtworzenie danych serwera z backupu.

### 17.3 Device E2E

- BlueStacks publisher -> BlueStacks consumer;
- BlueStacks publisher -> Sony consumer;
- exact candidate pin bez zmiany globalnego active;
- start Kodi z dostępnym QNAP;
- start Kodi bez QNAP;
- start Sony z Nord VPN oraz z niedostępnym route do LAN;
- zmiana aktywnej rewizji;
- pending next-start i zmiana `host_only`;
- rollback po health check failure;
- corrupt/signature/path failure bez żadnej mutacji;
- repo origin `repository.mwodevelop`;
- brak cache po apply;
- Umbrella bez sekretów i osobny RD playback po hostowym pre-provision;
- mwoScrapers aktywny;
- WatchNixtoons2 playback;
- brak sekretów w raporcie.

Wyniki urządzeń są zapisywane w redagowanym, odtwarzalnym formacie. Sam status
GUI, obecność pliku albo rozpoczęcie resolvera nie jest dowodem sukcesu.
Live testy RD i WatchNixtoons2 uzupełniają deterministyczny E2E z lokalnym
fake serverem; nie są jego jedyną podstawą.

## 18. Retencja i backup

Retencja aplikacyjna jest podstawowa:

- co najmniej 20 ostatnich rewizji kanału;
- bieżąca active, ostatnie N poprzednich active oraz rewizje jawnie przypięte;
- starsze active po usunięciu payloadu zachowują mały audit record;
- kandydat ma konfigurowalny TTL, limit liczby i limit bajtów per kanał;
- candidate z aktywnym assignmentem, oczekiwanym wymaganym raportem lub
  approval jest GC root i nie wygasa;
- TTL kandydata zaczyna biec dopiero po unassign, supersede albo reject;
- po wygaśnięciu payload kandydata może zostać usunięty, ale mały wpis audytu
  pozostaje;
- content blobs są usuwane dopiero przez mark-and-sweep z grace period i po
  sprawdzeniu aktywnych upload/download leases.

Snapshot QTS jest drugą warstwą:

- 24 godzinne;
- 30 dziennych;
- 12 miesięcznych;
- wartości do ostatecznego zatwierdzenia po sprawdzeniu dostępnego snapshot
  space.

Trzecia warstwa to backup poza QNAP. Snapshot na zdegradowanym lub pojedynczym
RAID nie jest kopią zapasową.

## 19. Migracja

1. Nie usuwać istniejących `.kodi-private/snapshots`.
2. Nie usuwać `tools/kodi_reinstall.py`.
3. Zbudować `devices.json` na podstawie obecnego configu.
4. Utworzyć pierwszą rewizję profilu bez sekretów.
5. Zweryfikować ją na nowej instancji BlueStacks.
6. Ponownie sparować czysty consumer zamiast kopiować enrollment ze snapshotu.
7. Dodać Sony dopiero po sukcesie BlueStacks.
8. Zachować hostowy restore jako break-glass path.
9. Po uruchomieniu szyfrowanych sekretów wykonać pełny restore drill.
10. Dopiero po dwóch udanych restore drillach rozważyć ograniczenie starych
   lokalnych snapshotów.

## 20. Ryzyka i zabezpieczenia

| Ryzyko | Zabezpieczenie |
|---|---|
| zdegradowany RAID QNAP | blocker wdrożenia i backup poza NAS |
| utrata QNAP | lokalna konfiguracja działa dalej, host snapshot pozostaje |
| zły profil mastera | candidate, ręczna promocja i rollback |
| różne wersje dodatków | najpierw update przez repo, potem apply ustawień |
| kod pozostaje nowszy po rollbacku profilu | kompatybilne constraints i jawny status `CODE_ADVANCED` |
| różne ABI/Kodi | compatibility gate w manifeście |
| Android scoped storage | zapis wewnątrz procesu Kodi |
| Kodi nadpisuje plik przy zamknięciu | API/adaptery, `host_only`, brak generycznej podmiany |
| zmiana blokuje start Kodi | limit prób, kwarantanna i hostowy break-glass |
| ustawienia skórki zależne od ekranu | device overlays i opt-in |
| dwa mastery | single publisher + CAS |
| wyciek tokenów | osobne tokeny, redakcja, docelowo client-side encryption |
| sklonowana tożsamość po restore | enrollment zawsze device-local i ponowne pairing |
| przejęty QNAP lub MITM | podpisy rewizji/promocji i zweryfikowany bootstrap TLS |
| złośliwa ścieżka w manifeście | allowlist polityki i canonical path checks |
| uszkodzony download | staging i SHA-256 |
| restart w trakcie apply | journal transakcji i recovery przy starcie |
| niedostępny serwer | backoff, brak mutacji, Kodi startuje normalnie |
| VPN odcina LAN Sony | test route, timeout i odroczenie bez mutacji |
| obraz bez ARMv7 | obowiązkowy multiarch CI i smoke na QNAP |
| niespójna kopia SQLite | Backup API/controlled stop i restore drill |

## 21. Kryteria akceptacji

Projekt jest ukończony dopiero, gdy:

1. wszystkie urządzenia mają stabilne `logical_device_id`;
2. adresy są w `.kodi-private/devices.json`, a nie w publicznym repo;
3. `kodi-reinstall.json` używa `logical_device_id`;
4. QNAP RAID jest zdrowy i istnieje backup poza QNAP;
5. serwer działa po restarcie QNAP;
6. nowy consumer może zostać sparowany bez konta administratora NAS;
7. każdy klient ma własne `enrollment_id`, generację i klucz podpisujący, a
   restore nie klonuje jego enrollmentu;
8. rewizje, assignmenty, raporty i zmiany kanału mają poprawne podpisy;
9. kanał ma monotoniczną generację i zweryfikowany checkpoint;
10. exact candidate przechodzi canary bez zmiany globalnego active;
11. profil jest wersjonowany i możliwy do cofnięcia;
12. klient pozostaje sprawny bez QNAP;
13. dodatki zachowują origin repozytorium;
14. cache i bazy nie są synchronizowane;
15. synchronizator nie tworzy dodatkowego plaintextu sekretów w Git, obrazie,
    QNAP, stagingu, journalu, backupie, logach ani raportach;
16. routine sync przechodzi E2E na BlueStacks i Sony;
17. corrupt digest, podpis lub ścieżka powoduje zero mutacji;
18. health failure po apply powoduje kompensacyjny rollback lub jawny
    `ROLLBACK_REQUIRES_HOST`;
19. routine E2E nie zależy od synchronizacji credentiali RD;
20. pełny restore sekretów przechodzi osobny E2E;
21. istniejący upstream/testing/stable pipeline nadal przechodzi bez zmian
    semantycznych;
22. wydanie stable następuje dopiero po review i okresie canary.

## 22. Kolejność zależności

```text
device registry -> profile schema v2 -> local server API
                                           |
                                           v
                              Kodi service addon -> addon testing
                                           |               |
                                           +-------+-------+
                                                   |
                                                   v
                                      non-secret local/device E2E

naprawa RAID + backup -> QNAP production deployment
                                      |
                                      +---- non-secret E2E
                                                  |
                                                  v
                                           profile canary
                                                  |
                                                  v
                                      manual profile active

addon testing + non-secret E2E -> obserwacja -> manual addon stable

QNAP deployment + encryption feasibility -> encrypted secret sync
```

Implementacja nie powinna rozpoczynać się od dodatku Kodi ani wdrożenia
kontenera. Pierwszym krokiem jest rejestr urządzeń i kontrakt profilu, ponieważ
oba są zależnościami wszystkich późniejszych elementów. Naprawa RAID może
biec równolegle, ale pozostaje twardą bramą wyłącznie dla produkcyjnego
wdrożenia QNAP.
