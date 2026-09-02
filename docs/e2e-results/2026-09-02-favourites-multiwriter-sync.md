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

Pierwsza certyfikacja release wykryła też krótkie okno inicjalizacji katalogu Umbrelli:
Kodi pokazywało już okno Videos, ale `Files.GetDirectory` zwracało jeszcze
`-32602 Invalid params`. Sonda ponawia teraz wyłącznie ten dokładny błąd w istniejącym
limicie czasu; inne błędy JSON-RPC nadal kończą próbę natychmiast. Dwa kolejne testy
live po świeżym starcie Kodi zwróciły po jednym właściwym wyniku i okno Videos.

Wolniejszy przebieg zdalny wykazał następnie, że odpytywanie tego samego katalogu,
gdy GUI nadal posiada jego wywołanie pluginu, może podtrzymywać `-32602`. Sonda
rozdziela teraz dwie odpowiedzialności: najpierw, przed nawigacją GUI, sprawdza
wynik wyszukiwania niezależnym żądaniem, a następnie osobno przechodzi
rzeczywistą ścieżkę klawiatury i powrotu do Videos. Inne błędy pluginu i JSON-RPC
nadal kończą próbę natychmiast.

Pełny lokalny certyfikator odtworzył również zimny start: pierwsza sonda mogła
zainicjalizować Umbrellę, lecz poprzednia polityka restartowała Kodi przed drugą
próbą i ponownie tworzyła zimny stan. Sonda zwraca teraz osobny kod wyjścia tylko
dla tego warunku. Certyfikator po nim pozostawia dogrzaną instancję i uruchamia
nowy proces sondy; wszystkie inne kody błędów nadal powodują pełny restart Kodi.

Na X88 certyfikator znalazł następnie rzeczywistą usterkę instalacji zależności:
`script.module.urllib3` deklarował wersję 2.2.3, ale brakowało katalogu `http2`,
przez co import `requests` zatrzymywał Umbrellę. Androidowy rollout weryfikuje
teraz zawartość wszystkich przypiętych czystych zależności Pythona z oficjalnego
repozytorium Kodi względem SHA-256 ZIP-u i naprawia pakiet, gdy sama wersja w
bazie Kodi jest poprawna, lecz pliki są niepełne albo zmienione.

## Wydanie stable i rozszerzony rollout

- końcowy release zakończył się `COMPLETE`; promocja snapshotu została zatwierdzona,
  a publiczny lock i 57 opublikowanych plików repozytorium zweryfikowano po deployu;
- rollout canary BlueStacks/X88 zakończył się `COMPLETE`; wszystkie sondy dodatków,
  Umbrella/Real-Debrid, providerów, Rapideo, YouTube i runtime przeszły, a pełny
  zestaw lokalny miał wynik 731 testów;
- Bedroom TV początkowo zachowywał proces Kodi w tle przy wyłączonym EventServerze.
  Adapter odróżnia teraz gotowy proces od uśpionego PID-u, aktywuje aplikację i
  ponawia kontrolę gotowości. Test wymuszający powrót do launchera potwierdził tę
  ścieżkę;
- Bedroom TV został przeparowany, oba strumienie stanu włączono, a rollout zakończył
  się `COMPLETE` z dziewięcioma Favourites i pełnym zestawem 732 testów;
- `nuc-mwo` i `nuc-alek` przeszły ręczny cutover do generacji 2. Test live ujawnił i
  naprawił brak przekazywania opcjonalnego klucza szyfrowania w hostowym transporcie
  parowania Flatpak. Po ponownym przebiegu oba profile raportowały Favourites i
  playback `HEALTHY`, cursor 6/13, pending events 0 i aktywny fence;
- końcowy wspólny no-op BlueStacks, X88 i Bedroom TV potwierdził Favourites
  `HEALTHY`, cursor 6, pending 0 oraz identyczny semantyczny SHA-256. Sony TV nie było
  celem tego rolloutu na wyraźne polecenie operatora;
- po wszystkich poprawkach hostowego rolloutu pełny zestaw regresyjny zakończył się
  wynikiem 734 testów, a kontrola statyczna zmienionych plików i `git diff --check`
  przeszły bez uwag.

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
