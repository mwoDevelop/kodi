# Synchronizacja upstream E2E

Uruchom z dowolnego katalogu:

```bash
/home/mwo/projects/kodi/tests/e2e/upstream_sync/run.sh
```

Test przeprowadza dwa niezależne przebiegi wykrywania na żywo i wymaga, aby drugi
przebieg był identyczny pod względem bajtów i zawierał `noop`. Następnie rekonstruuje
Umbrella i WatchNixtoons2 na podstawie ich zaakceptowanych tożsamości upstream, sprawdza
każdą obserwację dostawcy, uruchamia wszystkie testy komponentów, materializuje dokładne
blokady stable/testing w nowej kasie, dwukrotnie buduje repozytorium Kodi i potwierdza,
że ​​zamek stable nie został zmodyfikowany.

Raporty zapisywane są do `.e2e/upstream-sync/`. Skrypt nie posiada tokena zapisu i nie
tworzy rozgałęzień, pull requesty ani wydań.
