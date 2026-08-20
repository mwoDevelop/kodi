# E2E automatycznego release Umbrelli — 19–20.08.2026

## Zakres

Test obejmuje izolacje komponentu, status publiczny, hermetyczna atestacje,
allowlisty PR, promocje stable, forward rollback, pojedynczy writer Pages,
watchdog, odtwarzalnosc forka, klienta Profile Sync i rzeczywisty smoke test
X88. Test nie wlacza `UMBRELLA_AUTO_MERGE_ENABLED`.

## Wyniki

- glowne repo: `572 passed` lokalnie, w PR testing, stable i podczas rolloutu;
- fork Umbrelli: `59 passed` oraz udany `rebuild_downstream.py --check`;
- Profile Sync: `40 passed`;
- workflow: 17 plikow YAML poprawnie sparsowanych;
- build Pages z `status/umbrella.json`: dwa niezalezne buildy bajtowo identyczne;
- `git diff --check` i `compileall`: bez bledow.

Wydano Umbrelle `6.7.85.1` z upstream
`653190cd64c37eadae537568518238b3f8e5a27d`. Publiczny indeks stable wskazuje
te wersje, ZIP ma oczekiwany SHA-256
`3eda5c1cbb8f04386ea9f8ddf869dad75a4842c7a6ee1d0b51e5dc3b56ebbcc9`,
a `status/umbrella.json` raportuje `pipeline.state=in_sync` oraz
`release.health=healthy`.

## Dowody GitHub

- kandydat forka i malware/test: run `32317503063`;
- no-op forka: run `32317785802`;
- publikacja testing snapshotu: run `32318246094`;
- hermetyczna atestacja: run `32319219558`;
- promocja stable: run `32319399024`;
- E2E PR stable: run `32319427482`;
- materializacja stable: run `32319619464`;
- atomowy deploy Pages: run `32319861929`;
- koncowy reconcile no-op: run `32320291170`.

## Smoke test urzadzen

Scoped rollout X88 `de1b23edc9a34930ab70728c9e2d5b05` zakonczyl sie
`COMPLETE`: Umbrella `6.7.85.1`, stable origin, mwoScrapers i providerzy,
Real-Debrid, Rapideo, OpenSubtitles.com, Profile Sync oraz portable favourites
przeszly. `opensubtitles.org` zachowal znane ograniczenie konta
`VIP_REQUIRED`, a YouTube jawnie raportuje brak osobistego zestawu API jako
`API_CONFIG_REQUIRED`; nie sa to regresje Umbrelli.

Test ujawnil i naprawil zaleznosc od stratnego EventServera podczas odczytu
originow dodatkow. Odczyt korzysta teraz ze wspolnego JSON-RPC z fallbackiem,
co odblokowalo pelny rollout. BlueStacks nie byl wystawiony w demonie ADB i
zostal oznaczony `DEFERRED`; nie zastepowano go inna instancja.

## Odtworzenie

```bash
KODI_COMPONENT_ROOT="$PWD" .venv/bin/python -m pytest -q tests

(cd umbrella && .venv-downstream/bin/python tools/rebuild_downstream.py --check)
(cd umbrella && .venv-downstream/bin/python -m pytest -q)
(cd profile-sync-addon && PYTHONPATH=resources/lib ../.venv/bin/python -m pytest -q)
```

Zdalne CI powtarza ten sam komplet przed scaleniem zmian kodu i dokumentacji.
