# YouTube w zarządzanych instalacjach Kodi

Projekt instaluje oficjalny `plugin.video.youtube` natywnie z
`repository.xbmc.org`. Nie forkuje dodatku i nie publikuje jego ZIP-a w repozytorium
mwoDevelop. `manifests/kodi-default-addons.json` przypina wersję i SHA-256 użyte do
kwalifikacji, a Kodi zachowuje oficjalny origin i mechanizm aktualizacji.

Funkcja obejmuje instalację, osobiste klucze API i wspólny dla floty profil sesji
OAuth. Docelową ścieżką runtime jest zaszyfrowany Secret Broker na QNAP oraz koperta
HPKE per enrollment; hostowy rollout pozostaje rollbackiem do chwili zakończenia
cutoveru. Sekret nie wchodzi do zwykłej rewizji Profile Sync i nie jest wersjonowany.

## Prywatne referencje

Ignorowany plik `.env` o trybie `0600` może zawierać:

```dotenv
YOUTUBE_API_KEY=REDACTED
YOUTUBE_CLIENT_ID=REDACTED.apps.googleusercontent.com
YOUTUBE_CLIENT_SECRET=REDACTED
YOUTUBE_USER=operator-account-hint@example.invalid
```

`YOUTUBE_USER` jest lokalną tożsamością oczekiwanego konta i musi odpowiadać polu
`account_hint` w prywatnej sesji. `YOUTUBE_PASS` nie jest obsługiwany przez dodatek ani
adapter i nigdy nie jest kopiowany na urządzenie. Google wymaga zgody OAuth; hasło,
CAPTCHA, 2FA i formularz logowania nie są częścią rolloutu.

W Google Cloud należy włączyć YouTube Data API v3, utworzyć ekran zgody oraz klienta
OAuth typu „TVs and Limited Input devices”. Klucz API powinien być ograniczony do
YouTube Data API v3. Wszystkie trzy wartości są sekretami operacyjnymi, chociaż po
dostarczeniu do przejętego urządzenia mogą zostać z niego odczytane.

Prywatny profil reinstalacji używa tylko referencji:

```json
{
  "adapter": "youtube-oauth-v1",
  "api_key_ref": "YOUTUBE_API_KEY",
  "client_id_ref": "YOUTUBE_CLIENT_ID",
  "client_secret_ref": "YOUTUBE_CLIENT_SECRET",
  "account_hint_ref": "YOUTUBE_USER"
}
```

Kanoniczna sesja znajduje się w ignorowanym pliku
`.kodi-private/youtube/session.json` o trybie `0600`. Zawiera osobiste API, oczekiwany
identyfikator kanału oraz trzy refresh tokeny wymagane przez wersję 7.4.4: TV,
użytkownika i VR. Wartości są przekazywane do urządzenia tylko w krótkotrwałym pliku,
a raport zawiera wyłącznie statusy logiczne.

Import do Brokera przygotowuje również ignorowany dokument o prawach `0600`:

```bash
.venv/bin/python tools/youtube_secret_set.py
.venv/bin/python tools/qnap_secret_broker.py import \
  --input .kodi-private/secret-broker/youtube-generation-1.json
```

Import zaczyna od `PREPARED`. Liniowe przejścia wykonuje się jawnie, na przykład:

```bash
.venv/bin/python tools/qnap_secret_broker.py transition youtube-home 1 \
  --from PREPARED --to CANARY_VERIFIED
```

Profile Sync ma tryby `shadow`, `canary` i `active`. Domyślny `shadow` tylko
weryfikuje kopertę. Canary stosuje zestaw po `CANARY_VERIFIED`, a flota w trybie
`active` wyłącznie zestaw `ACTIVE`. Agent nie zachowuje kopii plaintextu w swoim
stanie; oficjalny dodatek musi jednak zapisać refresh tokeny w swoim prywatnym
`addon_data`, aby sesja działała po restarcie.

## Instalacja i konfiguracja

Pełny rollout uzgadnia dodatek i konfigurację razem z pozostałymi funkcjami Kodi:

```bash
.venv/bin/python tools/kodi_ops.py rollout --dry-run
.venv/bin/python tools/kodi_ops.py rollout
```

Sam adapter Android można uruchomić diagnostycznie:

```bash
.venv/bin/python tools/kodi_youtube_configure.py \
  --serial 127.0.0.1:5555 \
  --references .env
```

Adapter ustawia kanoniczne pola API przypiętej wersji dodatku, kończy setup wizard,
wiąże opcjonalny serwer HTTP dodatku z loopback, odświeża trzy tokeny, sprawdza przez
YouTube Data API oczekiwany kanał i atomowo zapisuje minimalny stan dodatku. Prywatny
plik tymczasowy i raport na pamięci współdzielonej Androida są usuwane w bloku
`finally`. Raport nie zawiera kluczy, tokenów, adresu konta ani identyfikatora kanału.

`inputstream.adaptive` jest obowiązkową zależnością binarną. Oficjalne repo Kodi dla
Androida publikuje ją dla ARM64 i ARMv7, dlatego Kodi działające jako pakiet `x86` w
emulatorze nie jest kwalifikowanym canary. Instancja BlueStacks używana przez projekt
ma oficjalny Kodi 21.3 ARM64 uruchamiany przez native bridge; adapter odrzuca wariant
`x86` przed pokazaniem dialogu instalacji. Natywna instalacja z repo może otworzyć
modalne potwierdzenie. Automatyzacja akceptuje wyłącznie dialog, który pojawił się
bezpośrednio po jej własnym `InstallAddon`, i odmawia działania przy wcześniej
otwartym oknie potwierdzenia.

Adapter przyjmuje albo kompletny zestaw API w `.env`, albo kompletną sesję prywatną.
Brak obu źródeł daje `API_CONFIG_REQUIRED`; częściowy zestaw jest błędem bez mutacji.
Uzgadnianie oficjalnego dodatku porównuje jego pliki z przypiętym ZIP-em, dzięki czemu
potrafi naprawić uszkodzoną instalację tej samej wersji bez zmiany originu Kodi.

## Utworzenie i rotacja sesji OAuth

Na zaufanym hoście uruchom:

```bash
.venv/bin/python tools/youtube_session_authorize.py --references .env
```

Narzędzie pokaże kolejno trzy publiczne kody: YouTube TV, osobistego klienta i YouTube
VR. Każdy kod zatwierdź na wskazanej stronie Google dla konta z `YOUTUBE_USER`.
Narzędzie nie czyta ani nie wysyła `YOUTUBE_PASS`; po sukcesie weryfikuje kanał i
atomowo zastępuje prywatną sesję. Następny rollout propaguje ją na urządzenia.

Kwalifikowana wersja 7.4.4 żąda dla wszystkich trzech klientów pełnego scope
`https://www.googleapis.com/auth/youtube`. Bieżące tokeny potwierdzono przez endpoint
Google `tokeninfo`. Nie można zawęzić już wydanego refresh tokenu; przejście na
`youtube.readonly` wymagałoby nowej zgody i osobnej kwalifikacji zmodyfikowanego
klienta. Projekt pozostawia oficjalny dodatek bez forka i używa dedykowanego konta.

Stan adaptera oznacza:

- `AUTHORIZATION_REQUIRED` — brak lokalnych refresh tokenów;
- `CONSENT_PENDING` — zapisano mniej niż trzy wymagane tokeny;
- `ACCOUNT_READY` — wszystkie tokeny odświeżono, a oczekiwany kanał zweryfikowano;
- `API_CONFIG_REQUIRED` — brakuje osobistego zestawu API;
- `UNQUALIFIED_UPSTREAM` — Kodi zainstalowało wersję nowszą od przetestowanej.

Po `ACCOUNT_READY` sprawdź wyszukiwanie, subskrypcje i odtworzenie filmu, uruchom
ponownie Kodi oraz urządzenie, a potem powtórz rollout. Drugi przebieg powinien być
bez zmian i nie może ponownie żądać kodu.

## Diagnostyka i cofnięcie

- `YouTubeApiDisabled`: włącz YouTube Data API v3 w projekcie klucza.
- `YouTubeQuotaExceeded`: sprawdź quota w Google Cloud; adapter nie usuwa sesji.
- `YouTubeApiProbeFailed`: sprawdź DNS, zegar i VPN przed zmianą poświadczeń.
- `YouTubeSessionInvalid`: wykonaj ponownie `youtube_session_authorize.py`, a potem
  rollout; token został unieważniony lub wygasł.
- timeout na urządzeniu przy poprawnej sesji: sprawdź trasę Google przez VPN i zegar;
  adapter nie zastępuje wtedy poprzedniego działającego stanu.
- niekwalifikowana wersja: nie wykonuj downgrade'u ani migracji tokenu; zakwalifikuj
  nowy oficjalny ZIP najpierw na BlueStacks i X88.

Adapter zachowuje poprzednie ustawienia i przywraca je, jeżeli sonda nowego zestawu API
nie przejdzie. Cofnięcie lub usunięcie konta Google jest osobną operacją: najpierw
unieważnij zgodę po stronie Google, następnie wyloguj dodatek lokalnie. Nie publikuj
`access_manager.json`, `api_keys.json` ani raportów zawierających ich zawartość.

## Aktualizacje upstream

`check-youtube-upstream.yml` codziennie pobiera najnowszy oficjalny ZIP Kodi,
materializuje ZIP oraz rozpakowane drzewo i przepuszcza oba przez wspólną bramę
ClamAV/Semgrep/Gitleaks. Zmiana tworzy PR do przeglądu manifestu. Nie ma automatycznego
merge ani promocji; wymagane pozostają testy BlueStacks, X88 i regresja starej
funkcjonalności. QNAP watchdog monitoruje ten workflow niezależnie od ogólnego
`reconcile-upstreams.yml`.

Oficjalny dodatek zawiera własne publiczne identyfikatory klientów/API, które Gitleaks
poprawnie wskazuje jako potencjalne sekrety. Po ręcznym przeglądzie przypiętej wersji
zaakceptowano wyłącznie cztery pary ścieżka+reguła w
`security/youtube-7.4.4-baseline.json`; każda pozycja jest dodatkowo związana z SHA-256
całego pliku. Baseline nie przechowuje ani nie drukuje wykrytej wartości. Nowa wersja,
zmieniony plik, nowa ścieżka lub inna reguła pozostają aktywnym błędem bezpieczeństwa.
