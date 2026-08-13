# Wspólne konto OpenSubtitles.org i OpenSubtitles.com w Umbrella

Data próby: 2026-08-13.

## Zakres

- oba adaptery korzystają z tych samych prywatnych referencji
  `OPENSUBTITLES_USER` i `OPENSUBTITLES_PASS`;
- klient `.com` w Umbrella może wystartować z `OPENSUBTITLES_TOKEN`, lecz po jego
  wygaśnięciu odnawia token loginem użytkownika i hasła;
- sekrety trafiają do Kodi krótkotrwałym plikiem i są usuwane po wykonaniu;
- rutynowy rollout nie pobiera pliku i nie zużywa dziennego limitu.

## Wyniki urządzeń testowych

| Urządzenie | Umbrella | Login/wyszukiwanie `.com` | Kontrolne pobranie `.com` | `.org` |
|---|---:|---:|---:|---:|
| BlueStacks1 | 6.7.81.20 | 25 polskich wyników, HTTP 200 | 57 281 B, HTTP 200 | login i 7 wyników; `VIP_REQUIRED` |
| X88 Pro 20 | 6.7.81.20 | 25 polskich wyników, HTTP 200 | 57 281 B, HTTP 200 | login i 7 wyników; `VIP_REQUIRED` |

Konto `.com` jest poziomu bez VIP, ale udostępnia działające pobrania w ramach
limitu. Stare API `.org` zwraca zamiast napisów promocyjny SRT VIP. Adapter
pozostawia zweryfikowane dane konta i HTTPS, lecz nie ustawia tej usługi jako
domyślnej. Dzięki temu działający klient `.com` w Umbrella nie jest zastępowany
przez pozornie poprawną odpowiedź `.org`.

Eksport z BlueStacks potwierdził obecność niepustych ustawień
`opensubsusername`, `opensubspassword` i `opensubstoken` w prywatnym pliku Umbrella
mode-`0600`. Wartości nie są publikowane w tym raporcie ani w repozytorium.
