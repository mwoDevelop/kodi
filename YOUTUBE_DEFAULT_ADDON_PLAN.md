# Plan domyślnej instalacji i konfiguracji YouTube w Kodi

Status: release 1 zaimplementowany i zakwalifikowany technicznie na Androidzie;
autoryzacja konta pozostaje zablokowana do czasu dostarczenia kompletnego zestawu
`YOUTUBE_API_KEY`, `YOUTUBE_CLIENT_ID` i `YOUTUBE_CLIENT_SECRET`

Data: 2026-08-17

Aktualizacja realizacji: 2026-08-18

- oficjalny `plugin.video.youtube` 7.4.4 oraz natywna zależność
  `inputstream.adaptive` przechodzą instalację, kontrolę originu i drugi przebieg
  `NO_CHANGE` na BlueStacks ARM64 oraz X88 ARMv7;
- adapter nie odczytuje `YOUTUBE_PASS` i przy braku kompletnego personal API kończy
  się bez mutacji stanem `API_CONFIG_REQUIRED`;
- pełne oznaczenie `ACCOUNT_READY`, interaktywny Google device flow i release
  polityki konta pozostają otwarte do czasu skonfigurowania klienta OAuth typu TV;
- kwalifikacja Flatpak i opcjonalny release 2 recovery sesji nie wchodzą do
  ukończonej części Android release 1.

Plan jest rozszerzeniem
[`QNAP_CONTROL_PLANE_DEVICE_CONVERGENCE_PLAN.md`](QNAP_CONTROL_PLANE_DEVICE_CONVERGENCE_PLAN.md).
Nie wprowadza forka wtyczki YouTube ani nie dodaje jej do publicznego repo
`mwoDevelop`; kod dodatku ma nadal pochodzić z oficjalnego repozytorium Kodi.
Uwagi i sposób ich rozstrzygnięcia zapisano w
[`docs/YOUTUBE_DEFAULT_ADDON_PLAN_REVIEW.md`](docs/YOUTUBE_DEFAULT_ADDON_PLAN_REVIEW.md).

## 1. Cel

1. Instalować `plugin.video.youtube` domyślnie na każdej zarządzanej instalacji
   Kodi.
2. Uzgadniać bezpieczny, minimalny profil ustawień YouTube.
3. Pozwalać urządzeniom wymagającym YouTube używać wskazanego konta Google bez
   przechowywania hasła Google w Kodi ani automatyzowania formularza logowania.
4. Zachować działającą lokalną sesję po zwykłym restarcie; reinstall domyślnie
   wymaga ponownego device flow.
5. Włączyć YouTube do istniejącego procesu: pin artefaktu, skan, BlueStacks,
   X88, stable i dopiero potem reszta dostępnej floty.

Realizacja jest podzielona na dwie niezależnie wydawane części:

- **release 1:** natywna instalacja z oficjalnego repo Kodi, klucze API, lokalna
  sesja i interaktywny device flow, bez centralnego backupu tokenu;
- **release 2:** QNAP secrets oraz opcjonalne recovery sesji dopiero po akceptacji
  ADR-0005, spike'u bezpieczeństwa i pełnym restore drill.

Domyślna instalacja YouTube i release 1 nie zależą od ukończenia magazynu sekretów
QNAP. Release 2 nie jest domyślnie dołączony do zakresu pierwszej implementacji.

## 2. Ustalenia i decyzja dotycząca poświadczeń

Na dzień planu oficjalne repo Kodi Omega publikuje `plugin.video.youtube` 7.4.4.
Dodatek wymaga `script.module.requests` i `inputstream.adaptive`; pozostałe
zależności w `addon.xml` są opcjonalne. Implementacja ma jednak każdorazowo
odczytać bieżące metadane oficjalnego repo i przypiąć dokładny ZIP oraz SHA-256,
a nie polegać na numerze zapisanym w tym dokumencie.

`YOUTUBE_USER` i `YOUTUBE_PASS` nie są poprawnym interfejsem logowania dodatku.
Google wymaga OAuth 2.0 dla telewizorów i urządzeń z ograniczonym wejściem: Kodi
wyświetla kod, a użytkownik zatwierdza dostęp na osobnym urządzeniu. Ten przepływ
celowo nie przekazuje aplikacji loginu ani hasła. Bezpośrednie logowanie hasłem
jest również blokowane jako „less secure app”.

Przyjmujemy następujący kontrakt:

- `YOUTUBE_USER` pozostaje prywatną etykietą oczekiwanego konta i pomocą dla
  operatora podczas interaktywnej autoryzacji; nie jest wysyłany do API logowania;
- `YOUTUBE_PASS` jest jawnie nieużywany, nie trafia na urządzenia, do QNAP, logów,
  backupów ani raportów; po migracji należy usunąć go z `.env`;
- wspólna konfiguracja API używa prywatnych referencji `YOUTUBE_API_KEY`,
  `YOUTUBE_CLIENT_ID` i `YOUTUBE_CLIENT_SECRET`; klient OAuth musi mieć typ
  „TVs and Limited Input devices”;
- opcjonalny `YOUTUBE_EXPECTED_CHANNEL_ID` jest prywatnym identyfikatorem konta i
  służy do maszynowej weryfikacji wybranego kanału,
  ponieważ sam adres e-mail nie musi być zwracany przez dozwolone scope YouTube;
- każda instalacja przechodzi jednorazowy Google device flow. Nie automatyzujemy
  przeglądarki, CAPTCHA, 2FA ani wyboru konta za pomocą hasła z `.env`;
- token OAuth jest bearer secretem lokalnej sesji. Nie kopiujemy jednego pliku
  sesji pomiędzy flotą i nie twierdzimy, że Google kryptograficznie wiąże token z
  urządzeniem;
- koperta per enrollment ogranicza, kto może pobrać i odszyfrować recovery copy,
  ale po odszyfrowaniu root lub przejęte urządzenie może skopiować plaintext tokenu.

Źródła decyzji:

- [oficjalna strona dodatku Kodi](https://kodi.tv/addons/omega/plugin.video.youtube/);
- [dokumentacja dodatku: Personal API Keys](https://github.com/anxdpanic/plugin.video.youtube/wiki/Personal-API-Keys);
- [Google OAuth dla TV i urządzeń z ograniczonym wejściem](https://developers.google.com/identity/protocols/oauth2/limited-input-device);
- [Google: blokowanie logowania samym loginem i hasłem](https://support.google.com/accounts/answer/6010255).

## 3. Model docelowy

### 3.1 Kod dodatku i jednoznaczny model aktualizacji

- produkcyjny tryb to `kodi-native-official`: instalację i aktualizację wykonuje
  standardowy updater Kodi z originem `repository.xbmc.org`, zgodnie z ADR-0003;
- manifest domyślnych dodatków otrzymuje jawne `install_mode`, minimalną
  kwalifikowaną wersję oraz dane artefaktu użytego do certyfikacji; nie udaje, że
  Kodi pobrało ZIP za pomocą narzędzia mwoDevelop;
- dokładny oficjalny ZIP, źródło, licencja i SHA-256 są przypięte jako wejście
  kwalifikacji i dowód canary, ale kopia ZIP-a nie jest publikowana w repo
  mwoDevelop;
- na canary instalacja przez oficjalne repo jest porównywana z kwalifikowanym
  drzewem plików; na flocie natywny updater daje co najmniej dowód origin+version,
  a nie fałszywy dowód tych samych bajtów;
- model zależności jest per-addon i obejmuje ograniczenia wersji oraz macierz Kodi
  major/platform/ABI. `inputstream.adaptive` jest capability binarną instalowaną i
  włączaną natywnie przez Kodi, a nie wspólnym ZIP-em Pythona w
  `kodi-official-dependencies.json`;
- Android i Flatpak mają oddzielną kwalifikację drzewa zależności;
- ZIP i rozpakowana zawartość przechodzą istniejącą wspólną bramę malware;
- nie tworzymy forka ani kopii YouTube w repo `mwodevelop.github.io/kodi`.

Jeśli auto-update podniesie urządzenie do niezakwalifikowanej wersji, agent
raportuje `UNQUALIFIED_UPSTREAM`, nie wykonuje mutacji schematu ustawień/tokenów i
nie robi ślepego downgrade'u. Nowa wersja przechodzi przyspieszoną kwalifikację.

### 3.2 Ustawienia i API

Powstaje allowlistowany adapter `youtube-oauth-v1`. Adapter:

1. wymaga obsługiwanej wersji dodatku i znanego schematu jego plików;
2. w release 1 tworzy backup tylko zarządzanej konfiguracji, jawnie wykluczając
   pliki sesji; recovery copy sesji może pojawić się dopiero w release 2;
3. po spike'u używa dokładnie jednego kanonicznego mechanizmu konfiguracji API;
   nie modyfikuje równolegle `settings.xml` i `api_keys.json` bez dowodu, że wymaga
   tego przypięta wersja;
4. przed bezpośrednią zmianą plików wycisza Kodi, zachowuje owner/mode, zapisuje
   atomowo i weryfikuje wynik po restarcie;
5. traktuje lokalną stronę HTTP i port 50152 jako opcjonalną powierzchnię wykrytą
   w spike'u. Jeśli zostanie użyta, musi być związana z loopback, krótkotrwała i
   wyłączona po operacji;
6. ustawia wyłącznie zatwierdzoną allowlistę preferencji, m.in. język/region,
   zgodność z `inputstream.adaptive` i zakończony setup wizard;
7. restartuje Kodi w jawnej barierze i sprawdza publiczne wyszukiwanie oraz
   odtwarzanie;
8. zachowuje poprzednią działającą konfigurację i sesję, jeżeli nowa konfiguracja
   albo sieć nie przejdzie preflightu.

Dokładne identyfikatory ustawień zostaną zebrane z wersji przypiętej w manifeście.
Adapter nie może zgadywać nazw pól ani kopiować całego `addon_data` z urządzenia
wzorcowego.

### 3.3 Sesja OAuth i QNAP

Stan sesji dodatku jest dzielony na:

- wspólny secret set API: API key, client ID i client secret;
- per-device secret: minimalny, allowlistowany stan niezbędny do recovery sesji;
- niesekretne ustawienia wspólne: profil preferencji;
- prywatny inventory: `YOUTUBE_USER` i `YOUTUBE_EXPECTED_CHANNEL_ID`.

W release 1 wspólne klucze są dostarczane przez istniejący prywatny mechanizm, a
sesja pozostaje wyłącznie lokalna. Klucze API, client ID i client secret są
chronione w magazynie i transporcie, lecz po dostarczeniu do Kodi mogą zostać
odczytane z przejętego urządzenia. Dlatego klient używa minimalnych scope, API key
jest ograniczony do YouTube Data API, obowiązują quota alerts i procedura rotacji.

W release 2 wspólne klucze i recovery copy mogą być przechowywane przez magazyn
sekretów QNAP. Device Agent dostaje kopertę dla konkretnego enrollmentu. Inny
enrollment nie może pobrać ani odszyfrować koperty; nie oznacza to, że skopiowany
plaintext bearer token jest bezużyteczny poza urządzeniem.

Do czasu zaakceptowania ADR-0005 i wydania magazynu sekretów QNAP:

- wspólne klucze API mogą pochodzić z ignorowanego `.env` hosta;
- sesja pozostaje lokalna na urządzeniu i nie wchodzi do rutynowego backupu;
- portable state, favourites i wspólna rewizja Profile Sync nie zawierają tokenów;
- rollout nie może deklarować pełnej autonomii ani usuwać działającej sesji.

Po reinstallu tworzącym nowe enrollment domyślną ścieżką jest ponowny device flow.
Ewentualny wyjątek recovery wymaga osobnej akceptacji i sagi
`RECOVERY_PREPARED -> REWRAPPED -> VERIFIED -> OLD_REVOKED`; nie wolno wdrożyć go
przed restore drill. Brak poprawnego tokenu prowadzi do `AUTHORIZATION_REQUIRED`,
a nie do użycia `YOUTUBE_PASS`.

## 4. Zmiany implementacyjne

### Repo `mwoDevelop/kodi`

- rozszerzyć manifest domyślnych dodatków o `kodi-native-official`, per-addon
  dependency closure i dowód kwalifikacji;
- rozdzielić wspólną logikę manifestu od transportów: Android/ADB i
  Linux/Flatpak; oba transporty mają instalować przez Kodi, nie kopiować katalogu
  `addons/`;
- dodać wersjonowany adapter `tools/kodi_youtube_configure.py`; transporty
  uruchamiają ten sam kod wewnątrz Kodi, aby nie interpretować settings/tokenów na
  hoście;
- zarejestrować `youtube-oauth-v1` w `tools/kodi_private_addons.py`;
- rozszerzyć prywatny schemat profilu o referencje API, account hint i opcjonalny
  expected channel ID;
- włączyć wynik `youtube` do zredagowanego raportu `tools/kodi_ops.py` i później
  do raportu Device Agenta;
- dodać obserwację oficjalnych metadanych YouTube do watchdoga upstream bez
  automatycznego merge/promote;
- opisać konfigurację, ręczny device flow, revocation i recovery.

### Profile Sync Server i Control Plane

- w release 1 obsłużyć prywatne referencje `youtube-api-v1` (`global-user`) bez
  importowania tokenu sesji do QNAP;
- w release 2, po akceptacji ADR-0005, dodać `youtube-session-v1` (`device`) i
  powiązać recovery copy z logical device ID, enrollment ID, generacją, adapterem
  oraz rewizją stanu;
- upload recovery copy przyjmuje tylko własne enrollment przez mTLS, CAS i nonce;
  lokalna sesja jest aktywnym źródłem prawdy, QNAP tylko repliką recovery i nigdy
  nie nadpisuje nowszej sesji starszym backupem;
- eksportować wyłącznie minimalne pola wymagane przez zakwalifikowaną wersję,
  bez cache, historii i innych danych profilu;
- raportować osobno `CODE_READY`, `API_CONFIG_REQUIRED`, `API_READY`,
  `AUTHORIZATION_REQUIRED`, `CONSENT_PENDING`, `ACCOUNT_READY`,
  `SESSION_BACKUP_STALE`, `TOKEN_REFRESH_FAILED`, `QUOTA_EXCEEDED`, `CLOCK_SKEW`,
  `CONSENT_DENIED`, `NETWORK_UNAVAILABLE`, `REVOKED` i `UNQUALIFIED_UPSTREAM`, bez
  tokenu, e-maila, channel title ani channel ID;
- zapewnić rotację kluczy API bez usunięcia działającej sesji przed sukcesem;
- po spike'u zdecydować, czy stabilny interfejs dodatku pozwala zdalnie rozpocząć
  device flow. Jeśli nie, akcja tylko raportuje `AUTHORIZATION_REQUIRED`, a
  operator wykonuje autoryzację w GUI Kodi; żaden wariant nie przyjmuje hasła.

### Device Agent

- tryb `audit` wykrywa brak dodatku, drift wersji, brak API keys i stan sesji;
- produkcyjny `apply` zawsze wykonuje sagę `install addon -> restart -> verify
  schema -> apply API settings -> restart -> device flow/authorization required ->
  health`; journal pozwala bezpiecznie wznowić etap;
- ważna lokalna sesja działa przy niedostępnym QNAP;
- błędny/wycofany token nie resetuje pozostałego profilu Kodi;
- zmiana kluczy lub plików sesji jest serializowana z działaniem dodatku, aby
  uniknąć równoczesnego zapisu.

## 5. Kolejność realizacji i granice wydań

### 5.1 Release 1 — instalacja, API i lokalna sesja

1. Spike na BlueStacks: pobrać oficjalny ZIP, ustalić zależności, format ustawień,
   kanoniczny mechanizm API, pliki sesji, interfejs device flow i bezpieczny health
   check; zapisać jedynie nazwy pól, nigdy wartości.
2. Dodać natywną instalację i uruchomienie dodatku. Anonimowe odtwarzanie testować
   tylko jeśli spike potwierdzi, że jest wspierane; wyszukiwanie API nie jest bramą
   przed konfiguracją keys.
3. Dodać adapter wspólnych kluczy API i test redaction/rollback.
4. Skonfigurować klienta OAuth typu TV oraz wykonać ręczny device flow na
   BlueStacks dla konta wskazanego przez `YOUTUBE_USER`.
5. Powtórzyć od początku na X88, również z aktywnym OpenVPN.
6. Wykonać pełne E2E starych funkcji Kodi oraz review zmian.
7. Zakwalifikować transport i dependency closure Flatpak na NUC przed objęciem NUC
   statusem wspieranym.
8. Utworzyć jeden release polityki stable dopiero po sukcesie obu Android canary.
   Promocja kodu/API nie czeka na interaktywną zgodę urządzeń offline.
9. Zrobić rollout na pozostałe dostępne urządzenia. Każde urządzenie może
   wymagać osobnego, jawnego zatwierdzenia kodu Google.
10. Po teście repo, schematów i runbooków dowodzącym brak odczytu usunąć
    `YOUTUBE_PASS` z `.env`; `YOUTUBE_USER` pozostaje prywatną wskazówką operatora.

### 5.2 Release 2 — opcjonalne recovery sesji przez QNAP

1. Zaakceptować ADR-0005 i threat model bearer tokenu.
2. Zaimplementować upload minimalnej recovery copy przez mTLS/CAS oraz stan
   `SESSION_BACKUP_STALE`.
3. Udowodnić, że obce/revoked enrollment nie pobierze ani nie odszyfruje koperty;
   nie testować fałszywej tezy, że wykradziony plaintext token nie działa.
4. Przeprowadzić sagę recovery na tym samym logical device po reinstallu:
   `RECOVERY_PREPARED -> REWRAPPED -> VERIFIED -> OLD_REVOKED`.
5. Przetestować konflikt nowszej lokalnej sesji, uszkodzony/starszy backup,
   przerwanie operacji i pełny restore drill przed włączeniem funkcji domyślnie.

Nie wydajemy osobnej wersji dla każdego urządzenia. BlueStacks i X88 pracują na
tym samym kandydacie, a dopiero ich wspólny sukces otwiera stable.

## 6. Testy i bramy

### Testy statyczne i bezpieczeństwa

- poprawny origin `repository.xbmc.org`, kwalifikacyjny SHA-256 i kompletna
  per-platform dependency closure;
- skan ZIP-a i rozpakowanej zawartości ClamAV/Semgrep/Gitleaks;
- adapter odrzuca nieznaną wersję lub schemat plików;
- `YOUTUBE_PASS` nie jest odczytywany przez kod i canary secret nie pojawia się w
  logach, raportach, audit, backup metadata, argumentach procesów, plikach
  tymczasowych, ADB shared storage ani artefaktach CI;
- jeżeli spike użyje strony HTTP, jest dostępna tylko krótkotrwale na loopback;
- w release 2 koperta innego enrollmentu oraz replay starego assignmentu są
  odrzucane;
- testy dokumentują, że installed/TV client secret i API key nie zachowują
  poufności na przejętym urządzeniu.

### E2E na BlueStacks i X88

- instalacja na czystym profilu i poprawny origin;
- uruchomienie dodatku oraz anonimowe odtwarzanie tylko jeśli wspierane;
- zastosowanie kluczy API bez ich ujawnienia;
- device flow, potwierdzenie `YOUTUBE_EXPECTED_CHANNEL_ID`, dostęp do subskrypcji
  i odtworzenie materiału wymagającego zalogowanej sesji;
- odświeżenie tokenu oraz drugi przebieg `NO_CHANGE` bez ponownego kodu;
- wygasły device code, odpowiedź `slow_down`, odmowa zgody, `invalid_grant`,
  wyłączone API/quota exceeded, niezgodny Brand Account/channel ID i clock skew;
- restart Kodi i urządzenia, chwilowy brak QNAP oraz brak internetu;
- X88 z aktywnym VPN i dostępem do LAN poza tunelem;
- unieważnienie tokenu daje `AUTHORIZATION_REQUIRED`, bez kasowania innych
  ustawień Kodi;
- upgrade N -> N+1 zachowuje ważną sesję albo zatrzymuje rollout przed stable;
- przerwanie atomowego zapisu i próba równoczesnego zapisu przez dodatek;
- w release 1 reinstall kończy się `AUTHORIZATION_REQUIRED`; testy recovery i
  negatywnego dostępu do koperty należą dopiero do release 2;
- pełna regresja Umbrella/MwoScrapers, Rapideo, napisów, favourites i Profile Sync.

Przed rolloutem na NUC te same bramy instalacji, ustawień i OAuth przechodzą na
Kodi Flatpak. Sukces Android nie jest automatycznie dowodem zgodności Flatpak.

### Flota po stable

- instalacja i konfiguracja na Sony TV, Bedroom TV oraz obu profilach NUC, gdy są
  dostępne;
- urządzenie offline otrzymuje `DEFERRED` i konwerguje po powrocie;
- raport rozróżnia gotowość kodu/API, konta, backupu sesji oraz błędy sieci/quota;
- rollout kodu może być `COMPLETE`, gdy wymagany zbiór online ma `CODE_READY` i
  `API_READY`; rollout konta jest osobną oceną i wymaga `ACCOUNT_READY` albo jawnego
  `PARTIAL` dla urządzeń oczekujących na zgodę.

## 7. Aktualizacje upstream

- watchdog porównuje oficjalne metadane repo Kodi oraz źródłowy release/tag z
  kwalifikowanym manifestem;
- zmiana tworzy PR aktualizujący wyłącznie manifest kwalifikacji, hash, zależności,
  schemat ustawień/sesji i raport malware; ZIP nie trafia do repo mwoDevelop;
- nie ma automatycznego merge, ponieważ zmiana formatu tokenów może wymagać
  reautoryzacji;
- Kodi nie może zostać uznane za zgodne tylko na podstawie nowszego numeru wersji.
  Drift auto-update jest audytowany, a decyzja to szybka kwalifikacja nowej wersji
  lub bezpieczne zatrzymanie dalszego rolloutu; nie wykonujemy ślepego downgrade'u
  działającej sesji;
- kandydatem jest dokładna rewizja manifestu i oficjalny artefakt pobrany po HTTPS,
  nie pakiet w repo testing mwoDevelop;
- po kwalifikacji obowiązuje canary BlueStacks/X88 i jedna promocja polityki
  stable. Zmiana schematu OAuth blokuje promocję do czasu testu migracji lub
  reautoryzacji.

## 8. Rollback i recovery

- przed zmianą adapter zachowuje prywatny backup zarządzanych plików YouTube;
- błąd ustawień przywraca poprzednie pliki i restartuje Kodi;
- brak sieci, QNAP lub chwilowy błąd refreshu nie usuwa działającego tokenu;
- revocation jest jawną, wznawialną sagą
  `REVOCATION_REQUESTED -> GOOGLE_REVOKED -> LOCAL_REMOVED -> RECOVERY_RETIRED`;
  częściowa awaria ma jawny status i retry;
- w release 2 usunięcie dodatku nie usuwa recovery copy przed końcem retencji;
- pełne usunięcie konta z urządzenia wymaga osobnej, audytowanej operacji.

## 9. Kryteria zakończenia

Plan jest zrealizowany, gdy:

1. YouTube jest domyślnie instalowany z oficjalnego repo Kodi na wszystkich
   dostępnych urządzeniach;
2. BlueStacks i X88 przeszły wszystkie bramy na jednym kandydacie;
3. wspólne API keys i per-device tokeny nie występują w repo ani logach;
4. `YOUTUBE_PASS` nie jest używany i został usunięty po zakończeniu migracji;
5. każde urządzenie używające konta zostało jawnie autoryzowane device flow;
6. drugi przebieg release 1 daje `NO_CHANGE`, a reinstall jawnie wymaga ponownej
   autoryzacji;
7. dla opcjonalnego release 2 inne enrollment nie może pobrać ani odszyfrować
   cudzej koperty, a restore drill tego samego logical device działa;
8. pełne stare E2E Kodi oraz CI są zielone;
9. dokumentacja z sekcji 10 istnieje, jej przykłady przechodzą testy i opisuje
   instalację, autoryzację, utratę tokenu, revocation, upgrade oraz granicę recovery;
10. po pomyślnym stable wykonano rollout całej dostępnej floty i zapisano datowany
    raport E2E.

## 10. Plan uzupełnienia dokumentacji

Dokumentacja jest częścią odpowiedniego PR i bramy release, a nie pracą odkładaną
po wdrożeniu. Żaden przykład nie zawiera prawdziwych identyfikatorów konta,
device-code, API keys ani tokenów.

| Dokument | Zakres zmiany |
|---|---|
| `docs/youtube.md` | Główny runbook: Google Cloud project, YouTube Data API, consent screen, klient TV, ograniczenia API key, minimalne scope, konfiguracja dodatku, device flow, wybór konta/Brand Account, quota, revoke i reauth. |
| `README.md`, `docs/README.md` | Status funkcji, ograniczenia release 1/2 i link do runbooka oraz review. |
| `docs/kodi-private-profile.md` | Przykład `youtube-oauth-v1`, prywatne referencje API, `YOUTUBE_USER`, zakaz `YOUTUBE_PASS`, lokalny stan sesji i granica recovery. |
| `docs/kodi-operations.md` | Komendy audit/apply/canary/rollout, statusy `AUTHORIZATION_REQUIRED` i `PARTIAL`, rollback oraz przykładowe zredagowane wyniki. |
| `docs/scheduled-processes.md` | Oficjalne źródła upstream, częstotliwość watchdoga, PR bez auto-merge, alarmy schema/quota i obsługa driftu auto-update. |
| `docs/control-plane/threat-model.md` | Bearer-token risk, możliwość odczytu API/client keys na przejętym urządzeniu, minimalne scope oraz ograniczenia koperty. |
| przyszłe `docs/control-plane/secrets.md` | Typy `youtube-api-v1`/`youtube-session-v1`, CAS, envelope, rotacja i release 2 recovery. |
| `docs/control-plane/device-bootstrap.md` | Instalacja Android/Flatpak, wymagane capabilities, interaktywny device flow i ponowna autoryzacja po reinstallu. |
| `docs/control-plane/backup-restore-dr.md` | Brak tokenu w release 1 backup, opcjonalna saga release 2 i restore drill. |
| `docs/control-plane/incident-response.md` | Wyciek API key/client secret/tokenu, revocation saga, utrata konta i recovery. |
| `docs/control-plane/troubleshooting.md` | `invalid_grant`, wygasły kod, quota, API disabled, Brand Account, VPN, DNS i clock skew. |
| README Profile Sync/Device Agent | Capabilities, wersje adaptera i maszyna stanów code/API/account/recovery. |
| `docs/e2e-results/README.md` | Format dowodu bez e-maila, channel title/ID, device-code oraz tokenów. |
| dokumentacja schematów i ADR-y | `install_mode`, dependency closure, secret types, profile adapter, statusy, zgodność N/N-1 i decyzja ADR-0005. |

Bramy dokumentacji:

- każdy przykład CLI działa na fixture lub w `--dry-run` bez sekretów;
- CI sprawdza linki, schematy, przykładowe payloady i redakcję canary secret;
- `tests/test_documentation.py` pozostaje obowiązkowy;
- release 1 wymaga przejścia runbooka od czystego Kodi do `ACCOUNT_READY` na
  BlueStacks i X88;
- release 2 wymaga niezależnego przejścia runbooka recovery od nowego enrollmentu
  do `VERIFIED`, z późniejszym `OLD_REVOKED`.

## 11. Szacunek

- instalacja, manifesty, zależności i adapter API: 1–2 dni;
- canary OAuth, testy VPN, token lifecycle i rollback: 1–3 dni;
- integracja z niewydanym jeszcze QNAP secrets/Device Agent: część odpowiednich
  faz głównego planu, około 2–4 dodatkowych dni po udostępnieniu magazynu sekretów;
- rollout pozostałej floty: zależny od dostępności urządzeń i osobnych zgód Google,
  zwykle 1–2 godziny pracy technicznej plus czas interaktywnej autoryzacji.
