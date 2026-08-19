# E2E automatycznego release Umbrelli — 2026-08-19

## Zakres

Test obejmuje izolacje komponentu, status publiczny, hermetyczna atestacje,
allowlisty PR, promocje stable, forward rollback, pojedynczy writer Pages,
watchdog, odtwarzalnosc forka oraz klienta Profile Sync. Test nie wlacza
`UMBRELLA_AUTO_MERGE_ENABLED` i nie stanowi dowodu wdrozenia zdalnego.

## Wyniki

- glowne repo: `570 passed`;
- fork Umbrelli: `56 passed` oraz udany `rebuild_downstream.py --check`;
- Profile Sync: `40 passed`;
- workflow: 17 plikow YAML poprawnie sparsowanych;
- build Pages z `status/umbrella.json`: dwa niezalezne buildy bajtowo identyczne;
- `git diff --check` i `compileall`: bez bledow.

Po udostepnieniu pelnych uprawnien oba testy repozytorium HTTP zostaly wykonane
z rzeczywistym lokalnym socketem i przeszly poprawnie.

## Odtworzenie

```bash
KODI_COMPONENT_ROOT="$PWD" .venv/bin/python -m pytest -q tests

(cd umbrella && .venv-downstream/bin/python tools/rebuild_downstream.py --check)
(cd umbrella && .venv-downstream/bin/python -m pytest -q)
(cd profile-sync-addon && PYTHONPATH=resources/lib ../.venv/bin/python -m pytest -q)
```

Zdalne CI powinno powtorzyc ten sam komplet przed scaleniem.
