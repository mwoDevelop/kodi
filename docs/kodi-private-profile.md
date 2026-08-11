# Prywatne migawki profilu Kodi

Ten workflow odtwarza nową instalację Kodi na Androidzie bez zapisywania poświadczeń
lub tokenów w commitach. Prywatne migawki znajdują się w `.kodi-private/`, który jest
wyłączony ze śledzenia Git, kontekstów budowania Dockera i zwykłych artefaktów
repozytorium.

Migawka jest celowo niezaszyfrowana w schemacie 1. Traktuj katalog jako tajny materiał:
utrzymuj go w trybie `0700`, nie dołączaj go do zgłoszeń ani wydań i nie kopiuj go do
niezaufanego miejsca docelowego kopii zapasowej. Następna faza przechowywania powinna
zaszyfrować migawkę, zanim zostanie ona dopuszczona do Git, na przykład za pomocą `age`
lub SOPS i kluczy przechowywanych poza tym repozytorium.

## Zawartość

Polityka jest zdefiniowana w `manifests/kodi-profile-policy.json`. Zachowuje:

- kod i manifesty zainstalowanych dodatków, w tym wybraną skórkę;
- główne ustawienia Kodi XML/JSON, źródła, mapy klawiszy, listy odtwarzania i
  profile;
- trwałe dane `addon_data` każdego dodatku, w tym dane uwierzytelniające Umbrella i
  Real-Debrid;
- lokalne grafiki adresowane zawartością dla ulubionych WatchNixtoons2;
- ustawienia wybranej skórki;
- dokładny plik APK Android Kodi potrzebny do odtworzenia instalacji.

Nie obejmuje:

- bazy danych Kodi, miniatury, dane urządzeń peryferyjnych, logi, pliki tymczasowe i pobrane
  pakiety dodatków;
- cache grafik, providerów, wyszukiwania, metadanych, synchronizacji Trakt i pozostałe
  cache Umbrella;
- każdy katalog dodatków `cache/` i `temp/`.

Ulubione WatchNixtoons2 stanowią celowy wyjątek od ogólnego wykluczenia pamięci
podręcznej miniatur. Podczas eksportu znane starsze adresy URL CDN są normalizowane do
bieżącego hosta obrazu, pobierane z ograniczonym rozmiarem i sprawdzaniem poprawności
obrazu oraz przechowywane w pliku `userdata/favourite-artwork/`. `favourites.xml`
następnie odwołuje się do ścieżki `special://profile/` zaadresowanej treścią. Mały
manifest źródłowy umożliwia późniejszy eksport w celu odświeżenia obrazu; jeśli sieć CDN
jest chwilowo niedostępna, zachowywany jest ostatni zweryfikowany obraz lokalny. Pliki
cookie i sufiksy nagłówków adresów URL nie są używane ani utrwalane.

Rutynowa usługa profili celowo zarządza małą listą dozwolonych ustawień semantycznych,
kanonicznym dokumentem ulubionych i zestawem grafik adresowanych zawartością. Nie
rozpowszechnia poświadczeń, tokenów, dowolnych ustawień dodatków ani pamięci
podręcznych, które można odbudować. Te prywatne wartości pozostają w ignorowanych
migawkach hostów i są stosowane tylko w drodze jawnego wdrożenia na każdym urządzeniu.
Dzięki temu podziałowi cykliczny kanał QNAP jest deterministyczny i bezpieczny do
podpisania, a jednocześnie umożliwia odtworzenie czystej instalacji Kodi z tego hosta.

Autorytatywna lista urządzeń prywatnego wdrożenia, wydawca i aktualne adresy sieciowe
znajdują się w pliku `.env` o trybie `0600`:

```bash
KODI_SYNC_PUBLISHER=sony-tv
KODI_SYNC_DEVICES=bluestacks1,sony-tv,bedroom-tv,x88pro20,nuc-mwo,nuc-alek
KODI_DEVICE_SONY_TV_ADB=192.0.2.10:5555
KODI_DEVICE_NUC_MWO_SSH_HOST=192.0.2.20
KODI_PROFILE_SYNC_CHANNEL=home-stable
KODI_PROFILE_SYNC_STARTUP_DELAY_SECONDS=15
KODI_PROFILE_SYNC_INTERVAL_HOURS=6
KODI_PROFILE_SYNC_READ_ONLY=true
```

Odniesienia do tożsamości logicznej, platformy, oczekiwanego modelu i poświadczeń
pozostają w `.kodi-private/devices.json`; `.env` jest autorytatywny dla członkostwa i
punktów końcowych sieci. Wybrany wydawca musi także mieć rolę `publisher` w tym
rejestrze.

Audyt bez zmiany ulubionych:

```bash
.venv/bin/python tools/kodi_portable_state_rollout.py audit \
  --result .kodi-private/e2e/portable-state-audit.json
```

Zsynchronizuj wszystkie aktualnie osiągalne cele:

```bash
.venv/bin/python tools/kodi_portable_state_rollout.py sync \
  --result .kodi-private/e2e/portable-state-sync.json
```

Przed eksportem starsze działania WatchNixtoons2 są migrowane do
`plugin.video.watchnixtoons2.mwodevelop` i materializują się zweryfikowane zdalne
grafiki. Następnie wydawca tworzy deterministyczny plik ZIP poniżej
`.kodi-private/portable-state/`. Każdy cel sprawdza dokładny inwentarz archiwalny,
SHA-256 i przywoływany zestaw grafik, stosuje go z prywatnym dziennikiem i rollback,
restartuje Kodi dopiero po zmianie i weryfikuje wynik z wnętrza Kodi. To samo wdrożenie
konfiguruje nietajną tożsamość i harmonogram `mwoDevelop Profile Sync` dla każdego
urządzenia logicznego. Tokeny rejestracji i nasiona podpisu nigdy nie są kopiowane
między urządzeniami. Powtórzona aplikacja zwraca `NO_CHANGE`.

Produkcyjny profil tożsamości korzysta z trwałego uwierzytelnionego zaplecza HTTPS oraz
odrębnego klucza rejestracji, tokenu i podpisu dla każdego urządzenia. Testy na
tymczasowym backendie muszą zachować i przywrócić tę tożsamość produkcyjną w sposób
atomowy; nigdy nie mogą pozostawiać rejestracji ani tokenu powiązanego z tymczasowym
punktem końcowym.

Niedostępne urządzenia są zgłaszane i pozostawiane bez zmian. Mutacja Linux/Flatpak jest
dozwolona dopiero po tym, jak sonda cyklu życia zakwalifikowała bieżące mapowania
`special://home` i `special://profile` z dziennika wykonawczego Kodi, udowodniła
UID/home konta i potwierdziła, że ​​Kodi jest zatrzymany. Dedykowane wdrożenie przesyła
następnie niezmienne pliki ZIP do tymczasowego katalogu pomostowego Flatpak; Ekstrakcja
ZIP, wymiana dodatków, rollback, `UpdateLocalAddons`, włączenie i Profile Sync są
wykonywane w Kodi. Wersje Umbrella, mwoScrapers, opakowania i WatchNixtoons2 z blokadą
stable są uzgadniane za pomocą Kodi przed zastosowaniem profilu zarządzanego. Nigdy nie
edytuje `Addons*.db`.

Zarejestruj i zweryfikuj jednego kwalifikowanego głównego Flatpak pod kątem bieżącej
aktywnej wersji produkcyjnej:

```bash
.venv/bin/python tools/kodi_flatpak_profile_sync_rollout.py \
  --device nuc-alek \
  --revision-id sha256:4c7d728d214a6d31d1d277d2fd6b30957bc2d07d873648df5e0ffda69a1c905e \
  --profile-sync-sha256 541bc709b1a6106466509af2de273ba1562ac8297cfc0027209eb6df22c665b8 \
  --repository-sha256 0bde0bf4b61a178cacc07d8ffc2b5006b8374b1ec2c1a12d610ea02c2e6dc287 \
  --result .kodi-private/e2e/nuc-alek-profile-sync.json
```

Pierwsze pomyślne wywołanie powoduje zapisanie prywatnego, jawnego potwierdzenia
instalacji. Powtarzające się wywołanie wykorzystuje już zainstalowane dodatki i
przeprowadza kontrolę tylko synchronizacji w Kodi; jest to powtarzalny test bez zmian.
Każdy podmiot główny systemu Unix utrzymuje niezależny stan rejestracji poniżej
ignorowanego katalogu `.kodi-private/flatpak-profile-sync/`. Tokeny dostępu, nasiona
podpisywania urządzeń i nasiona promotorów/wydawców offline nigdy nie trafiają do danych
wyjściowych Git ani CI.

Kodi odbudowuje swoją dodatkową bazę danych po przywróceniu. Bazy danych bibliotek
multimediów zostały odroczone od schematu 1, ponieważ zastąpienie działającej bazy
danych Kodi nie jest operacją niepodzielną ani przenośną. Wynika to z rozróżnienia
zastosowanego w Kodi pomiędzy trwałymi [danymi
użytkownika](https://kodi.wiki/view/Userdata) i szerszą, pełnoprofilową [kopią
zapasową](https://kodi.wiki/view/Backup).

## Eksport

Z katalogu głównego repozytorium:

```bash
mkdir -p .kodi-private/snapshots
chmod 700 .kodi-private .kodi-private/snapshots

.venv/bin/python tools/kodi_profile.py \
  --serial 127.0.0.1:5555 \
  export \
  --output .kodi-private/snapshots/bluestacks1-$(date -u +%Y%m%dT%H%M%SZ)
```

Eksporter na krótko zatrzymuje Kodi, aby uzyskać spójną migawkę ustawień, a następnie
uruchamia go ponownie. Sprawdza, czy miejsce docelowe znajduje się poniżej prywatnego
katalogu ignorowanego przez Git, rejestruje SHA-256 dla każdego pliku i zapisuje migawkę
dopiero po pomyślnym zakończeniu eksportu.

Sprawdź migawkę przed jej użyciem lub skopiowaniem:

```bash
.venv/bin/python tools/kodi_profile.py verify \
  .kodi-private/snapshots/SNAPSHOT_NAME
```

## Przywracanie na czystym urządzeniu Android

Cel musi być osiągalny poprzez ADB i zgodny z nagraną wersją Kodi i ABI procesora:

```bash
.venv/bin/python tools/kodi_profile.py \
  --serial 127.0.0.1:5715 \
  install-kodi \
  .kodi-private/snapshots/SNAPSHOT_NAME

.venv/bin/python tools/kodi_profile.py \
  --serial 127.0.0.1:5715 \
  restore \
  .kodi-private/snapshots/SNAPSHOT_NAME
```

Instalator przyznaje Kodi wymagane uprawnienia do multimediów Android. Przywracanie
odbywa się w ramach własnego procesu Kodi, weryfikuje każdy zarchiwizowany plik przed
jego zastąpieniem, odbudowuje inwentarz dodatków, włącza nagrane dodatki, aktywuje
nagraną skórkę i usuwa tymczasowe pliki transferu.

W przypadku urządzeń Android TV bez narzędzi powłoki wymaganych przez transport w Kodi,
`tools/kodi_reinstall.py` obsługuje również jawny tryb przywracania `adb-push`.
Zatrzymuje Kodi, kopiuje już zweryfikowany ładunek, pozwala Kodi odbudować swoje bazy
danych, włącza nagrane dodatki, utrwala wybraną skórkę, restartuje Kodi i sprawdza wynik
przez JSON-RPC.

Narzędzia drukują tylko liczniki i migawki lub identyfikatory pakietów. Nigdy nie
drukują ustawień dodatków, danych uwierzytelniających, tokenów, magnesów ani ustalonych
adresów URL przesyłania strumieniowego.

## Czysta reinstalacja z tego hosta

Zachowaj docelowy ekwipunek w ignorowanym pliku prywatnym
`.kodi-private/kodi-reinstall.json`. Każdy wpis przypina numer seryjny ADB i oczekiwany
model, migawkę, wersję Kodi, APK SHA-256, tryb przywracania i wymagane dodatki. Mapuje
także przywrócone niestandardowe dodatki do repozytorium, które faktycznie je indeksuje,
więc Kodi zachowuje automatyczne prawo własności do aktualizacji po odbudowaniu bazy
danych dodatków. Plik APK musi również pozostać pod `.kodi-private/`.

Opcjonalny `default_addons_manifest` najwyższego poziomu wskazuje na wersjonowaną
politykę publiczną, taką jak `manifests/kodi-default-addons.json`. Po przywróceniu
prywatnej migawki i przed jej sprawdzeniem, ponowna instalacja workflow uzgadnia
wszystkie wymienione zewnętrzne dodatki od oficjalnego wydawcy HTTPS. Weryfikuje pobrany
plik SHA-256, bezpieczny układ ZIP, tożsamość i wersję dodatku, zależności, stan
włączenia i pochodzenie repozytorium. Poświadczenia dodatku pozostają wyłącznie w
profilu prywatnym; manifest publiczny zawiera wyłącznie pochodzenie i niezmienne
tożsamości artefaktów.

Konfiguracja dodatku prywatnego to osobna faza poinstalacyjna. Zignorowana konfiguracja
ponownej instalacji może deklarować adapter znajdujący się na liście dozwolonych i
odniesienia do wartości w ignorowanym pliku mode-`0600` `.env`:

```json
{
  "private_references_file": ".env",
  "default_addon_private_profiles": [
    {
      "adapter": "rapideo-v1",
      "username_ref": "RAPIDEO_USER",
      "password_ref": "RAPIDEO_PASS"
    }
  ]
}
```

Adapter Rapideo działa po oficjalnym uzgodnieniu dodatku i przed ostatecznym
sprawdzeniem przywracania. Pełny rollout najpierw eksportuje zweryfikowany token z
urządzenia wskazanego przez `KODI_SYNC_PUBLISHER` do ignorowanego pliku
`.kodi-private/rapideo/token.json` w trybie `0600`. Adapter ustawia go poprzez Kodi i
weryfikuje punkt końcowy konta. Dopiero gdy nie ma autorytatywnego tokenu, wykonuje
logowanie danymi z `.env`. Nie usuwa już działającego tokenu przed udanym
uwierzytelnieniem, więc błąd sieci lub VPN nie niszczy poprzedniej sesji.

Tymczasowy plik danych uwierzytelniających i oczyszczony wynik są zawsze usuwane z
pamięci współdzielonej Android. Ani raport przywracania, ani argumenty procesu nie
zawierają poświadczeń ani tokenów. Token można bezpiecznie odświeżyć niezależnie:

```bash
.venv/bin/python tools/kodi_rapideo_token.py export --device sony-tv
```

Dostępna jest również samodzielna idempotentna ponowna próba konfiguracji urządzenia:

```bash
.venv/bin/python tools/kodi_rapideo_configure.py \
  --serial ADB_ENDPOINT --references .env \
  --adb /home/mwo/android-sdk/platform-tools/adb \
  --adb-server-port 5038
```

To samo uzgodnienie można przeprowadzić ponownie bez ponownej instalacji Kodi:

```bash
.venv/bin/python tools/kodi_default_addons.py \
  --serial ADB_ENDPOINT \
  --adb /home/mwo/android-sdk/platform-tools/adb \
  --adb-server-port 5038
```

Dokładna zgodna instalacja jest zgłaszana jako `unchanged`. Nieudana kopia starszego ADB
może pozostawić katalog pamięci masowej Android, którego nazwy Kodi nie może zmienić.
Moduł uzgadniający ponawia próbę naprawy osieroconej dopiero wtedy, gdy JSON-RPC
udowodni, że dodatek nie istnieje w bazie danych Kodi; aktywne dodatki zawsze zachowują
niepodzielną kopię zapasową i ścieżkę rollback.

Przeglądaj i sprawdzaj każdy cel bez zmiany któregokolwiek urządzenia:

```bash
./tools/kodi_reinstall.py
```

Po przejrzeniu rozpoznanych identyfikatorów modelu, wersji, ABI i migawek wykonaj
autoryzowaną dezinstalację, oczyszczenie, instalację, przywrócenie i weryfikację:

```bash
./tools/kodi_reinstall.py --yes
```

Ogranicz operację do jednego skonfigurowanego celu lub powtórz tylko przywracanie:

```bash
./tools/kodi_reinstall.py --target sony-tv --yes
./tools/kodi_reinstall.py --target sony-tv --restore-only --yes
```

Jeśli jeden dodatek utraci tylko plik ustawień zarządzanych, przywróć dokładnie ten plik
z już zweryfikowanej migawki, zamiast zastępować cały profil:

```bash
.venv/bin/python tools/kodi_profile.py \
  --serial 192.168.1.8:5555 \
  restore-path .kodi-private/snapshots/sony-20260727T101733Z \
  --allow-kodi-upgrade \
  --allow-addon-upgrade \
  --path userdata/addon_data/plugin.video.umbrella/settings.xml
```

Jeśli nie można wyeksportować pełnej migawki źródłowej (na przykład dlatego, że Android
poprawnie odmawia ADB dostępu do prywatnego katalogu mode-`0700` Profile Sync), nie
osłabiaj uprawnień urządzenia. Eksportuj tylko wymagane pliki dodatku `settings.xml` do
`.kodi-private/` i stosuj je transakcyjnie:

```bash
PYTHONPATH=. .venv/bin/python tools/kodi_addon_settings_rollout.py \
  --serial ADB_ENDPOINT \
  --setting plugin.video.umbrella=.kodi-private/e2e/umbrella-settings.xml \
  --setting script.module.mwoscrapers=.kodi-private/e2e/mwoscrapers-settings.xml \
  --result .kodi-private/e2e/private-addon-settings-rollout.json
```

Narzędzie akceptuje tylko zwykłe pliki i identyfikatory bezpiecznych dodatków, sprawdza,
czy każdy docelowy dodatek jest zainstalowany i włączony, a także ponownie wykorzystuje
blokadę przywracania, dziennik, rollback i weryfikację skrótu w Kodi. Budzi Android TV,
restartuje Kodi, sprawdza, czy wersje dodatków się nie zmieniły i przeprowadza drugą
weryfikację semantyczną z poziomu Kodi. Jego raport zawiera identyfikatory i
podsumowania, ale nigdy nie ustawia wartości. Źródłowe pliki XML i wygenerowany raport
pozostają ignorowane i nie można ich zatwierdzać.

`restore-path` akceptuje tylko dokładne ścieżki obecne w zweryfikowanym manifeście
migawki i ogranicza selektywne odzyskiwanie do `userdata/`. W przypadku `addon_data`
wymagana jest również instalacja dodatku z migawką w tej samej wersji;
`--allow-addon-upgrade` pozwala jedynie na wyraźny ruch do przodu w obrębie tej samej
linii głównej. Polecenie tworzy minimalne archiwum zawierające te ścieżki, wiąże wynik z
losowym identyfikatorem operacji i skrótem wyboru, serializuje operacje przywracania z
blokadą urządzenia i ponawia próbę dostarczenia EventServer tylko do momentu, gdy Kodi
atomowo potwierdzi pojedynczy zapis. Po ponownym uruchomieniu Kodi i umożliwieniu
załadowania usług dodatkowych, przed raportowaniem powodzenia sprawdza każdy zwykły plik
pod względem rozmiaru i SHA-256 w Kodi. Dodatek `settings.xml` jest stosowany poprzez
interfejs API ustawień Kodi, więc aktywna usługa nie może go nadpisać z przestarzałej
pamięci, a następnie zweryfikować poprzez kanoniczne podsumowanie wybranych
identyfikatorów i wartości ustawień. Jeśli dodatek zmieni lub odrzuci token OAuth
podczas uruchamiania, dokładna kontrola po ponownym uruchomieniu zgłasza niepowodzenie;
odśwież migawkę źródłową lub ponownie autoryzuj to konto, zamiast traktować nieaktualne
dane uwierzytelniające jako pomyślne przywrócenie. Częściowa awaria interfejsu API
ustawień jest przywracana do obrazu wstępnego. Następnie usuwane są wszystkie pliki
tymczasowe po stronie urządzenia; jeśli nie można potwierdzić czyszczenia, blokada
zostaje zachowana do jawnego odzyskania. Narzędzie nigdy nie drukuje ustawień ani
poświadczeń.

Jeśli proces hosta zostanie przerwany i pozostawi blokadę urządzenia, przerwij go i
odzyskaj jawnie (spowoduje to zatrzymanie Kodi przed usunięciem jakichkolwiek danych
przejściowych):

```bash
.venv/bin/python tools/kodi_profile.py \
  --serial 192.168.1.8:5555 \
  recover-lock
```

Nie uruchamiaj `recover-lock`, gdy aktywne jest przywracanie, które chcesz zakończyć.

Zakres czyszczenia jest celowo przypisany do pakietu Kodi i tych ścieżek:

- `/sdcard/Android/data/org.xbmc.kodi`;
- `/sdcard/Android/obb/org.xbmc.kodi`;
- `/sdcard/.kodi`.

Kodi 21.2 i 21.3 na Android TV wykorzystują ten sam odpowiedni układ profili:
`files/.kodi/addons/` i `files/.kodi/userdata/`. Katalogi takie jak `media/`, `system/`,
`temp/` i wersjonowane bazy danych są generowane przez nowo zainstalowany Kodi i nie
stanowią dowodu na inny format profilu Android TV.

Nie odinstalowuj zastąpionego repozytorium, dopóki nie zostaną utworzone kopie zapasowe
jego dodatków i `addon_data` oraz nie przejdzie pomyślnie testu migracji na rzeczywistym
urządzeniu. Kodi może usunąć zależne dodatki i ich ustawienia użytkownika w ramach
dezinstalacji repozytorium, nawet po ponownym przypisaniu źródła aktualizacji. Wolę
pozostawić stare repozytorium wyłączone do czasu, aż zweryfikowane czyszczenie workflow
wykaże, że zarządzane dodatki i ustawienia przetrwały.

## Lista kontrolna walidacji

Po przywróceniu:

1. `verify` ponownie lokalna migawka.
2. Potwierdź `JSONRPC.Ping`, aktywną skórkę i włączony stan wymaganych dodatków.
3. Uruchom `tests/e2e/umbrella_search_e2e.py`, aby uzyskać prawdziwe wyszukiwanie
   Umbrella.
4. Uruchom `tests/e2e/sony_kodi_matrix.py --direct-play` dla co najmniej jednego filmu i
   jednego odcinka.
5. Uruchom `tests/e2e/sony_watchnixtoons2.py`, aby uzyskać dostęp do katalogu i
   odtwarzania.

Biegacze E2E usuwają ze swoich raportów dane uwierzytelniające, magnesy, adresy URL
wtyczek i rozwiązane adresy URL multimediów.

## Zasady dotyczące urządzeń Android

Ustawienia systemowe znajdujące się poza Kodi są wersjonowane oddzielnie w ramach
`manifests/device-profiles/`. Profile zawierają nazwy pakietów, żądane zasady i
odniesienia do prywatnych wartości `.env`, ale nigdy same dane uwierzytelniające.

Zastosuj i zweryfikuj politykę X88 Pro 20 za pomocą:

```bash
.venv/bin/python tools/android_device_profile.py \
  --profile manifests/device-profiles/x88pro20.json \
  --serial 192.168.1.8:5555 \
  --adb /home/mwo/android-sdk/platform-tools/adb \
  --adb-server-port 5038 \
  --env-file .env \
  apply --yes
```

Obecna polityka X88 łączy Android `Always-on VPN` z natywną akcją ponownego uruchomienia
`Connect latest` OpenVPN Connect i celowo pozostawia blokadę. Nie można w tym celu użyć
zwykłego profilu nazwy użytkownika/hasła: OpenVPN Connect uruchamia się, zanim dostępny
jest jego interaktywny magazyn danych uwierzytelniających i raportuje
`AON_REQUEST_CREDS`. Dlatego też wdrożenie X88 renderuje prywatny profil automatycznego
logowania z `.env`; zaimportowany profil może zostać uwierzytelniony bez wyświetlania
monitu `Enter credentials`. Tymczasowo niedostępna sieć VPN nadal nie może odcinać
urządzenia od ADB, Kodi ani sieci lokalnej.

Wersjonowany profil X88 deklaruje `inline_auth_user_pass`, zmienną środowiskową ścieżki
profilu prywatnego, nazwę zaimportowanego połączenia i obie zasady ponownego
uruchamiania. Audyt dodatkowo wymaga, aby plik prywatny był w trybie `0600` i sprawdza,
czy jego wbudowane poświadczenia odpowiadają `.env`, ale nigdy nie uwzględnia tych
wartości w wynikach. Zgodne środowisko wykonawcze wymaga również podłączonego,
zatwierdzonego przez Android interfejsu `tun0`; Same zapisane ustawienia nie są
akceptowane jako dowód autostartu. Polityka X88 wymaga również, aby `192.168.1.0/24`
korzystał z `net_gateway`, co odpowiada wykluczeniu sieci LAN NordVPN, więc QNAP Profile
Sync pozostaje osiągalny poza VPN.

Profile połączeń OpenVPN i dane uwierzytelniające usługi NordVPN pozostają w
`.kodi-private/` i `.env`; wersjonowane są tylko ich nazwy i odniesienia. Polecenie
Apply korzysta z interfejsu użytkownika ustawień OpenVPN Connect oznaczonego etykietą
dostępności, ponieważ aplikacja nie udostępnia interfejsu API konfiguracji zarządzanej
dla tej opcji; audyt uzupełniający sprawdza, czy wybrana opcja radiowa rzeczywiście
pozostała.
