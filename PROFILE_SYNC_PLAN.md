# Plan synchronizacji profili, urządzeń i aktualizacji Kodi

Status: plan po review, w realizacji etapowej

Data: 2026-07-28

Repo nadrzędne: `mwoDevelop/kodi`

Lokalizacja robocza: `/home/mwo/projects/kodi`

Dokument powiązany: `UPSTREAM_SYNC_PLAN.md`

Raporty review:

- `docs/PROFILE_SYNC_PLAN_REVIEW.md`;
- `docs/PROFILE_SYNC_QNAP_PLAN_REVIEW.md`;
- `docs/PROFILE_SYNC_NUC_PLAN_REVIEW.md`.

Stan realizacji 2026-07-28:

- Etap 1: zrealizowany lokalnie i pokryty testami;
- Etap 2: schema 2 portable-common oraz schema 3 z deterministycznymi
  `base/layers` są zaimplementowane; reader schema 2 pozostaje zgodny;
- Etap 3: zrealizowany transakcyjny store, loopback API development,
  przenośny Ed25519 na Kodi x86/ARMv7 oraz build obrazu
  `linux/amd64,linux/arm/v7`;
- Etap 4: osobne repo dodatku, pairing, heartbeat i podpisany check
  read-only opublikowane w `stable`; wersja 0.1.6 wybiera warstwy wyłącznie
  z podpisanego assignmentu i administracyjnych target tags; E2E wersji
  0.1.5 zaliczone na BlueStacks i Sony TV, a E2E 0.1.6 na Bedroom TV zalicza
  instalację z repo testing, pairing, uwierzytelniony heartbeat, podpisany
  check i invariant read-only no-apply;
- Etap 5: transakcyjny adapter Umbrella, journal, recovery, rollback i
  kwarantanna są zaimplementowane i pokryte testami lokalnymi; urządzeniowy
  apply E2E pozostaje do wykonania;
- Etap 6A: kontenerowy kontrakt Compose, walidator polityki, hostowy lifecycle,
  manifest GHCR `linux/amd64,linux/arm/v7` oraz nietrwały live smoke QNAP
  z restartem, awarią/odtworzeniem i pełnym cleanupem są zrealizowane;
  produkcja 6B pozostaje zablokowana do zakończenia Etapu 0 i spełnienia bram
  bezpieczeństwa API, migracji, TLS oraz backupu;
- rozszerzenie Linux/Flatpak: live discovery NUC zrealizowane dla kont `mwo`
  i `alek`; registry v2, neutralne ADB/SSH, lifecycle Android/Flatpak oraz
  read-only inventory są zaimplementowane i pokryte testami; osobne klucze SSH
  obu kont zostały zainstalowane i przeszły test izolacji między kontami, lecz
  dalsza live kwalifikacja czeka na ponowną dostępność NUC;
- rozszerzenie Android: `Bedroom TV` (`Google TV Streamer`, codename
  `kirkwood`) znajduje się w prywatnym registry v2, przeszedł read-only
  lifecycle inventory oraz odwracalny rollout Kodi 21.3, profilu, skórki i
  dodatków. E2E Profile Sync 0.1.6 i playback WatchNixtoons2 0.26.1 zakończyły
  się powodzeniem. Playback po poprawce Umbrella także zaliczył bramę z
  aktywnym NordVPN i został promowany bajt po bajcie do `stable`. Sony TV i
  Bedroom TV zostały przepięte z repo testing na dokładny indeks stable, a
  pomocnicze repo testing usunięto po weryfikacji zgodności kandydatów;
- Etapy 7–8: nierozpoczęte.

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
9. zachowuje obecny awaryjny workflow hosta oparty o prywatne snapshoty oraz
   transport właściwy dla platformy: ADB na Androidzie i SSH dla Kodi
   Flatpak na Linuksie;
10. traktuje każde konto systemowe z osobnym katalogiem danych Kodi jako
    niezależny endpoint synchronizacji, nawet jeśli konta współdzielą host i
    systemowy pakiet Kodi.

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
                    - Android przez ADB tylko przy bootstrapie/break-glass
                    - Linux Flatpak per konto przez SSH tylko przy bootstrapie
                    - runtime sync bezpośrednio z dodatku do QNAP
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
15. Jeden fizyczny host może mieć wiele niezależnych endpointów Kodi. Każdy
    endpoint ma własny `logical_device_id`, `enrollment_id`, token, klucz,
    journal, backup lokalny i raporty.
16. Konto systemowe jest granicą bezpieczeństwa. Sekrety, enrollment i stan
    `nuc-mwo` nie mogą zostać skopiowane do `nuc-alek` ani odwrotnie.
17. Transport hostowy jest rozszerzeniem OCP. Logika profilu używa wspólnego
    kontraktu transportu i nie zawiera warunków zależnych od nazw Android,
    Flatpak, NUC, `mwo` lub `alek`.
18. Systemowy pakiet `tv.kodi.Kodi` z Flathub jest aktualizowany przez Flatpak,
    nie przez repo Kodi ani Profile Sync. Repo mwoDevelop zarządza wyłącznie
    dodatkami wewnątrz osobnego katalogu danych każdego konta.

## 4. Stan początkowy

### 4.1 Kodi i urządzenia

Obecnie prywatne endpointy są częściowo przechowywane w:

```text
.kodi-private/kodi-reinstall.json
```

Znane cele:

- BlueStacks1, model `SM-S901E`;
- Sony Android TV, model `BRAVIA 4K GB ATV3`;
- Bedroom TV, model `Google TV Streamer`, codename `kirkwood`, Android 14,
  Kodi 21.3, `armeabi-v7a`;
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

### 4.4 NUC Linux/Flatpak

Live discovery 2026-07-27 potwierdził:

- prywatny endpoint NUC działa przez SSH;
- openSUSE Tumbleweed, kernel 7.1.2, `x86_64`;
- fizyczny model `IP3 Tech TB20C`;
- systemową instalację `tv.kodi.Kodi 21.3-Omega` z Flathub;
- brak ustawionego stabilnego hostname systemu, dlatego tożsamość nie może
  zależeć od bieżącego `localhost`;
- dwa dostępne konta systemowe: `mwo` i `alek`;
- osobne, zapisywalne katalogi danych:
  - `/home/mwo/.var/app/tv.kodi.Kodi/data`;
  - `/home/alek/.var/app/tv.kodi.Kodi/data`;
- dostęp sieciowy Flatpak wymagany przez klienta Profile Sync;
- wyłącznie `Master user` wewnątrz Kodi na obu kontach.

Stan dodatków jest rozbieżny. Konto `mwo` ma istniejącą Umbrella i
WatchNixtoons2, lecz nie ma `repository.mwodevelop`, mwoScrapers ani klienta
Profile Sync. Konto `alek` ma niemal czysty profil i również nie ma naszych
dodatków.

To nie jest przypadek wielu profili wewnętrznych Kodi. Każde konto systemowe
jest osobną instancją danych i otrzymuje własną tożsamość:

```text
physical_host_id: nuc-host
  logical_device_id: nuc-mwo
    principal_id: principal-nuc-01
  logical_device_id: nuc-alek
    principal_id: principal-nuc-02
```

Oba endpointy zaczynają jako `consumer`. Nadanie `publisher` któremukolwiek z
nich wymaga osobnej decyzji i canary; nie wynika ze współdzielenia hosta.

Prywatny `.env` wymaga korekty przed automatyzacją: drugi klucz
`NUC_PASS_MWO` ma zostać nazwany `NUC_PASS_ALEK`. Docelowo hasła zastępują
osobne klucze SSH bez prawa eskalacji, ograniczone do właściwego konta.

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
- onboarding i E2E Bedroom TV jako osobnego consumera Android;
- dwa niezależne endpointy NUC Linux/Flatpak: `nuc-mwo` i `nuc-alek`;
- bootstrap oraz break-glass przez SSH w kontekście właściwego konta;
- izolacja konfiguracji i sekretów między kontami tego samego hosta;
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
- obsługa wielu profili wewnętrznych Kodi w jednym katalogu `userdata`;
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
│       ├── compose.smoke.yaml
│       ├── README.md
│       ├── env.example
│       └── smoke.env.example
├── tools/
│   ├── kodi_devices.py
│   ├── kodi_transports.py
│   ├── kodi_lifecycle.py
│   ├── kodi_android.py
│   ├── kodi_flatpak.py
│   ├── kodi_profile.py
│   ├── kodi_reinstall.py
│   ├── profile_sync_admin.py
│   └── qnap_profile_sync.py
├── profile-sync-addon/             # osobne repo/submoduł
└── .kodi-private/
    ├── devices.json
    ├── kodi-reinstall.json
    ├── qnap-profile-sync.env
    ├── qnap-profile-sync-smoke.env
    ├── ssh/
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

Transport i lifecycle platformy są rozłączne. `kodi_transports.py` definiuje
ograniczony kontrakt I/O i tożsamości, implementowany przez `AdbTransport` oraz
`SshTransport`. Nie udostępnia konsumentom dowolnego `run`, nie zatrzymuje Kodi
i nie przyjmuje niezweryfikowanych ścieżek.

`kodi_lifecycle.py` definiuje `KodiPlatformLifecycle`, komponowany z wybranym
transportem. `AndroidKodiLifecycle` i `FlatpakKodiLifecycle` odpowiadają za
`probe_kodi`, bootstrap, backup/restore, kontrolę quiescence i verify.
`kodi_profile.py`, dispatcher `kodi_reinstall.py` oraz E2E zależą od tych
interfejsów, a nie od kombinacji SSH+Flatpak. Dzięki temu Linux bez Flatpaka
może w przyszłości dodać lifecycle bez duplikowania transportu SSH.

## 7. Rejestr urządzeń

Rzeczywisty rejestr:

```text
.kodi-private/devices.json
```

Plik jest ignorowany przez Git. Wersjonowane będą wyłącznie:

- `manifests/devices.schema.json`;
- przykład bez prawdziwych adresów;
- testy walidatora.

Obecna schema 1 wymaga `endpoints.adb` i nie może opisać NUC. Schema 2
wprowadza:

- `physical_host_id`, aby grupować konta tego samego hosta bez łączenia ich
  tożsamości;
- `principal_id`, czyli stabilną, nieprzezroczystą granicę konta/instancji
  danych Kodi, niezawierającą loginu;
- `platform`: `android`, `android-emulator` albo `linux-flatpak`;
- rozłączną konfigurację transportu `adb` albo `ssh`;
- `credential_ref`, który wskazuje nazwę sekretu w prywatnym env lub klucz
  SSH, ale nigdy nie zawiera hasła;
- prywatny `user_ref` rozwiązywany dopiero na hoście;
- oczekiwany `kodi_data_root` dla Flatpak, potwierdzany przez discovery
  `special://home`/`special://profile` wewnątrz runtime, a następnie
  sprawdzany po canonicalizacji względem home z `getent passwd`.

Loader czyta schema 1 oraz 2 i normalizuje oba do jednego modelu wewnętrznego
v2. Osobna migracja 1 -> 2:

- tworzy backup;
- jest idempotentna;
- zachowuje `logical_device_id`, role i endpointy Androida;
- zapisuje atomowo wyłącznie schema 2;
- przed zatwierdzeniem porównuje byte-equivalent resolve wszystkich
  istniejących celów Android.

Stary Android-only `kodi_reinstall.py` jawnie odrzuca cel Linux do chwili
wdrożenia dispatchera transport+lifecycle.

Docelowy dokument:

```json
{
  "schema": 2,
  "devices": {
    "sony-living-room": {
      "physical_host_id": "sony-living-room",
      "principal_id": "principal-sony-owner",
      "platform": "android",
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
      "physical_host_id": "bluestacks1",
      "principal_id": "principal-bluestacks-owner",
      "platform": "android-emulator",
      "roles": ["publisher", "consumer"],
      "expected": {
        "model": "SM-S901E",
        "kodi_major": 21
      },
      "endpoints": {
        "adb": "<private-bluestacks-adb-endpoint>"
      },
      "profile_channel": "home-stable"
    },
    "nuc-mwo": {
      "physical_host_id": "nuc-host",
      "principal_id": "principal-nuc-01",
      "platform": "linux-flatpak",
      "roles": ["consumer"],
      "expected": {
        "model": "IP3 Tech TB20C",
        "kodi_major": 21,
        "abi": ["x86_64"],
        "flatpak_app_id": "tv.kodi.Kodi",
        "kodi_data_root": ".var/app/tv.kodi.Kodi/data"
      },
      "endpoints": {
        "ssh": {
          "host": "<private-nuc-host>",
          "user_ref": "NUC_USER_MWO",
          "credential_ref": "NUC_SSH_KEY_MWO",
          "known_hosts_ref": "NUC_KNOWN_HOSTS"
        }
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
`logical_device_id`, wybiera osobno transport i lifecycle przez registry/
factory, sprawdza tożsamość hosta, platformę, UID, konto, Kodi major, listę ABI,
owner i canonical data root, a dopiero potem wykonuje operację.

Tożsamość SSH wymaga przypiętego host key oraz zapamiętanego fingerprintu
tożsamości maszyny; hostname, model i zmienny adres DHCP nie wystarczają.
Wywołania OpenSSH używają tablicy argumentów, `BatchMode=yes`, dedykowanego
`UserKnownHostsFile`, wyłączonego agent forwarding i braku sudo. Hasło może
służyć wyłącznie do ręcznego bootstrapu osobnego klucza per konto.

Dla urządzeń fizycznych zalecane są rezerwacje DHCP. QNAP rejestruje także
`last_seen`, ostatni obserwowany adres i wersję klienta, ale nie traktuje
adresu jako poświadczenia.

Rejestry mają różne, jawne role:

- `.kodi-private/devices.json` jest administracyjnym inventory hosta dla ADB,
  SSH/Flatpak, JSON-RPC i operacji reinstall/restore;
- rejestr QNAP przechowuje enrollment, klucze publiczne, role oraz
  administracyjnie przypisane, nieprzezroczyste `target_tags`; heartbeat
  klienta może raportować obserwowane platformę, Kodi i ABI, ale self-report
  nie wybiera warstwy ani nie stanowi autoryzacji;
- `logical_device_id` jest stabilnym aliasem urządzenia, natomiast każda
  ponowna instalacja tworzy nowe `enrollment_id`, podniesioną
  `enrollment_generation`, token i klucz podpisujący;
- token, klucz i enrollment nie są kopiowane ze snapshotu. Po czystej
  reinstalacji urządzenie jest ponownie parowane;
- overlay jest wiązany przede wszystkim z administracyjnie nadanym
  `device_class`/`target_tags`.
  Wyjątek per `logical_device_id` wymaga jawnego wpisu.

Na NUC wspólny `physical_host_id` służy wyłącznie do inventory, harmonogramu i
lockingu operacji współdzielonych. Nie jest tożsamością ani podstawą
autoryzacji QNAP. Operacje profilowe mają lock per
`(physical_host_id, principal_id)`. QNAP nie deduplikuje enrollmentów po
hoście: `nuc-mwo` i `nuc-alek` pozostają dwiema niezależnymi instalacjami.
Para `(physical_host_id, principal_id)` jest unikalna, a każdy
`logical_device_id` ma najwyżej jedną aktywną generację enrollmentu.

## 8. Model profilu

Obecna polityka zostanie rozszerzona, a nie zastąpiona konkurencyjnym plikiem.
Polityka schema v2 definiuje dwa rozłączne scope'y:

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

Aktualna revision schema 2 i klient obsługują płaską listę adapterów, lecz nie
potrafią reprezentować opisanych niżej warstw platformowych. Przed ich
produkcyjnym apply powstaje revision schema 3:

- reader klienta zachowuje kompatybilność odczytu schema 2;
- schema 3 rozdziela portable base od uporządkowanych layers;
- warstwa ma ograniczenia zgodności Kodi major, platformy, listy ABI, wersji
  adaptera i origin/wersji zarządzanego dodatku;
- wybór warstw wynika z podpisanego assignmentu i administracyjnych
  `target_tags`, a nie z nieufnego heartbeat;
- kanoniczny manifest i podpis obejmują base, warstwy, selektory i ich
  deterministyczną kolejność;
- schema nie zawiera loginu Unix, home, IP, `physical_host_id` ani
  `principal_id`; wyjątek urządzenia używa wyłącznie `logical_device_id`;
- sekrety pozostają osobnymi envelope'ami per enrollment.

Do wdrożenia schema 3 klient Linux/Flatpak pozostaje read-only albo stosuje
wyłącznie jawnie oznaczony portable common subset schema 2. Nie wolno
interpretować nieznanych pól schema 2 jako overlayów.

Manifest przechowuje również:

- wersję adaptera i zakres kompatybilnych wersji dodatku;
- deklarację własności zarządzanych kluczy/ścieżek;
- jawne tombstones dla usunięć.

Usunięcie dotyczy tylko elementu wcześniej zarządzanego przez ten sam adapter.
Brak elementu w profilu nie oznacza zgody na skasowanie niezarządzanych danych.
Kolejność nakładania jest deterministyczna:

```text
portable -> platform/device_class overlay -> logical_device overlay
```

`physical_host_id` nie wybiera overlayu w MVP. Nawet ustawienia pozornie
wspólnego sprzętu, na przykład wyjście audio, mogą należeć do użytkownika.
Ustawienia użytkownika, historia, konta usług i sekrety są co najmniej
`logical_device` scoped. Brak jawnej zgody polityki na współdzielenie oznacza
izolację między `nuc-mwo` i `nuc-alek`.

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

MVP obsługuje wyłącznie domyślny profil Kodi w każdym katalogu danych. Wiele
kont systemowych z osobnymi katalogami Flatpak jest obsługiwane jako wiele
endpointów. Dopiero wykrycie dodatkowych profili wewnętrznych w jednym
`userdata/profiles.xml` powoduje raport `UNSUPPORTED_MULTI_PROFILE` bez
mutacji.

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

### 10.1 Postać wdrożenia w Container Station

Backend działa na daemonie Container Station, ale jedynym źródłem prawdy dla
cyklu życia aplikacji jest Compose CLI wywoływany przez SSH z narzędzia
hostowego. GUI Container Station służy wyłącznie do obserwacji stanu; nie
importujemy w nim ponownie tej samej aplikacji ani nie zmieniamy jej
konfiguracji ręcznie.

Źródłem deklaracji jest:

```text
deploy/qnap-profile-sync/compose.yaml
deploy/qnap-profile-sync/compose.smoke.yaml
```

Nie ustawiamy stałego `container_name`. Nazwę i izolację zapewnia jawny Compose
project name:

- produkcja: `qnap-profile-sync`;
- smoke: `qnap-profile-sync-smoke`.

Obie deklaracje przechodzą walidację lokalną i w CI. Smoke używa pliku bazowego
oraz override, produkcja wyłącznie pliku bazowego.

Docelowa topologia:

```text
Sony / BlueStacks
        |
        | HTTPS, tylko LAN
        v
QNAP reverse proxy
        |
        | http://127.0.0.1:18765
        v
Container Station application: qnap-profile-sync
        |
        +-- /data  -> /share/ProfileSync/data
        |
        +-- key registry (read-only)
             -> /share/ProfileSync/config/key-registry.json
```

Kontener produkcyjny:

- działa jako jawnie skonfigurowany i zweryfikowany dedykowany UID/GID,
  domyślnie `10001:10001`, jeśli nie koliduje na QNAP;
- ma root filesystem `read_only`;
- odrzuca wszystkie capabilities;
- używa `no-new-privileges`;
- ma `init`, limit pamięci 256 MB i limit 128 procesów;
- używa `tmpfs` wyłącznie dla `/tmp`;
- publikuje API tylko na loopback QNAP;
- ma healthcheck HTTP i `restart: unless-stopped`;
- uruchamia wyłącznie tryb ze zweryfikowanym key registry;
- nie otrzymuje administracyjnych credentiali QNAP.

Przed startem preflight uruchamia próbę zapisu i odczytu do `/data` jako
docelowy UID/GID, sprawdza właściciela i minimalne ACL oraz potwierdza, że key
registry jest istniejącym zwykłym plikiem. Bind mounty używają długiej składni
z `bind.create_host_path: false`, aby literówka nie utworzyła katalogu zamiast
pliku.

### 10.2 Artefakty i katalogi QNAP

Po przejściu bramy storage powstaje dedykowany udział:

```text
/share/ProfileSync/
  compose/
    compose.yaml
    compose.smoke.yaml
    deployment.env
    current-digest.txt
    previous-digest.txt
  config/
    key-registry.json
    tls-bootstrap/
  data/
    state.sqlite
    blobs/
    uploads/
  rollback-cache/
    application/
    restore-drills/
```

Zasady:

- kanoniczną ścieżką bazy jest `/data/state.sqlite`, czyli
  `/share/ProfileSync/data/state.sqlite` na hoście;
- `deployment.env`, rejestr kluczy i publiczny bootstrap TLS mają minimalne
  uprawnienia i nie trafiają do Git;
- prywatny klucz TLS pozostaje własnością QNAP reverse proxy i nie trafia do
  katalogu projektu, Compose ani backupu profilu;
- plik Compose nie zawiera tokenów, haseł ani kluczy prywatnych;
- obraz jest wskazywany jako `ghcr.io/...@sha256:<digest>`;
- `data` i plik rejestru kluczy są bind mountami, nie anonimowymi volume;
- `rollback-cache` nie jest montowany do procesu API i nie jest nazywany
  backupem, ponieważ znajduje się na tej samej macierzy;
- prawdziwy backup jest zaszyfrowanym, spójnym zestawem SQLite + blob store
  zapisanym poza QNAP i okresowo przechodzącym restore drill;
- przed utworzeniem katalogów skrypt rozwiązuje i zatwierdza bezwzględne
  ścieżki, UID/GID, właścicieli i ACL; nie polega na automatycznym tworzeniu
  bind mountów przez Dockera.

### 10.3 Dwa tryby realizacji

Przed naprawą RAID dopuszczony jest tylko `qnap-smoke`:

- identyczny obraz ARMv7 i te same ograniczenia bezpieczeństwa;
- osobny Compose project `qnap-profile-sync-smoke`, brak stałego
  `container_name`, osobny port i `restart: "no"`;
- obowiązkowy override `compose.smoke.yaml`, który nie może wskazywać ścieżek
  produkcyjnych;
- baza oraz key registry wygenerowane wyłącznie dla testu;
- dane w `tmpfs` albo w jednoznacznie oznaczonym katalogu jednorazowym;
- brak prawdziwych profili, credentiali, kluczy produkcyjnych i autostartu;
- po teście eksportowany jest wyłącznie zredagowany raport, a stan testowy
  jest usuwany;
- restart QNAP może przerwać test bez utraty istotnych danych.

Po uzyskaniu `[UU]`, backupu poza NAS i udanym restore drill uruchamiany jest
`qnap-production`:

- trwałe katalogi `/share/ProfileSync`;
- QNAP reverse proxy z HTTPS;
- pairing z przypiętym bootstrapem zaufania;
- `restart: unless-stopped` i automatyczny start aplikacji Container Station;
- snapshoty, retencja i backup poza QNAP;
- monitoring health oraz kontrolowany rollback obrazu i danych.

Smoke i produkcja nie współdzielą bazy, tokenów, key registry ani nazwy
katalogu danych. Nie współdzielą też Compose project name, host portu ani
polityki restartu. Wynik smoke nie może zostać przemianowany na produkcję.

Transport testu 6A jest jawny i nie zależy od produkcyjnego reverse proxy:

```text
Android Kodi http://127.0.0.1:<device-port> -> adb reverse -----+
NUC Kodi http://127.0.0.1:<device-port> -> SSH remote forward --+
                                                               |
host 127.0.0.1:<host-port>
  -> SSH local forward
QNAP 127.0.0.1:<smoke-port>
  -> kontener smoke
```

Tunel powstaje osobno dla BlueStacks, Sony i Bedroom TV oraz jako kontrolowany
remote forward na NUC. Po jego utworzeniu test potwierdza na wszystkich pięciu
klientach, że wskazany lokalny port prowadzi do dokładnego smoke projectu.
Plain HTTP jest dozwolony tylko na loopback w tym kontrolowanym przebiegu;
wynik 6A nie jest dowodem poprawności TLS. Wszystkie tunele i reguły
`adb reverse` są usuwane razem z aplikacją smoke.

### 10.4 Aktualizacja i rollback kontenera

GitHub Actions buduje, testuje i publikuje manifest wieloarchitekturowy, ale
nie wdraża samodzielnie na QNAP. Workflow używa Buildx/QEMU, testuje kod oraz
obraz, publikuje warianty `linux/amd64` i `linux/arm/v7`, zapisuje niezmienny
digest i weryfikuje manifest przez `docker buildx imagetools inspect`. Sam
lokalny build z `push: false` nie spełnia bramy 6A.

Preferowany jest publiczny obraz GHCR, który nie zawiera sekretów. Jeśli obraz
pozostanie prywatny, credential jest zapisany w hostowym credential store
Container Station i nie trafia do Compose, env, logów ani repo.

Wdrożenie wykonuje skrypt administracyjny z hosta przez Compose CLI po SSH:

1. odczytuje aktualny i docelowy digest;
2. sprawdza obecność wariantu `linux/arm/v7`;
3. odczytuje wersję schematu DB i macierz kompatybilności obrazu;
4. wykonuje spójny backup SQLite Backup API + blob store, zapisuje poprzedni
   digest i potwierdza możliwość odczytu kopii;
5. uruchamia migracje forward oraz preflight nowego obrazu na odizolowanej
   kopii danych;
6. pobiera obraz po digescie;
7. renderuje i waliduje Compose;
8. odtwarza aplikację przez Compose CLI;
9. czeka na liveness i readiness;
10. wykonuje API smoke i test z klientów Android oraz Linux/Flatpak;
11. po błędzie przywraca poprzedni digest razem z kompatybilną kopią DB i
    blobów.

Nie stosujemy Watchtower, ruchomych tagów, `latest`, automatycznych migracji
bez backupu ani samoczynnej promocji profilu.

Stary obraz nigdy nie otwiera bazy po migracji, jeśli jego deklarowana macierz
kompatybilności nie obejmuje nowego schematu. Jeżeli rollback kodu wymaga
rollbacku danych, kontener pozostaje zatrzymany do czasu odtworzenia spójnego
zestawu DB + bloby. Katalog `rollback-cache` skraca tę operację, ale nie
zastępuje backupu poza NAS.

### 10.5 Kontrakt API i brama ekspozycji

Poniższe zasoby są kontraktem docelowym, a nie twierdzeniem, że wszystkie są
już zaimplementowane:

```text
Istniejące MVP:
POST /v1/pair
POST /v1/devices/heartbeat
POST /v1/revisions
POST /v1/channels/{channel}/candidates
POST /v1/channels/{channel}/assignments
POST /v1/channels/{channel}/promote
POST /v1/reports
GET  /v1/enrollments/{enrollment_id}/assignment?channel={channel}
GET  /v1/enrollments/{enrollment_id}/revisions/{revision_id}
GET  /health

Docelowe przed 6B:
POST /v1/channels/{channel}/rollback
GET  /v1/blobs/{sha256}
GET  /ready
```

Istniejący serwer jest jawnie oznaczony jako loopback development. Podpisuje
i weryfikuje dokumenty domenowe, lecz zapisy revision/candidate/assignment/
promote nie mają jeszcze kompletnego uwierzytelnienia aktora i egzekwowania
roli na warstwie HTTP. Dlatego nie są gotowe do wystawienia przez reverse
proxy.

Docelowo `/health` pozostaje liveness i poza `status/mode` zwraca identyfikator
serwisu, wersję API oraz build. `/ready` sprawdza otwarcie DB, wspieraną wersję
schematu, dostępność blob store i poprawny rejestr kluczy. Metadane wersji
serwera, API, schematu i buildu pochodzą z jednego kontraktu; numer wersji nie
jest duplikowany ręcznie między modułami.

Przed 6B publish, assignment, promote, rollback, revocation i zarządzanie
rolami wymagają uwierzytelnienia, właściwej roli oraz proof-of-possession.
Podpis obejmuje cały kanoniczny dokument operacji, co najmniej actor,
operation, channel, revision, expected generation, next generation,
idempotency key i expiry. Serwer ponownie sprawdza rolę, replay, CAS oraz
zgodność wszystkich pól z podpisem.

Do czasu wdrożenia tej bramy reverse proxy nie wystawia operacji
administracyjnych. Dopuszczalny jest jedynie izolowany smoke 6A z syntetycznym
rejestrem i bez danych produkcyjnych; jego endpoint nie jest osiągalny z LAN.

Trwałe dane są montowane z dedykowanego udziału QNAP. Nic ważnego nie jest
przechowywane wewnątrz warstwy kontenera ani katalogu QPKG.

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

Docelowo ten sam deterministyczny ZIP dodatku ma działać na Androidzie i w
Flatpak Kodi; jest to brama kwalifikacyjna, a nie obecnie potwierdzony fakt.
Heartbeat raportuje obserwowane platformę, listę ABI, Kodi major i wersję
klienta. Nie wysyła loginu, home, endpointu SSH, `physical_host_id` ani
`principal_id`. Administracyjne target tags są wiązane z enrollmentem po
stronie serwera i podpisywane w assignment.

Na NUC każda sesja użytkownika ma własny `special://profile`, dlatego
instalacja dodatku, pairing i stan klienta są wykonywane osobno dla kont.
Hostowy bootstrap może umieścić dokładny, sprawdzony hash ZIP repozytorium w
kontrolowanym inboxie właściwego użytkownika. Instalacja odbywa się wyłącznie
przez wspierane UI/API Kodi w jego sesji graficznej. Jeżeli kwalifikacja nie
znajdzie bezpiecznej ścieżki bez UI, narzędzie zwraca
`BOOTSTRAP_REQUIRES_USER` z instrukcją „Install from ZIP”. Nie rozpakowuje kodu
do `addons/` i nie modyfikuje `Addons*.db`.

Dalsze instalacje i aktualizacje dodatków wykonuje Kodi przez
`repository.mwodevelop`. Narzędzie nie uruchamia `flatpak update`, nie
modyfikuje systemowej instalacji `tv.kodi.Kodi`, nie zakłada dostępu sesji GUI
z SSH i nie zapisuje do katalogu drugiego użytkownika.

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
- zmiany `host_only` są raportowane i przekazywane dispatcherowi hosta, który
  wybiera ADB/Android albo SSH+Flatpak lifecycle;
- rollback kodu dodatku nie jest częścią tej transakcji.

## 12. Kolejność synchronizacji klienta

Po starcie lub ręcznym wywołaniu:

1. Sprawdź pairing i ważność tokenu.
2. Wyślij heartbeat z `logical_device_id`, `enrollment_id`,
   `enrollment_generation`, obserwowanym modelem, listą ABI, wersją Kodi i
   wersją dodatku. Nie używaj self-reportu jako autoryzacji lub selektora.
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
16. Zapisz `next_start` jako pending; klient nie wymusza restartu platformy w
    MVP.
17. Zmiany `host_only` pokaż jako niezastosowane.
18. Zweryfikuj aktywną skórkę, dodatki i podstawowe JSON-RPC.
19. Wyślij raport sukcesu albo wykonaj kompensacyjny rollback konfiguracji.

Każdy raport zawiera `assignment_kind: active|candidate`, exact revision i
podpis enrollmentu. Stan `APPLIED` oznacza zastosowanie assignmentu, a nie
globalną promocję rewizji do `active`.

Jeśli QNAP jest niedostępny, klient pozostawia lokalną konfigurację bez zmian i
próbuje ponownie z backoffem. Niedostępność serwera nie może blokować startu
Kodi.

Na Linux/Flatpak runtime sync odbywa się wewnątrz procesu Kodi tak samo jak na
Androidzie. SSH nie jest ścieżką okresowego synchronizowania plików; służy
wyłącznie do discovery, stagingu bootstrapu, kontrolowanego restore
zatrzymanego Kodi i E2E. Operacja hostowa identyfikuje UID oraz właściciela
procesu i odmawia mutacji, gdy Kodi danego konta działa. Nie zatrzymuje procesu
automatycznie i nigdy nie zatrzymuje sesji drugiego konta.

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
- polityka promocji działa na klasach kompatybilności, co najmniej:
  `android-emulator`, `android-tv:<abi-set>` i `linux-flatpak:x86_64`;
- wymagany zestaw klas i exact canary jest zamrażany w zdarzeniu candidate;
  warstwa specyficzna dla urządzenia dodaje to urządzenie do bramy;
- promocja wymaga jednego aktywnego, zakwalifikowanego raportu sukcesu z każdej
  wymaganej klasy. `nuc-alek` jest Linux canary, a `nuc-mwo` post-canary
  rollout; izolacja obu kont pozostaje osobnym obowiązkowym E2E;
- urządzenie offline nie zmienia po cichu bramy. Pominięcie wymaga jawnego,
  podpisanego i audytowanego waivera;
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

SSH do NUC jest wyłącznie kanałem administracyjnym hosta. Docelowo każde konto
ma osobny klucz bez hasła w command line, bez `sudo`, bez agent forwarding i z
weryfikacją host key przez osobny plik `known_hosts`. Prywatny rejestr
przechowuje wyłącznie referencje do osobnych plików klucza i `known_hosts`,
nie ich zawartość. Hasła przejściowe pozostają w niewersjonowanym `.env`; klucze
`NUC_PASS_MWO` i `NUC_PASS_ALEK` muszą być jednoznaczne i walidowane jako
różne wpisy konfiguracyjne, nawet jeżeli wartości byłyby takie same.

Bootstrap zaufania jest jawny. MVP używa lokalnej nazwy DNS i certyfikatu lub
CA rzeczywiście zaufanych przez `ssl.create_default_context()` w Pythonie/
OpenSSL uruchomionym wewnątrz Android Kodi oraz Flatpak Kodi. Test `curl` na
hoście NUC nie jest dowodem zaufania sandboxa. Pinning fingerprintu wymaga
osobnego etapu implementacji i negatywnych testów klienta; nie wolno opisywać
go jako istniejącej funkcji. `verify=False` i trwały plain HTTP są zabronione;
HTTP jest dozwolony tylko na loopback w testach.

Runbook 6B definiuje i testuje:

- stabilną lokalną nazwę DNS oraz rozwiązywanie jej ze wszystkich klientów;
- łańcuch certyfikatu zaufany przez Android oraz Flatpak Kodi i plan
  odnowienia;
- prywatny klucz TLS przechowywany wyłącznie przez QNAP reverse proxy;
- allowlistę LAN/VPN i firewall bez publicznego port-forwardingu;
- dostęp Sony zarówno z aktywnym Nord VPN z dozwolonym LAN, jak i bez VPN;
- alarm przed wygaśnięciem certyfikatu i test po jego odnowieniu.

Każda rewizja jest podpisana kluczem publishera przypisanym do kanału. Każde
zdarzenie promote/rollback jest podpisane osobnym kluczem promotera i zawiera
monotoniczną generację kanału. Klient przypina publiczne klucze podczas
kontrolowanego enrollmentu i sprawdza podpis, kanał, schema, policy digest oraz
generację przed pobraniem payloadu. SHA-256 blobów chroni integralność
transportu, ale sam nie zastępuje podpisu.

### 14.2 Sekrety

Klucz podpisujący enrollment z MVP nie jest kluczem szyfrowania sekretów.
Jego przenośna implementacja kryptograficzna na Kodi ARMv7/x86 jest bramą MVP,
ale nie wymaga sprzętowej ochrony Android Keystore. Na NUC klucz każdego
principala pozostaje w profilu dodatku należącym do jego konta systemowego i
nie jest kopiowany między kontami. Flatpak nie chroni go przed tym samym
użytkownikiem Unix ani administratorem hosta; granicą bezpieczeństwa jest konto
systemowe i kontrola dostępu hosta. Profil `service.mwodevelop.profilesync`,
jego stan, token, seed, journal i backup są bezwzględnie wykluczone ze
snapshotów użytkownika.

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
- dodatek odszyfrowuje lokalnie po kwalifikacji biblioteki na ARMv7 i x86;
- envelope dla `nuc-mwo` i `nuc-alek` są różne, nawet gdy oba endpointy
  otrzymują tę samą rewizję niesekretną.

Przed implementacją etapu 2 obowiązuje feasibility gate dla bezpiecznego
przechowywania encryption key na Kodi/Android i Kodi/Flatpak. Spike sprawdza
Android Keystore lub równoważny mechanizm oraz magazyn per-user na Linuksie,
trwałość po restarcie, zachowanie po reinstalacji, revocation, ARMv7/x86,
separację kont NUC oraz gwarancję, że klucz nie trafia do snapshotu.
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
| NUC host bootstrap/restore | wyłącznie ręcznie | SSH jako dokładny użytkownik |
| NUC runtime sync | start Kodi / co 6 h | dodatek -> QNAP, bez SSH |
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

1. Dodać schema 1 `manifests/devices.schema.json`, przykład, prywatny registry
   i `tools/kodi_devices.py`. **Zrealizowane dla ADB.**
2. Zmigrować `kodi-reinstall.json` do `logical_device_id`.
   **Zrealizowane dla obecnych urządzeń Android.**
3. Podnieść registry do schema 2 z `physical_host_id`, `principal_id`,
   `platform` i rozłącznym transportem ADB/SSH. **Zrealizowane.**
4. Dodać loader schema 1 i 2, normalizację do modelu wewnętrznego v2 oraz
   idempotentną migrację z backupem, atomowym zapisem i porównaniem resolve
   istniejących Androidów. Zapisywać wyłącznie schema 2. **Zrealizowane.**
5. Dodać `bedroom-tv` jako consumera Android z oczekiwanym modelem
   `Google TV Streamer`, codename `kirkwood`, Kodi major 21 i osobnym
   enrollmentem. **Registry i read-only lifecycle inventory zrealizowane;
   enrollment pozostaje.**
6. Dodać `nuc-mwo` oraz `nuc-alek` jako consumerów ze wspólnym
   `physical_host_id: nuc-host`.
7. Dla Bedroom TV wykryć `ro.product.cpu.abilist` oraz ABI APK; nie kodować
   pojedynczego `armeabi-v7a` jako założenia. **Zrealizowane.**
8. Zachować walidację tożsamości hosta, konta, canonical home/data root, listy
   ABI i wersji przed każdą mutacją.
9. Do czasu dispatchera Android-only reinstall ma zwracać jawny
   `UNSUPPORTED_PLATFORM` dla Linux.

### Etap 1B: transport Linux/Flatpak i bootstrap NUC

1. Poprawić prywatny env: drugi `NUC_PASS_MWO` przemianować na
   `NUC_PASS_ALEK`; walidator ma odrzucać brakujące i zduplikowane nazwy.
   **Zrealizowane lokalnie; plik pozostaje niewersjonowany.**
2. Dodać neutralne `AdbTransport` i `SshTransport` oraz osobne lifecycle
   `AndroidKodiLifecycle` i `FlatpakKodiLifecycle`. **Zrealizowane.**
3. Ograniczyć transport do zweryfikowanych operacji I/O; nie udostępniać
   dowolnego shell `run`, automatycznego stop ani nieograniczonych ścieżek.
   **Zrealizowane dla read-only inventory.**
4. Dodać dispatcher `probe`, `inventory`, `bootstrap`, `backup`, `restore` i
   `verify`, zawsze dla jednego jawnego `logical_device_id`.
5. Wymusić OpenSSH `BatchMode=yes`, przypięty host key i machine fingerprint,
   osobny klucz per konto, brak `sudo`/agent forwarding, timeouty oraz zakaz
   operacji poza home wskazanego UID. **Kontrakt i testy fake SSH
   zrealizowane; enrollment kluczy na NUC czeka na dostępność hosta.**
6. Ustalać UID i home przez zweryfikowane konto oraz `getent passwd`, bez
   rozwijania `~`. Wewnątrz Flatpaka wykryć rzeczywiste
   `special://home`/`special://profile`, a potem canonicalizować ścieżkę,
   wykonać `lstat` i odrzucić symlink escape lub obcego ownera.
7. Wykrywać systemową instalację `tv.kodi.Kodi`, wersję, ABI, uprawnienia
   sandboxa, uruchomiony proces i dodatkowe profile wewnętrzne Kodi. Domyślny
   wpis Master User nie oznacza sam w sobie unsupported multi-profile.
8. Dodać tryb `--dry-run` pokazujący zakres bez nazw sekretów i wartości
   ustawień.
9. Utworzyć osobny pre-bootstrap backup niesekretnych metadanych obu kont;
   istniejące sekrety MWO pozostawić wyłącznie lokalnie.
10. Umieścić hash-verified ZIP repo w inboxie właściwego konta i zainstalować
   go przez wspierane UI/API Kodi. Gdy nie ma bezpiecznej automatyzacji sesji
   GUI, zakończyć `BOOTSTRAP_REQUIRES_USER`; nie pisać do `addons/` ani DB.
11. Wykonać inventory origin istniejących dodatków `nuc-mwo`. Migracja origin
    odbywa się dopiero po backupie i zgodzie, przez wspierany uninstall/
    install/update Kodi; `nuc-alek` pozostaje pierwszym czystym canary.
12. Zainstalować `service.mwodevelop.profilesync` osobno na obu kontach przez
    `repository.mwodevelop`, bez kopiowania katalogów kodu.
13. Sparować oba klienty jako niezależne enrollmenty; bootstrap jednego konta
    nie może odczytać ani zmienić tokenu drugiego.
14. Pozostawić systemowy Flatpak Kodi poza zakresem mutacji. Niezgodna wersja
    kończy się `HOST_UPDATE_REQUIRED`, nie próbą aktualizacji hosta.

### Etap 2: polityka v2 i revision schema 3

1. Rozszerzyć istniejącą politykę o klasy danych.
2. Zachować read compatibility istniejącej płaskiej revision schema 2.
3. Zdefiniować revision schema 3 z portable base, uporządkowanymi layers,
   ograniczeniami zgodności i podpisanym wyborem przez administracyjne tags.
4. Oddzielić routine profile od disaster-recovery snapshot.
5. Dodać diff logiczny bez ujawniania wartości sekretów.
6. Dodać semantyczne adaptery per setting z default-deny.
7. Dodać ownership, tombstones i deterministyczną kolejność overlayów.
8. Dodać eksport deterministyczny i content-addressed blobs.
9. Zachować zgodność odczytu snapshotów schema 1 jako osobnego scope
   disaster recovery.
10. Zablokować platform overlay apply na Linux do wdrożenia schema 3; schema 2
    może dostarczać tylko portable common subset.

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
11. Dodać migrację DB/API administracyjnie wiążącą compatibility class i
    opaque `target_tags` z enrollmentem. Self-report heartbeat pozostaje
    obserwacją, nie podstawą assignmentu.

### Etap 4: dodatek Kodi

1. Utworzyć `service.mwodevelop.profilesync`. **Zrealizowane.**
2. Dodać pairing i heartbeat. **Zrealizowane.**
3. Dodać weryfikację podpisów i generacji kanału; TLS pozostaje bramą
   wdrożenia QNAP. **Podpisy i generacja zrealizowane.**
4. Dodać active/canary assignment, check/download/staging.
   **Check read-only zrealizowany; download/staging pozostają.**
5. Dodać zarządzanie wymaganymi dodatkami przez repo Kodi.
6. Dodać jawnie włączane adaptery dla ustawień niesekretnych.
7. Dodać crash-resilient journal, pending next-start i kwarantannę.
8. Dodać health report i kompensacyjny rollback konfiguracji.
9. Dodać admin CLI poza Kodi.
10. Opublikować wyłącznie w `testing`. **Zrealizowane dla wersji 0.1.5.**
11. Zakwalifikować klienta w sandboxie `tv.kodi.Kodi` na `x86_64`: sieć,
    storage, bibliotekę kryptograficzną, journal i restart dodatku.
12. Dodać do heartbeat obserwowane platformę, Kodi major i listę ABI bez
    username, home, endpointu SSH, host/principal ID. Klient nie wybiera nimi
    własnej klasy ani warstwy.
13. Potwierdzić osobny stan `special://profile/addon_data` dla `nuc-mwo` i
    `nuc-alek`.
14. Odrzucać wewnętrzny multi-profile jako `UNSUPPORTED_MULTI_PROFILE`, ale
    akceptować wiele kont systemowych jako osobne procesy/instancje.
15. Zakwalifikować trust chain przez prawdziwe `ssl.create_default_context()`
    wewnątrz Android Kodi i Flatpak Kodi; test hostowego `curl` nie wystarcza.

Kontrolowany test 2026-07-27 potwierdził na BlueStacks i Sony TV:

- instalację wersji 0.1.5 z `repository.mwodevelop.testing`;
- jednorazowy pairing bez wynoszenia tokenu i klucza z procesu Kodi;
- uwierzytelniony heartbeat;
- weryfikację podpisanego przypisania candidate;
- brak `apply` w trybie read-only.

Odtwarzalny przebieg i zredagowany wynik:

```bash
PYTHONPATH=. .venv/bin/python \
  tests/e2e/profile_sync_addon_device.py \
  --device bluestacks1 \
  --device sony-tv \
  --result \
  docs/e2e-results/2026-07-27-profile-sync-addon-0.1.5-read-only.json
```

### Etap 5: E2E ustawień niesekretnych

1. BlueStacks jako publisher.
2. Czysta dodatkowa instancja BlueStacks jako consumer.
3. Sony jako consumer.
4. Candidate przypięty tylko do czystego BlueStacks i apply.
5. Po sukcesie exact candidate przypięty tylko do Sony i apply.
6. Zbudować i opublikować exact bytes wyłącznie do `testing`, zanim rozpocznie
   się urządzeniowy canary.
7. Zamrozić w kandydacie wymagane klasy kompatybilności i canary. Promocja
   następuje dopiero po raportach wymaganych klas albo podpisanym waiverze.
8. Potwierdzenie aktywnej skórki lub jawnego `host_only`.
9. Potwierdzenie repo origin dodatków.
10. Deterministyczny test adapterów z lokalnym fake add-on/API.
11. Umbrella search bez credentiali albo z oczekiwanym brakiem autoryzacji.
12. RD playback wyłącznie na consumerze pre-provisioned hostowym restore i
    oznaczony jako test zależny od zewnętrznej usługi.
13. WatchNixtoons2 katalog i playback jako uzupełniający live smoke.
14. Uszkodzony digest/podpis/path: zero mutacji.
15. Poprawny technicznie, lecz wadliwy profil: health failure i rollback.
16. Test niedostępnego QNAP i VPN bez uszkodzenia Kodi.
17. Dodać Bedroom TV jako trzeci consumer Android, wykonać read-only pairing,
    exact candidate apply, rollback i test niedostępnego QNAP.
18. Wykonać read-only discovery i dry-run osobno dla `nuc-mwo` oraz
    `nuc-alek`.
19. Użyć czystszego `nuc-alek` jako canary klasy Linux/Flatpak.
20. Po sukcesie przypiąć ten sam exact candidate do `nuc-mwo` jako
    post-canary rollout, zachowując
    istniejące niezarządzane ustawienia i lokalne sekrety.
21. Potwierdzić, że repo/addon origin, skórka i portable settings są poprawne
    na obu kontach, a synchronizator nie kopiuje ani bezpośrednio nie
    modyfikuje cache, DB i Thumbnails.
22. Zmienić niesekretne ustawienie wyłącznie na `nuc-alek` i potwierdzić zero
    mutacji oraz zero odczytu credentiali `nuc-mwo`.
23. Uruchomić Kodi jednocześnie w dwóch sesjach albo zasymulować blokadę i
    potwierdzić, że hostowa operacja jednego konta nie zatrzymuje drugiego.
24. Potwierdzić start/cykliczny pull bez aktywnego SSH; runtime zależy tylko od
    sieci Kodi -> QNAP.
25. Zapisać osobne zredagowane raporty E2E zawierające platformę, exact
    revision i enrollment, ale nie username, home, IP ani sekrety.
26. Po przejściu wymaganych klas wykonać obserwację, ręczną promocję profilu
    do `active`, a dopiero potem startowy pull i apply konsumentów.

### Etap 6: QNAP

#### Etap 6A: implementacja i nietrwały smoke

Brama wejścia:

- po restarcie potwierdzone SSH, daemon Container Station, Compose CLI,
  `armv7l`, wolne miejsce i aktualny `/proc/mdstat`;
- opublikowany i sprawdzony digest GHCR zawierający `linux/arm/v7`;
- `docker compose config` przechodzi dla base + smoke override;
- automatyczna kontrola wyklucza produkcyjne ścieżki, nazwę projektu, port,
  key registry oraz politykę restartu;
- wszystkie dane, profile, tokeny i klucze są syntetyczne.
- dla bazowego smoke Android: istnieją schema 2 registry, zakwalifikowany
  dispatcher ADB/Android oraz read-only enrollmenty klientów Android;
- dla rozszerzonego rerunu NUC: zakończone są Etapy 1B i 2, zakwalifikowany
  klient Flatpak, administracyjne target tags i dwa osobne read-only
  enrollmenty. Brak gotowości NUC nie blokuje bazowego smoke infrastruktury.

Realizacja:

1. Dodać workflow publikujący zweryfikowany manifest
   `linux/amd64,linux/arm/v7`, zapisujący digest i wynik
   `buildx imagetools inspect`.
2. Dodać `compose.smoke.yaml`, `smoke.env.example` i walidację polityki
   Compose w CI.
3. Dodać skrypt hostowy `qnap_profile_sync.py` z operacjami `preflight`,
   `smoke-deploy`, `status`, `logs`, `verify`, `destroy-smoke`.
4. Renderować base + smoke override z osobnego, niewersjonowanego env i
   uruchamiać przez SSH jako project `qnap-profile-sync-smoke`.
5. Uruchomić smoke z `restart: "no"`, testowym regularnym plikiem key registry,
   osobnym portem i nietrwałą bazą.
6. Potwierdzić architekturę obrazu, `/health`, `/ready`, wersję schematu,
   migrację SQLite, ręczny restart procesu oraz brak sekretów w inspect/logach.
7. Utworzyć SSH local forward do loopback QNAP, następnie osobne `adb reverse`
   dla BlueStacks, Sony i Bedroom TV. Każdy tunel ma własny identyfikator,
   `ExitOnForwardFailure`, loopback-only bind oraz pewny cleanup;
   potwierdzić dokładny identyfikator smoke API na każdym kliencie.
8. Wykonać bazowy pairing, heartbeat, signed revision download i read-only
   check z BlueStacks, Sony i Bedroom TV przez `http://127.0.0.1` klienta.
9. Po bramie NUC powtórzyć smoke z osobnym SSH remote forward/control socket
   i lokalnym portem dla każdego konta albo udokumentowanym, izolowanym relay.
   Potwierdzić `nuc-mwo` i `nuc-alek` osobno; tunel jednego konta nie może
   odziedziczyć poświadczeń drugiego.
10. Zasymulować niedostępność QNAP i potwierdzić brak mutacji Kodi.
11. Zapisać zredagowany raport E2E w `docs/e2e-results`.
12. Usunąć reguły `adb reverse`, local/remote forward SSH, control sockety,
    projekt Compose,
    testowe dane, pliki env i registry.

Brama wyjścia:

- nie pozostał kontener, sieć, volume, autostart, tunel ani katalog smoke;
- raport zawiera digest, platformę, renderowany policy summary i wyniki
  wszystkich klientów objętych danym przebiegiem bez sekretów;
- wynik jest oznaczony jako test loopback, a nie walidacja TLS lub produkcji.

Etap 6A można wykonać przy zdegradowanym RAID, ponieważ nie przechowuje
istotnych ani unikalnych danych. Każde wykrycie zapisu do ścieżki produkcyjnej
natychmiast przerywa test.

#### Etap 6B: produkcyjna aplikacja Container Station

Brama wejścia:

- Etap 0 zakończony: RAID `[UU]`, zaszyfrowany backup poza NAS i udany restore
  niewrażliwego pliku;
- 6A zakończony bez pozostałości;
- API publish/admin ma role, proof-of-possession, pełne podpisane dokumenty,
  ochronę replay/idempotency i testy negatywne;
- istnieją wersjonowane migracje, `/ready`, Backup API, spójny backup DB +
  bloby, macierz kompatybilności schematu oraz przećwiczony rollback;
- runbook DNS/TLS/firewall/odnowienia przechodzi na BlueStacks, Sony, Bedroom
  TV i obu klientach NUC.

Realizacja:

1. Utworzyć udział i strukturę `/share/ProfileSync`.
2. Wybrać niekolidujący dedykowany UID/GID, utworzyć katalogi i minimalne ACL,
   zweryfikować zapis jako ten użytkownik oraz regularny plik key registry.
3. Wygenerować produkcyjny key registry i publiczny bootstrap zaufania poza
   kontenerem; prywatny klucz TLS pozostawić w QNAP reverse proxy.
4. Wdrożyć project `qnap-profile-sync` przez Compose CLI po SSH z przypiętym
   digestem; GUI Container Station pozostawić tylko do obserwacji.
5. Skonfigurować QNAP reverse proxy: HTTPS z LAN/VPN do loopback kontenera,
   firewall i monitoring certyfikatu.
6. Potwierdzić brak bezpośrednio wystawionego portu API poza loopback i brak
   nieautoryzowanych operacji administracyjnych.
7. Uruchomić migrację, liveness, readiness, pairing i read-only E2E wszystkich
   pięciu klientów: BlueStacks, Sony, Bedroom TV, `nuc-mwo` i `nuc-alek`.
8. Skonfigurować `restart: unless-stopped`, wykonać pełny reboot QNAP i
   potwierdzić dokładnie jeden project oraz brak driftu Compose.
9. Skonfigurować snapshoty QTS, retencję aplikacyjną, rollback cache i
   zaszyfrowany backup poza QNAP.
10. Wykonać restore drill serwera na oddzielnym katalogu danych i zweryfikować
    spójność DB + blobów.
11. Zweryfikować aktualizację do nowego digestu, forward migration oraz
    rollback obrazu razem z właściwą wersją DB + blobów.
12. Dopiero po canary dopuścić QNAP jako źródło profilu `active`.

Brama wyjścia:

- reboot, update, restore i rollback mają zredagowane raporty;
- wszystkie pięć instancji przechodzi test HTTPS i odrzuca błędny
  certyfikat;
- nie ma drugiej aplikacji zarządzanej równolegle z GUI ani ruchomego tagu;
- backup poza QNAP jest świeższy niż ostatnia promocja danych produkcyjnych.

### Etap 7: zaszyfrowane sekrety

1. Wybrać bibliotekę po spike na ARMv7/x86.
2. Zakwalifikować bezpieczne przechowywanie klucza na Androidzie oraz osobno
   w sandboxie Flatpak każdego konta Linux.
3. Zaimplementować device keys i envelope encryption.
4. Dodać rotację i unieważnianie.
5. Dodać testy braku plaintextu w stagingu, journalu, backupie i logach.
6. Dodać ręczny restore sekretów w dodatku.
7. Wykonać autonomiczny RD restore/playback E2E bez przenoszenia credentiali
   między principalami NUC.
8. Dopiero po stabilizacji rozważyć automatyczny restore.

### Etap 8: stabilizacja i wydanie

1. Audyt bezpieczeństwa.
2. Niezależne review implementacji względem niniejszego planu.
3. Pełny lokalny E2E.
4. CI bez sekretów.
5. Deterministyczny build exact bytes.
6. Publikacja do testing.
7. Canary klasy Android emulator na BlueStacks.
8. Canary klasy Android TV na urządzeniu odpowiadającym faktycznej liście ABI;
   Bedroom TV jest dodatkowym canary, gdy ma inną klasę albo device overlay.
9. Canary klasy Linux Flatpak x86_64 na `nuc-alek`.
10. Obowiązkowy E2E izolacji i post-canary rollout na `nuc-mwo`.
11. Okres obserwacji.
12. Ręczna promocja tych samych bajtów do stable.

## 17. Testy

### 17.1 Unit

- walidacja rejestru urządzeń;
- bezpieczne rozwiązywanie `logical_device_id`;
- loader registry schema 1/2, normalizacja v2 oraz idempotentna, atomowa
  migracja 1 -> 2 z backupem i bez zmiany istniejących ID/resolve;
- osobne factory neutralnego transportu ADB/SSH i lifecycle Android/Flatpak;
- Android-only reinstall odrzuca Linux przed uruchomieniem transportu;
- canonicalizacja Flatpak data root, owner oraz ochrona przed symlink escape;
- rozdzielenie `physical_host_id`, `principal_id` i enrollmentu;
- unikalność `(physical_host_id, principal_id)` i jedna aktywna generacja
  enrollmentu per `logical_device_id`;
- walidacja unikalnych referencji credentiali bez odczytu ich wartości;
- klasyfikacja plików polityki;
- deterministyczny manifest;
- golden vectors kanonikalizacji i podpisów;
- podpisane assignmenty i raporty enrollmentu;
- SHA-256 i inventory;
- osobne CAS publish/promote/rollback i idempotency keys;
- role i tokeny;
- default-deny per setting, ownership i tombstones;
- deterministyczne overlaye;
- revision schema 2 read compatibility, schema 3 layers i odmowa nieznanego
  selektora;
- target tags z enrollmentu wybierają warstwę, self-report heartbeat nie;
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
- publikacja manifestu GHCR, zapis digestu i `imagetools inspect` dla
  `linux/amd64` oraz `linux/arm/v7`;
- `docker compose config` dla produkcji oraz base + smoke override;
- statyczna polityka Compose: digest, loopback, read-only, cap-drop,
  `create_host_path: false`, brak stałego `container_name` i brak autostartu
  smoke;
- runtime smoke Compose na katalogach tymczasowych z cleanup assertion;
- runtime smoke na rzeczywistym QNAP ARMv7;
- rozróżnienie `/health` liveness od `/ready` DB/schema/key-registry;
- upgrade schematu na kopii i rollback obrazu razem z DB + blobami;
- odtworzenie danych serwera z backupu poza NAS;
- fake SSH transport + Flatpak lifecycle inventory/bootstrap bez dostępu do
  home innego konta i bez arbitrary shell/path;
- blokada per `(physical_host_id, principal_id)` dla profilu i host-wide tylko
  dla jawnie współdzielonej operacji;
- OpenSSH pinned known_hosts, `BatchMode`, brak sudo/agent forwarding i
  negatywny test zmiany host key;
- bootstrap zwraca `BOOTSTRAP_REQUIRES_USER` zamiast zapisu do addons/DB, gdy
  nie ma zakwalifikowanego Kodi API/UI;
- ten sam klient ZIP i golden crypto vectors na Flatpak `x86_64`;
- TLS sprawdzony przez Python/OpenSSL wewnątrz Android Kodi oraz Flatpak Kodi;
- brak zależności runtime sync od dostępności SSH;

### 17.3 Device E2E

- BlueStacks publisher -> BlueStacks consumer;
- BlueStacks publisher -> Sony consumer;
- BlueStacks publisher -> Bedroom TV consumer;
- BlueStacks publisher -> `nuc-alek` consumer;
- BlueStacks publisher -> `nuc-mwo` consumer;
- izolacja `nuc-mwo` <-> `nuc-alek` na wspólnym hoście;
- Flatpak system app pozostaje niezmieniona, dodatki są per konto;
- bootstrap/reinstall jednego konta nie zatrzymuje Kodi drugiego konta;
- wewnętrzny dodatkowy profil Kodi kończy się
  `UNSUPPORTED_MULTI_PROFILE` bez mutacji;
- exact candidate pin bez zmiany globalnego active;
- start Kodi z dostępnym QNAP;
- start Kodi bez QNAP;
- start Sony z Nord VPN oraz z niedostępnym route do LAN;
- zmiana aktywnej rewizji;
- pending next-start i zmiana `host_only`;
- rollback po health check failure;
- corrupt/signature/path failure bez żadnej mutacji;
- repo origin `repository.mwodevelop`;
- synchronizator nie kopiuje ani bezpośrednio nie modyfikuje cache/DB/
  Thumbnails; zmiany wykonane samodzielnie przez Kodi są dozwolone;
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
8. Dodać Bedroom TV po sukcesie Sony i zachować osobny enrollment.
9. Zmigrować registry do schema 2 i potwierdzić byte-equivalent resolve
   istniejących endpointów Android, zachowując reader schema 1.
10. Poprawić prywatne nazwy sekretów NUC, ręcznie zainstalować osobne klucze
    SSH i skonfigurować przypięte host keys/machine identity.
11. Dodać `nuc-alek` jako czysty Linux canary, wykonać bootstrap oraz pairing.
    Do revision schema 3 pozostaje read-only/portable common subset.
12. Wdrożyć revision schema 3 i administracyjne target tags, a następnie
    wykonać niesekretny canary apply na `nuc-alek`.
13. Dopiero po sukcesie `nuc-alek` wykonać dry-run oraz bootstrap `nuc-mwo`,
    zinwentaryzować origin i zachować istniejące niezarządzane ustawienia oraz
    sekrety.
14. Potwierdzić niezależne enrollmenty i brak cross-account diff.
15. Zachować hostowy restore ADB/SSH jako break-glass path.
16. Po uruchomieniu szyfrowanych sekretów wykonać pełny restore drill osobno
    dla każdego principala.
17. Dopiero po dwóch udanych restore drillach rozważyć ograniczenie starych
    lokalnych snapshotów.

## 20. Ryzyka i zabezpieczenia

| Ryzyko | Zabezpieczenie |
|---|---|
| zdegradowany RAID QNAP | blocker produkcji 6B; tylko izolowany i nietrwały smoke 6A |
| utrata QNAP | lokalna konfiguracja działa dalej, host snapshot pozostaje |
| smoke zapisuje stan produkcyjny | osobny project/port/path/key registry, `restart: no`, policy gate i cleanup |
| dwa control plane Container Station | wyłącznie Compose CLI po SSH, GUI tylko do obserwacji |
| bind mount tworzy zły katalog | preflight ścieżek/UID/ACL i `create_host_path: false` |
| zły profil mastera | candidate, ręczna promocja i rollback |
| różne wersje dodatków | najpierw update przez repo, potem apply ustawień |
| kod pozostaje nowszy po rollbacku profilu | kompatybilne constraints i jawny status `CODE_ADVANCED` |
| różne ABI/Kodi | compatibility gate w manifeście |
| heartbeat fałszuje klasę | administracyjne target tags w enrollmencie; self-report tylko obserwacyjny |
| Android scoped storage | zapis wewnątrz procesu Kodi |
| Flatpak ma inny data root | discovery app ID, canonical path i owner gate |
| dwa konta NUC współdzielą host | opaque principal w prywatnym inventory, osobne logical/enrollment/token/journal |
| wyciek danych między kontami | logical-device scoped policy, osobne procesy i cross-account negative E2E |
| SSH zapisuje do złego home | credential ref, user/owner check, brak sudo i path containment |
| zmieniony host pod adresem NUC | pinned host key i machine fingerprint; model/hostname/IP nie wystarczają |
| hostowa operacja zatrzymuje oba Kodi | blokada i lifecycle per konto, drugi proces pozostaje nietknięty |
| Profile Sync aktualizuje Flatpak | twardy zakaz; `tv.kodi.Kodi` aktualizuje wyłącznie host admin |
| zduplikowana nazwa sekretu `.env` | fail-fast config validation i osobne nazwy MWO/ALEK |
| bootstrap omija Kodi | tylko hash-verified ZIP przez wspierane UI/API albo `BOOTSTRAP_REQUIRES_USER` |
| obcy origin dodatku na `nuc-mwo` | inventory, backup i migracja przez Kodi; brak kopiowania/takeover |
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
| niespójna kopia SQLite/blobów | Backup API, skoordynowany blob snapshot i restore drill |
| migracja uniemożliwia rollback obrazu | schema compatibility matrix i rollback spójnego DB + blob set |
| nieautoryzowana operacja admin | role, PoP, podpis całego dokumentu, replay protection i deny w reverse proxy |
| wygasły lub niezaufany TLS | lokalny DNS, renewal runbook, alert i test w runtime Android Kodi oraz Flatpak Kodi |

## 21. Kryteria akceptacji

Projekt jest ukończony dopiero, gdy:

1. wszystkie urządzenia mają stabilne `logical_device_id`;
2. adresy są w `.kodi-private/devices.json`, a nie w publicznym repo;
3. `kodi-reinstall.json` używa `logical_device_id`;
4. QNAP RAID jest zdrowy i istnieje backup poza QNAP;
5. produkcyjny serwer działa po restarcie QNAP i jest zarządzany wyłącznie
   przez Compose CLI po SSH;
6. nowy consumer może zostać sparowany bez konta administratora NAS;
7. każdy klient ma własne `enrollment_id`, generację i klucz podpisujący, a
   restore nie klonuje jego enrollmentu;
8. rewizje, assignmenty, raporty i zmiany kanału mają poprawne podpisy;
9. kanał ma monotoniczną generację i zweryfikowany checkpoint;
10. exact candidate przechodzi canary bez zmiany globalnego active;
11. profil jest wersjonowany i możliwy do cofnięcia;
12. klient pozostaje sprawny bez QNAP;
13. dodatki zachowują origin repozytorium;
14. synchronizator nie kopiuje ani bezpośrednio nie modyfikuje cache i baz;
15. synchronizator nie tworzy dodatkowego plaintextu sekretów w Git, obrazie,
    QNAP, stagingu, journalu, backupie, logach ani raportach;
16. routine sync przechodzi E2E na BlueStacks, Sony, Bedroom TV, `nuc-alek`
    i `nuc-mwo`;
17. corrupt digest, podpis lub ścieżka powoduje zero mutacji;
18. health failure po apply powoduje kompensacyjny rollback lub jawny
    `ROLLBACK_REQUIRES_HOST`;
19. routine E2E nie zależy od synchronizacji credentiali RD;
20. pełny restore sekretów przechodzi osobny E2E;
21. istniejący upstream/testing/stable pipeline nadal przechodzi bez zmian
    semantycznych;
22. obraz wdrożeniowy ma zweryfikowany manifest ARMv7 i jest przypięty po
    digescie;
23. smoke i produkcja mają odrębne project/path/port/key registry, a cleanup
    smoke nie pozostawia kontenera, sieci, danych ani tunelu;
24. endpointy administracyjne wymagają roli, PoP i podpisu całej operacji;
25. `/ready` potwierdza zgodność DB, schematu, blob store i key registry;
26. update, backup i rollback obejmują zgodny zestaw obrazu, DB oraz blobów;
27. HTTPS, DNS, firewall i odnowienie certyfikatu przechodzą test wewnątrz
    runtime Kodi na wymaganych klasach Android oraz obu klientach NUC;
28. `nuc-mwo` i `nuc-alek` mają wspólny `physical_host_id`, ale osobne
    logical/opaque-principal/enrollment/token/key/journal;
29. registry schema 2 rozwiązuje neutralny ADB lub SSH oraz właściwy lifecycle
    Android/Flatpak i zachowuje zgodność odczytu/migracji Androida;
30. bootstrap oraz routine E2E przechodzą osobno na obu kontach NUC;
31. test negatywny potwierdza brak odczytu i mutacji danych drugiego konta;
32. systemowy `tv.kodi.Kodi` nie jest mutowany, a synchronizator nie kopiuje
    ani bezpośrednio nie modyfikuje cache/DB/Thumbnails;
33. runtime pull na NUC działa bez aktywnego SSH, a niedostępny QNAP nie
    blokuje startu Kodi;
34. wewnętrzny multi-profile jest odrzucany bez mutacji;
35. revision schema 3 reprezentuje podpisane warstwy, a reader nadal
    bezpiecznie obsługuje schema 2;
36. administracyjne target tags, nie self-report heartbeat, wybierają klasy i
    warstwy;
37. wydanie stable następuje dopiero po publikacji testing, E2E klas i okresie
    obserwacji.

## 22. Kolejność zależności

```text
registry reader 1/2 -> atomic registry v2 migration
                              |
                              v
             neutral transport (ADB/SSH)
                              |
                              v
        platform lifecycle (Android/Flatpak)
                              |
                              +---- per-account bootstrap/enrollment
                              |
policy v2 -> revision schema 3 + server target tags
                              |
                              v
                 addon unit/local qualification
                              |
                              v
                 deterministic build -> testing
                              |
                              v
              canary/E2E per compatibility class
                              |
                              v
               observation -> manual stable/active

naprawa RAID + backup -> QNAP production deployment
                                      |
                                      +---- non-secret E2E
                                                  |
                                                  v
                                           profile canary
                                                  |
                                                  v
                                      manual profile active

QNAP deployment + encryption feasibility -> encrypted secret sync
```

Najpierw powstaje kompatybilny registry v2, potem neutralny transport i
lifecycle. Apply warstw platformowych czeka na revision schema 3 i serwerowe
target tags. Publikacja `testing` poprzedza każdy urządzeniowy canary; stable
następuje po E2E i obserwacji. Naprawa RAID może biec równolegle, ale pozostaje
twardą bramą wyłącznie dla produkcyjnego wdrożenia QNAP.
