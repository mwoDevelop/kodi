# Sony Android TV: Diagnoza NordVPN / Torrentio

Data: 26.07.2026

## Wynik

Instalacja Sony przebiegła prawidłowo, a autoryzacja Real-Debrid była ważna. Błąd został
odizolowany w bieżącej trasie NordVPN: Torrentio zwrócił HTTP 403 na Sony, podczas gdy
te same żądania zwróciły HTTP 200 na BlueStacks i od hosta programistycznego.

NordVPN pozostaje podłączony do telewizora. Dzielone tunelowanie Android TV wyklucza
Kodi z VPN, podczas gdy inne wybrane aplikacje nadal korzystają z tunelu. Po tej zmianie
wyszukiwanie i odtwarzanie Torrentio i Umbrella będzie działać na Sony.

## Kontrolowana sonda sieciowa

| Punkt końcowy | Sony do NordVPN | Sony z wyłączeniem Kodi | Sterowanie BlueStacks |
| --- | ---: | ---: | ---: |
| Real-Debrid `/time` | HTTP 200 | HTTP 200 | HTTP 200 |
| Torrentio, Sintel | Strumienie HTTP 403 / 0 | HTTP 200 / 5 strumieni | HTTP 200 / 5 strumieni |
| Torrentio, Dom Smoka S03E01 | Strumienie HTTP 403 / 0 | Strumienie HTTP 200/122 | Strumienie HTTP 200/122 |

Możliwości sieci z podzielonym tunelem wykluczają Kodi UID 10196. Interfejs VPN
pozostaje podłączony i zweryfikowany, a inne UID aplikacji pozostają do niego
przypisane.

## Zmiany konfiguracji Sony

- Włączone dzielone tunelowanie NordVPN; Kodi wykluczony z tunelu.
- Czas TTL pamięci podręcznej dostawcy Umbrella zmieniono z 48 na 6 godzin.
- Pamięć podręczna dostawcy Umbrella została wyczyszczona po utworzeniu lokalnej kopii
  zapasowej.
- Debugowanie Umbrella włączone na poziomie 1.
- `rd_cloud.enabled` pozostawiono wyłączone, zgodnie z obejściem użytkownika.
- `realdebrid.saveToCloud` wyłączony, aby pasował do działającego profilu BlueStacks.
- Filtry nazw plików i źródeł niezapisanych w pamięci podręcznej nie zostały dokręcone,
  ponieważ mogłoby to ukryć użyteczne wyniki.

Nowa baza danych dostawców zawiera cztery wpisy w pamięci podręcznej po kontrolowanych
testach. Ponowna autoryzacja Real-Debrid nie była potrzebna.

## Wyniki urządzenia E2E

| Urządzenie | Sprawa | Wynik | Rozwiąż | Obserwowane odtwarzanie |
| --- | --- | --- | ---: | ---: |
| Sony Android TV / Kodi 21.2 | Sintel | grał | 20,552 s | 16,162 s |
| Sony Android TV / Kodi 21.2 | Dom Smoka S01E01 | grał | 26,574 s | 16,172 s |
| Sony Android TV / Kodi 21.2 | Dom Smoka S03E01 | grał | 18,378 s | 16,147 s |
| BlueStacks1 / Kodi 21.3 | Dom Smoka S03E01 | grał | 16,110 s | 16,054 s |

Skupione wyszukiwanie telewizyjne dla `House of the Dragon` również przeszło na oba
urządzenia i zwróciło dokładną serię. Raporty nie zawierają żadnych danych
uwierzytelniających, magnesów ani ustalonych adresów URL multimediów.

## Powielanie

Odtwarzanie nagranego dźwięku:

```bash
.venv/bin/python tests/e2e/sony_kodi_matrix.py \
  --adb /home/mwo/android-sdk/platform-tools/adb \
  --serial 192.168.1.12:5555 \
  --host 127.0.0.1 \
  --jsonrpc-port 19091 \
  --direct-play \
  --case house_of_the_dragon_s03e01 \
  --observe-seconds 15 \
  --result docs/e2e-results/sony-hotd-s03e01.json
```

Wyszukiwanie telewizji:

```bash
.venv/bin/python tests/e2e/umbrella_search_e2e.py \
  --adb /home/mwo/android-sdk/platform-tools/adb \
  --serial 192.168.1.12:5555 \
  --host 127.0.0.1 \
  --jsonrpc-port 19091 \
  --term "House of the Dragon" \
  --media-type tv \
  --result docs/e2e-results/sony-tv-search.json
```

Referencje:

- [Lista współpracy VPN Real-Debrid](https://real-debrid.com/vpn)
- [NordVPN na Android
  TV](https://support.nordvpn.com/hc/en-us/articles/19928244437777-Installing-and-using-NordVPN-on-Android-TV-or-Nvidia-Shield)
- [Tunel dzielony
  NordVPN](https://support.nordvpn.com/hc/en-us/articles/19618692366865-What-is-Split-Tunneling-and-how-to-use-it)
