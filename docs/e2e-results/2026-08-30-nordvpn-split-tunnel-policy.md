# NordVPN Android TV — polityka dzielonego tunelowania

Data testu: 2026-08-30.

## Cel

Utrwalić jedną politykę dla urządzeń z natywnym NordVPN: dzielone tunelowanie
jest włączone, jedyną aplikacją wykluczoną z VPN jest Netflix, a Kodi pozostaje
w tunelu. Profile nie zawierają poświadczeń.

## Wynik urządzeń

| Urządzenie | Klient | Wynik |
|---|---|---|
| Sony TV | NordVPN | zaliczone 8/8; jedyną luką w zakresach UID VPN jest UID pakietu Netflix, Kodi jest objęte tunelem |
| Bedroom TV | NordVPN | profil zapisany; ADB niedostępne podczas testu (`No route to host`) |
| X88 Pro 20 | OpenVPN Connect | zaliczone 9/9 po restarcie i automatycznym `connect_latest`; natywny NordVPN jest niekompatybilny |
| BlueStacks1 | brak polityki urządzenia | emulator niedostępny podczas testu; nie jest celem profilu Android TV |

## Bramki

- testy profilu NordVPN i istniejącego profilu X88: `11 passed`;
- Ruff dla nowego narzędzia i testów: zaliczone;
- pełne `tests/e2e/run.sh`: `666 passed`;
- ponowny audyt Sony po implementacji: `compliant: true`;
- ponowny audyt X88 po restarcie: `compliant: true`.

Lista wykluczeń natywnego klienta nie jest modyfikowana przez nieudokumentowane
pliki prywatne aplikacji. Android publikuje jednak zakresy UID aktywnej sieci VPN,
co pozwala powtarzalnie udowodnić dokładny stan bez rozpoznawania obrazu.

## Źródła zachowania klientów

- [Dzielone tunelowanie NordVPN na Android TV](https://support.nordvpn.com/hc/en-us/articles/19618692366865-What-is-Split-Tunneling-and-how-to-use-it-with-NordVPN)
- [Ustawienia OpenVPN Connect na Androidzie](https://openvpn.net/connect-docs/app-settings-android.html)
