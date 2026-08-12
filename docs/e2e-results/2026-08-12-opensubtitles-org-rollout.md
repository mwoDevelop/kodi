# OpenSubtitles.org — domyślna konfiguracja i test kanarków

Data: 2026-08-12

## Zakres

- przypięty oficjalny dodatek Kodi `service.subtitles.opensubtitles` 5.1.5;
- prywatne referencje `OPENSUBTITLES_USER` i `OPENSUBTITLES_PASS` z `.env`;
- domyślna usługa napisów dla filmów i seriali;
- język polski oraz angielski jako zapasowy;
- atomowa korekta starszego endpointu XML-RPC z HTTP na HTTPS;
- test logowania, wyszukania i pobrania wykonywany wewnątrz Kodi;
- drugi przebieg bez zmian.

## Wyniki urządzeń

| Urządzenie | Dodatek | Logowanie | Wyszukiwanie | Pobranie | Drugi przebieg |
|---|---:|---:|---:|---:|---:|
| BlueStacks | 5.1.5 | `200 OK` | `200 OK`, 7 wyników | 102 B | `changed=false` |
| X88 Pro 20 | 5.1.5 | `200 OK` | `200 OK`, 7 wyników | 102 B | `changed=false` |

Na obu urządzeniach raport potwierdził zapisanie konta bez ujawniania jego wartości,
wybranie usługi dla filmów i seriali, `Polish` jako język preferowany oraz aktywny
endpoint TLS. W chwili próby X88 korzystał bezpośrednio z Ethernetu; aplikacja
OpenVPN była obecna, ale system nie raportował aktywnego transportu VPN.

## Porównanie z klientem Umbrella

Kod Umbrella korzysta z `https://api.opensubtitles.com/api/v1`, nie z API `.org`.
Kontrolne logowanie do `.com` tym samym użytkownikiem i hasłem zwróciło HTTP 401 bez
tokenu. XML-RPC `.org` nie udostępnił adresu e-mail konta, a prywatne referencje nie
zawierały osobnej tożsamości `.com`, dlatego nie wykonywano nieudowodnionego wariantu
e-mail. Osobny dodatek `.org` pozostaje aktywną, działającą usługą całego Kodi.

## Automatyzacja i regresja

Adapter jest wykonywany przez androidową fazę `converge` po instalacji domyślnych
dodatków i przed konfiguracją providerów. Ten sam profil prywatny został dodany do
ignorowanej konfiguracji czystego odtworzenia. Końcowy, powtarzalny
`tests/e2e/run.sh` na izolowanej gałęzi opartej o `main`: `457 passed`.

Końcowy scoped rollout z gałęzi opartej o `main` zwrócił `NO_CHANGE` dla BlueStacks;
OpenSubtitles, providery, Rapideo i Real-Debrid przeszły. X88 potwierdził `pass` dla
OpenSubtitles, providerów i Rapideo, ale cały przebieg miał status `PARTIAL`, ponieważ
niezależna sonda Real-Debrid nie była zdrowa po trzech próbach. W chwili testu X88 nie
miał aktywnego transportu VPN. Nie wpływa to na potwierdzony wynik OpenSubtitles.
