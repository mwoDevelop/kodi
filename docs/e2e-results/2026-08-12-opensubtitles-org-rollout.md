# OpenSubtitles.org — diagnoza fałszywego pobrania

Data: 2026-08-12

## Zakres

- przypięty oficjalny dodatek Kodi `service.subtitles.opensubtitles` 5.1.5;
- prywatne referencje `OPENSUBTITLES_USER` i `OPENSUBTITLES_PASS` z `.env`;
- domyślna usługa napisów dla filmów i seriali;
- język polski oraz angielski jako zapasowy;
- atomowa korekta starszego endpointu XML-RPC z HTTP na HTTPS;
- test logowania, wyszukania i semantycznej poprawności pobrania wykonywany
  wewnątrz Kodi;
- drugi przebieg bez zmian.

## Wyniki urządzeń

| Urządzenie | Dodatek | Logowanie | Wyszukiwanie | Pobranie | Drugi przebieg |
|---|---:|---:|---:|---:|---:|
| BlueStacks | 5.1.5 | `200 OK` | `200 OK`, 7 wyników | 102 B, placeholder VIP | niezaliczony |
| X88 Pro 20 | 5.1.5 | `200 OK` | `200 OK`, 7 wyników | 102 B, placeholder VIP | niezaliczony |

Pierwsza wersja sondy sprawdzała tylko status HTTP/XML-RPC, obecność payloadu i jego
długość. Było to niewystarczające: konto ma `IsVIP=0`, a API `.org` zwraca plik SRT
z jedną planszą „Become OpenSubtitles.org VIP member” zamiast napisów. Kontrola
została poprawiona tak, aby rozpoznawać oba stabilne markery tego placeholdera i
zwracać `VipRequiredError`. Nie wolno uznawać wcześniejszych 102 B za działające
napisy.

## Porównanie z klientem Umbrella

Kod Umbrella korzysta z `https://api.opensubtitles.com/api/v1`, nie z API `.org`.
Kontrolne logowanie do `.com` tym samym użytkownikiem i hasłem zwróciło HTTP 401 bez
tokenu. XML-RPC `.org` nie udostępnił adresu e-mail konta, a prywatne referencje nie
zawierały osobnej tożsamości `.com`, dlatego nie wykonywano nieudowodnionego wariantu
e-mail. Osobny dodatek `.org` pozostaje zainstalowaną alternatywą, ale nie jest
kwalifikowany jako działająca usługa do czasu aktywnego VIP lub zmiany zachowania API.

## Automatyzacja i regresja

Adapter jest wykonywany przez androidową fazę `converge` po instalacji domyślnych
dodatków i przed konfiguracją providerów. Ten sam profil prywatny został dodany do
ignorowanej konfiguracji czystego odtworzenia. Końcowy, powtarzalny
`tests/e2e/run.sh` na izolowanej gałęzi opartej o `main`: `457 passed`.

Historyczne raporty rolloutu oznaczające OpenSubtitles jako `pass` opierały się na
starej kontroli długości. Po zgłoszeniu rzeczywistej treści pliku przeprowadzono
bezpośrednią, zredagowaną próbę API: logowanie, wyszukiwanie i pobranie miały status
`200 OK`, lecz 102-bajtowy rezultat został prawidłowo sklasyfikowany jako placeholder
VIP. Nowa regresja obejmuje ten dokładny przypadek.
