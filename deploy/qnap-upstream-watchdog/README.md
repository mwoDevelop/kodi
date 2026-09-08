# Watchdog synchronizacji upstream na QNAP

W przypadku rutynowych kompilacji i wdrożeń współdzielonych z innymi usługami Kodi QNAP,
użyj [`tools/qnap_images.py`](../../docs/qnap-images.md).

Ta niezależna usługa Container Station odpytuje najnowsze uruchomienie każdego
cyklicznego workflow upstream. Raportuje `monitored_state=FAILED`, gdy brakuje
workflow, zakończył się on błędem albo jest przeterminowany. Stan kontenera opisuje
natomiast gotowość obserwatora: poprawny, kompletny i świeży raport pozostaje
`healthy` nawet wtedy, gdy wykrył awarię monitorowanego workflow.

Proces odpytuje GitHub co 15 minut, a po wysłaniu remediacji ponawia odczyt po
60 sekundach; Container Station ocenia ostatni utrwalony wynik co pięć minut.
Wersjonowany manifest pozostawia jeden pełny cykl obserwatora między progiem
remediacji a progiem alertu. Obejmuje centralne uzgadnianie, audyt zaakceptowanych
providerów i artefaktów, discovery providerów, Umbrella i WatchNixtoons2. Zobacz pełny
[katalog procesów cyklicznych](../../docs/scheduled-processes.md), aby poznać
własność, granice zapisu i polecenia weryfikacji.

Dokument statusu schema 2 rozdziela `observer_ready`,
`collection_state=READY|PARTIAL|ERROR` i
`monitored_state=HEALTHY|FAILED|UNKNOWN`. Błąd GitHub API lub niekompletny katalog
nie jest fałszywie klasyfikowany jako awaria workflow — daje `UNKNOWN` i niezdrowy
healthcheck obserwatora.

Usługa korzysta z uwierzytelnionych odczytów API GitHub i jednej ograniczonej
operacji zapisu: `workflow_dispatch` dla workflowów wymienionych w wersjonowanym
manifeście. Token nie jest
wersjonowany: narzędzie wdrożeniowe sprawdza zgodność tożsamości z `GITHUB_USER`
i zapisuje go na QNAP wyłącznie w pliku `watchdog.env` o trybie `0600`. Zmienna
`GITHUB_PASS` może być użyta tylko wtedy, gdy zawiera token PAT; zwykłe hasło konta
GitHub nie działa z REST API. W okresie migracji narzędzie może użyć tokena aktywnej,
zgodnej sesji `gh auth`, gdy `GITHUB_PASS` nie jest PAT. Wdrożenie kończy się błędem,
jeśli API nadal zwraca limit anonimowy `60/h`.

Jeżeli `GITHUB_USER` jest adresem e-mail używanym do logowania w przeglądarce,
API nie może go zwrócić bez dodatkowego zakresu `user:email`. W takim przypadku
walidator akceptuje wyłącznie token należący do wersjonowanego właściciela
repozytoriów `mwoDevelop`; token dowolnego innego konta jest odrzucany.

Aplikacja wymaga odczytu monitorowanych repozytoriów, `Checks: read` (adnotacje
przyczyn błędów) oraz `Actions: write`, ale nie
wymaga zapisu treści, PR, release ani administracji repozytorium. Dedykowany token
w `GITHUB_TOKEN` powinien być ograniczony do repozytoriów obecnych w manifeście.
Migracyjny token `gh auth` może mieć szersze zakresy, dlatego należy zastąpić go
dedykowanym PAT. Obecny walidator wdrożeniowy potrafi dowieść capability na
podstawie klasycznego zakresu `workflow`; fine-grained PAT bez nagłówka zakresów
jest odrzucany fail-closed zamiast ujawniać brak uprawnień dopiero po awarii crona.
Kontener nie ma opublikowanych portów, dodatkowych capabilities ani zapisywalnego
głównego systemu plików. Bind mounty obejmują trzy pliki certyfikatów obserwatora
read-only oraz prywatny katalog `state/` (RW, UID 10001, tryb 0700) na trwały
dziennik prób `attempts.json` (0600). Nie ma dostępu do innych danych QNAP.
Prywatny endpoint
`https://upstream-watchdog:9445/v1/status` jest osiągalny wyłącznie w sieci
`mwodevelop-control` i wymaga certyfikatu klienta mTLS; służy Control Plane do
sprawdzania świeżości cyklu. Wdrażaj wyłącznie niezmienny
wieloarchitekturowy digest GHCR. Sekret jest widoczny dla administratora silnika
w metadanych kontenera, dlatego dostęp administracyjny do Container Station pozostaje
granicą zaufania.

Uruchom Compose na `/var/run/docker.sock`, silniku zarządzanym i wyświetlanym przez GUI
Container Station 3. Nie używaj oddzielnego silnika `/var/run/system-docker.sock`.

```bash
docker compose \
  --env-file deploy/qnap-upstream-watchdog/env.example \
  -f deploy/qnap-upstream-watchdog/compose.yaml config
```

Rutynowe wdrożenie pobiera prywatne referencje z ignorowanego pliku `.env`:

```bash
python tools/qnap_images.py deploy upstream-watchdog --reconcile
```

`--reconcile` ponownie stosuje prywatną konfigurację także wtedy, gdy digest obrazu
stable się nie zmienił. Jest wymagane po dodaniu lub rotacji tokena.

Materiał mTLS powstaje razem z nową konfiguracją Control Plane. Dla istniejącej
instalacji można go dołożyć bez rotowania certyfikatu operatora:

```bash
python tools/watchdog_observer_credentials.py
python tools/qnap_images.py deploy upstream-watchdog control-plane --reconcile
```

Skonfiguruj Container Station/QTS tak, aby powiadamiał o niezdrowym kontenerze. Dokument
statusu pozostaje w pliku tmpfs o rozmiarze 1 MiB i zawiera tylko identyfikatory
workflow, czasy, wnioski i nazwy repozytoriów.

## Trwała ochrona puli Actions

`--remediate` wymaga jawnego `--remediation-ledger`. Skrypt wdrożeniowy tworzy
pierwszy dziennik krótkotrwałym kontenerem bez sieci; zwykły start nigdy go nie
resetuje. Zapis rezerwacji próby (fsync pliku i katalogu, atomic replace) następuje
**przed** POST. Blokada pojedynczego writera zapobiega równoległym dispatchom.
Uszkodzenie, utrata lub brak możliwości zapisu daje `remediation_ready=false`
i blokuje remediację, ale nadal pozwala odczytywać stan workflow. Nie usuwać
dziennika ani markera `state-initialized-v1` w celu pozornego naprawienia alarmu.

Adnotacje GitHub Actions są czytane ograniczoną liczbą zapytań i nie są
zapisywane. `failure_category=BILLING_BLOCKED` oznacza potwierdzoną blokadę
budżetu/magazynu, a `NOT_OBSERVED` nieznaną przyczynę. W obu sytuacjach
ponowienie następuje nie częściej niż co 24 h. Nowszy sukces tego samego
workflow/ref usuwa potwierdzoną blokadę. Pozostałe awarie zachowują minimalny
odstęp manifestu, lecz wszystkie automatyczne próby mają dodatkowy limit
trzech rezerwacji na ruchome 24 h. Ręczne działania operatora i cron GitHub
nie są zatrzymywane przez ten lokalny licznik. Alarm domenowy nie znika
po samym dispatchu. Rollback automatyczny uruchamia obserwację bez remediacji.

Powtarzalny test odtworzenia kontenera z tym samym wolumenem (bez prawdziwych
zapytań GitHub, czas symulowany) i testy przypadków błędów:

```bash
docker build -f deploy/qnap-upstream-watchdog/Dockerfile -t kodi-watchdog-e2e .
.venv/bin/python tests/e2e/watchdog_retry_container.py --image kodi-watchdog-e2e
.venv/bin/python -m pytest -q tests/test_watchdog_remediation.py tests/test_upstream_watchdog.py tests/test_qnap_images.py
```

E2E usuwa wyłącznie swój losowo nazwany wolumen testowy; nie dotyka stanu QNAP.
