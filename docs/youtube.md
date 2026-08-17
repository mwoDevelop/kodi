# YouTube w zarządzanych instalacjach Kodi

Projekt instaluje oficjalny `plugin.video.youtube` natywnie z
`repository.xbmc.org`. Nie forkuje dodatku i nie publikuje jego ZIP-a w repozytorium
mwoDevelop. `manifests/kodi-default-addons.json` przypina wersję i SHA-256 użyte do
kwalifikacji, a Kodi zachowuje oficjalny origin i mechanizm aktualizacji.

Pierwsze wydanie tej funkcji obejmuje instalację, osobiste klucze API i lokalną sesję
OAuth. Token sesji nie jest kopiowany między urządzeniami ani zapisywany przez Profile
Sync na QNAP. Po czystej reinstalacji trzeba ponownie wykonać logowanie urządzenia.

## Prywatne referencje

Ignorowany plik `.env` o trybie `0600` może zawierać:

```dotenv
YOUTUBE_API_KEY=REDACTED
YOUTUBE_CLIENT_ID=REDACTED.apps.googleusercontent.com
YOUTUBE_CLIENT_SECRET=REDACTED
YOUTUBE_USER=operator-account-hint@example.invalid
```

`YOUTUBE_USER` jest wyłącznie lokalną wskazówką, które konto wybrać na stronie Google.
Nie jest przesyłany przez adapter. `YOUTUBE_PASS` nie jest obsługiwany, nie jest
kopiowany na urządzenie i należy go usunąć z `.env`. Automatyzowanie hasła, CAPTCHA,
2FA lub formularza logowania Google nie jest częścią rozwiązania.

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
wiąże opcjonalny serwer HTTP dodatku z loopback i wykonuje publiczną sondę YouTube Data
API. Prywatny plik tymczasowy i raport na pamięci współdzielonej Androida są usuwane w
bloku `finally`. Raport nie zawiera wartości kluczy ani wskazówki konta.

Brak kompletu `YOUTUBE_API_KEY`, `YOUTUBE_CLIENT_ID` i `YOUTUBE_CLIENT_SECRET` daje
jawny stan `API_CONFIG_REQUIRED`; instalacja kodu może się udać, ale konto nie jest
gotowe. Częściowy zestaw referencji jest błędem i nie powoduje mutacji.

## Interaktywny OAuth

Po konfiguracji otwórz w Kodi `YouTube -> Sign In`. Dodatek wyświetla kod urządzenia;
na zaufanym komputerze lub telefonie otwórz adres wskazany przez Google, zaloguj się na
konto oznaczone lokalnie przez `YOUTUBE_USER` i zaakceptuj zakresy. Przypięta wersja
dodatku może poprosić kolejno o więcej niż jeden kod dla używanych klientów TV/VR.
Nie wyłączaj Kodi przed ukończeniem całego przepływu.

Stan adaptera oznacza:

- `AUTHORIZATION_REQUIRED` — brak lokalnego refresh tokenu;
- `CONSENT_PENDING` — zapisano część tokenów, ale przepływ nie jest kompletny;
- `ACCOUNT_READY` — dodatek ma kompletny lokalny zestaw sesji;
- `API_CONFIG_REQUIRED` — brakuje osobistego zestawu API;
- `UNQUALIFIED_UPSTREAM` — Kodi zainstalowało wersję nowszą od przetestowanej.

Po `ACCOUNT_READY` sprawdź wyszukiwanie, subskrypcje i odtworzenie filmu, uruchom
ponownie Kodi oraz urządzenie, a potem powtórz rollout. Drugi przebieg powinien być
bez zmian i nie może ponownie żądać kodu.

## Diagnostyka i cofnięcie

- `YouTubeApiDisabled`: włącz YouTube Data API v3 w projekcie klucza.
- `YouTubeQuotaExceeded`: sprawdź quota w Google Cloud; adapter nie usuwa sesji.
- `YouTubeApiProbeFailed`: sprawdź DNS, zegar i VPN przed zmianą poświadczeń.
- `AUTHORIZATION_REQUIRED` po reinstalacji: wykonaj nowy device flow; jest to
  oczekiwane w release 1.
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
