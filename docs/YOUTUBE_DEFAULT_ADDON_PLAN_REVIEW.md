# Niezależny review planu domyślnego dodatku YouTube

Data: 2026-08-17

Zakres: spójność i wykonalność
[`YOUTUBE_DEFAULT_ADDON_PLAN.md`](../YOUTUBE_DEFAULT_ADDON_PLAN.md) względem
istniejącego instalatora dodatków, Profile Sync, QNAP Control Plane, Device Agenta
oraz zaakceptowanych ADR-ów.

Reviewer nie edytował planu. Poniższe rozstrzygnięcia zastosowano następnie w
osobnym kroku.

## Wniosek

Kierunek instalacji oficjalnego dodatku i zakaz używania `YOUTUBE_PASS` są
poprawne. Pierwotna wersja nie była jednak gotowa do implementacji centralnego
recovery OAuth: przeceniała ochronę koperty per enrollment i uzależniała pierwszy
release od niezaakceptowanego jeszcze modelu importu sekretów. Po korektach
release 1 może objąć natywną instalację, API i lokalną sesję; QNAP recovery jest
osobnym release 2 po akceptacji ADR-0005.

## Ustalenia i rozstrzygnięcia

| Priorytet | Uwaga review | Rozstrzygnięcie w planie |
|---|---|---|
| P0 | Koperta per enrollment ogranicza dystrybucję, lecz Google refresh token pozostaje bearer secretem możliwym do skopiowania po odszyfrowaniu. | Usunięto obietnicę kryptograficznego związania tokenu z urządzeniem; test cross-device dotyczy dostępu do koperty, a threat model obejmuje przejęty root. |
| P0 | Restore po reinstallu przeczył głównemu planowi i proponowanemu ADR-0005. | Release 1 nie backupuje sesji i domyślnie wymaga ponownego device flow; recovery przesunięto do release 2 z osobną sagą i restore drill. |
| P1 | Plan mieszał przypięty ZIP z instalacją i auto-update oficjalnego repo. | Wybrano `kodi-native-official`: Kodi instaluje kod, a przypięty ZIP jest dowodem kwalifikacji, nie pakietem publikowanym przez mwoDevelop. |
| P1 | Adapter ustawień mógł działać przed instalacją dodatku. | Produkcyjna saga ma kolejność install, restart, schema check, API apply, restart, auth, health. |
| P1 | Nie opisano uploadu tokenu do QNAP, konfliktów i replay. | Release 2 wymaga własnego endpointu enrollmentu, mTLS, CAS/nonce, minimalnego eksportu i stanu `SESSION_BACKUP_STALE`; lokalna sesja jest źródłem aktywnym. |
| P1 | Zdalne rozpoczęcie device flow było niepotwierdzonym założeniem. | Spike ma bramę go/no-go; fallback to `AUTHORIZATION_REQUIRED` i ręczna operacja w GUI Kodi. |
| P1 | Plan zakładał równoczesne modyfikowanie `settings.xml` i `api_keys.json` oraz stałą powierzchnię HTTP. | Spike wybiera jeden kanoniczny format; zapis jest wykonywany przy wyciszonym Kodi, atomowo i z zachowaniem uprawnień; HTTP jest opcjonalne i loopback-only. |
| P1 | `inputstream.adaptive` potraktowano jak wspólną zależność Python. | Dodano per-addon closure i macierz Kodi/platform/ABI; binarne capability jest instalowane natywnie i kwalifikowane osobno na Android/Flatpak. |
| P1 | Sugerowano pełną poufność wspólnych kluczy po wdrożeniu. | Dodano minimalne scope, ograniczenie API key, quota alerts, rotację i jawne ryzyko odczytu na przejętym urządzeniu. |
| P1 | Rollout mieszał gotowość kodu z interaktywną autoryzacją konta. | Rozdzielono statusy code, API, account i recovery oraz kryteria `COMPLETE`/`PARTIAL`. |
| P1 | Revocation opisano jak jedną atomową operację. | Dodano wznawialną sagę Google, local i recovery z jawnym stanem częściowym. |
| P1 | Nie było drogi oficjalnego upstream do stable bez publikacji w testing. | Kandydatem jest rewizja manifestu plus oficjalny artefakt; PR zawiera hash, zależności, schema diff i malware report. |
| P1 | Testy nie obejmowały typowych awarii OAuth i API. | Dodano expired code, `slow_down`, deny, `invalid_grant`, quota/API disabled, Brand Account, clock skew, concurrency i Flatpak. |
| P2 | Channel ID opisano jak publiczne ustawienie. | `YOUTUBE_EXPECTED_CHANNEL_ID` jest prywatnym inventory i nie trafia do raportów. |
| P2 | Anonimowe wyszukiwanie było niepotwierdzonym wymaganiem. | Rozdzielono start/anonimowe odtwarzanie od wyszukiwania po konfiguracji API. |
| P2 | Usunięcie `YOUTUBE_PASS` nie miało bramy. | Usunięcie następuje po teście repo, schematów i runbooków dowodzącym brak odczytu. |

## Zakres dokumentacji

Review zalecił centralny `docs/youtube.md` oraz aktualizację instrukcji operacji,
profilu prywatnego, procesów cyklicznych, threat modelu, bootstrapu, DR, incident
response, troubleshooting, dokumentacji schematów i indeksu E2E. Pełna macierz,
odpowiedzialność PR-ów i bramy CI znajdują się w sekcji 10 poprawionego planu.

## Elementy zachowane bez zmian kierunku

- oficjalne repo Kodi, bez forka i bez kopii YouTube w repo mwoDevelop;
- zakaz używania hasła Google;
- jeden kandydat testowany najpierw na BlueStacks, potem X88;
- allowlistowany adapter zamiast kopiowania całego `addon_data`;
- zachowanie działającej lokalnej sesji przy awarii QNAP;
- brak automatycznego merge/promote upstream;
- regresja pozostałych funkcji Kodi oraz osobna zgoda Google na urządzeniu.
