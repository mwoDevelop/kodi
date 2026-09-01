# Brama kompatybilności dodatków Kodi — 2026-09-01

Zakres obejmował wspólną ocenę dokładnych artefaktów, crash-safe transakcję
Androida, build repo, stable/default rollout, Android restore preflight oraz
Flatpak payload/restore.

## Wyniki

| Próba | Wynik |
|---|---|
| Build stable i testing | `AUDIT_PASS` dla Android arm64, Android emulator x86_64 i Linux Flatpak x86_64 |
| Testy jednostkowe i deterministyczne E2E | 711 testów, sukces |
| BlueStacks stable/default | oba raporty `AUDIT_PASS`; drugi przebieg `NO_CHANGE` |
| BlueStacks exact transaction | WatchNixtoons2 0.30.3: `ACTIVATED -> VERIFIED -> COMMITTED` |
| BlueStacks kontrolowany błąd | syntetyczny 0.30.4~rollbacktest: `ROLLED_BACK`, przywrócono 0.30.3 i dokładne bajty ZIP-a |
| BlueStacks pełna regresja | run `a36890d29a09491e9cb53b9e11ef1474`, `COMPLETE` |
| X88 stable/default | oba raporty `AUDIT_PASS`; zarządzane ustawienie YouTube wyrównane, kolejny przebieg `NO_CHANGE` |
| X88 pełna regresja | run `a87695cbecfe483ab0a7f78e04e8394e`, `COMPLETE` |
| NUC `nuc-mwo` Flatpak | runtime 21.3 zakwalifikowany, sync `NO_CHANGE`, run `46cc292a8cc84ad7a95ae7addfe35fcd`, `COMPLETE` |
| Android restore preflight | wszystkie 28 katalogów snapshotu BlueStacks ocenione przed planowaną destrukcją; dry-run `2e4dbde13cbc44f4a09543256385810e`, `COMPLETE` |

Pełne przebiegi BlueStacks i X88 potwierdziły także providery mwoScrapers,
Real-Debrid, Rapideo, YouTube, OpenSubtitles.com, Profile Sync i portable state.
OpenSubtitles.org nadal jawnie raportuje znane ograniczenie konta `VIP_REQUIRED`;
nie jest to regresja bramy, a domyślny dodatek OpenSubtitles.com działa.

## Dowody bezpieczeństwa

- niezgodny kandydat kończy się przed pierwszym ADB push;
- journal i backup Androida pozostają pod `special://home` na tym samym
  filesystemie co dodatki;
- następny proces rozpoznaje transakcję po ID dodatku, także bez hostowego UUID;
- commit jest możliwy dopiero po porestartowym potwierdzeniu wersji i włączenia;
- wymuszony błąd po aktywacji odtworzył poprzednią wersję i pliki;
- build zapisał deterministyczne SHA-256 polityki i projektowanego grafu;
- restore nie ogranicza audytu do `required_addons`, lecz sprawdza każdy kopiowany
  katalog dodatku.

Nie zwiększono wersji dodatków ani repozytorium Kodi, ponieważ zmiana dotyczy
narzędzi hosta, polityki kwalifikacyjnej, restore i raportowania, a nie kodu ZIP-ów
publikowanych użytkownikom.
