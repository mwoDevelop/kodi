# Watchdog synchronizacji upstream na QNAP

W przypadku rutynowych kompilacji i wdrożeń współdzielonych z innymi usługami Kodi QNAP,
użyj [`tools/qnap_images.py`](../../docs/qnap-images.md).

Ta niezależna usługa Container Station odpytuje najnowsze uruchomienie każdego
cyklicznego workflow upstream. Raportuje `monitored_state=FAILED`, gdy brakuje
workflow, zakończył się on błędem albo jest przeterminowany. Stan kontenera opisuje
natomiast gotowość obserwatora: poprawny, kompletny i świeży raport pozostaje
`healthy` nawet wtedy, gdy wykrył awarię monitorowanego workflow.

Proces odpytuje GitHub co 15 minut; Container Station ocenia ostatni utrwalony wynik
co pięć minut. Wersjonowany manifest obejmuje centralne uzgadnianie, audyt zaakceptowanych
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

Aplikacja wymaga odczytu publicznych repozytoriów oraz `Actions: write`, ale nie
wymaga zapisu treści, PR, release ani administracji repozytorium. Dedykowany token
w `GITHUB_TOKEN` powinien być ograniczony do repozytoriów obecnych w manifeście.
Migracyjny token `gh auth` może mieć szersze zakresy, dlatego należy zastąpić go
dedykowanym PAT. Obecny walidator wdrożeniowy potrafi dowieść capability na
podstawie klasycznego zakresu `workflow`; fine-grained PAT bez nagłówka zakresów
jest odrzucany fail-closed zamiast ujawniać brak uprawnień dopiero po awarii crona.
Kontener nie ma opublikowanych portów, dodatkowych capabilities ani zapisywalnego
głównego systemu plików. Jedyne bind mounty to trzy pliki certyfikatów obserwatora,
zamontowane read-only z zarządzanego katalogu QNAP. Prywatny endpoint
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
