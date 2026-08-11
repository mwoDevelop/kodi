# Weryfikacja Sony Android TV stable — 26.07.2026

Cel: Sony BRAVIA 4K GB ATV3, Android 9, Kodi 21.2, ADB `192.168.1.12:5555`.

## Zainstalowano z repository.mwodevelop

| Dodatek | Wersja | Pochodzenie Kodi |
| --- | --- | --- |
| repozytorium.mwodevelop | 1.0.0 | repozytorium.mwodevelop |
| wtyczka.wideo.umbrella | 6.7.81.10 | repozytorium.mwodevelop |
| moduł.skrypt.mwoscrapers | 0.1.3 | repozytorium.mwodevelop |
| skrypt.mwoscrapers | 0.1.1 | repozytorium.mwodevelop |
| wtyczka.video.watchnixtoons2.mwodevelop | 0,25,2 | repozytorium.mwodevelop |

Publiczny stable Umbrella ZIP i promowany testing ZIP były identyczne pod względem
bajtów:

`c2802365ec91be704c3ec92f16a647142e7736a7f37844d51b1503af121acca6`

Wybrane pliki zasad i integracji downstream w telewizorze były zgodne z publicznym
stable ZIP przy użyciu SHA-256 po instalacji za pośrednictwem menedżera dodatków Kodi.

## Wyniki odtwarzania

| Testuj | Wynik | Rozwiąż | Obserwacja |
| --- | --- | ---: | ---: |
| Umbrella / Sintel (2010) | grał | 19,389 s | 16,581 s |
| Umbrella / Dom Smoka S01E01 | grał | 33,188 s | 16,165 s |
| Umbrella / Matrix (1999) | niegrywalny | brak strumienia | nie dotyczy |
| WatchNixtoons2 / najnowsze wydania | 15 wpisów do katalogu | nie dotyczy | nie dotyczy |
| WatchNixtoons2 / Mao odcinek 17 | grał | 16,142 s | 12 s |

`The Matrix` załadował postęp źródłowy Umbrella, a Kodi odrzucił wynik jako niemożliwy
do odtworzenia. Kontrolowana diagnostyka Real-Debrid przeprowadzona przed promocją
stable zwróciła kod HTTP 451 / Real-Debrid 35 (`infringing_file`) dla wszystkich ośmiu
unikalnych kandydatów objętych próbą. Jest to odrzucenie po stronie dostawcy, a nie
awaria uwierzytelniania, repozytorium, skrobaka lub programu rozpoznawania nazw.

Ostatnie udane uruchomienia Umbrella przeprowadzono w oparciu o łańcuch Umbrella ->
MwoScrapers -> Real-Debrid -> Kodi VideoPlayer. Kodi utworzył strumień wejściowy i
demuxer oraz zaawansowane odtwarzanie w oknie obserwacyjnym. WatchNixtoons2 niezależnie
załadował swój katalog na żywo, ustalił znaną ścieżkę, utworzył demuxer i zaawansowane
odtwarzanie.

## Naprawiono problemy objęte wersją

- Odpowiedzi kolekcji Real-Debrid, które są listami, nie powodują już zgłaszania
  `AttributeError` w klasyfikacji transportu.
- Dodatek downstream wykrywa `repository.mwodevelop` bez zakodowania na stałe
  identyfikatora repozytorium upstream.
- Gra automatyczna korzysta z ograniczonej, zróżnicowanej kolejki i honoruje `Only try
  one source`.
- Błędy kodu 35 Real-Debrid są rejestrowane bez ujawniania magnesów i buforowane
  negatywnie dla sesji.
- Nieprawidłowe odpowiedzi OpenSubtitles `(None, filename)` są ignorowane zamiast
  zgłaszać wyjątki dotyczące adresu URL i pustych napisów.
- Wiązka testowa Sony wykrywa, że ​​terminal Kodi jest niemożliwy do odtworzenia,
  zamiast czekać na pełny limit czasu mechanizmu rozpoznawania nazw.

## Powielanie

Z włączonym Kodi JSON-RPC/EventServer i izolowanym serwerem ADB:

```bash
export ADB_SERVER_SOCKET=tcp:localhost:5038
tests/e2e/sony_kodi_matrix.py \
  --adb /home/mwo/android-sdk/platform-tools/adb \
  --serial 192.168.1.12:5555 \
  --host 192.168.1.12 \
  --case sintel \
  --case house_of_the_dragon_s01e01

tests/e2e/sony_watchnixtoons2.py \
  --adb /home/mwo/android-sdk/platform-tools/adb \
  --serial 192.168.1.12:5555 \
  --host 192.168.1.12
```

Wiązka przewodów WatchNixtoons2 wymaga tymczasowego ustawienia metody odtwarzania na `1`
(automatyczne odtwarzanie najwyższej jakości), więc nie pozostaje żadne okno dialogowe
dotyczące jakości modalnej dla zdalnej automatyzacji.

Tymczasowe ustawienia debugowania/automatycznego odtwarzania nie zostały zachowane.
Oryginalne ustawienia Umbrella zostały dokładnie przywrócone, a tymczasowy plik ustawień
WatchNixtoons2 został usunięty po teście.
