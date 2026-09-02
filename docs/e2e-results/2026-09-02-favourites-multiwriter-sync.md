# E2E wielokierunkowej synchronizacji Kodi Favourites

Data: 2026-09-02  
Zakres: `kodi.favourites`, Profile Sync, QNAP, BlueStacks i X88  
Prywatność: raport nie zawiera tytułów, URL-i, tokenów ani identyfikatorów enrollmentu.

## Dokładne artefakty kandydujące

- `service.mwodevelop.profilesync` 1.4.2, commit
  `3074a4c90f51f9cbb9cd18a422619d02bd92d365`, ZIP SHA-256
  `60a8077ca874e56363287b7002b7daa7339f14e741dfb2061997e9bc4e7c2f22`;
- backend Profile Sync 0.10.0 oraz Kodi Control Plane 0.11.0 działały na QNAP jako
  zdrowe kontenery z wdrożonych immutable obrazów kandydujących;
- zakres serwerowy: `scope:home`.

## Wyniki funkcjonalne

1. BlueStacks i X88 zostały jawnie włączone jako writerzy Favourites. Stara,
   osierocona generacja enrollmentu X88 została unieważniona dopiero po poprawnym
   sparowaniu i konwergencji nowej.
2. Pierwszy pull na X88 odtworzył dokładnie dziewięć skrótów oraz dziewięć grafik.
   Kanoniczny dokument na obu klientach miał ten sam SHA-256
   `651ec69c3d846879fc31e2c37bc1a8fec471506a2f7f466dc900dcfd1fc64a53`.
3. Test konfliktowy utworzył dwie różne lokalne wersje dokumentu przy wspólnej
   rewizji bazowej. Serwer przyjął dwa pełne commity, zwiększył licznik konfliktów
   dokładnie o jeden i nadał zwycięskiemu dokumentowi rewizję 5. Nie nastąpiło
   scalanie pozycji.
4. Oba klienty pobrały zwycięski dokument i osiągnęły identyczny stan. Potwierdza to
   model last-accepted-write-wins oraz wykrywanie stale-base w Profile Sync 1.4.2.
5. Znaczniki testowe zostały usunięte pełnym kolejnym commitem. Serwer osiągnął
   rewizję 6, oba klienty cursor 6, `HEALTHY`, pending 0 i aktywny dynamic fence.
6. Stan końcowy obu urządzeń ponownie zawiera dokładnie dziewięć wpisów, dziewięć
   miniaturek, zero znaczników testowych i identyczny pierwotny digest. Powtórna
   synchronizacja obu urządzeń była no-op.

## Znaleziona i usunięta regresja rolloutu

Kanał testing poprawnie przypisuje niezmienione dodatki do repozytorium stable.
Na czystszym X88 brakowało jednak samego wpisu `repository.mwodevelop`, przez co Kodi
nie mogło zatwierdzić takiego originu mimo obecności wszystkich kandydatów testing.
Adapter Android instaluje teraz wcześniej zweryfikowany dokładny ZIP repozytorium
stable jako zależność wspierającą. Operacja nie pobiera dodatków stable i zachowuje
hybrydową politykę originów.

Rzeczywisty rollout X88 po poprawce zakończył się `AUDIT_PASS`,
`ATTESTATION_PASS`, poprawą originów oraz idempotentnym ponowieniem. Profile Sync
1.4.2 został następnie zainstalowany transakcyjnie na obu canary.

## Powtarzalne testy

```bash
cd /home/mwo/projects/kodi
.venv/bin/python -m pytest -q

cd /home/mwo/projects/kodi/profile-sync-addon
../.venv/bin/python -m pytest -q

cd /home/mwo/projects/kodi-profile-sync-server
../kodi/.venv/bin/python -m pytest -q

cd /home/mwo/projects/kodi-control-plane
../kodi/.venv/bin/python -m pytest -q
```

Test produkcyjny pojedynczego klienta:

```bash
PYTHONPATH=. .venv/bin/python tests/e2e/profile_sync_production_device.py \
  --device DEVICE --devices .kodi-private/devices.json \
  --server-url https://192.168.1.39:18765 \
  --ca-certificate .kodi-private/profile-sync-production/tls/ca.crt \
  --channel home-stable --action sync-favourites
```

Konflikt E2E wymaga dwóch klientów z tym samym cursorem, dwóch różnych lokalnych
dokumentów i ręcznej kolejności commitów. Po próbie należy opublikować oczyszczony
dokument, zsynchronizować oba klienty, sprawdzić równy digest i wykonać jeszcze jeden
no-op.
