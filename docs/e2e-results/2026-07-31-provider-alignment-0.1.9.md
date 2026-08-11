# Dostosowanie dostawcy 0.1.9 i certyfikacja programu rozpoznawania nazw VPN

Data: 2026-07-31

## Wynik

Kandydat łączy MwoScrapers 0.1.9 i Umbrella 6.7.81.19. Torrentio i Comet są włączone w
każdym celu. Cele Android TV korzystają z opcjonalnego przekaźnika LAN Torrentio, po
którym następuje publiczna sieć rezerwowa; BlueStacks i X88 korzystają bezpośrednio z
publicznego punktu końcowego. Comet zawsze korzysta ze swojego niezależnego publicznego
punktu końcowego.

Pamięć podręczna dostawcy Umbrella wynosi sześć godzin, RD Cloud jest wyłączona, a `Only
try one source` ma wartość false w zarządzanych profilach. Komenda konfiguracyjna
resetuje tylko `providers.db` po zmianie punktu końcowego.

Umbrella ogranicza każdą próbę RD, ale typowy termin ostateczny wynosi 45 sekund.
Obejmuje to serializowane wywołania API obserwowane przez NordVPN bez rozpoczynania
nakładających się procesów roboczych mechanizmu rozpoznawania nazw. Moduł uruchamiający
E2E osobno czeka na rzeczywisty odtwarzacz JSON-RPC lub jawne zdarzenie zamykające;
powolne uruchamianie demuxera/MediaCodeca nie jest traktowane jako zatrzymane
odtwarzanie.

## Dowód urządzenia

| Urządzenie | Ścieżka Torrentio | VPN | Rozwiąż | Obserwowane odtwarzanie | Wynik |
| --- | --- | --- | ---: | ---: | --- |
| BlueStacks | publiczne | nie | 37,665 s | 10,112 s | minęło |
| X88 Pro 20 | publiczne | niedostępne na tym sprzęcie | 40,757 s | 10,492 s | minęło |
| Sony TV | Przekaźnik LAN plus publiczna rezerwa | NordLynx | 49,894 s | 10,271 s | minęło |
| Bedroom TV | Przekaźnik LAN plus publiczna rezerwa | NordVPN | 45,457 s | 10,392 s | minęło |

Sony początkowo rozwiązało grywalny adres URL RD, ale trzydniowe połączenie NordLynx z
Warszawą nr 297 przekroczyło limit czasu podczas otwierania strumienia CDN. Ponowne
połączenie z nowym tunelem warszawskim nr 308 pozwoliło zachować przypisanie Kodi
podzielonego tunelu i zatwierdzono ten sam kontrolowany scenariusz Sintel. To oddziela
sukces dostawcy i rozwiązania RD od nieaktualnej ścieżki multimediów VPN.

## Odtwórz

Wyrównaj jeden cel:

```bash
python3 tools/kodi_mwoscrapers_configure.py \
  --serial DEVICE \
  --torrentio-endpoint ENDPOINT \
  --comet-endpoint https://comet.feels.legal
```

Uruchom odtwarzanie poprzez Kodi JSON-RPC i urządzenie EventServer:

```bash
python3 tests/e2e/sony_kodi_matrix.py \
  --adb /home/mwo/android-sdk/platform-tools/adb \
  --serial DEVICE \
  --host 127.0.0.1 \
  --jsonrpc-port FORWARDED_PORT \
  --event-via-adb \
  --case sintel \
  --timeout 240 \
  --observe-seconds 10 \
  --direct-play \
  --result result.json
```

Oczyszczony wynik rejestruje wersje dodatków, klasy punktów końcowych, wyniki modułu
rozpoznawania nazw i nieodwracalny odcisk palca źródła. Nigdy nie przechowuje tokenów
RD, magnesów ani ustalonych adresów URL multimediów.
