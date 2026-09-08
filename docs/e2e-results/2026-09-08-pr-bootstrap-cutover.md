# Bootstrap PR i tygodniowy monitoring — 8 września 2026

## Zgoda i zakres

Użytkownik wyraźnie zgodził się na jednorazowy owner bypass mwoScrapers
#31–#34. To operatorskie wdrożenie po niezależnym review i CI, nie approval
wystawiony przez Copilota ani samodzielne zatwierdzenie polityki przez bota.
Jeden wymagany approval, strict base, rozwiązywanie rozmów, usuwanie starych
reviews i obowiązkowe `test`/`malware-scan` pozostają aktywne dla przyszłych PR.

## Kolejność

1. Scalenie #33; przestawienie zależnego #34 na `main`, aktualizacja bazy i CI.
2. Po #34 aktualizacja #31; skoordynowane scalenie tygodniowych cronów i Kodi
   #360 z lockiem obrazu watchdoga. Następnie deploy i reconcile katalogu panelu.
3. Aktualizacja #32 do nowego `main`, ponowne CI i operatorskie scalenie.
   Ręczny health probe na dokładnym produkcyjnym commicie; odczyt panelu.
4. Odczyt zabezpieczeń po merge, test zaufanego kontrolera w trybie bez mutacji.
   Kwalifikacja pakietu Kodi i publikacja stable pozostają osobną bramą urządzeń.

## Dowody przygotowania

- #33: merge `b7b3981468b53af38dcb0e01b3b37ec864538ca9`, 17:00:10 UTC.
- #34 po aktualizacji bazy: `b58ff4819edaa1ad697efecb84ef412c7ee89daa`;
  lokalnie 177 testów PASS. Wymagane ponowne CI przed merge.
- Przed cutover siedem kontenerów QNAP `running`/`healthy`. Monitorowane błędy
  są osobną osią stanu; nie były kasowane ręcznie.
- Przygotowany approval obrazu watchdoga z runu **34235470320**; SHA raportu
  `9b57080d00519b0874468a06ca9588e93bbf1c63aab3dccd78f67390d0de68a0`.
  `qnap_lock.py compose` potwierdził historię i zgodność inputów pięciu usług.
  Jedynym zmienianym digestem jest watchdog
  `sha256:db5513a0334969dbb3671da6cf32b9621fd0172ec78e0cdb0f1f3d5b771760c3`.
  Pozostałe cztery approval są ponownie wykorzystane bez rebuilda.
- Testy narzędzi GitHub, watchdoga i locka QNAP: **40 PASS**.
- X88: osiągalny, Kodi 21.3 działa. Pierwsza próba BlueStacks: błąd transportu
  ADB; wymaga ponownego zestawienia połączenia przed oceną dostępności.

## Status odbioru

Bootstrap i wdrożenie usług zakończone; publikacja dodatku stable pozostaje
osobnym etapem. Zastane zmiany QTS Gateway nie są częścią commitów bootstrapu.

| PR | Scalony commit | Dowód aktualnego CI |
|---|---|---|
| mwoScrapers #33 | `b7b3981468b53af38dcb0e01b3b37ec864538ca9` | 34236814188 SUCCESS |
| mwoScrapers #34 | `57a9d327d0016f99cd70b7c9828580c96ea46583` | 34254496187 attempt 2 SUCCESS |
| mwoScrapers #31 | `cf430c155cee2865fa00909911c53b737a1a6613` | 34255413045 SUCCESS |
| mwoScrapers #32 | `6bee1f1a4244c5032970ba551c8ffed2f9b75dd0` | 34255873275 SUCCESS |
| Kodi #360 | `ded68bb58c5340b23ebf89404eba0ebd251901fe` | 34254882139, 34254873012 SUCCESS |

W #34 pierwszy skan przeszedł, lecz finalizacja artefaktu przez GitHub zwróciła
403. Jedno ponowienie nieudanych jobów zakończyło się sukcesem; brama nie była
pomijana. Konflikt README w #32 rozwiązano zachowując opis poprawki i automatu.

### Produkcyjny wynik i QNAP

- Jawny health `main` **34256251932 SUCCESS** na `6bee1f1...`: wszystkie sześć
  providerów PASS. CI `main` **34256248267 SUCCESS**. Wynik gałęzi PR nie był
  używany jako dowód naprawy produkcyjnego audytu.
- Watchdog wdrożony z zatwierdzonego locka `5b2c8f5c...`; Control Plane zachował
  digest, ale został uzgodniony z nowym katalogiem przez `--reconcile`.
- Drugie zwykłe `qnap_images.py deploy upstream-watchdog control-plane`:
  **NO_CHANGE** dla obu. Siedem kontenerów `running` i `healthy`.
- Panel przez API i prawdziwy Chrome CDP pokazuje crony `23 4 * * 1` i
  `41 4 * * 1` jako OK; codzienny health `3 5 * * *` również OK.
  Osiem źródeł danych OK; przycisk odświeżenia `aria-busy=true` → `false`,
  pusty komunikat błędu. Pierwsza automatyczna próba logowania nie ukończyła
  nawigacji; powtórzenie na gotowej stronie zakończyło się sukcesem. Nie
  resetowano konta ani nie zmieniano credentiali/certyfikatów.
- Naturalny odczyt watchdoga o **17:29:43 UTC** usunął historyczny
  `BILLING_BLOCKED` i błąd provider health bez kasowania rejestru.
  W tej migawce trwała publikacja Pages **34256532116**; watchdog zachowuje
  alarm do jej sukcesu, a panel poprawnie pokazuje sam workflow jako RUNNING.
  Nie jest to awaria kontenera. Kolektor odświeża całość co 900 sekund.
- Bedroom TV: brak dostępu ADB; przypisanie nadal oczekujące. Ostrzeżenie
  `FLEET_ASSIGNMENT_PENDING` pozostaje zasadne; brak rolloutu = DEFERRED.
- Po merge nadal aktywne: jeden approval, strict base, `test`, `malware-scan`.
  Pozostały otwarty PR #29 nie został objęty jednorazowym bypassem.
- Workflow **34255409339 SUCCESS** na zaufanym `main`: #31 odrzucony jako
  `MANUAL_REQUIRED`, bez approval/merge. Flaga Copilota `observe`; automatyczna
  akceptacja wyłączona. Nie udowadnia to jeszcze dodatniej ścieżki bota bez bypassu.

### BlueStacks i X88

- Emulator działający początkowo na porcie 5715 był inną instancją. Uruchomiono
  właściwe BlueStacks1 (Rvc64, 5555), nie zmieniając tożsamości w inventory.
- Kandydat z czystego `main`, 26 plików, mwoScrapers **0.2.2**, SHA ZIP:
  `774c51eec678d3304a8cd75cada0674042776a607c7b35d4e6b2dd786e145597`.
- `build_addon_candidate.py` + `kodi_addon_candidate_rollout.py`: najpierw
  BlueStacks, następnie X88; oba `AUDIT_PASS`, `ATTESTATION_PASS`, transakcja
  `COMMITTED` i wersja aktywna 0.2.2.
- `kodi_mwoscrapers_probe.py`: po **42 przypadki PASS** na urządzenie, bez
  błędów sieci/kontraktu i bez fałszywie dodatniego odcinka S99E99. PirateBay
  zwrócił na obu urządzeniach te same liczby: **21, 6, 98, 78, 9, 27, 0**.
  To test wyszukiwania/kontraktu; nie jest testem odtwarzania każdego wyniku.
- Prywatne raporty: `.kodi-private/bootstrap-weekly-watchdog-20260908/`
  (`main-health/provider-health.json`, `bluestacks-matrix.json`, `x88-matrix.json`).

Powtórzenie kwalifikacji wyszukiwania z hosta:

```bash
.venv/bin/python tools/kodi_mwoscrapers_probe.py \
  --serial 127.0.0.1:5555 --timeout 300 \
  --result .kodi-private/bluestacks-provider-matrix.json
.venv/bin/python tools/kodi_mwoscrapers_probe.py \
  --serial 192.168.1.16:5555 --timeout 300 \
  --result .kodi-private/x88-provider-matrix.json
```

### Dodatkowe korekty i testy

1. Emulator przy zatrzymanym Kodi zwracał z `pidof` tekst o liczbie usług.
   `bool(stdout)` fałszywie oznaczało `running=true`. Transport teraz akceptuje
   wyłącznie dodatnie numery PID, a przy nieprawidłowym tekście próbuje
   `toybox pidof`; dalsza niejednoznaczność kończy się wyjątkiem, nie zgodą na
   mutację. Live stop/start BlueStacks potwierdził pusty PID po zatrzymaniu,
   poprawny PID i JSON-RPC `pong` po starcie. Niezależny review agy-yolo,
   `gemini-3.8-flash-high`, sesja `834a4431-cb74-4233-b72b-06971e97431b`:
   brak uwag blokujących, 19 testów PASS. Zweryfikowane minimum puli 0.9276411533355713.
2. Test budowania kandydata był związany z literalną wersją 0.2.1. Porównuje
   teraz wersję z rzeczywistym `addon.xml`, zachowując kontrolę deterministyczności.
   Pierwszy pełny przebieg ujawnił ten błąd testu; po korekcie **835 PASS**.
3. Izolowane E2E API/mTLS oraz CDP panelu PASS. Publiczny smoke przed nową
   publikacją: **57/57 plików**. mwoScrapers z aktualną bazą: **186 PASS**.

### Pozostały zakres

Osobny release ZIP-a 0.2.2: immutable snapshot testing, promocja stable i rollout
pozostałych dostępnych urządzeń. Na dwóch kanarkach jest teraz lokalny kandydat,
nie wydanie pobrane z publicznego stable. P3–P5 planu Copilota (natywne approvals,
agent naprawczy, panel kolejki PR) pozostają niewdrożone.
