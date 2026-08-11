# Oczyszczanie Kodi i regresja Android — 26.07.2026

## Stan końcowy

Instalacje BlueStacks1 (`Rvc64`, Kodi 21.3) i Sony BRAVIA Android TV (Kodi 21.2)
zawierają tylko te włączone repozytoria:

- `repository.mwodevelop` 1.0.0;
- `repository.xbmc.org`, oficjalne repozytorium Kodi.

Jedynym źródłem menedżera plików na obu urządzeniach jest:

`mwodevelop -> https://mwodevelop.github.io/kodi/repo/`

Ostateczna baza danych i manifesty dodatków na dysku są zgodne:

| Dodatek | Wersja | Pochodzenie |
| --- | ---: | --- |
| Umbrella (mwoDevelop) | 6.7.81.11 | `repository.mwodevelop` |
| WatchNixtoons2 (mwoDevelop) | 0,25,2 | `repository.mwodevelop` |
| Moduł MwoScrapers | 0.1.3 | `repository.mwodevelop` |
| Menedżer MwoScrapers | 0.1.1 | `repository.mwodevelop` |

Rapideo i jego repozytorium zostały usunięte. Starsze wpisy pamięci podręcznej pakietów
dla Rapideo, ViperScrapers, ResolveURL, POV, IPTV Lister, MicroJenScrapers, pomocników
YouTube, SpeedTester i Umbrella 6.7.81.10 również zostały usunięte, jeśli były obecne: 8
ZIP na BlueStacks1 i 39 ZIP na Sony. W momencie usuwania nie był zainstalowany żaden z
odpowiednich starszych dodatków.

Świeże kopie zapasowe urządzeń są przechowywane poza repozytorium w:

`/home/mwo/.local/share/kodi-cleanup-backups/20260726/`

## Korekcja modułu przeliczającego

Sony ujawniło błąd zgodności dostawcy Umbrella podczas rozwiązywania `Breaking Bad
S01E01`:

`AttributeError: 'source' object has no attribute 'sources_packs'`

Umbrella 6.7.81.11 izoluje możliwości opcjonalnego dostawcy za adapterem downstream.
Dostawcy bez obsługi pakietów są pomijani przy wyszukiwaniu pakietów; dostawcy
obsługujący pakiety otrzymują niezmienione argumenty i wyniki. Zestaw downstream
przeszedł 28 testów, w tym rekonstrukcję z bazy upstream oraz zarejestrowaną serię
poprawek.

Dokładny publiczny stable ZIP ma SHA-256:

`c37ba5e4d557c7ec76a6b9d2f6bc2ea2f65ade0e3697a8085b985c0933e98d5d`

Był promowany bajt po bajcie z testing. Dodatek repozytorium Kodi pozostaje w wersji
1.0.0.

## Wyniki urządzenia E2E

Każdy przypadek rozpoznawania nazw działał niezależnie, aby zapobiec wpływowi
przekroczenia limitu czasu okna Kodi na następny przypadek.

| Urządzenie | Sprawa | Wynik | Rozwiąż | Zaobserwowano |
| --- | --- | --- | ---: | ---: |
| BlueStacks1 | Umbrella / Sintel | grał | 19,767 s | 12,034 s |
| BlueStacks1 | Umbrella / Breaking Bad S01E01 | grał | 15,735 s | 12,043 s |
| Sony | Umbrella / Sintel | grał | 19,149 s | 12,137 s |
| Sony | Umbrella / Breaking Bad S01E01 | nieodtwarzalny zestaw źródeł, brak wyjątku w programie rozpoznawania nazw | nie dotyczy | nie dotyczy |
| BlueStacks1 | WatchNixtoons2 / Mao Odcinek 17 | grał | 11,039 s | 12 s |
| Sony | WatchNixtoons2 / Mao Odcinek 17 | grał | 16,451 s | 12 s |

Obydwa przebiegi WatchNixtoons2 załadowały także aktualny katalog `Latest Releases` i
zarejestrowały 15 różnych przykładowych wpisów. Uruchomienie Sony Breaking Bad nie
znalazło użytecznego strumienia, ale nie ma poprzedniego wyjątku `sources_packs`; ta
sama sprawa została pomyślnie rozegrana na BlueStacks1.

Raporty do odczytu maszynowego:

- [BlueStacks1 / Sintel](2026-07-26-cleanup-bluestacks1-sintel.json)
- [BlueStacks1 / Breaking Bad](2026-07-26-cleanup-bluestacks1-breaking-bad.json)
- [BlueStacks1 / WatchNixtoons2](2026-07-26-cleanup-bluestacks1-watchnixtoons2.json)
- [Sony / Sintel](2026-07-26-cleanup-sony-sintel.json)
- [Sony / Breaking Bad](2026-07-26-cleanup-sony-breaking-bad.json)
- [Sony / WatchNixtoons2](2026-07-26-cleanup-sony-watchnixtoons2.json)

## Stan przywrócony

Tymczasowe ustawienia autoodtwarzania i ustawienia testowe WatchNixtoons2 zostały
usunięte lub przywrócone. Tryby odtwarzania Umbrella powróciły do ​​`0`,
`sources.retryall` powróciły do ​​`true` i przywrócono oryginalne opcje debugowania
(`true` na BlueStacks1, `false` na Sony). Dostęp do serwera zdarzeń BlueStacks1 ze
wszystkich interfejsów powrócił do `false`, a tymczasowe przekazywanie ADB JSON-RPC
zostało usunięte.

Obydwa urządzenia zostały pomyślnie uruchomione po ostatecznym audycie zatrzymanej bazy
danych.
