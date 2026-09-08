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

W trakcie. Ten zapis nie jest jeszcze dowodem wdrożenia ani wydania dodatku.
Zastane niepowiązane zmiany QTS Gateway nie są częścią commitów bootstrapu.
