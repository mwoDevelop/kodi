# Operacje release, rollout i restore Kodi

`tools/kodi_ops.py` jest głównym interfejsem operatora. Składa istniejące,
testowalne adaptery w content-addressed plan i zapisuje prywatny raport pod
`.kodi-private/kodi-ops/runs/<run_id>/`. Nie umieszcza endpointów, ustawień ani
poświadczeń w publicznym raporcie.

## Wymagania

- uruchamiaj polecenia z głównego katalogu repozytorium;
- używaj `.venv/bin/python`;
- `.env` i `.kodi-private/devices.json` muszą mieć tryb `0600` i zawierać
  aktualną listę `KODI_SYNC_DEVICES`;
- pełny rollout używa BlueStacks i X88 jako canary w tej kolejności;
- preflight odtwarza ulotne połączenia sieciowe ADB z prywatnego inventory,
  dzięki czemu restart izolowanego demona ADB nie wymaga ręcznego `adb connect`;
- release wymaga czystego `main` równego dokładnemu `origin/main` oraz
  zalogowanego GitHub CLI;
- restore wymaga wcześniejszego dry-run i jawnego `--yes`.

## Rollout

Najpierw wygeneruj plan i wykonaj tylko sondy odczytowe:

```bash
.venv/bin/python tools/kodi_ops.py rollout --dry-run
```

Pełny rollout uzgadnia przypięte obrazy QNAP, następnie BlueStacks, X88,
pozostałe Android TV i oba profile NUC:

```bash
.venv/bin/python tools/kodi_ops.py rollout
```

Rollout nigdy nie buduje obrazów. Wdraża wyłącznie digesty z
`manifests/locks/qnap-stable.json`. Każdy wpis locka wiąże commit źródłowy,
hash zadeklarowanych inputów, platformy, SHA raportu antymalware i dokładny
run workflow. Prywatny `.kodi-private/qnap-images.json` jest tylko cache i nie
autoryzuje wdrożenia.

Ogranicz mutacje do jednego urządzenia; QNAP pozostaje wtedy read-only, a
BlueStacks i X88 nie są dodawane jako ukryte cele:

```bash
.venv/bin/python tools/kodi_ops.py rollout --device sony-tv
```

Wybierz kilka urządzeń. Orchestrator zachowa ich kanoniczną kolejność:

```bash
.venv/bin/python tools/kodi_ops.py rollout \
  --device sony-tv \
  --device nuc-mwo
```

Wymuś ponawianą diagnostykę zewnętrznego providera i Real-Debrid także dla
niezmienionych celów:

```bash
.venv/bin/python tools/kodi_ops.py rollout --full-diagnostics
```

Po przerwaniu wznów dokładnie zapisany plan. Nie można dołączać nowych
selektorów urządzeń:

```bash
.venv/bin/python tools/kodi_ops.py rollout --resume RUN_ID
```

Zmiana stable locka lub QNAP locka kończy wznowienie jako `DRIFTED`; utwórz
wtedy nowy dry-run. Zewnętrzna awaria po wyczerpaniu retry daje
`DIAGNOSTIC_FAILED`, stan `PARTIAL` i kod 2. Na canary zatrzymuje dalsze fale,
ale bez dowodu lokalnej regresji nie cofa poprawnej konfiguracji.

## Release

Przejrzyj read-only plan:

```bash
.venv/bin/python tools/kodi_ops.py release --dry-run
```

Pełny release wykonuje testy i skan, publikuje immutable snapshot testing,
buduje tylko zmienione inputy obrazów QNAP, publikuje ich immutable approval,
certyfikuje BlueStacks oraz X88 i tworzy jeden PR aktualizujący oba locki:

```bash
.venv/bin/python tools/kodi_ops.py release
```

Prawidłowym wynikiem pierwszej fazy jest `WAITING_APPROVAL` i kod 3. Po
niezależnym review oraz merge PR wznów ten sam run:

```bash
.venv/bin/python tools/kodi_ops.py release --resume RUN_ID
```

Wznowienie sprawdza exact-head CI, merge SHA, immutable attestation ID i
SHA-256, dokładne bajty QNAP candidate, zakończenie deployu oraz publiczne
bajty. Dopiero potem wykonuje pełny rollout. Orchestrator nie zatwierdza i nie
scala własnego PR.

Wariant bez promocji stable:

```bash
.venv/bin/python tools/kodi_ops.py release --no-promote
```

Wariant bez automatycznego rollout po promocji:

```bash
.venv/bin/python tools/kodi_ops.py release --no-rollout
```

## Restore jednego urządzenia

Tryb `repair` nie odinstalowuje ani nie instaluje Kodi:

```bash
.venv/bin/python tools/kodi_ops.py restore \
  --device x88pro20 \
  --mode repair \
  --dry-run

.venv/bin/python tools/kodi_ops.py restore \
  --device x88pro20 \
  --mode repair \
  --yes
```

Tryb `reinstall` tworzy i weryfikuje świeży backup, ponownie sprawdza model
bezpośrednio przed usunięciem, instaluje przypięte APK i odtwarza tylko profil
powiązany z celem:

```bash
.venv/bin/python tools/kodi_ops.py restore \
  --device x88pro20 \
  --mode reinstall \
  --dry-run

.venv/bin/python tools/kodi_ops.py restore \
  --device x88pro20 \
  --mode reinstall \
  --yes
```

W v1 nie istnieje `restore --all`. Destrukcyjny restore Linux/Flatpak jest
fail-closed jako niezakwalifikowany; dla profili NUC użyj bezpiecznego
`rollout --device nuc-mwo` albo `rollout --device nuc-alek`.

## Stan przenośny i Profile Sync

Publisher jest wybierany przez `KODI_SYNC_PUBLISHER` i rolę `publisher` w
prywatnym inventory; obecnie jest nim Sony TV. Pełny rollout eksportuje z niego
content-addressed bundle favourites/artwork, tworzy na QNAP podpisaną rewizję
`kodi.favourites`, a następnie wymaga kolejno raportów candidate i active z
BlueStacks oraz X88. Dopiero po obu raportach promuje rewizję. Profile Sync/QNAP
jest autorytatywnym kanałem rutynowej konfiguracji. Bezpośredni `apply` bundle
pozostaje bootstrapem i kompensacją; gdy semantyczny hash favourites, dokładny
inwentarz artwork i zastosowana rewizja są zgodne, zwraca `NO_CHANGE` bez zapisu.

Scoped rollout nie publikuje rewizji, nie odczytuje publishera i nie mutuje QNAP.
Używa wyłącznie przypiętego prywatnego bundle oraz aktywnej rewizji. Po każdym
przebiegu brama wymaga kompletnych grafik, aktualnych akcji WatchNixtoons2 i
spójnej, sparowanej tożsamości Profile Sync.

Androidowy adapter nie ufa samej obecności ustawień Profile Sync. Przy poprawnej
tożsamości wymaga podpisanego przypisania aktywnej rewizji oraz zgodności
`assigned_revision == applied_revision`. Brak enrollmentu tworzy jednorazowy kod
na QNAP, paruje dokładny logical device ID, publikuje świeże przypisanie schema 2
i wykonuje sync. Istniejąca obca tożsamość jest błędem fail-closed i nie jest
automatycznie zastępowana.

## Rapideo i VPN X88

Pełny rollout eksportuje istniejący, zweryfikowany token Rapideo z publishera do
`.kodi-private/rapideo/token.json` (tryb `0600`). Adapter urządzenia otrzymuje
token przez krótkotrwały plik, usuwa go z pamięci współdzielonej po wykonaniu i
nie kasuje poprzedniego tokenu przed udanym uwierzytelnieniem. Raport zawiera
wyłącznie stan oraz hash tokenu, nigdy jego wartość.

Przed Rapideo adapter porównuje każdy plik sześciu przypiętych zależności z
oficjalnym, zweryfikowanym SHA-256 ZIP-a Kodi Omega. Sama zgodna wersja w bazie
Kodi nie wystarcza. Brakujący lub zmieniony plik naprawia tylko wskazany moduł;
pełny drugi przebieg musi zwrócić dla zależności `unchanged`.

Pełny rollout eksportuje też prywatne ustawienia Umbrella z publishera do
`.kodi-private/umbrella/settings.xml` w trybie `0600`. Na urządzeniu zachowuje
kompletny, działający zestaw danych Real-Debrid; autorytatywnej kopii używa jako
recovery tylko wtedy, gdy brakuje któregoś wymaganego pola. Ustawia wtedy przez
API Kodi wyłącznie pięć pól uwierzytelnienia oraz flagę włączenia. Nie kopiuje
całego pliku ustawień i nie nadpisuje tokenów legalnie odświeżonych lokalnie.

X88 używa profilu `NordVPN-PL314-TCP443-Auto-X88`, z wyłączeniem
`192.168.1.0/24` z tunelu, always-on i `connect_latest` po restarcie. Prywatny
profil można odtworzyć z szablonu bez wypisywania danych usługi:

```bash
.venv/bin/python tools/nordvpn_openvpn_profile.py \
  .kodi-private/devices/x88pro20/vpn/nordvpn/pl314.nordvpn.com.tcp443.openvpn-connect.ovpn \
  .kodi-private/devices/x88pro20/vpn/nordvpn/pl314.nordvpn.com.tcp443.autologin.openvpn-connect.ovpn \
  --bypass-cidr 192.168.1.0/24

.venv/bin/python tools/kodi_rapideo_token.py export --device sony-tv
```

## Wyniki i raport

| Kod | Stan | Znaczenie |
|---:|---|---|
| 0 | `COMPLETE` | wszystkie wymagane etapy zaliczone |
| 2 | `PARTIAL` | `DEFERRED` lub `DIAGNOSTIC_FAILED` |
| 3 | `WAITING_APPROVAL` | oczekiwanie na niezależny review i merge |
| 4 | `DRIFTED` | lock, PR lub generation odbiega od planu |
| 5 | `FAILED` | deterministyczna brama lub wymagany etap zawiódł |
| 6 | `RECOVERY_REQUIRED` | automatyczna kompensacja nie jest bezpieczna |

Każdy run zapisuje:

```text
.kodi-private/kodi-ops/runs/<run_id>/
  plan.json
  state.json
  report.json
  evidence/*.json
```

Katalog ma tryb `0700`, a pliki `0600`. Raporty są budowane z allowlisty pól.
Pełne backupy pozostają osobno pod `.kodi-private/kodi-ops/backups/` i nie są
kopiowane do evidence ani Git.

## Diagnostyka niskiego poziomu

Istniejące narzędzia pozostają wspieranymi adapterami diagnostycznymi. Używaj
ich bezpośrednio, gdy raport wysokiego poziomu wskazuje konkretny etap:

- `tools/qnap_images.py status` — stan kontenerów i watchdoga;
- `tools/kodi_inventory.py DEVICE` — transport i cykl życia Kodi;
- `tools/kodi_portable_state_rollout.py audit --device DEVICE` — favourites,
  artwork i tożsamość Profile Sync;
- `tools/kodi_umbrella_rd_probe.py` — zredagowana kontrola Real-Debrid;
- `tools/kodi_mwoscrapers_endpoint_probe.py` — zredagowana kontrola providerów.

Nie uruchamiaj ręcznie sekwencji mutujących adapterów zamiast orchestratora,
jeżeli celem jest powtarzalny rollout lub release.
