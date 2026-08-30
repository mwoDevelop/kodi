# Powtarzalne E2E

## Read-only QNAP Control Plane

Uruchom rzeczywisty przepływ między równorzędnymi checkoutami serwera Profile
Sync i Control Plane, z dwoma oddzielnymi CA, uwierzytelnieniem mTLS operatora,
odrzuceniem klienta bez certyfikatu i odrzuceniem mutacji:

```bash
.venv/bin/python tests/e2e/control_plane_readonly.py
```

Test korzysta wyłącznie z tymczasowych baz, portów i certyfikatów; nie łączy się z
produkcyjnym QNAP ani urządzeniami Kodi.

Uruchom z dowolnego katalogu:

```bash
/home/mwo/projects/kodi/tests/e2e/run.sh
```

Skrypt:

1. usuwa tylko `/home/mwo/projects/kodi/.e2e`;
2. buduje dwie kompletne migawki repozytorium;
3. porównuje je rekurencyjnie;
4. uruchamia tymczasowe lokalne repozytorium HTTP;
5. zaczyna się tylko od Umbrella i rozwiązuje rekurencyjnie MwoScrapers na podstawie
   wymaganych zależności Kodi;
6. ładuje rejestr dostawców zewnętrznych;
7. kompiluje izolowane pliki programu tłumaczącego downstream;
8. wykonuje testy struktury repozytorium, zależności, pochodzenia i bezpieczeństwa ZIP.

Formularz kontenera:

```bash
/home/mwo/projects/kodi/tests/e2e/run-docker.sh
```

Opakowanie kontenera wymaga działającego demona Docker. CI używa natywnego skryptu w
nowym programie uruchamiającym GitHub, który zapewnia tę samą właściwość czystego
systemu plików bez konieczności stosowania Docker-in-Docker.

## Oficjalny dodatek YouTube

Pełny rollout instaluje przypiętą, zakwalifikowaną wersję z
`repository.xbmc.org`, sprawdza origin oraz zależności i uruchamia wspólny adapter
konfiguracji wewnątrz Kodi. Sam adapter na Androidzie można zweryfikować poleceniem:

```bash
.venv/bin/python tools/kodi_youtube_configure.py \
  --serial 127.0.0.1:5555 \
  --references .env
```

Raport musi wskazywać `personal_api_configured: true` i poprawną publiczną sondę API.
`AUTHORIZATION_REQUIRED` jest oczekiwane przed ręcznym device flow, lecz nie jest
dowodem gotowości konta. Po logowaniu w GUI wymagane są: `ACCOUNT_READY`, wyszukiwanie,
subskrypcje, odtwarzanie, restart Kodi i urządzenia oraz drugi przebieg bez zmian.
Test wykonuje się najpierw na BlueStacks, następnie na X88 z aktywnym VPN. Wartości
kluczy, kod urządzenia, tokeny i wskazówka konta nie mogą trafić do raportu. Szczegółowy
runbook znajduje się w [dokumentacji YouTube](../../docs/youtube.md).
BlueStacks musi używać oficjalnego APK Kodi 21.3 ARM64; pakiet Kodi `x86` nie może
załadować oficjalnej binarnej zależności `inputstream.adaptive` i test ma wtedy
zakończyć się jawnym błędem ABI.

## BlueStacks1 / Kodi 21.3

Zbuduj `dist`, podłącz ADB do instancji `BlueStacks1`, a następnie przygotuj test
urządzenia do odzyskania:

```bash
python tests/e2e/bluestacks_e2e.py \
  --phase prepare \
  --adb /path/to/platform-tools/adb \
  --backup-dir .device-backups/bluestacks1-$(date +%Y%m%d-%H%M%S)
```

Czysty test zależności wymaga nieobecności Umbrella i MwoScrapers przed `prepare`;
skrypt rejestruje ten stan po utworzeniu kopii zapasowej istniejącego profilu.
Zainstaluj skopiowane repozytorium ZIP i tylko Umbrella za pośrednictwem własnego
menedżera dodatków Kodi, zgodnie z wydrukiem skryptu. Następnie sprawdź zainstalowane
identyfikatory, wersje, repozytorium (`origin` w bazie danych dodatku Kodi),
automatyczną instalację MwoScrapers i dziennik Kodi:

```bash
python tests/e2e/bluestacks_e2e.py \
  --phase verify \
  --adb /path/to/platform-tools/adb \
  --backup-dir .device-backups/bluestacks1-YYYYMMDD-HHMMSS \
  --result docs/e2e-results/bluestacks1.json
```

Domyślnie oczekiwane jest repozytorium testing. Aby skorzystać z kanału produkcyjnego,
przekaż `--expected-origin repository.mwodevelop` zarówno do `prepare`, jak i `verify`.
Spowoduje to również wybranie ZIP repozytorium stable i zakończy się niepowodzeniem,
jeśli którykolwiek komponent pozostanie podłączony do kanału testing.

Po kontrolowanym wyszukiwaniu Sintel, wyborze źródła, co najmniej 30 sekundach
odtwarzania i zatrzymaniu odtwarzacza Kodi, sprawdź potok multimediów na podstawie
zredagowanych, bezpiecznych znaczników dziennika:

```bash
python tests/e2e/bluestacks_e2e.py \
  --phase playback \
  --adb /path/to/platform-tools/adb \
  --backup-dir .device-backups/bluestacks1-YYYYMMDD-HHMMSS \
  --result docs/e2e-results/bluestacks1.json \
  --sources 5 \
  --observed-seconds 30
```

Ten celowy projekt trójfazowy uwzględnia pamięć masową o określonym zakresie Android i
testuje rzeczywistą ścieżkę repozytorium Kodi zamiast wstrzykiwać pliki do profilu Kodi.

Zweryfikuj publiczny adres URL źródła pliku za pomocą własnego katalogu HTTP Kodi i
silników ZIP:

```bash
python tests/e2e/kodi_http_source.py \
  --adb /home/mwo/android-sdk/platform-tools/adb \
  --serial emulator-5554
```

Sprawdzanie kończy się niepowodzeniem, chyba że Kodi wyświetli listę
`repository.mwodevelop-1.0.0.zip`, pobierze i otworzy to archiwum, znajdzie katalog
główny `repository.mwodevelop` i odczyta jego manifest `addon.xml`.

## WatchNixtoons2 na BlueStacks1

Zainstaluj `WatchNixtoons2 (mwoDevelop)` z repozytorium stable poprzez GUI Kodi. Otwórz
`Latest Releases`, zapisz liczbę elementów i dostępną jakość, odtwarzaj wybraną jakość
przez kontrolowany interwał, a następnie zatrzymaj odtwarzanie. Sprawdź własność stable,
stan czyszczenia, artefakt deterministyczny i potok mediów Kodi za pomocą:

```bash
python tests/e2e/watchnixtoons2_bluestacks.py \
  --adb /home/mwo/android-sdk/platform-tools/adb \
  --serial emulator-5554 \
  --catalog-items 16 \
  --qualities 480 720 1080 \
  --quality 720 \
  --observed-seconds 25 \
  --result docs/e2e-results/2026-07-25-bluestacks1-watchnixtoons2.json
```

Weryfikator jest przeznaczony tylko do odczytu w profilu Kodi. Nie powiedzie się, chyba
że dodatek mwoDevelop jest włączony i jest własnością repozytorium stable, nie ma
starszego dodatku i repozytorium testing, a najnowszy pasujący dziennik odtwarzania
zawiera strumień wejściowy, demuxer, dekoder audio i czyste znaczniki zamknięcia
odtwarzacza.

## Sony Android TV / Kodi 21.3

Użyj izolowanego serwera ADB, gdy inny lokalny klient Android zastępuje serwer domyślny:

```bash
/home/mwo/android-sdk/platform-tools/adb -P 5038 start-server
/home/mwo/android-sdk/platform-tools/adb -P 5038 connect 192.168.1.12:5555
export ADB_SERVER_SOCKET=tcp:localhost:5038
```

Matryca Umbrella może wywołać prawdziwy adres URL autoodtwarzania poprzez zatwierdzony
Kodi JSON-RPC, obserwuje odtwarzacz i przechowuje zredagowaną diagnostykę resolwera Kodi
i Umbrella. Najpierw przekaż port TCP JSON-RPC Kodi:

```bash
/home/mwo/android-sdk/platform-tools/adb \
  -s 192.168.1.12:5555 forward tcp:19091 tcp:9090

.venv/bin/python tests/e2e/sony_kodi_matrix.py \
  --adb /home/mwo/android-sdk/platform-tools/adb \
  --serial 192.168.1.12:5555 \
  --host 127.0.0.1 \
  --jsonrpc-port 19091 \
  --direct-play \
  --case sintel \
  --observe-seconds 15 \
  --result docs/e2e-results/sony-umbrella-matrix.json
```

W przypadku deterministycznego testu odtwarzania WatchNixtoons2 biegacz wymaga
efektywnego ustawienia `Auto Play Highest Quality` (domyślnego od wersji mwoDevelop
0.29.2). Gdy profil użytkownika nie nadpisuje tej wartości, biegacz odczytuje ją z
definicji zainstalowanego dodatku. Następnie sprawdza aktualny katalog `Latest Releases`
i znany odcinek w mediach Kodi:

```bash
.venv/bin/python tests/e2e/sony_watchnixtoons2.py \
  --adb /home/mwo/android-sdk/platform-tools/adb \
  --serial 192.168.1.12:5555 \
  --host 127.0.0.1 \
  --jsonrpc-port 19091 \
  --observe-seconds 15 \
  --result docs/e2e-results/sony-watchnixtoons2.json
```

Obydwa raporty pomijają dane uwierzytelniające, magnesy i rozwiązane adresy URL
multimediów.

Przed matrycą resolwera oczyszczona sonda Real-Debrid może odróżnić nieprawidłowe konto
od trybu sprawdzania pamięci podręcznej `disabled_endpoint` obsługiwanego przez
Real-Debrid. Działa wewnątrz Kodi i emituje tylko typ konta, kody HTTP/błędów i czasy;
nigdy nie eksportuje tokena ani tożsamości konta:

```bash
.venv/bin/python tools/kodi_umbrella_rd_probe.py \
  --adb /home/mwo/android-sdk/platform-tools/adb \
  --adb-server-port 5038 \
  --serial 192.168.1.8:5555
```

Skoncentrowana regresja wyszukiwania otwiera prawdziwą wirtualną klawiaturę Umbrella,
przesyła termin i sprawdza, czy Kodi otrzymuje pasujący wynik z katalogu. Natychmiast
kończy się niepowodzeniem, jeśli nieaktualny mod `source_progress` nadal blokuje
interfejs użytkownika:

```bash
.venv/bin/python tests/e2e/umbrella_search_e2e.py \
  --adb /home/mwo/android-sdk/platform-tools/adb \
  --serial 192.168.1.12:5555 \
  --host 127.0.0.1 \
  --jsonrpc-port 19091 \
  --term "House of the Dragon" \
  --media-type tv \
  --result docs/e2e-results/sony-umbrella-search.json
```

Pomiń `--media-type tv` (lub pomiń `--media-type movie`) przy wyszukiwaniu filmów.

## BlueStacks1 / Kodi 21.3

BlueStacks może udostępniać JSON-RPC Kodi tylko w interfejsie sprzężenia zwrotnego
gościa. Prześlij go przez dokładny cel ADB `BlueStacks1`:

```bash
export ADB_SERVER_SOCKET=tcp:localhost:5038
/home/mwo/android-sdk/platform-tools/adb -s 127.0.0.1:5555 forward tcp:19190 tcp:9090

.venv/bin/python tests/e2e/sony_kodi_matrix.py \
  --adb /home/mwo/android-sdk/platform-tools/adb \
  --serial 127.0.0.1:5555 \
  --host 127.0.0.1 \
  --jsonrpc-port 19190 \
  --direct-play \
  --case sintel \
  --observe-seconds 15 \
  --result docs/e2e-results/bluestacks1-umbrella-matrix.json
```

Port ADB jest dynamiczny; przed uruchomieniem polecenia potwierdź, że `127.0.0.1:5555`
nadal identyfikuje instancję `Rvc64`/`BlueStacks1`. Dostęp JSON-RPC musi być również
włączony w Kodi na czas trwania testu, a następnie przywrócony.

Ta sama kontrola wyszukiwania ukierunkowanego wykorzystuje przekazany punkt końcowy
JSON-RPC w BlueStacks:

```bash
.venv/bin/python tests/e2e/umbrella_search_e2e.py \
  --adb /home/mwo/android-sdk/platform-tools/adb \
  --serial 127.0.0.1:5555 \
  --host 127.0.0.1 \
  --jsonrpc-port 19190 \
  --term "House of the Dragon" \
  --media-type tv \
  --result docs/e2e-results/bluestacks1-umbrella-search.json
```

## Test canary zastosowania i rollbacku Profile Sync

Uruchom odwracalny kanarek na urządzeniu rzeczywistym zainstalowanego aplikatora stable
Profile Sync:

```bash
PYTHONPATH=. .venv/bin/python \
  tests/e2e/profile_sync_apply_device.py \
  --device x88pro20 \
  --adb /home/mwo/android-sdk/platform-tools/adb \
  --adb-server-port 5037 \
  --result .kodi-private/e2e/x88pro20-profile-sync-apply.json
```

Sonda wykonuje jedno pomyślne zastosowanie zarządzanego ustawienia Umbrella, przywraca
pierwotną wartość, zgłasza błąd po pierwszym zapisie drugiej transakcji i wymaga
rollback, kwarantanny, oczyszczenia dziennika i przywrócenia dokładnych ustawień.
Prywatny stan Profile Sync jest przywracany bajt po bajcie wewnątrz Kodi i nigdy nie
opuszcza urządzenia.

## Produkcyjny TLS Profile Sync i etap podpisanego raportu

Utwórz jednorazowy plik parowania na hoście bez drukowania kodu, a następnie skonfiguruj
lub zsynchronizuj jeden punkt końcowy Android za pośrednictwem prawdziwej usługi QNAP:

```bash
python tools/qnap_profile_sync.py --references .env \
  create-production-pairing \
  --logical-device-id bluestacks1 --channel home-stable \
  --target-tag home --target-tag android-emulator:x86_64 \
  --output .kodi-private/profile-sync-production/pairing-bluestacks1.json
PYTHONPATH=. .venv/bin/python \
  tests/e2e/profile_sync_production_device.py \
  --device bluestacks1 --devices .kodi-private/devices.json \
  --server-url https://192.0.2.39:18765 \
  --ca-certificate .kodi-private/profile-sync-production/tls/ca.crt \
  --pairing-file \
    .kodi-private/profile-sync-production/pairing-bluestacks1.json \
  --channel home-stable --action configure
```

Sonda in-Kodi kopiuje tylko publiczny certyfikat urzędu certyfikacji, przechowuje
tajemnice rejestracji w Kodi i emituje oczyszczony znacznik. `--action sync` wymaga
dodatkowo podpisanego przypisania, zastosowania dokładnej wersji i podpisanego raportu,
aby nie był on w toku.
