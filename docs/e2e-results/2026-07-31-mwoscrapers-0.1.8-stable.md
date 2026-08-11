# MwoScrapers 0.1.8 publiczna wersja rezerwowa Comet i wdrożenie stable

Data: 2026-07-31

## Wynik

MwoScrapers 0.1.8 został opublikowany w repozytorium stable mwoDevelop Kodi. Torrentio
pozostaje włączony, podczas gdy Comet jest teraz niezależnym, włączonym publicznym
rozwiązaniem awaryjnym. Rozdzielczość źródła i odtwarzanie Real-Debrid nie zależą od
QNAP.

Implementacja jest zgodna z publicznym punktem końcowym Stremio udostępnionym przez
[projekt Comet](https://github.com/g0ldyy/comet). Jego domyślny publiczny punkt końcowy
jest oparty na konfiguracji w [przykładowym środowisku
Comet](https://github.com/g0ldyy/comet/blob/main/.env-sample). MwoScrapers korzysta
wyłącznie z publicznego punktu końcowego metadanych; Dane uwierzytelniające Real-Debrid,
przesyłanie magnesów i rozdzielczość odtwarzalnych adresów URL pozostają w Umbrella.

## Niezmienne wydanie

- MwoScrapers źródłowy PR:
  [mwoDevelop/script.module.mwoscrapers#12](https://github.com/mwoDevelop/script.module.mwoscrapers/pull/12);
- zatwierdzenie scalania źródła: `e50595c6ba0971499d663079c8acc63b1efb117f`;
- wersja dodatkowa: `0.1.8`;
- dodatek ZIP SHA-256:
  `18d09f6cfc73d46669688a2e8cfd0c2233f54ec1418fd84109ebbf3532f3613f`;
- certyfikowana migawka:
  `c2db18b284b1dea363d8564d677c8a42a3c6fff2f0ad27f09d45620dee659faa`;
- certyfikacja urządzenia: [run
  30628413038](https://github.com/mwoDevelop/kodi/actions/runs/30628413038);
- promocja dokładnej migawki: [uruchom
  30628911260](https://github.com/mwoDevelop/kodi/actions/runs/30628911260);
- Wdrożenie stable: [uruchom
  30629172028](https://github.com/mwoDevelop/kodi/actions/runs/30629172028).

Publiczna suma kontrolna indeksu stable to
`5d8d10890c0f59fd7762a5afd8f8834f8c4ab7ea5fb24b4fec279c3485d33528`. Publiczny stable ZIP
zawiera dokładny, certyfikowany skrót powyżej. `repository.mwodevelop` pozostaje wersją
`1.0.0`.

## Wdrożenie urządzenia

Kolejność wydania była następująca: BlueStacks, X88 Pro 20, a następnie Sony TV.

| Urządzenie | Kodi | Umbrella | MwoScrapers | Szukaj | Odtwarzanie RD | WatchNixtoons2 |
| --- | --- | --- | --- | --- | --- | --- |
| BlueStacks | 21,3 | 6.7.81.18 | 0.1.8 | minęło | minęło | minęło |
| X88 Pro 20 | 21,3 | 6.7.81.18 | 0.1.8 | minęło | minęło | minęło |
| Sony TV z NordVPN | 21,3 | 6.7.81.18 | 0.1.8 | minęło | minęło | minęło |

Każda kontrola funkcjonalna wykorzystywała izolowany proces Kodi. Matryce po czyszczeniu
zweryfikowały inwentarz, dokładne wersje, pochodzenie repozytoriów, wyszukiwanie
Umbrella, funkcję rozpoznawania/odtwarzania Sintel i odtwarzanie WatchNixtoons2.

Na wszystkich trzech urządzeniach:

- każdy zarządzany dodatek mwoDevelop jest własnością `repository.mwodevelop`;
- Brak `repository.mwodevelop.testing`;
- Wdrożenie grafiki ulubionych `CARTOONS` dopasowało i zmaterializowało wszystkie siedem
  skrótów WatchNixtoons2 bez żadnych błędów.

Bedroom TV był nieosiągalny w `192.168.1.18:5555`, a NUC SSH był nieosiągalny w
`192.168.1.25:22`; oba zostały pominięte po niepowodzeniu kontroli protokołu TCP i
sąsiadów.

## Ograniczenie X88 NordVPN

X88 nie ma aktywnego tunelu VPN. Poprzednio zainstalowana wersja `9.9.2` była wersją
mobilną i nie działała na telewizorze. Google Play rozwiązał problem z tym samym
pakietem mobilnym, ponieważ oprogramowanie sprzętowe X88 nie identyfikuje się jako
obsługiwany element docelowy Android TV.

Oficjalny pakiet APK TV NordVPN został pobrany ze strony [NordVPN Android
TV](https://nordvpn.com/download/android-tv/). Przed instalacją porównano jego
certyfikat podpisu SHA-256 z zainstalowanym pakietem Google Play i dopasowano:
`bc64ae0725af656b3b10b684cd1df4c9d6b7f81bc5dc32df3a3b2ce94ce61466`. Zainstalowana wersja
telewizora to `9.9.2+sideload-tv`; jego APK SHA-256 to
`82e4b6828c7aeb973565f6f213016ce8beba52583a111d7e6f84655a4f94a3ce`.

Wersja telewizora wyświetliła następnie wyraźny ekran „urządzenie niekompatybilne”
NordVPN. NordVPN dokumentuje ten stan jako sprzętowy magazyn kluczy lub ograniczenie
certyfikacji urządzenia i zaleca inne certyfikowane urządzenie lub router VPN. Nie
pominięto żadnej kontroli bezpieczeństwa ani zgodności. Wyniki X88 Kodi w tym raporcie
potwierdzają zatem wydanie stable bez VPN; Sony udowadnia to samo wydanie z aktywną
trasą NordVPN `tun0`.

## Niezależność dostawcy

Odkażona sonda punktu końcowego dała następujące wyniki na żywo:

| Urządzenie | Comet film publiczny | Obserwacja Torrentio |
| --- | ---: | --- |
| BlueStacks | 132 | publiczny limit czasu |
| X88 Pro 20 | 132 | Przekaźnik LAN i publiczny limit czasu |
| Sony TV z NordVPN | 132 | Przekroczono limit czasu przekaźnika sieci LAN, publiczny HTTP 403 |

Wyszukiwanie Umbrella i odtwarzanie Real-Debrid są nadal przekazywane na każdym
dostępnym urządzeniu. To pokazuje, że awaria QNAP lub awaria Torrentio/VPN nie powoduje
już usunięcia ścieżki każdego dostawcy.

Przekaźnik QNAP pozostał opcjonalną, bezstanową optymalizacją Torrentio. Nie otrzymuje
danych uwierzytelniających Real-Debrid, magnesów ani ustalonych adresów URL odtwarzania.

## Wady naprawione podczas certyfikacji

- Kanarki Android TV używają teraz domyślnie X88 po BlueStacks.
- Każda funkcjonalna siła kanarkowa zatrzymuje najpierw Kodi, zapobiegając
  zanieczyszczeniu stanu kodeka lub programu tłumaczącego w następnym teście.
- Certyfikacja urządzenia odczytuje wersje dodatków i pochodzenie z poziomu Kodi, który
  obsługuje pamięć masową o zakresie Android.
- Odczyty pochodzenia o określonym zakresie wysyłają ponownie porzucone polecenie
  EventServer.
- Sonda diagnostyczna punktu końcowego ponawia teraz także porzuconą komendę `RunScript`
  w ramach pierwotnego limitu czasu.
- Chronione narzędzie do czyszczenia dodatków usuwa repozytorium dopiero po
  udowodnieniu, że żaden zainstalowany dodatek nadal nie używa go jako źródła. Katalog
  jest przywracany niepodzielnie, jeśli czyszczenie bazy danych nie powiedzie się.

Odpowiednie połączone żądania ściągnięcia:

- [#81](https://github.com/mwoDevelop/kodi/pull/81),
  [#82](https://github.com/mwoDevelop/kodi/pull/82),
  [#83](https://github.com/mwoDevelop/kodi/pull/83),
  [#84](https://github.com/mwoDevelop/kodi/pull/84),
  [#85](https://github.com/mwoDevelop/kodi/pull/85) i
  [#86](https://github.com/mwoDevelop/kodi/pull/86).

## Powtarzalna weryfikacja

Uruchom testy repozytorium:

```bash
.venv/bin/pytest -q tests
```

Uruchom dokładną matrycę urządzenia stable:

```bash
python tools/certify_device_matrix.py \
  --snapshot snapshot.tar \
  --devices .kodi-private/devices.json \
  --references .env \
  --device bluestacks1 \
  --device x88pro20 \
  --output post-cleanup-device-matrix.json
```

Uruchom oczyszczoną sondę dostawcy:

```bash
python tools/kodi_mwoscrapers_endpoint_probe.py \
  --serial DEVICE \
  --timeout 120
```

Ostateczny pakiet lokalny przeszedł testy `216`. Kontrole PR dotyczące czyszczenia i
ponownej próby sondy zostały przekazane w seriach
[30630458321](https://github.com/mwoDevelop/kodi/actions/runs/30630458321) i
[30632130038](https://github.com/mwoDevelop/kodi/actions/runs/30632130038). Ostatnia
automatyczna publikacja testing
[30632298105](https://github.com/mwoDevelop/kodi/actions/runs/30632298105) przeszła
przez bramę złośliwego oprogramowania, wykryła publiczne dane wyjściowe o identycznych
bajtach i poprawnie nie utworzyła ani nowej migawki, ani wdrożenia.
