# Dowody etapu 0

Data: 24.07.2026

## Umowa

Przypięta podstawa Umbrella: `fb1fa4fe7fdab82091a6502da3f3610df2dcf71f` (`6.7.81`).

Umbrella dynamicznie importuje skonfigurowany katalog `lib` dodatku i wywołuje
`<module>.sources(ret_all=...)`. Każda zwrócona klasa dostawcy implementuje:

- `hasMovies`, `hasEpisodes`, `pack_capable` i `priority`;
- `sources(data, hostDict)`;
- znormalizowane słowniki wyników torrentów wykorzystywane przez Umbrella.

MwoScrapers implementuje ten interfejs bez kopiowania kodu źródłowego providerów.
Umbrella pozostaje odpowiedzialna za deduplikację i rozstrzyganie wyników między
providerami.

## Dowody dotyczące upstreamu

| Rodzina | Wersja | Przypięty SHA-256 |
|---|---:|---|
| Coco | 1.0.39 | `c6de1ad7ae612fe22a5b102504b9b6f7cebe8fe961de321bdae86b5dced5af59` |
| Viper | 1.5.4 | `9c089bdffa6f30a0a987dfaf289c15eebddeaefc786171609e4e2ef6793f8f4a` |
| Magneto | 6.07.04 | `f46f4d4f25453f3683beebd00bf35ab181e0588da32a4e8dd73917db27615427` |

Pakiety deklarują GPL-3.0 w `addon.xml`, ale nie zawierają oddzielnego pliku licencji i
nie ustanawiają pełnego łańcucha własności poszczególnych plików. W związku z tym żaden
plik providera nie został skopiowany. Torrentio i Comet to oryginalne adaptery
obsługujące publiczny format JSON zgodny ze Stremio i wyposażone w testy offline.

## Model zagrożeń podczas importu

`mwoscrapers/tools/safe_ingest.py` inwentaryzuje pliki ZIP bez ekstrakcji i importu
modułów. Odrzuca próby wyjścia poza katalog, ścieżki bezwzględne i ścieżki Windows,
dowiązania symboliczne, pliki urządzeń, zagnieżdżone archiwa, ścieżki zduplikowane lub
kolidujące wielkością liter oraz przekroczenia limitów liczby plików, rozmiaru i
współczynnika kompresji.

Zaplanowany audyt ma uprawnienie `contents: read`, nie otrzymuje sekretów, używa
przypiętych wersji GitHub Actions i blokady współbieżności oraz przechowuje wyłącznie
wygenerowany raport przez 14 dni.

## Próba procesu wydania

Główne repozytorium tworzy kompletną migawkę Pages z przypiętych commitów submodułów.
Sygnatury czasowe ZIP, uprawnienia, kolejność i ustawienia kompresji są stałe. Przed
publikacją dwie niezależne kompilacje muszą być identyczne pod względem bajtów.

GitHub Pages używa `<hashes>false>`, ponieważ nie może obsłużyć nagłówka odpowiedzi
`content-sha256` Kodi. Zamiast tego CI i test dymu po wdrożeniu weryfikują jawny
manifest SHA-256.

Kanał stable początkowo zawiera tylko dodatek repozytorium. Kanał testing zawiera
Umbrella `6.7.81.1` i MwoScrapers `0.1.0`.
