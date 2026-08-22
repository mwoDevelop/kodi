# Watchdog synchronizacji upstream na QNAP

W przypadku rutynowych kompilacji i wdrożeń współdzielonych z innymi usługami Kodi QNAP,
użyj [`tools/qnap_images.py`](../../docs/qnap-images.md).

Ta niezależna usługa Container Station odpytuje najnowsze uruchomienie każdego
cyklicznego workflow upstream. Zgłasza `unhealthy`, gdy brakuje workflow, zakończył się
on błędem albo jest starszy niż 36 godzin, dzięki czemu brakujący cron GitHub jest widoczny.

Proces odpytuje GitHub co sześć godzin; Container Station ocenia ostatni utrwalony wynik
co pięć minut. Wersjonowany manifest obejmuje centralne uzgadnianie, audyt zaakceptowanych
providerów i artefaktów, discovery providerów, Umbrella i WatchNixtoons2. Zobacz pełny
[katalog procesów cyklicznych](../../docs/scheduled-processes.md), aby poznać
własność, granice zapisu i polecenia weryfikacji.

Usługa korzysta wyłącznie z uwierzytelnionych odczytów API GitHub. Token nie jest
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

Aplikacja wykonuje wyłącznie żądania `GET`; docelowy PAT powinien mieć tylko prawa
odczytu publicznych repozytoriów. Migracyjny token `gh auth` może mieć szersze zakresy,
dlatego należy zastąpić go dedykowanym PAT w `GITHUB_TOKEN` albo `GITHUB_PASS`.
Kontener nie ma woluminów, opublikowanych portów, dodatkowych capabilities ani
zapisywalnego głównego systemu plików. Wdrażaj wyłącznie niezmienny
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

Skonfiguruj Container Station/QTS tak, aby powiadamiał o niezdrowym kontenerze. Dokument
statusu pozostaje w pliku tmpfs o rozmiarze 1 MiB i zawiera tylko identyfikatory
workflow, czasy, wnioski i nazwy repozytoriów.
