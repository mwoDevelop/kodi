# Cykl życia schematów

Źródłem prawdy jest
[`manifests/schema-lifecycle.json`](../manifests/schema-lifecycle.json). Ta tabela
jest walidowana w CI i nie może samodzielnie zmieniać znaczenia wersji.

| Format | Bieżące schematy | Legacy | Reader produkcyjny | Migrator offline |
|---|---:|---:|---|---|
| `device_registry` | 2 | 1 | `tools/kodi_devices.py` | `tools/migrations/legacy_config.py` |
| `disaster_recovery_snapshot` | 1 | — | `tools/kodi_profile.py` | klasyfikator zawartości WatchNixtoons2 |
| `favourite_artwork_manifest` | 1 | — | `tools/favourite_artwork.py` | — |
| `portable_state` | 1 | — | `tools/kodi_portable_state.py` | — |
| `profile_policy` | 2 | 1 | `tools/kodi_profile.py` | `tools/migrations/legacy_policy.py` |
| `profile_sync_local_state` | 1 | — | Profile Sync | — |
| `profile_sync_revision` | 2, 3 | — | Profile Sync | — |
| `reinstall_config` | 2 | 1 | `tools/kodi_reinstall.py` | `tools/migrations/legacy_config.py` |
| `stable_lock` | 2 | — | `tools/build_repo.py` | — |
| `testing_lock` | 1 | — | `tools/build_repo.py` | — |

Snapshot disaster recovery schema 1 jest bieżącym kontenerem. Jego zawartość
może jednak zostać oznaczona jako `LEGACY_QUARANTINED`, jeżeli przywróciłaby
stary dodatek WatchNixtoons2. Historyczny `policy_sha256` snapshotu nie jest
samodzielnym dokumentem policy i nie podlega migracji. Pole `installer`
przechowuje dokładnie jedną tożsamość platformy: zweryfikowane APK Androida
albo przypięty scope/origin/ref Flatpaka. Nie jest to nowa wersja schematu.
