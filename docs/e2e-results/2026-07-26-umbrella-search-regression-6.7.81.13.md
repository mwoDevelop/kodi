# Regresja wyszukiwania Umbrella na Sony i BlueStacks — 26.07.2026

## Wynik

Wyszukiwanie Umbrella działa zarówno na uruchomionych instalacjach Kodi z stable
`plugin.video.umbrella` 6.7.81.13 z `repository.mwodevelop` 1.0.0.

Awaria Sony została odtworzona jako nieaktualny modal Umbrella `source_progress`. Modal
może pozostać aktywny po ścieżce programu rozpoznawania terminala i uniemożliwiać
otwarcie klawiatury wirtualnej. Polityka cyklu życia downstream teraz uzbraja właściwość
keep-alive synchronicznie przed uruchomieniem wątku modalnego; monitor tylko czeka na
zwolnienie i nigdy nie uzbraja ponownie już zwolnionego okna.

Rozwiązywanie autoodtwarzania uruchamia także każde wywołanie mechanizmu rozpoznawania
wybranego źródła za pośrednictwem ograniczonego procesu roboczego. Wynik spóźniony nie
może zostać zaakceptowany po upływie 8 sekund na podejście. Obie zmiany są obecne w
modułach zasad downstream i rejestracji poprawek, zapewniając możliwość rekonstrukcji
forka i odizolowanie go od kodu upstream zgodnie z polityką OCP projektu.

## Zwolnione artefakty

- Znacznik Umbrella: `mwo-6.7.81.13`
- Zatwierdzenie wydania Umbrella: `fb689588a9b4e3502886e1ca63a48ccaa9f399c2`
- Publiczny stable ZIP SHA-256:
  `5ddb813669fde54096caf5c3f9b86ac7a0e26bf9ae132197d996f1b18b378d58`
- Publiczne stable `addons.xml` SHA-256:
  `a8de1caf21b8bce85413a0af2476cfb515282c71298c16b62b0fec5fb63a9213`
- `repository.mwodevelop` pozostaje w wersji `1.0.0`.

Publiczny ZIP stable został pobrany ponownie po wdrożeniu i bajt po bajcie pasował do
blokady stable.

## Regresja urządzenia

| Urządzenie | Kodi | Testuj | Wynik |
| --- | ---: | --- | --- |
| Sony BRAVIA | 21,2 | Wyszukaj `Big Buck Bunny` po próbie rozpoznawania nazw, bez ponownego uruchamiania Kodi | 2 pasujące wyniki |
| Sony BRAVIA | 21,2 | Wyszukaj `Sintel` natychmiast po deterministycznym 180-sekundowym przekroczeniu limitu czasu mechanizmu rozpoznawania nazw, bez ponownego uruchamiania Kodi | `Sintel (2010)` |
| BlueStacks1 / Rvc64 | 21,3 | Wyszukaj `Big Buck Bunny` | 2 pasujące wyniki |

Ostateczna wersja dodatku Kodi wyświetla raport Umbrella 6.7.81.13 na obu urządzeniach.
Ich bazy danych dodatków zgłaszają wszystkie pięć dodatków mwoDevelop włączonych i
pochodzących z `repository.mwodevelop`:

- `plugin.video.umbrella`;
- `plugin.video.watchnixtoons2.mwodevelop`;
- `script.module.mwoscrapers`;
- `script.mwoscrapers`;
- `repository.mwodevelop`.

Raporty do odczytu maszynowego:

- [Wyszukiwanie Sony po przekroczeniu limitu czasu modułu rozpoznawania
  nazw](2026-07-26-sony-search-after-jsonrpc-timeout-6.7.81.13.json)
- [Próba deterministycznego rozpoznawania nazw firmy
  Sony](2026-07-26-sony-sintel-jsonrpc-6.7.81.13.json)
- [Wyszukiwanie
  BlueStacks1](2026-07-26-bluestacks1-big-buck-bunny-search-6.7.81.13.json)

## Oddzielna obserwacja resolwera

Deterministyczne uruchomienie Sony `Sintel` wywołało adres URL wtyczki poprzez
zatwierdzony Kodi JSON-RPC i załadowało interfejs użytkownika postępu źródła Umbrella,
ale pełne zeskrobanie dostawcy nie wygenerowało odtwarzacza w ciągu 180 sekund. Różni
się to od stałego cyklu życia okna wyszukiwania: wyszukiwanie zakończyło się sukcesem
natychmiast po przekroczeniu limitu czasu w tym samym procesie Kodi.

Ograniczenie 8 sekund dodane w wersji 6.7.81.13 dotyczy indywidualnej próby rozwiązania
wybranego źródła. Celowo nie przerywa wykrywania dostawcy, które może poprzedzać
rozwiązanie i jest regulowane przez limity czasu dla własnego dostawcy.

Macierz E2E wykorzystuje teraz JSON-RPC `Player.Open` do bezpośredniego odtwarzania
zamiast niepotwierdzonego i zależnego od urządzenia transportu EventServer. Każde
bezpośrednie wywołanie niesie ze sobą unikalny identyfikator jednorazowy E2E, więc Kodi
nie może ponownie wykorzystać poprzedniej ścieżki wtyczki.

## Powielanie

```bash
export ADB_SERVER_SOCKET=tcp:localhost:5038

PYTHONPATH=tests/e2e .venv/bin/python tests/e2e/umbrella_search_e2e.py \
  --adb /home/mwo/android-sdk/platform-tools/adb \
  --serial 192.168.1.12:5555 \
  --host 127.0.0.1 \
  --jsonrpc-port 19091 \
  --term Sintel \
  --result docs/e2e-results/sony-umbrella-search.json

PYTHONPATH=tests/e2e .venv/bin/python tests/e2e/umbrella_search_e2e.py \
  --adb /home/mwo/android-sdk/platform-tools/adb \
  --serial 127.0.0.1:5555 \
  --host 127.0.0.1 \
  --jsonrpc-port 19190 \
  --term "Big Buck Bunny" \
  --result docs/e2e-results/bluestacks1-umbrella-search.json
```

Przeszedł kompletny pakiet lokalny: `58 passed`.

## Przywrócono stan urządzenia

Oryginalne bazy danych wyszukiwania Umbrella zostały przywrócone po testing. Ich
wartości SHA-256 po ponownym uruchomieniu są zgodne z kopiami zapasowymi sprzed testu:

- Sony: `a708a44cb2254b4e60ae4e95a0ebe58c967e8813c3f25597d67cb60b03d0c85b`;
- BlueStacks1: `536ee51ff0a2c0f1d1e397a7cd1f333bedff5463f4c7c5a2f0e7f7c8b83ffd81`.

W raportach nie są przechowywane żadne dane uwierzytelniające, magnesy ani rozpoznane
adresy URL multimediów Real-Debrid.
