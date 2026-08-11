# Wdrożenie Profile Sync 0.1.8 stable

Data: 2026-07-31

## Zwolnione artefakty

- Dodatek Kodi: `service.mwodevelop.profilesync` 0.1.8;
- zatwierdzenie dodatku: `69fd1921906e32a2e1bd4e5106690ebe103b41a2`;
- publiczny stable ZIP SHA-256:
  `0542cad64b30c2491ae42ce1b4a07011d002ba1de6b064092443cea1ba942574`;
- niezmienna migawka testing:
  `b89c7205c1a6a40f573c24bc1a9e68725da066c3b5b49a50d5308ada05d50698`;
- Serwer QNAP: 0.2.1, kompilacja `git:0e36e579078c57034be05b440c933096e5807007`;
- Obraz QNAP:
  `ghcr.io/mwodevelop/kodi-profile-sync-server@sha256:166a4303b083daf23a10e18d4ffc756e0b16d3aedb9a073583c755addc20390f`.

`repository.mwodevelop` celowo pozostaje w wersji 1.0.0.

## Dowody promocyjne

- Nakład publikacji testing: `30640650514`;
- przebieg certyfikacji urządzenia: `30643501928`;
- Promocja dokładnej migawki: `30644134769`;
- recenzja promocji PR: `#93`;
- Uruchomienie wdrożenia stable: `30644515552`.

Certyfikacja dotyczyła BlueStacks i X88 Pro 20. stable workflow skopiował certyfikowany
ładunek migawki bez konieczności przebudowywania komponentów ZIP. Kontrola HTTP po
wdrożeniu pobrała publiczny plik ZIP stable i odtworzyła powyższy SHA-256.

## Wyniki urządzenia

| Urządzenie | Kodi | Pochodzenie stable | Izolowany czek podpisany | Synchronizacja produkcji | Zastosuj/rollback |
|---|---:|---|---|---|---|
| BlueStacks1 | 21,3 | przejść | przejść | przejść | przejść |
| X88 Pro 20 | 21,3 | przejść | przejść | przejść | przejść |
| Sony TV | 21,3 | przejść | przejść | sparowany; odkryto aktywną wersję | przejść |

Po izolowanym teście BlueStacks i X88 zachowały oryginalny bajt po bajcie z rejestracji
produkcyjnej. Sony otrzymało oddzielną rejestrację produkcyjną. W tym raporcie nie ma
kodu parowania, tokena dostępu, materiału początkowego podpisu ani poświadczeń.
Jednorazowe pliki parowania zostały usunięte po użyciu.

Po rejestracji Sony kopia zapasowa `production-final-20260731` została pobrana z QNAP,
zaszyfrowana poza serwerem NAS za pomocą AES-256-GCM i ponownie otwarta tylko w pamięci.
SQLite zgłosił schemat 2, `integrity_check=ok`, trzy rejestracje i dwa podpisane raporty
Canary. Zaszyfrowany plik ma tryb `0600`; pobrany tekst jawny został usunięty.

Sonda produkcyjna X88 ujawniła jednorazowe, stratne uruchomienie EventServera. Uprząż
E2E preferuje teraz JSON-RPC i wraca do EventServer. Izolowana sonda usuwa teraz również
stan produkcyjny tylko w ramach swojej tymczasowej transakcji, czeka na wyraźny znacznik
czyszczenia i przywraca pierwotny stan przed zgłoszeniem powodzenia.

## Stan przenośny i repozytoria

Ostateczny audyt tylko do odczytu dotyczący BlueStacks, X88 i Sony zwrócił `OK` dla
każdego urządzenia i ten sam skrót ulubionych. Każdy miał:

- 8 ulubionych;
- 7 aktualnych akcji WatchNixtoons2;
- 7 przenośnych elementów WatchNixtoons2;
- brak brakujących plików graficznych;
- unikalna, spójna tożsamość logiczna Profile Sync i rejestracja produkcyjna.

Po promocji repozytorium testing zostało usunięte z BlueStacks i X88. Wszystkie trzy
urządzenia udostępniają tylko `repository.mwodevelop` 1.0.0 i oficjalne repozytorium
Kodi, a wszystkie pięć komponentów mwoDevelop ma pochodzenie stable.

Bedroom TV i oba konta NUC były niedostępne i celowo nie zgłaszano, że pomyślnie
przeszły ostateczne wdrożenie.

## Powtarzalne kontrole

```bash
PYTHON=/path/to/venv/bin/python tests/e2e/run.sh
PYTHONPATH=. /path/to/venv/bin/python \
  tests/e2e/profile_sync_addon_device.py \
  --repository-channel stable --device <logical-device-id> \
  --devices /path/to/private/devices.json \
  --server-repository /path/to/kodi-profile-sync-server
PYTHONPATH=. /path/to/venv/bin/python \
  tests/e2e/profile_sync_production_device.py \
  --action sync --device <logical-device-id> \
  --devices /path/to/private/devices.json \
  --server-url https://<private-qnap>:18765 \
  --ca-certificate /path/to/private/ca.crt
PYTHONPATH=. /path/to/venv/bin/python \
  tools/kodi_portable_state_rollout.py audit \
  --devices /path/to/private/devices.json \
  --references /path/to/private/.env
```

Kompilacja repozytorium została wygenerowana dwukrotnie i porównana rekurencyjnie.
Ostatecznym wynikiem pakietu był `275 passed`.
