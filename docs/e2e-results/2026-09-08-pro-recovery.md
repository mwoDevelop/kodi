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
  crony i poprawka providera pozostają niewdrożone do czasu rozstrzygnięcia blokady.
- Backend Profile Sync **#20** scalony, 54 testy PASS. Obraz 0.10.1 z runu
  **34222380562** (test, malware, build multiarch, verify-release SUCCESS):
  `sha256:2f45b391f6386c042418caa91ccb81c53cf8ecae709192e09feeb0ef1fae2ad8`.
- Control Plane **#26** scalony, 83 testy PASS. Wersja 0.12.2 dodaje parser
  tygodniowych cronów (niedziela=0, UTC, brak fałszywych dziennych opóźnień).
  Obraz z runu **34222727817**, wszystkie bramy SUCCESS:
  `sha256:a3ca46e9336aa4d7713d7c3611bb9988677b876e3c4e87f2a9a180a34d056329`.
- Test kandydata PirateBay **34223536138 SUCCESS** ujawnił błąd panelu:
  sukces na gałęzi PR był mylnie uznawany za naprawę zadania produkcyjnego.
  Control Plane **#27** (0.12.3) filtruje ręczne przebiegi po gałęzi ostatniego
  crona, ponownie sprawdza odpowiedź i odrzuca niezgodny stan z cache.
  92 testy PASS; odtworzenie z prawdziwym API GitHub potwierdza odrzucenie
  sukcesu kandydata przy nadal nieudanym zadaniu na `main`.
  Docelowy obraz z runu **34224571699** zastępuje przygotowany 0.12.2:
  `sha256:d3874682ba53ee1cdfe015fb3b614f1ba10aff19a4b2d28489182c343ba51748`.
- Raporty bezpieczeństwa mają wynik `clean`; hash raportu i wejść obrazu
  sprawdzono z approval dla dokładnych commitów i digestów. Pozostałe trzy
  obrazy nie są zmieniane. Katalogi cronów w tym wdrożeniu nadal są codzienne.
- Backup backendu: `before-pro-recovery-20260908`, 7 blobów, SHA bazy
  `9967483c333f102351b65cdb78def06ec8f0a9fe77133eb2870c6b5187a8ab49`.
  Kopia prywatna `.kodi-private/backups/before-pro-recovery-20260908.sqlite`.
- Bedroom TV: TCP/ADB timeout, przypisanie `PENDING`, brak rolloutu — DEFERRED.
  Pozostałe pięć urządzeń ma zastosowane przypisania. Sam heartbeat nie jest
  dowodem aktualnie działającego Kodi ani testem odtwarzania.

## Odbiór wdrożenia

Preflight wykazał działające QPKG 0.3.4 poza tym zakresem; stable kod zawiera
pakiet 0.3.2. Dodano i przetestowano ochronę przed downgrade podczas aktualizacji
kontenerów. Istniejąca nowsza brama jest weryfikowana i zachowywana, a jej
niepowiązane zmiany lokalne pozostają nietknięte. Poprawiono brak linku do tego
raportu wykryty w pierwszym pełnym CI promocji.

### Wynik — 8 września, 12:27 UTC

- PR **kodi #359** scalony do `main` (`49354ffc0dc579805fe52aae1254cf8c406d2ee3`),
  CI **34225428790**, **34225434411** i ponowny test `main` **34225824182** SUCCESS.
- Skrypt `tools/qnap_images.py deploy profile-sync control-plane` wdrożył oba
  obrazy. Odczyt metadanych pakietów w działających kontenerach: Profile Sync
  **0.10.1**, Control Plane **0.12.3**. Identyfikator stable:
  `227c2ad3142831233ddc6898e7d9baba25bfd26d6fe67ef529401e13367fa80b`.
- Ponowne identyczne wywołanie: **NO_CHANGE** dla obu serwisów.
- Wszystkie siedem kontenerów QNAP: `running` i `healthy`. Watchdog ma gotowy
  kolektor (`READY`), ale monitorowany wynik `FAILED` dla jednego zadania —
  to osobne informacje, nie sprzeczność z kontrolą zdrowia procesu.
- QPKG nadal **0.3.4**, SHA skryptu uruchomieniowego przed/po identyczne:
  `343cab2424e2cfc77e7e1972ce09c642f01d7a51af2b3fac1422135cf82b6ed0`.
  Nie zmieniano skrótu ani sesji logowania w przeglądarce.
- Pełne lokalne testy projektu: **822 PASS**. Backend: **54 PASS**. Panel:
  **92 PASS**. E2E `control_plane_readonly.py`: PASS (API mTLS, odrzucenie
  braku certyfikatu i niedozwolonych mutacji, cykl publikacji konfiguracji).
  `control_plane_dashboard_cdp.py`: PASS na izolowanej makiecie.
- Dodatkowo produkcyjne API: `POST /api/v1/refresh` HTTP 200; odczyt dashboardu
  pokazuje osiem źródeł `OK`, 11 z 12 procesów GitHub `OK`. Audyt zdrowia
  providerów po odrzuceniu gałęzi testowej wrócił z fałszywego `OK` do
  **FAILED**, zgodnie z produkcją. Efektywny run to **34210497296**, nie run
  kandydata **34223536138**. Nieudana ręczna próba na `main` **34221782367**
  nie jest uznawana przez obecną politykę za udaną remediację crona.
- Produkcyjny panel przez CDP 9222: kliknięcie „Odśwież stan”,
  `aria-busy=true` → `false`, brak błędu, wiersz provider health **FAILED**.
  Wcześniej otwarta karta wymagała odświeżenia danych; sama aktualizacja obrazu
  nie zmienia już wyrenderowanej tabeli w przeglądarce.
- Przypisania konfiguracji zachowane: pięć urządzeń `APPLIED` + `FRESH`,
  Bedroom TV `PENDING` + `STALE`. Ponowny test ADB Bedroom TV: timeout.
  Sony, X88 i NUC są osiągalne. Nie wdrażano dodatków na urządzenia.

### Otwarte kroki — bez fałszywego potwierdzenia sukcesu

1. **Review mwoScrapers #31 i #32**: oba mają zielone testy, lecz wymagają
   zatwierdzenia przez uprawnionego reviewera albo jawnej decyzji właściciela
   o zmianie samego wymogu approvals. Nie użyto obejścia administracyjnego.
2. Po scaleniu #32 uruchomić health probe na `main`, potwierdzić rzeczywisty
   wynik i odświeżyć watchdog/panel. Obecne `FAILED` watchdoga nie oznacza
   awarii procesu kontenera. Historyczny bezpiecznik `BILLING_BLOCKED` dla tego
   zadania nie jest dowodem nadal blokowanego konta Pro; czeka na pozytywną
   próbę na właściwej gałęzi. Nie usunięto ręcznie rejestru prób.
3. Po scaleniu #31 dokończyć **kodi #360 (draft)**: zmiana katalogów kadencji,
   budowa i promocja obrazu watchdoga oraz reconcile konfiguracji panelu.
   Codzienne zadania nie zostały przedwcześnie oznaczone jako cotygodniowe.
4. Bedroom TV: po odzyskaniu łączności potwierdzić zastosowanie przypisania
   i heartbeat. Nie uznawać `STALE` za pewny dowód wyłączonego urządzenia.

### Powtórzenie kontroli

W katalogu głównym projektu, z prywatną konfiguracją i certyfikatami operatora:

```bash
.venv/bin/python tools/qnap_images.py --references .env status
.venv/bin/python tools/qnap_images.py --references .env deploy profile-sync control-plane
.venv/bin/python tests/e2e/control_plane_readonly.py
.venv/bin/python tests/e2e/control_plane_dashboard_cdp.py
.venv/bin/python tools/smoke_public.py
```

Pierwsze dwa polecenia dotyczą QNAP. Test `readonly` uruchamia izolowane
serwisy lokalne; test CDP używa własnej strony testowej, nie zmienia danych
produkcyjnych. Produkcyjny panel należy dodatkowo odświeżyć i porównać z
przebiegami GitHub na gałęziach monitorowanych przez katalog.
