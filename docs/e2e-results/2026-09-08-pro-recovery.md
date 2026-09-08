# Odblokowanie automatyzacji po GitHub Pro — 8 września 2026

## Plan i zakres

1. Potwierdzić Pro i wykonać kontrolowane próby zablokowanych audytów/CI.
2. Oddzielić historyczne błędy rozliczeń od nowej awarii providera.
3. Opublikować i wdrożyć wyłącznie przeskanowane poprawki serwerów, z backupem.
4. Odświeżyć panel po wdrożeniu, porównać GitHub, QNAP i DOM przez CDP.
5. Nie zmieniać budżetów ani omijać wymaganych reviews. Dalsza zmiana kadencji
   i poprawka dodatku wymagają osobnych zaakceptowanych PR.

## Wyniki przed wdrożeniem

- Pro aktywny ($4/mies.). Testowe zadania ruszyły i upload raportów działa.
- Audyt bezpieczeństwa mwoScrapers: run **34221778077 SUCCESS**, discovery:
  **34221780171 SUCCESS**. Oba panel pokazuje już jako `OK` po refresh.
- Promocja Umbrelli: **34222138702 SUCCESS**, panel `DELAYED` → `OK`.
- Provider health **34221782367 FAILED**: nie billing. Torrentio, Comet, Torz,
  MediaFusion i EZTV przeszły; PirateBay nie zwrócił filmów, odcinki działają.
- Potwierdzenie PirateBay: zapytanie z rokiem zwraca sentinel id=0; bez roku
  Matrix daje 31 ścisłych dopasowań. Przygotowany PR **mwoScrapers #32**
  (0.2.2), bez rozluźnienia filtrów i bez zmiany próbek/progów. 83 testy + ruff
  PASS, live PirateBay movie-a 31, movie-b 0, episode-a 9, episode-b 27.
- PR mwoScrapers **#31**: CI zielone, ale obowiązuje ruleset wymagający jednego
  review (`REVIEW_REQUIRED`). Nie usunięto ani nie ominięto reguły. Cotygodniowe
  crony i nowy provider pozostają niewdrożone do czasu rozstrzygnięcia blokady.
- Backend Profile Sync **#20** scalony, 54 testy PASS. Obraz 0.10.1 z runu
  **34222380562** (test, malware, build multiarch, verify-release SUCCESS):
  `sha256:2f45b391f6386c042418caa91ccb81c53cf8ecae709192e09feeb0ef1fae2ad8`.
- Control Plane **#26** scalony, 83 testy PASS. Wersja 0.12.2 dodaje parser
  tygodniowych cronów (niedziela=0, UTC, brak fałszywych dziennych opóźnień).
  Obraz z runu **34222727817**, wszystkie bramy SUCCESS:
  `sha256:a3ca46e9336aa4d7713d7c3611bb9988677b876e3c4e87f2a9a180a34d056329`.
- Oba raporty bezpieczeństwa mają wynik `clean`; hash raportu i wejść obrazu
  sprawdzono z approval dla dokładnych commitów i digestów. Pozostałe trzy
  obrazy nie są zmieniane. Katalogi cronów w tym wdrożeniu nadal są codzienne.
- Backup backendu: `before-pro-recovery-20260908`, 7 blobów, SHA bazy
  `9967483c333f102351b65cdb78def06ec8f0a9fe77133eb2870c6b5187a8ab49`.
  Kopia prywatna `.kodi-private/backups/before-pro-recovery-20260908.sqlite`.
- Bedroom TV: TCP/ADB timeout, przypisanie `PENDING`, brak rolloutu — DEFERRED.
  Pozostałe pięć urządzeń ma zastosowane przypisania. Sam heartbeat nie jest
  dowodem aktualnie działającego Kodi ani testem odtwarzania.

## Odbiór wdrożenia

Wymagany odczyt wersji/health i zachowanych przypisań po deployu, drugi deploy
`NO_CHANGE`, E2E API/mTLS, odświeżenie DOM i publiczne repo. Stan końcowy zostanie
dopisany po rzeczywistym wdrożeniu; powyższe nie jest jeszcze dowodem deployu.
