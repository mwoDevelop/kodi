# Profile Sync 1.1.1 — canary BlueStacks i X88

Data testu: 2026-08-22  
Snapshot testing: `01f23f1f38db5931d951918fab221ca9437bd198af761d0c364894eb2c61aee9`

## Wynik

Profile Sync 1.1.1 został pobrany z publicznego repozytorium testing. SHA-256
ZIP-a był zgodny z lockiem:
`6ae17881d183ce64a8afc6302e05d82051da90c57bf3c770ccb24ffd6888a6ab`.

Na `bluestacks1` i `x88pro20` potwierdzono:

- wersję Profile Sync 1.1.1 i origin `repository.mwodevelop.testing`;
- aktywną rewizję profilu `fbf33000dbc24317c65707029b9356a80049522ab9a49c6ce5170b33130c9110`
  w generacji 4;
- wiązanie Umbrella z `script.module.mwoscrapers` oraz wyłączony filtr
  `realdebrid.filter.filename`;
- zdrowe konto Real-Debrid i poprawne rozpoznanie wyłączonego endpointu
  `instantAvailability`;
- wyszukiwanie Umbrella, odtwarzanie Big Buck Bunny przez resolver oraz
  odtwarzanie WatchNixtoons2.

Pełny `certify_device_matrix.py` zakończył się `result=passed` dla obu
urządzeń. Każdy test funkcjonalny był wykonywany po osobnym restarcie Kodi.

## Providerzy

BlueStacks przeszedł pełną macierz 42 prób dla sześciu providerów. Na X88 pięć
providerów zwróciło łącznie wyniki: Comet 587, Torz 407, PirateBay 239,
MediaFusion 150 i EZTV 2. Torrentio zwróciło HTTP 403 dla wszystkich profili
nagłówków z adresu wyjściowego VPN X88. Jest to izolowana degradacja endpointu,
nie awaria mwoScrapers ani Real-Debrid; kontrolowane odtwarzanie Umbrella na X88
zakończyło się powodzeniem.

## Naprawa wykryta przez E2E

Wysyłanie polecenia przez EventServer na X88 mogło zostać przyjęte przez
lokalny `nc`, ale nie dotrzeć do Kodi. Narzędzia publikacji profilu i macierzy
providerów używają teraz JSON-RPC jako pierwszej drogi, a po braku raportu
próbują kolejno EventServer na urządzeniu i z hosta. Testy regresyjne obejmują
zarówno podstawową drogę, jak i cichy drop.
