# Niezależny review planu kompatybilności dodatków

Data: 2026-09-01

Przedmiot: `KODI_ADDON_RUNTIME_COMPATIBILITY_PLAN.md`

Reviewer nie edytował repozytorium. Porównał plan z aktualnymi ścieżkami Android,
Flatpak, restore, build oraz natywnym instalatorem Kodi. Pierwotny werdykt: `REVISE`.

## P0 — uwagi blokujące

1. **Restore oceniał zbyt mały zbiór.** Pełny snapshot kopiuje całe `addons/**` i
   może ponownie włączyć dodatek spoza `required_addons`. Przyjęto audyt wszystkich
   kopiowanych katalogów dodatków przed uninstall. Nieparsowalny albo niezgodny
   dodatek zatrzymuje restore; nie jest po cichu pomijany.
2. **Transakcja Androida nie była crash-safe.** `special://temp` oraz marker hosta
   nie gwarantują odzyskania po restarcie lub utracie procesu. Przyjęto trwały journal
   i backup pod `special://home`, kontrolę tego samego filesystemu, atomowy zapis z
   `fsync`, jeden aktywny transaction per addon oraz idempotentne operacje
   `status/commit/rollback`. Następny proces wykrywa transakcję bez znajomości UUID.
3. **`kodi-native-official` nie wiązał oceny z instalowanymi bajtami.**
   `InstallAddon(id)` może wybrać inny artefakt z aktualnego indeksu. Przyjęto exact
   ZIP transaction dla zastępowania istniejącej wersji. Dla nieobecnego dodatku
   natywna instalacja jest dopuszczalna wyłącznie z porestartowym porównaniem całego
   drzewa do przypiętego ZIP-a; różnica usuwa nowy, nieposiadający poprzednika stan i
   kończy przebieg błędem.
4. **Flatpak restore nie miał faktów rzeczywistego docelowego runtime.** Instalacja
   z refa może pobrać nowszy commit. Przyjęto obowiązkowy probe wersji, architektury i
   ścieżek po instalacji, ale przed skopiowaniem profilu, oraz ponowną ocenę wszystkich
   przenoszonych dodatków. Deklarowana wersja snapshotu nie jest faktem live. Jeśli
   docelowy runtime jest niezgodny, profil nie jest kopiowany, a restore wykonuje
   istniejącą bezpieczną kompensację albo raportuje `RECOVERY_REQUIRED`.

## P1 — uwagi istotne

- Zastąpiono porównanie samego numerycznego prefiksu semantyką wersji zgodną z Kodi,
  obejmującą `~alpha`, `~beta` i sufiksy dystrybucyjne. Nieznany format jest
  fail-closed.
- Runtime platform jest zbiorem tokenów, np. `android` i `android-aarch64`, a
  `<platform>` listą. Pierwszy release odrzuca każdy arbitralny ZIP z kodem natywnym;
  istniejący, natywnie instalowany `inputstream.adaptive` pozostaje objęty osobną
  kwalifikacją ABI.
- Ocena używa projekcji finalnego grafu: planowana wersja przesłania zainstalowaną,
  ID są unikalne, cykle są odrzucane, a kolejność instalacji jest topologiczna.
  Obecna opcjonalna zależność może być nieobecna; jeśli jest planowana lub obecna,
  także musi spełnić deklarowany zakres.
- Centralny parser sprawdza limity rozmiaru i dekompresji, ratio, duplikaty i kolizje
  wielkości liter, backslash/NUL, szyfrowanie, tryby plików, symlinki oraz bezpieczny
  XML bez DTD/entity. Produkcyjny helper zostaje przeniesiony z `tests/e2e` do
  `tools/device`.
- Polityka otrzymuje JSON Schema, strict unknown fields i kanoniczny digest.
  Build używa przypiętego katalogu kwalifikowanych zależności, bez live fetch.
- `tests/e2e/run.sh` jest nazywany deterministyczną regresją/buildem, nie live E2E.
  Osobno wymagane są próby urządzeniowe, crash-window, exact-artifact mismatch,
  niezarządzany addon snapshotu i Flatpak post-install reprobe.

## P2 — doprecyzowania

Raport rozróżnia `AUDIT_PASS`, `NO_CHANGE`, `INCOMPATIBLE` i
`RECOVERY_REQUIRED`, zawiera digest grafu i transaction ID bez danych transportu.
Instalacja całego locka jest sekwencją sag per addon, nie jedną atomową transakcją;
częściowy przebieg ma jawny wynik i nie jest opisywany jako globalny rollback.

## Zakres pierwszego release

- zarządzane dodatki Python stable/default;
- exact Android transaction z trwałym odzyskaniem;
- audyt wszystkich dodatków kopiowanych przez restore;
- hostowy audyt payloadu Flatpak i post-install reprobe;
- arbitralny kod natywny fail-closed;
- natywny `inputstream.adaptive` pozostaje w istniejącej, przypiętej ścieżce Kodi.

Analiza ELF i automatyczne wspieranie nowych ABI są odłożone do kolejnego release.
To ograniczenie redukuje scope bez pozostawienia ścieżki instalującej nieoceniony
kod natywny.

## Werdykt po zastosowaniu uwag

Po naniesieniu powyższych zmian plan jest wykonalny i zachowuje OCP: adaptery tylko
budują `RuntimeFacts`, wspólny evaluator tworzy niezmienny plan, a instalatory go
konsumują. Nie pozostała znana luka P0 uniemożliwiająca rozpoczęcie implementacji.
