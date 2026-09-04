# Budowanie i wdrażanie obrazów QNAP

`tools/qnap_images.py` jest wspólnym punktem wejścia na hoście dla pięciu aplikacji Kodi
Container Station:

- `control-plane` (odczytowy agregator floty i audytu);
- `profile-sync`;
- `provider-relay`;
- `secret-broker` (szyfrowane zestawy sekretów dla urządzeń);
- `upstream-watchdog`.

Uruchamia należące do repozytorium buildy GitHub Actions, publikuje obrazy
wieloarchitekturowe do GHCR, weryfikuje wymagane platformy manifestów, rejestruje
niezmienne odniesienia do digestów w ignorowanym przez Git pliku
`.kodi-private/qnap-images.json`. Build odrzuca brudne
lub niewypchnięte repozytorium źródłowe, dlatego obraz zawsze odpowiada dokładnemu
commitowi Git.

W produkcyjnym release autorytatywnym źródłem jest jednak publiczny,
zreviewowany `manifests/locks/qnap-stable.json`, a nie ten prywatny cache.
`tools/kodi_ops.py release` uruchamia build tylko po zmianie deterministycznego
hasha zadeklarowanych inputów. Każdy workflow publikuje approval zawierający
immutable digest obrazu, commit, input hash, platformy, SHA raportu skanera i
run ID. `tools/qnap_candidate.py` składa komplet pięciu approval w jeden asset
testing, a PR promocji kopiuje dokładnie jego bajty do stable locka.

## Typowe polecenia

Sprawdź działające kontenery QNAP bez ich zmiany:

```bash
python tools/qnap_images.py status
```

W przypadku watchdoga `status` odczytuje również utrwalony wynik działania i zgłasza
czas kontroli, liczbę workflow, `observer_ready`, `collection_state`,
`monitored_state` oraz dokładne nazwy workflow zakończonych błędem lub nieznanych.
Pozwala to odróżnić działający watchdog, który wykrył błąd procesu, od uszkodzonego
lub niezdolnego do zebrania danych obserwatora.

Podejrzyj wszystkie buildy bez logowania do GHCR i bez uruchamiania Dockera:

```bash
python tools/qnap_images.py build all --dry-run
```

Zbuduj i opublikuj obrazy-kandydatów przez GitHub Actions, a produkcyjnie wdróż
wyłącznie digesty z zatwierdzonego stable locka:

```bash
python tools/qnap_images.py build all
python tools/qnap_images.py deploy all
```

Gdy digest stable się nie zmienił, ale trzeba ponownie zastosować prywatną
konfigurację wybranej usługi (na przykład po rotacji tokena Watchdoga), użyj:

```bash
python tools/qnap_images.py deploy upstream-watchdog --reconcile
```

`--reconcile` ponownie stosuje także konfigurację montowaną z hosta. Dla
Control Plane oznacza to kontrolowane odtworzenie jego kontenerów, ponieważ samo
skopiowanie zmienionego katalogu harmonogramów nie przeładowuje katalogu
zapamiętanego przez działający proces.

Bez jawnego `--reconcile` zgodny digest pozostaje bezpiecznym `NO_CHANGE`.

To interfejs niskopoziomowy do diagnostyki i kontrolowanych prac serwisowych.
Rutynowy rollout wykonuj przez `tools/kodi_ops.py rollout`; wtedy deploy jest
dozwolony wyłącznie z zatwierdzonego stable locka, pod zdalną blokadą i z
kontrolą CAS obserwowanego runtime.

Połączona forma build + deploy celowo omija promocję stable i jest dostępna
wyłącznie do kontrolowanego testu kandydata z jawnym potwierdzeniem:

```bash
python tools/qnap_images.py update all --allow-unpromoted
```

Domyślnym mechanizmem publikacji jest GitHub Actions. Pozwala to uniknąć lokalnego,
długotrwałego tokena `write:packages`; skrypt czeka na zakończenie każdego workflow,
a następnie ustala i zapisuje digest GHCR. W razie potrzeby dostępna jest jawnie uwierzytelniona
lokalna kompilacja Buildx:

```bash
python tools/qnap_images.py build all --publisher local
```

W operacji częściowej zastąp `all` jedną lub kilkoma nazwami:

```bash
python tools/qnap_images.py update upstream-watchdog --allow-unpromoted
python tools/qnap_images.py build profile-sync provider-relay
python tools/qnap_images.py build control-plane
```

Domyślnym checkoutem serwera Profile Sync jest katalog równorzędny
`../kodi-profile-sync-server`. W razie potrzeby zastąp go jawnie:

```bash
python tools/qnap_images.py \
  --profile-sync-repository /path/to/kodi-profile-sync-server \
  build profile-sync
```

Analogicznie źródło Control Plane jest domyślnie pobierane z
`../kodi-control-plane` i może zostać wskazane przez
`--control-plane-repository`. Przed pierwszym wdrożeniem wygeneruj rozdzielone
materiały mTLS; prywatne CA operatora nie jest współdzielone z CA Profile Sync:

```bash
python tools/control_plane_credentials.py --host-ip 192.168.1.39
python tools/qnap_images.py deploy control-plane --dry-run
```

Stary stable lock zawierający trzy usługi pozostaje czytelny tylko na czas
przejścia. `deploy all` wdraża wtedy dokładnie usługi obecne w locku; jawne
wdrożenie `control-plane` zostanie odrzucone do chwili promocji kompletnego,
czterousługowego locka.

## Granica bezpieczeństwa

- `build` wymaga czystych repozytoriów źródłowych, których dokładne commity są
  headami wypchniętych gałęzi `origin`, oraz uwierzytelnionego CLI `gh`;
- domyślny wydawca używa krótkotrwałych poświadczeń repozytorium `GITHUB_TOKEN` w ramach
  GitHub Actions; opcjonalny wydawca lokalny przekazuje poświadczenia GHCR do
  `docker login` przez standardowe wejście i nigdy nie zapisuje ich w pliku stanu obrazu;
- Buildx publikuje niezmienne manifesty wieloplatformowe, a skrypt weryfikuje wymagane
  wpisy `linux/amd64`, `linux/arm/v7` i, w przypadku watchdoga, `linux/arm64`;
- wdrożenie Profile Sync zachowuje istniejącą macierz RAID, TLS, rejestr kluczy, kopie
  zapasowe i bramki gotowości;
- wdrożenie przekaźnika providerów zachowuje bezstanową politykę Compose i sondę
  providera na żywo; sonda zewnętrznego providera jest krótko ponawiana po osiągnięciu
  lokalnej gotowości, aby tolerować wyścigi podczas uruchamiania i odpowiedzi upstream;
- wdrożenie watchdoga sprawdza wzmocnione zasady Compose i wycofuje poprzednie
  pliki Compose, jeśli nowy kontener nie może opublikować pełnego dokumentu statusu
  dokładnie 12 workflow z wersjonowanego manifestu; schemat 3 manifestu przypina
  także gałąź używaną przez awaryjny `workflow_dispatch` (`main` albo `master`),
  więc remediacja nie zależy od zaszytej nazwy gałęzi;
- healthcheck watchdoga sprawdza gotowość obserwatora, pełny katalog, świeżość i
  spójność schema; wykryta awaria workflow jest publikowana osobno jako
  `monitored_state=FAILED` i nie psuje kondycji kontenera. Wdrożenie nadal nie
  ukrywa tej awarii upstream w statusie ani w Control Plane;
- wdrożenie Control Plane publikuje wyłącznie API mTLS, nie montuje socketa
  Dockera, używa oddzielnego CA operatorów i łączy się z read-only integration
  API Profile Sync oraz endpointem Watchdoga przez prywatną sieć Compose; odczyty
  GitHub używają zweryfikowanego tokena read-only zamiast limitu anonimowego;

Wszystkie kontenery są uruchamiane przez silnik zarządzany przez GUI Container
Station. Żaden kontener aplikacyjny nie otrzymuje `/var/run/docker.sock`, a skrypt
nigdy nie kieruje operacji do QNAP `system-docker`.
