# Automatyczny katalog możliwości runtime Kodi

Data: 2026-09-01

## Zakres

Zaimplementowano rozdzielenie stabilnego kodu evaluatora od append-only katalogu
możliwości dokładnych stabilnych wydań Kodi. Katalog 21.2/21.3 pochodzi z
przypiętych commitów oficjalnego `xbmc/xbmc`, a generator odrzuca prerelease,
zmianę istniejącego tagu/commitu, niebezpieczne archiwum i nieznane zmienne.

Każdy build sprawdza iloczyn platform oraz 21.2/21.3. Android przed zarządzaną
mutacją porównuje systemowe manifesty zainstalowanego `base.apk`, a Flatpak
manifesty z rzeczywistego `share/kodi/addons`. Dodatkowe ABI dystrybucyjne jest
widoczne w raporcie, ale nie jest automatycznie zaufane przez evaluator.

## Testy odtwarzalne

- `tests/e2e/run.sh`: dwa identyczne buildy i `723 passed`;
- testy parsera przedziałów `minversion/version`, dokładnego wyboru
  `major.minor`, braku fallbacku, append-only kandydata i ograniczeń archiwum;
- fixture Kodi 22 dowodzi, że nowy wpis danych działa bez zmiany kodu;
- bezpośredni `discover` oraz `verify` dla oficjalnego stable 21.3:
  `NO_CHANGE`;
- katalog zawiera 26 bazowych możliwości dla każdego wydania 21.2 i 21.3.

## Live E2E

| Cel | Runtime | Atestacja | Regresja |
|---|---|---|---|
| BlueStacks1 | Kodi 21.3, Android emulator | 26/26, `ATTESTATION_PASS` | stable rollout `pass`/same wersje; Umbrella znalazła `Sintel (2010)`; YouTube odtwarzał 80 s, bez stall/403/błędu segmentu |
| X88 Pro 20 | Kodi 21.3, Android | 26/26, `ATTESTATION_PASS` | stable rollout `pass`/same wersje; Umbrella znalazła `Sintel (2010)`; YouTube odtwarzał 80 s, bez stall/403/błędu segmentu |
| NUC `mwo` | Kodi 21.3 Flatpak x86_64 | 26 bazowych + raportowane `game.libretro`, `ATTESTATION_PASS` | read-only probe poprawny |
| NUC `alek` | Kodi 21.3 Flatpak x86_64 | 26 bazowych + raportowane `game.libretro`, `ATTESTATION_PASS` | read-only probe poprawny |

Testy nie odczytywały ani nie zapisywały tokenów w raportach. Szczegółowe
wyniki live hosta znajdują się wyłącznie w ignorowanym katalogu
`.kodi-private/e2e`.

## Automatyzacja i monitoring

Workflow `check-kodi-runtime-upstream.yml` działa codziennie o 04:11 UTC oraz
ręcznie. `NO_CHANGE` niczego nie zapisuje. Nowy stable tworzy PR zmieniający
wyłącznie katalog i uruchamia `test.yml` dla dokładnego SHA brancha. Workflow
nie scala PR i nie modyfikuje urządzeń. Proces jest dodany do katalogu Control
Plane i Upstream Watchdoga.

## Granica wydania

Nie zmieniono ZIP-ów dodatków ani wersji repozytorium Kodi, więc release dodatku
nie jest wymagany. Wdrożenia QNAP dotyczą wyłącznie obserwacji nowego workflow.
