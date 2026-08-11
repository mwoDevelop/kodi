# Profile Sync 1.0 RC2 Android E2E

Data: 2026-08-03

Dokładny publiczny artefakt testing `service.mwodevelop.profilesync-1.0.0~rc2.zip` z
SHA-256 `f3d3b2d22abee846a152e47e037a80fabae0b60b38b421cd4b2f6c20973c2e3b` został
zakwalifikowany do produkcyjnego zaplecza QNAP i wersji aktywnego profilu
`sha256:4c7d728d214a6d31d1d277d2fd6b30957bc2d07d873648df5e0ffda69a1c905e`.

| Urządzenie | Profil zastosuj/powtórz | Stan przenośny | Umbrella szukaj | Odtwarzanie RD | WatchNixtoons2 |
| --- | --- | --- | --- | --- | --- |
| BlueStacks1 | przepustka / `NO_CHANGE` | 8 ulubionych, 7 przenośnych akcji, grafika ukończona | film + karnet telewizyjny | Sintel + przepustka do Breaking Bad | przejść |
| X88 Pro 20 | przepustka / `NO_CHANGE` | 8 ulubionych, 7 przenośnych akcji, grafika ukończona | film + karnet telewizyjny | Sintel + przepustka do Breaking Bad | przejść |
| Sony TV | przepustka / `NO_CHANGE` | 8 ulubionych, 7 przenośnych akcji, grafika ukończona | film + karnet telewizyjny | Przepustka Breaking Bad; Awaria specyficzna dla źródła Sintel | przejść |
| Bedroom TV | przepustka / `NO_CHANGE` | 8 ulubionych, 7 przenośnych akcji, grafika ukończona | Sintel + przepustka do Breaking Bad | Sintel + przepustka do Breaking Bad | przejść |

Bedroom TV używał Kodi 21.3 w Google TV Streamer. Aktywna wersja została zastosowana raz
i natychmiastowa druga synchronizacja zwróciła `NO_CHANGE`; kolejka raportów była pusta.
Sintel rozwiązał problem w około 59 sekund, a Breaking Bad S01E01 w około 24 sekundy, po
czym w obu przypadkach nastąpiło co najmniej 15 sekund obserwowanego odtwarzania.
WatchNixtoons2 rozwiązany w ciągu około 2 sekund i odtwarzany przez wymagany interwał
obserwacji.

Dwa podmioty główne Linux/Flatpak NUC nie zostały uznane za zaliczone, ponieważ ich
współdzielony host był nieosiągalny podczas tego przebiegu. Jest to rejestrowane jako
luka w dostępności urządzenia, a nie awaria oprogramowania Android ani data wydania
wersji oparta na czasie.

Prywatne raporty do odczytu maszynowego pozostają poza kontrolą wersji w ramach
`.kodi-private/e2e` i `.kodi-private/profile-sync-production/e2e`.

## Zamawianie wersji ostatecznej

Pierwszy końcowy deskryptor `1.0.0` został celowo odrzucony przed promocją stable: Kodi
zachował zainstalowany `1.0.0~rc2` zamiast traktować `1.0.0` jako aktualizację.
Ostatecznym kandydatem jest zatem `1.0.1`. Dzięki temu kod wykonawczy pozostaje
niezmieniony, a jednocześnie zapewnia monotonną ścieżkę aktualizacji dla każdego
urządzenia biorącego udział w kwalifikacji RC. Migawka `1.0.0` testing nie kwalifikuje
się do promocji stable.
