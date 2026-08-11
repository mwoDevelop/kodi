# Zestaw migracyjny legacy offline

Ten katalog nie jest importowany przez produkcyjne readery Kodi. Pozostaje
dostępny przez okres retencji starych backupów.

- `legacy_config.py` migruje atomowo parę registry/reinstall i wznawia pracę z
  journala po przerwaniu;
- `legacy_policy.py` migruje samodzielną policy schema 1 do schema 2;
- `watchnixtoons2_snapshot.py` tworzy nowy, zweryfikowany snapshot bez starego
  dodatku i repozytorium.

Do zwykłej obsługi użyj `python tools/migrate_legacy.py`. Niezmienny pakiet
recovery buduje `python tools/build_legacy_migration_kit.py`.
