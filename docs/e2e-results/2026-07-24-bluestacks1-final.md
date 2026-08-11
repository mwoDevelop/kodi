# Końcowe E2E BlueStacks1 — 24.07.2026

- Kodi: `21.3`
- Repozytorium: publiczne `repository.mwodevelop.testing` `1.0.0`
- Umbrella: `6.7.81.7`
- MwoScrapers: `0.1.2`
- Stan początkowy: brak Umbrella i MwoScrapers
- Działanie użytkownika: zainstaluj tylko Umbrella
- Wynik zależności: Kodi automatycznie zainstalował MwoScrapers
- Treść testu: `Sintel` (2010), IMDb `tt1727587`
- Dostawca: Torrentio do MwoScrapers
- Wyświetlane źródła: 5
- Obserwowano odtwarzanie: co najmniej 50 sekund 14:48
- Wideo/audio: dekoder Android H.264 i dekoder AAC
- Wynik: PASS

Rekord do odczytu maszynowego to `2026-07-24-bluestacks1-clean-dependency.json`. Zawiera
zainstalowane wersje, stan zależności przed/po, znaczniki bezpiecznej instalacji Kodi
oraz znaczniki odtwarzania od utworzenia strumienia wejściowego do zamknięcia
odtwarzacza.

Test jest powtarzalny w trzech fazach `tests/e2e/bluestacks_e2e.py`: `prepare`, `verify`
i `playback`. Instalacja i wybór źródła celowo przechodzą przez GUI Kodi; skrypt nigdy
nie dodaje dodatku do profilu Kodi.
