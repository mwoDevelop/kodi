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

Usługa korzysta wyłącznie z publicznych odczytów API GitHub. Nie ma tokena zapisu
repozytorium, woluminów, opublikowanych portów, dodatkowych capabilities ani zapisywalnego
głównego systemu plików. Wdrażaj wyłącznie niezmienny wieloarchitekturowy digest GHCR.

Uruchom Compose na `/var/run/docker.sock`, silniku zarządzanym i wyświetlanym przez GUI
Container Station 3. Nie używaj oddzielnego silnika `/var/run/system-docker.sock`.

```bash
docker compose \
  --env-file deploy/qnap-upstream-watchdog/env.example \
  -f deploy/qnap-upstream-watchdog/compose.yaml config
```

Skonfiguruj Container Station/QTS tak, aby powiadamiał o niezdrowym kontenerze. Dokument
statusu pozostaje w pliku tmpfs o rozmiarze 1 MiB i zawiera tylko identyfikatory
workflow, czasy, wnioski i nazwy repozytoriów.
