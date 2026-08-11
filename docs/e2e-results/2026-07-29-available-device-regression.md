# Regresja dostępnego urządzenia

Data: 29.07.2026

## Zakres

Regresja na żywo objęła każdego aktualnie osiągalnego zarejestrowanego konsumenta Kodi:

- BlueStacks1 (`SM-S901E`);
- Sony TV (`BRAVIA 4K GB ATV3`);
- X88 Pro 20 (`X88Pro20`).

Bedroom TV był niedostępny przez ADB. Obydwa podmioty główne NUC Flatpak były
niedostępne przez SSH i nie zostały zgłoszone jako przetestowane.

Wszystkie trzy osiągalne urządzenia Android korzystały z Kodi 21.3 bez aktywnego
transportu VPN podczas tego przebiegu.

## Wyniki

Każde osiągalne urządzenie przeszło:

- stable Profile Sync 0.1.6 pochodzenie, parowanie, uwierzytelniony puls, podpisana
  kontrola kandydata i niezmiennik bez zastosowania tylko do odczytu;
- Umbrella 6.7.81.18 wyszukaj `House of the Dragon`;
- Odtwarzanie Umbrella przez Real-Debrid przez co najmniej 15 sekund;
- WatchNixtoons2 0.26.1 katalog na żywo i kontrolowane odtwarzanie przez 15 sekund;
- odwracalne pomyślne zastosowanie Profile Sync, wstrzyknięta awaria, rollback,
  kwarantanna, przywrócenie dokładnych ustawień i oczyszczenie dziennika.

Prywatne, zredagowane raporty JSON pozostają poniżej poziomu `.kodi-private/e2e` i nie
są zatwierdzane.

## Poprawki Runnera odkryte przez E2E na żywo

- Odrzuć tylko dokładnie nieszkodliwe okno dialogowe informacyjne PVR Kodi i nieaktualne
  menu zamykania; nieoczekiwane okna dialogowe nadal nie przechodzą testu wyszukiwania.
- Użyj zastępczego zdarzenia klucza Android, gdy Kodi JSON-RPC potwierdza akcję modalną,
  ale okno dialogowe Android TV pozostaje otwarte.
- Przeczytaj wersje dodatków poprzez Kodi, gdy pamięć o zasięgu Android ukrywa
  `addon.xml`.
- Zaakceptuj skupienie pierwszego planu Kodi na dowolnym wyświetlaczu Android, co jest
  wymagane przez środowisko wykonawcze BlueStacks obsługujące wiele wyświetlaczy.
- Dołącz reprezentatywne metadane `premiered` do bezpośrednich urządzeń Umbrella,
  dopasowując normalną wzbogaconą nawigację.
- Wysyłaj pakiety serwera zdarzeń Kodi bezpośrednio z hosta dla celów LAN ADB, których
  oprogramowanie sprzętowe Android nie ma `nc`; Cele pętli zwrotnej/emulatora pozostają
  domyślnie odrzucane.

Poprawki dotyczą tylko narzędzia E2E i przywracania po stronie hosta. Nie zmieniono
żadnego ładunku dodatku Kodi ani artefaktu repozytorium stable, więc nie była wymagana
żadna wersja dodatku.

## Powtarzalna weryfikacja repozytorium

```text
.venv/bin/pytest -q: 166 passed
tests/e2e/run.sh: deterministic build passed; 166 passed
```
