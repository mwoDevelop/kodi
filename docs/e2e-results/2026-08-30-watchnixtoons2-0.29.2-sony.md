# WatchNixtoons2 0.29.2 — Sony TV

Data testu: 2026-08-30  
Urządzenie: Sony `BRAVIA 4K GB ATV3`, Kodi 21.3  
Kanał: kandydat testing wdrożony bezpośrednio na jedno urządzenie

## Zakres

- `plugin.video.watchnixtoons2.mwodevelop` podniesiono z 0.29.1 do 0.29.2;
- domyślna wartość `playbackMethod` to `1`, czyli `Auto Play Highest Quality`;
- transformacja downstream zachowuje tę zmianę podczas przyszłych importów upstream;
- istniejące jawne ustawienia użytkownika nie są nadpisywane przez aktualizację dodatku;
- biegacz E2E odczytuje najpierw ustawienie użytkownika, a przy jego braku domyślną
  wartość z zainstalowanego dodatku i wymaga efektywnego `auto_highest`.

## Artefakt

- commit komponentu: `edb6553a25becf25e30b5c291441a81818d9ead8`;
- ZIP: `plugin.video.watchnixtoons2.mwodevelop-0.29.2.zip`;
- SHA-256: `0f2217a4e03519394a321229dabe328f93271c715bcaa0784de331acfe4d4f97`;
- 30 plików, czyste i odtwarzalne źródło komponentu.

## Wynik Sony

- instalacja dokładnego ZIP-a: `PASS`, dodatek 0.29.2 aktywny;
- transakcyjna migracja istniejącego profilu Sony z `playbackMethod=0` do `1`:
  `PASS`, weryfikacja po restarcie Kodi: `PASS`;
- katalog `Latest Releases`: `PASS`, 16 elementów w próbce;
- rozwiązanie `Mao Episode 17 English Subbed`: `PASS` w 8,487 s;
- brak dialogu wyboru jakości (`selected_quality=null`);
- odtwarzanie rozpoczęte i obserwowane przez 15 s przy prędkości `1`;
- log Kodi potwierdził otwarcie pliku, InputStream, demukser i dekoder AAC.

Wersja 0.29.2 pozostaje na tym etapie w locku `testing`; stabilny lock 0.29.1 i pozostałe
urządzenia nie zostały zmienione.
