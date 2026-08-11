# BlueStacks1 E2E — 24.07.2026

- Urządzenie: `BlueStacks1` (`127.0.0.1:5556`)
- Kodi: `21.2`
- Repozytorium: `repository.mwodevelop.testing` `1.0.0`
- Kompilacja odtwarzania Umbrella: `6.7.81.4`
- MwoScrapers: `0.1.1`
- Dostawca zewnętrzny wybrany poprzez GUI Kodi: `script.module.mwoscrapers`
- Treść testu: `Sintel` (2010), IMDb `tt1727587`
- Wyświetlane źródła: 5, wszystkie od Torrentio do MwoScrapers
- Próby Real-Debrid przed sukcesem: 4
- Odtwarzacz Kodi: wewnętrzny odtwarzacz wideo, prędkość `1`
- Obserwowane odtwarzanie: 31 sekund 14:48
- Kody RD okna testowego `34` / `35`: 0 / 0
- Wynik: PASS

Wcześniejsze uruchomienie kontrolne `Big Buck Bunny` wykazało błędnie oznakowany wynik
dostawcy: wybrany skrót został nazwany filmem testowym, ale Real-Debrid ujawnił inny
plik 2025. Umbrella odrzucił to bez odtwarzania. To odróżnia złe metadane źródłowe od
awarii transportu/resolwera.

Podczas udanego uruchomienia Sintel jeden kandydat zwrócił pusty, nieograniczony adres
URL. Odtwarzanie było kontynuowane z następnym źródłem; wynikająca z tego diagnostyka
`None.endswith` została naprawiona w wydaniu przednim `6.7.81.5`.

Instalacja i walidacja urządzenia są powtarzalne w przypadku
`tests/e2e/bluestacks_e2e.py`; deterministyczne repozytorium HTTP E2E to
`tests/e2e/run.sh`.
