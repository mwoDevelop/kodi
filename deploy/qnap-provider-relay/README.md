# Przekaźnik metadanych providerów na QNAP

W przypadku rutynowych buildów i wdrożeń współdzielonych z innymi usługami Kodi na QNAP
użyj [`tools/qnap_images.py`](../../docs/qnap-images.md). Poniższe polecenia pozostają
polityką przekazywania niższego poziomu i interfejsem cyklu życia.

Ta bezstanowa aplikacja Container Station jest wąskim mostem sieciowym używanym, gdy
adres wyjściowy VPN Kodi jest odrzucany przez publicznego providera. Nie otrzymuje poświadczeń
Real-Debrid ani rozwiązanego ruchu związanego z odtwarzaniem.

Cykl życia hosta dotyczy `/var/run/docker.sock`, silnika Docker zarządzanego i
wyświetlanego przez GUI Container Station 3. Nie wdrażaj tego projektu w oddzielnym
silniku `/var/run/system-docker.sock`.

Ograniczenia wdrożeniowe:

- przypnij `MWO_RELAY_IMAGE` przez digest GHCR;
- powiąż produkcję z jawnym prywatnym adresem LAN QNAP, nigdy `0.0.0.0`;
- nie dodawaj woluminów, wpisów tajnych, sieci hostów ani zwiększonych możliwości;
- zachowaj w obrazie stałą listę dozwolonych providerów i ścieżek;
- użyj izolowanego testu smoke na loopbacku przed wymianą projektu produkcyjnego.

Sprawdź politykę Compose:

```bash
python tools/qnap_provider_relay.py policy \
  --mode production \
  --env-file deploy/qnap-provider-relay/env.example \
  --allow-placeholder
```

Narzędzie cyklu życia hosta przesyła tylko ten plik Compose i plik środowiska w trybie
`0600`. Tryb smoke wykorzystuje unikalny katalog i projekt; po weryfikacji uruchom
pasujące polecenie `destroy`, aby usunąć wszystkie kontenery, sieci i pliki kontrolne.
