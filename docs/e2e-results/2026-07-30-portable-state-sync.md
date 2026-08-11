# Przenośna konwergencja stanu Kodi E2E — 30.07.2026

Deterministyczny pakiet `kodi.favourites` został wyeksportowany od zarejestrowanego
wydawcy Sony TV i zastosowany poprzez własny proces Kodi.

Pakiet: `sha256:4da887aa98967d543c782245c7f467697671dfd8c35d48c9a27242ba73a29708`

| Urządzenie logiczne | Wynik | Ulubione | WatchNixtoons2 | Przenośna grafika | Bieżące działania na forku |
| --- | --- | ---: | ---: | ---: | ---: |
| `bluestacks1` | `NO_CHANGE` | 8 | 7 | 7 | 7 |
| `sony-tv` | `NO_CHANGE` | 8 | 7 | 7 | 7 |
| `x88pro20` | `NO_CHANGE` | 8 | 7 | 7 | 7 |
| `bedroom-tv` | `UNAVAILABLE` (nieaktywny ADB) | — | — | — | — |
| `nuc-mwo` | `UNAVAILABLE` (SSH) | — | — | — | — |
| `nuc-alek` | `UNAVAILABLE` (SSH) | — | — | — | — |

Przed konwergencją BlueStacks nie miał faworytów; X88 miał pięć wpisów WatchNixtoons2
odnoszących się do pięciu nieobecnych plików lokalnych; Firma Sony miała siedem
przenośnych obrazów, ale wszystkie siedem działań nadal dotyczyło starszego
identyfikatora dodatku. Materializacja wydawcy zakończyła się siedmioma zweryfikowanymi
obrazami, siedmioma przeniesionymi akcjami i zerową liczbą niepowodzeń. Sondy w Kodi po
zastosowaniu potwierdziły dokładne zestawienie `favourites.xml` i brak brakujących
grafik referencyjnych na każdym osiągalnym celu.

Prywatne dowody nadające się do odczytu maszynowego są przechowywane w
`.kodi-private/e2e/2026-07-30-portable-and-profile-sync-final.json`.

W tym samym ostatecznym wdrożeniu każde osiągalne urządzenie miało własny identyfikator
logiczny Profile Sync, `home-stable`, 15-sekundowe opóźnienie uruchamiania,
sześciogodzinny interwał i tryb bezpieczeństwa tylko do odczytu. Wszystkie celowo
pozostały niesparowane, ponieważ nie wdrożono żadnego trwałego uwierzytelnionego
backendu HTTPS.

Następnie oddzielny zweryfikowany backend E2E został przekazany na wszystkie trzy
urządzenia:

- unikalne, jednorazowe parowanie i materiał siewny tokenu/podpisu dostępny wyłącznie
  lokalnie;
- uwierzytelnione bicie serca i podpisane zadanie kandydata;
- zachowanie przygotowanego profilu tożsamości po oczyszczeniu E2E;
- obowiązują pomyślne ustawienia oraz wstrzyknięta awaria rollback;
- wyczyść dziennik i przywróć ustawienia z dokładnością do bajtów.

Prywatny dowód:

- `.kodi-private/e2e/2026-07-30-profile-sync-identity-preserving-e2e.json`;
- `.kodi-private/e2e/2026-07-30-DEVICE-profile-sync-apply.json`;
- `.kodi-private/e2e/2026-07-30-post-profile-sync-e2e-audit.json`.
