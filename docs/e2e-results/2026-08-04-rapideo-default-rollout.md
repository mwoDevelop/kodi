# Domyślne wdrożenie dodatku Rapideo — 2026-08-04

Oficjalne repozytorium Rapideo `1.0.4`, wtyczka Rapideo `1.5.0` i wersja lustrzana Kodi
`script.module.xbmcswift2` `19.0.7` zostały uzgodnione w czterech dostępnych
instalacjach Android Kodi: BlueStacks1, X88 Pro 20, Sony TV, i Bedroom TV.

Dowód:

- każde pobrane archiwum odpowiadało przypiętej tożsamości SHA-256 i `addon.xml`;
- na wszystkich czterech urządzeniach włączono dodatki do repozytoriów i wtyczek;
- Rapideo został przypisany do `repository.rapideo_pl`, podczas gdy xbmcswift2 został
  przypisany do wbudowanego `repository.xbmc.org` Kodi;
- `Files.GetDirectory(plugin://plugin.video.rapideo_pl/)` zwrócił trzy pozycje menu
  głównego na każdym urządzeniu bez błędu Python;
- powtórne uzgodnienie X88 zgłosiło wszystkie trzy zarządzane dodatki jako `unchanged`;
- X88 został przywrócony ze zweryfikowanej migawki
  `ae3be132353673c4184874a8022eb99bf3b1b8a82946771d144cfec04b9bcdb4` po znalezieniu
  starszego katalogu sierocego należącego do ADB.

Nie można było sprawdzić ani zmienić dwóch zarejestrowanych profili Linux Flatpak w tym
przebiegu, ponieważ przypięty transport SSH zwrócił kod zakończenia 255. Jest to wyjątek
dostępności, a nie pomyślne roszczenie o wdrożenie.

## Ostateczna zbieżność

Naprawa czystego profilu X88 przywróciła starszą migawkę stable, więc ostateczny audyt
matrycy uzgodnił również obecne stable Umbrella `6.7.81.20`, mwoScrapers `0.1.10`,
WatchNixtoons2 `0.26.1` i Profile Sync `1.0.1`. Profile Sync otrzymał nową, jednorazową
rejestrację produkcyjną i przypisanie ładowania początkowego z podpisem offline dla
aktywnej wersji `home-stable`. Pierwsza synchronizacja zastosowała to, a powtórna
synchronizacja zwróciła `NO_CHANGE` bez oczekującego raportu.

Po sprawdzeniu poprawności zawsze włączonego tunelu OpenVPN X88, publiczny Torrentio
zwrócił HTTP 403, podczas gdy publiczny Comet zwrócił 132 oczyszczone rekordy źródłowe.
Obaj dostawcy pozostają włączeni, więc działający dostawca zostaje zachowany, zamiast
traktować politykę VPN Torrentio jako pusty wynik wyszukiwania. Następnie Umbrella
rozwiązał i odtworzył otwarty zasób testowy Sintel przez 10 sekund do Real-Debrid;
uruchomienie programu resolwerowego zajęło 52,886 sekundy. Sondy BlueStacks i X88
Real-Debrid zgłosiły, że konto premium i oczekiwane mapowanie `disabled_endpoint`
kodu-37 są w dobrym stanie.

Końcowy audyt stanu przenośnego czterech urządzeń wykazał te same osiem ulubionych,
siedem pozycji przenośnych WatchNixtoons2, brak brakujących grafik, Profile Sync `1.0.1`
i `NO_CHANGE` na BlueStacks1, X88 Pro 20, Sony TV i Bedroom TV. Cała czwórka używa
również Umbrella `6.7.81.20` z `repository.mwodevelop`, Rapideo `1.5.0` z
`repository.rapideo_pl` i xbmcswift2 `19.0.7` z `repository.xbmc.org`.
