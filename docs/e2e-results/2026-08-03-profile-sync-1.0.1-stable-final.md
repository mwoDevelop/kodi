# Ostateczne wdrożenie Profile Sync 1.0.1 stable

Data: 2026-08-03

Niezmienna migawka testing
`e12d6b8ba1839cbe5ed7e43c3c3e4a0cf7208e0fb12075471dcdcd44460055d3` została certyfikowana
i promowana bez konieczności przebudowywania archiwów komponentów. Publiczne archiwum
stable Profile Sync ma SHA-256
`99b05e41c24e3e1c4d1bad83ccb7dbe0a618441065b81ae36cc070b8fae0eb4e`.
`repository.mwodevelop` celowo pozostaje w wersji `1.0.0`.

## Udostępnij dowody

- przebieg certyfikacji urządzenia `30847171206` przekazany na BlueStacks1 i X88 Pro 20;
- Promocja stable `30847934079` zaliczona;
- sprawdzona promocja obejmująca tylko blokadę PR `#108` została połączona;
- Uruchomienie wdrożenia stable `30848088877` zakończone sukcesem;
- publiczne bajty stable odtwarzają certyfikowany Profile Sync SHA-256;
- deterministyczna kompilacja lokalna i kompletny zestaw regresji przekazany z `299
  passed`.

W ramach certyfikacji wykryto dwie wady wdrożenia niezależne od urządzenia. Umbrella nie
zawsze był powiązany z zewnętrznym dostawcą `script.module.mwoscrapers`, a wdrożenie
bezprzewodowego kandydata Kodi mogło spowodować utratę pakietu EventServer lokalnego
urządzenia. Konfiguracja dostawcy teraz jawnie włącza i wybiera mwoScrapers. Wdrażanie
sieci LAN sprowadza się teraz do polecenia EventServer wysłanego przez hosta. Sondy
współbieżnej synchronizacji produkcyjnej korzystają również z plików konfiguracyjnych
trybu 0600 z zakresem wywołania, zapobiegając ściganiu się tożsamości jednego urządzenia
z inną. Pierwsza poprawka została wydana przed certyfikacją; poprawki wiązki przewodów
wdrożeniowych zostały połączone w PR `#109` po pozytywnym przejściu testów regresji
lokalnej i CI.

## Matryca urządzenia stable

| Urządzenie | Profile Sync | Profil przenośny | Umbrella | WatchNixtoons2 |
| --- | --- | --- | --- | --- |
| BlueStacks1 | 1.0.1, `NO_CHANGE` | przejść | certyfikowane wyszukiwanie i odtwarzanie | certyfikowane odtwarzanie |
| X88 Pro 20 | 1.0.1, `NO_CHANGE` | przejść | certyfikowane wyszukiwanie i odtwarzanie | certyfikowane odtwarzanie |
| Sony TV | 1.0.1, `NO_CHANGE` | przejść | wyszukiwanie, przepustka do odtwarzania Sintel i Breaking Bad | przepustka odtwarzania |
| Bedroom TV | 1.0.1, `NO_CHANGE` | przejść | wyszukiwanie, przepustka do odtwarzania Sintel i Breaking Bad | przepustka odtwarzania |

Wszystkie cztery instalacje Android wykorzystują rejestrację produkcyjną na kanale
`home-stable` z tą samą aktywną wersją
`sha256:4c7d728d214a6d31d1d277d2fd6b30957bc2d07d873648df5e0ffda69a1c905e`, unikalnymi
tożsamościami logicznymi, walidacją HTTPS CA i brakiem oczekujących raportów. Każdy ma
tych samych osiem ulubionych i siedem przenośnych wpisów WatchNixtoons2, bez brakujących
grafik. Wszystkie pięć komponentów mwoDevelop jest udostępnianych i posiadanych przez
`repository.mwodevelop`; `repository.mwodevelop.testing` jest nieobecny.

Bedroom TV początkowo zawieszał Kodi w Android `surfaceDestroyed`, gdy Streamer Google
TV był uśpiony. Kontrola ABI wykazała zgodność 32-bitowej kompilacji Android i Kodi.
Wybudzenie wyświetlacza i uruchomienie jawnej aktywności Kodi usunęło awarię; nie była
wymagana ponowna instalacja ani mutacja profilu. Końcowe testy Sypialni rozpatrzono i
obserwowano Sintel przez 15 sekund, rozwiązano i obserwowano Breaking Bad S01E01 przez
15 sekund oraz grano przedmiotem WatchNixtoons2 przez 15 sekund.

Dwa podmioty główne Linux/Flatpak NUC zostały ponownie sprawdzone, ale ich transport SSH
był niedostępny. Nie są one zgłaszane jako zaliczone i nie unieważniają ukończonej
wersji Android.

## Kopia zapasowa produkcji

Po ostatecznej konwergencji QNAP stworzył spójną epokę online zawierającą bazę danych
SQLite i sześć obiektów BLOB z adresowaną zawartością. Epoka została pobrana,
zaszyfrowana poza NAS za pomocą AES-256-GCM i zapisana lokalnie jako prywatna kopia
zapasowa w trybie 0600. Wiertło odszyfrowujące i otwierające odtworzyło dokładny skrót
tekstu jawnego; SQLite `integrity_check` zwrócił `ok` z siedmioma rejestracjami. W tym
raporcie nie są zatwierdzane żadne dane uwierzytelniające, token, źródło podpisu ani
prywatna ścieżka kopii zapasowej.

Prywatne raporty urządzeń do odczytu maszynowego pozostają poza kontrolą wersji w ramach
`.kodi-private/e2e` i `.kodi-private/profile-sync-production/e2e`.
