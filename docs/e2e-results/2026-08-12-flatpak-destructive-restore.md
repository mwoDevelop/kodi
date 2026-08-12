# Kwalifikacja destrukcyjnego restore Kodi Flatpak

Data: 2026-08-12

## Zakres

Zakwalifikowano publiczną operację:

```bash
.venv/bin/python tools/kodi_ops.py restore \
  --device DEVICE --mode reinstall --yes
```

dla dwóch profili Kodi Flatpak na wspólnym hoście NUC. Adapter przypina model,
fingerprint hosta, UID principala, home, kanoniczny data root, aplikację,
architekturę, scope, origin, ref i wersję Flatpaka. Przed destrukcją tworzy
content-addressed snapshot, sprawdza wszystkie pliki i ponownie identyfikuje
cel. Cache, bazy bibliotek, thumbnails i lokalna tożsamość Profile Sync nie są
odtwarzane.

Kodi jest zainstalowane w scope systemowym. Reset zachował współdzielone
binaria i usunął wyłącznie dane wybranego UID. Po cache-free restore adapter
uruchomił Kodi pod kontrolowanym Xvfb, odtworzył świeży runtime log, sprawdził
mapowania `special://home`, `special://profile`, `special://masterprofile` i
`special://envhome`, zakończył proces przez EventServer, a dopiero potem
uruchomił stable rollout.

## Wyniki live

| Cel | UID | Backup | Odtworzone pliki | Wynik restore | Drugi rollout |
|---|---:|---:|---:|---|---|
| `nuc-alek` | 1001 | 34 MB | 2658 | `COMPLETE` | `NO_CHANGE` |
| `nuc-mwo` | 1000 | 175 MB | 4309 | `COMPLETE` | `NO_CHANGE` |

Oba restore zachowały systemowy Flatpak Kodi 21.3-Omega, ponownie uzgodniły
repo mwoDevelop, Umbrella, mwoScrapers, WatchNixtoons2 i Profile Sync 1.0.3.
Aktywna rewizja Profile Sync została zastosowana bez oczekującego raportu.

Końcowy scoped rollout obu profili miał status `COMPLETE`; oba adaptery
zwróciły `rollout_mode=sync` i `sync_status=NO_CHANGE`. Pełne hermetyczne E2E
po każdym odtworzeniu zakończyło się wynikiem 452 testów.

## Końcowy rollout floty

Pełny rollout `ba5e62ccb4034eb68a4db745631f8db1` objął sześć wpisów inventory.
BlueStacks, X88, Sony TV, `nuc-mwo` i `nuc-alek` przeszły; oba canary miały
działające źródła i Real-Debrid w pierwszej próbie. QNAP reconcile, Profile
Sync oraz 452 testy E2E przeszły. Bedroom TV było niedostępne i zgodnie z
kontraktem otrzymało `DEFERRED`, dlatego globalny raport ma status `PARTIAL`.
