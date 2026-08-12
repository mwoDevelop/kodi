# Repozytorium mwoDevelop Kodi

Powtarzalny system publikacji forków `mwoDevelop`: Umbrella, MwoScrapers,
WatchNixtoons2 i Profile Sync.

## Dokumentacja

Zacznij od [indeksu dokumentacji](docs/README.md). Oddziela on aktualne instrukcje operacyjne
od planów architektury, zapisów przeglądów i historycznych dowodów E2E.

| Zadanie | Dokument |
|---|---|
| Zainstaluj, zbuduj lub uruchom repozytorium E2E | Ten plik README |
| Przywróć lub zsynchronizuj konfigurację użytkownika Kodi | [Prywatne profile Kodi](docs/kodi-private-profile.md) |
| Obsługuj obrazy QNAP | [Cykl życia obrazu QNAP](docs/qnap-images.md) |
| Sprawdź zaplanowaną automatyzację i kontrole stanu | [Procesy cykliczne](docs/scheduled-processes.md) |
| Uruchom lub rozszerz testy E2E | [Przewodnik po testach E2E](tests/e2e/README.md) |
| Znajdź datowany wynik wdrożenia | [Indeks dowodów E2E](docs/e2e-results/README.md) |

## Budowanie

```bash
python3 tools/build_repo.py --output dist
python3 -m pytest
```

Kompilacja jest deterministyczna: niezależne locki stable/testing, commity
komponentów, zawartość plików i stałe metadane ZIP całkowicie definiują `dist/`.

## Instalacja kanału stable

Dodaj ten adres jako źródło plików w Kodi:

<https://mwodevelop.github.io/kodi/repo>

Następnie wybierz `Add-ons -> Install from zip file`, otwórz to źródło i zainstaluj
`repository.mwodevelop-1.0.0.zip`.

Plik ZIP repozytorium jest także dostępny bezpośrednio pod adresem:

<https://mwodevelop.github.io/kodi/repository.mwodevelop-1.0.0.zip>

Otwórz `mwoDevelop Add-ons`, a następnie zainstaluj żądane widoczne dodatki: Umbrella,
WatchNixtoons2 (mwoDevelop), mwoDevelop Profile Sync lub MwoScrapers Manager. Instalacja
Umbrella powoduje automatyczną instalację modułu technicznego MwoScrapers. Oddzielnie
widoczny menedżer otwiera ustawienia providerów i pokazuje, które z nich są włączone.

## Instalacja kanału testing

Zainstaluj `repository.mwodevelop.testing-1.0.0.zip` z:

<https://mwodevelop.github.io/kodi/repository.mwodevelop.testing-1.0.0.zip>

Używaj kanału testing wyłącznie dla kandydatów do wydania. Zawiera te same rodzaje dodatków co
stable, ale jego dokładne wersje mogą się różnić w trakcie testowania kandydata.
Autorytatywnym opisem zawartości obu kanałów są pliki w `manifests/locks/`.

## Powtarzalne E2E

```bash
tests/e2e/run.sh
```

lub w izolowanym kontenerze:

```bash
tests/e2e/run-docker.sh
```

Scenariusz przeprowadza dwie niezależne kompilacje, porównuje każdy bajt, obsługuje
udostępnia repozytorium przez HTTP, instaluje Umbrella i rekursywnie rozwiązuje
zależność MwoScrapers na podstawie metadanych repozytorium, sprawdza kontrakt
providerów oraz kompiluje downstreamowy resolver.

Aby wyrównać konfigurację providerów na docelowym urządzeniu Android z Kodi i
unieważnić wyłącznie cache providerów Umbrella, uruchom:

```bash
python3 tools/kodi_mwoscrapers_configure.py \
  --serial DEVICE \
  --torrentio-endpoint https://torrentio.strem.fun \
  --comet-endpoint https://comet.feels.legal
```

W przypadku urządzenia LAN, którego adres wyjściowy VPN jest odrzucany przez
Torrentio, podaj zamiast tego prywatny endpoint przekaźnika `/torrentio`. Adapter
zawsze zachowuje publiczny fallback Torrentio. Zapytania do Comet, poświadczenia
Real-Debrid, rozwiązywanie magnetów i końcowy adres URL materiału nigdy nie
przechodzą przez ten przekaźnik.

## Prywatna konfiguracja Kodi

`tools/kodi_profile.py` eksportuje i przywraca zainstalowane dodatki, ich ustawienia i
dane uwierzytelniające oraz wybraną skórkę, wykluczając pamięci podręczne i wygenerowane
bazy danych. Nieszyfrowane migawki są ograniczone do ignorowanego przez Git katalogu
`.kodi-private/`.

`tools/kodi_reinstall.py` udostępnia wykonywany z hosta workflow typu dry-run-first,
obejmujący zweryfikowaną dezinstalację, czyszczenie danych Kodi, instalację APK
dopasowanego do ABI, przywrócenie migawki oraz kontrolę dodatków i skórki na żywo.

Prywatny rejestr urządzeń i konfiguracja reinstalacji używają wyłącznie schema 2.
Zachowane backupy schema 1 obsługuje izolowany migrator offline. Najpierw wykonaj
próbę bez zmian, a dopiero potem zastosuj migrację:

```bash
python3 tools/migrate_legacy.py config \
  --platform bluestacks1=android-emulator
python3 tools/migrate_legacy.py config \
  --platform bluestacks1=android-emulator \
  --apply
```

`python3 tools/legacy_inventory.py` zapisuje zredagowany raport w
`.kodi-private/legacy-inventory.json`. Zestaw recovery o niezmiennej zawartości
buduje `python3 tools/build_legacy_migration_kit.py`.

Inwentaryzacja platformy w trybie tylko do odczytu ustala neutralny transport i cykl
życia Kodi bez wyświetlania endpointów, nazw użytkowników, katalogów domowych ani
odniesień do prywatnych danych:

```bash
python3 tools/kodi_inventory.py bluestacks1 \
  --adb /home/mwo/android-sdk/platform-tools/adb \
  --adb-server-port 5038
```

Zobacz [Prywatne migawki profili Kodi](docs/kodi-private-profile.md), aby poznać
granice bezpieczeństwa, dokładną zawartość, polecenia i powtarzalne kontrole urządzeń.

## Operacje

Do typowych operacji używaj jednego orchestratora:

```bash
.venv/bin/python tools/kodi_ops.py rollout --dry-run
.venv/bin/python tools/kodi_ops.py rollout
.venv/bin/python tools/kodi_ops.py rollout --device sony-tv
.venv/bin/python tools/kodi_ops.py release --dry-run
```

Pełny rollout obejmuje zatwierdzone obrazy QNAP, publikację Profile Sync,
BlueStacks i X88 jako canary, pozostałe Android TV, profile NUC oraz końcowe
E2E. Scoped rollout mutuje wyłącznie jawnie wskazane urządzenia. Pełne
przykłady, resume, wyniki, kody wyjścia, release z ręcznym approval i
bezpieczny restore opisuje [instrukcja operacji Kodi](docs/kodi-operations.md).

Zobacz [indeks dokumentacji](docs/README.md), który prowadzi do instrukcji
operacyjnych, architektury, review i materiałów historycznych.

Zobacz [Procesy cykliczne](docs/scheduled-processes.md), aby poznać aktualny katalog
workflow cron GitHub, monitoring QNAP, częstotliwość działania Kodi Profile Sync,
granice zapisu i polecenia weryfikacji na żywo.

Instrukcja [budowania i wdrażania obrazów QNAP](docs/qnap-images.md) opisuje wspólny
interfejs `build`, `deploy`, `update` i `status` dla wszystkich trzech obrazów
Container Station używanych przez projekt Kodi.
