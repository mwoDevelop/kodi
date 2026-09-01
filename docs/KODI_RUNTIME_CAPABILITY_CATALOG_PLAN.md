# Plan: automatyczny katalog możliwości runtime Kodi

Data: 2026-09-01

Status: `IMPLEMENTED_AND_LIVE_QUALIFIED_PENDING_MERGE`

Niezależny review: `KODI_RUNTIME_CAPABILITY_CATALOG_PLAN_REVIEW.md`.

## 1. Cel

Zwykła aktualizacja Kodi nie może wymagać zmiany implementacji evaluatorów,
rolloutów ani restore. Kod ma pozostać generyczny, a nowy runtime ma być
kwalifikowany przez wersjonowane dane wygenerowane z dokładnego oficjalnego
wydania Kodi.

Zmiana nie wyłącza zasady fail-closed. Nieznany runtime nie wpływa na zwykłe
działanie Kodi, ale zatrzymuje zarządzaną mutację dodatków lub restore do czasu
utworzenia i scalenia wpisu katalogu.

## 2. Stan obecny i problem

1. `kodi_addon_runtime_compatibility.py` wybiera ręcznie opisane możliwości po
   numerze major Kodi. Dodanie Kodi 22 wymaga ręcznej edycji danych, a obecny
   format nie przechowuje pochodzenia tych wartości.
2. `Addons.GetAddons` nie zwraca na Kodi 21.3 wbudowanych dostawców API
   `xbmc.*` i `kodi.binary.*`, więc sam JSON-RPC nie wystarcza do bezpiecznego
   odkrywania możliwości.
3. Oficjalny pakiet Kodi zawiera `assets/addons/*/addon.xml`. Każdy dostawca
   opisuje wersję maksymalną oraz opcjonalne minimum
   `<backwards-compatibility abi="...">`.
4. Kodi sprawdza przecięcie przedziału wymaganego przez `<import>` z
   przedziałem dostawcy. Obecny evaluator redukuje to do porównania jednej
   wersji minimalnej, przez co może dawać fałszywe odrzucenia albo akceptacje.
5. Build offline potrzebuje zaufanego katalogu nawet wtedy, gdy żadne
   urządzenie nie jest dostępne.

## 3. Decyzja architektoniczna

### 3.1. Stabilny kod, zmienny katalog

Rozdzielić w jednym atomowym bootstrap merge:

- statyczną politykę platform, ABI i dodatków natywnych w
  `manifests/kodi-addon-runtime-compatibility.json`;
- generowany katalog oficjalnych runtime w
  `manifests/kodi-runtime-capabilities.json`;
- JSON Schema katalogu w
  `manifests/kodi-runtime-capabilities.schema.json`.

Bootstrap obejmuje jednocześnie katalog 21.2/21.3, policy schema v2 bez
`runtimes`, catalog schema, nowy report schema, evaluator, wszystkich
konsumentów i testy. Nie istnieje okres podwójnego odczytu. Loader v2 odrzuca
stary klucz `runtimes`, zamiast go ignorować. Rollback wskazuje jeden commit
całego bootstrapu.

Evaluator przyjmuje `RuntimeFacts`, politykę i katalog. Wybór wpisu katalogu
odbywa się po znormalizowanej wersji wydania Kodi (`major.minor`), a nie po
warunku wpisanym w kod. Wersje z revision, np. `21.3+...`, mapują się do `21.3`.
Wpisy muszą być jednoznaczne; nie ma fallbacku do najbliższego major/minor.

### 3.2. Model możliwości

Każda możliwość ma:

- `id` jako klucz mapy;
- `min_compatible` z `backwards-compatibility/@abi`, a przy jego braku pustą
  dolną granicę;
- `provided` z `addon/@version`;
- SHA-256 źródłowego `addon.xml`.

Wymaganie dodatku ma dolną granicę z `minversion` albo, jeżeli jej brak,
z `version`, oraz górną granicę z `version`. Zgodność oznacza przecięcie
przedziałów zgodnie z `CAddonInfo::MeetsVersion` Kodi. Pusta `CAddonVersion`
odpowiada `0.0.0`, a comparator zachowuje semantykę Kodi dla epoch, tyldy i
rewizji. Dla zwykłego dodatku bez `backwards-compatibility` dolna granica
dostawcy pozostaje pusta.

Opcjonalna nieobecna zależność nadal jest dozwolona. Opcjonalna obecna albo
planowana zależność musi być zgodna.

### 3.3. Pochodzenie katalogu

Wpis wydania przechowuje:

- repozytorium `xbmc/xbmc`;
- tag wydania, dokładny commit i status prerelease;
- SHA-256 pobranego archiwum źródłowego jako dowód transportowy;
- znormalizowaną wersję;
- kanoniczny digest oparty na repo, commicie, wersji i hashach wszystkich
  wybranych plików, niezależny od sposobu rekompresji archiwum.

Wpisy są append-only. Istniejący normalized release key z innym tagiem,
commitem, zestawem blobów albo capability digest daje `REJECTED/TAG_DRIFT` i
nigdy nie jest zastępowany automatycznie. Wszystkie pliki są pobierane po
dokładnym commit SHA, nie po ruchomym tagu.

Generator ma allowlistę `api.github.com` i `codeload.github.com`, jawne timeouty
oraz limity downloadu, rozmiaru skompresowanego i nieskompresowanego, liczby
elementów i pojedynczego XML. Token jest używany tylko w nagłówku i nigdy nie
jest logowany. Generator nie uruchamia pobranego kodu i niczego z archiwum nie wypakowuje.
Czyta tylko ograniczoną liczbę regularnych `addons/*/addon.xml` lub
`addon.xml.in`, `version.txt`, wersję JSON-RPC i `versions.h`. Odrzuca linki,
duplikaty, nadmierne rozmiary, DTD/entity, nierozwiązane zmienne i niezgodność
wersji/tagu/commitu.

Pliki `.in` są materializowane wyłącznie ze ścisłej allowlisty zmiennych
z `version.txt`, `versions.h` i wersji JSON-RPC. Nieznana zmienna zatrzymuje
kwalifikację.

## 4. Generator i kandydat

Dodać `tools/kodi_runtime_catalog.py` z operacjami:

1. `discover`:
   - pobiera metadane najnowszego stabilnego wydania GitHub albo jawnie podany
     stabilny tag;
   - rozwiązuje tag do dokładnego commitu;
   - pobiera archiwum źródłowe po commicie;
   - najpierw porównuje release ID/tag/commit z istniejącym wpisem i kończy
     szybkim `NO_CHANGE` bez pobrania archiwum;
   - odkrywa wszystkie bezpośrednie `addons/<id>/addon.xml[.in]` należące do
     klasy system providers z `backwards-compatibility`; kontroluje kompletność
     i unikalność, bez listy ID skopiowanej ze starej polityki;
   - generuje append-only wpis i pełny katalog-kandydata;
   - raportuje `NO_CHANGE`, `REVIEW` albo `REJECTED` oraz `candidate_id`.
2. `verify`:
   - ponownie sprawdza katalog, schemat, digest, base SHA, pochodzenie kandydata,
     append-only wszystkich istniejących wpisów oraz `TAG_DRIFT`;
   - uruchamia evaluator dla wszystkich profilów build i zarządzanych ZIP-ów.
3. `apply`:
   - atomowo zapisuje wyłącznie zweryfikowany plik katalogu;
   - odmawia działania przy zmianach w innych plikach albo rozbieżnym base SHA.

V1 obsługuje wyłącznie stabilne wydania. Draft i prerelease są zawsze
odrzucane. Obsługa prerelease jest odłożona, ale nie będzie wymagała zmiany
evaluatorów.

## 5. Integracja z build, rollout i restore

1. Wszystkie dotychczasowe wywołania wspólnego evaluatora otrzymują ten sam
   katalog i zapisują jego digest w raporcie.
2. Build profile wskazują `runtime_releases`. Build kwalifikuje iloczyn każdej
   platformy/ABI i wszystkich wspieranych wydań, początkowo 21.2 oraz 21.3.
   Deklarowana wersja musi mapować się do dokładnego wpisu katalogu.
3. Restore/reinstall ma dwie bramy. Preflight przed destrukcją wybiera katalog
   na podstawie przypiętego instalatora i expected version. Po instalacji
   obowiązkowy live reprobe wybiera wpis dla faktycznego runtime przed
   skopiowaniem profilu lub aktywacją dodatku. Mismatch uruchamia istniejącą
   kompensację/rollback albo raportuje `RECOVERY_REQUIRED`. Dotyczy Android i
   Flatpak.
4. Nieznany runtime daje `RUNTIME_CATALOG_MISS`, a nie ogólne
   `UNSUPPORTED_KODI_MAJOR`. Raport zawiera wersję, ale nie dane transportu.
5. Brak katalogu, błędny digest, niejednoznaczny wpis lub prerelease użyty w
   stable są błędami fail-closed przed pierwszą mutacją.
6. Transakcje Androida i ich recovery pozostają bez zmian; nowy katalog jest
   bramą poprzedzającą `prepare`.

## 6. Automatyzacja GitHub

Dodać `check-kodi-runtime-upstream.yml`:

- `schedule` raz dziennie oraz `workflow_dispatch`;
- `concurrency` z `cancel-in-progress: false`;
- read-only job odkrywania i hermetycznej weryfikacji;
- artefakt zawierający raport i dokładny katalog-kandydata;
- job writer wyłącznie z `contents: write` i `pull-requests: write`;
- osobny dispatcher z `actions: write`, `contents: read`;
- unikalna, idempotentna gałąź `automation/kodi-runtime-catalog`, captured head
  SHA i `force-with-lease`;
- PR może zmieniać wyłącznie katalog;
- dispatcher uruchamia `test.yml --ref <branch>` i przez polling wymaga
  `run.headSha == captured_head_sha`, ponieważ API nie dispatchuje po SHA i PR
  utworzony przez `GITHUB_TOKEN` nie może polegać na kaskadowym triggerze;
- brak automatycznego merge. Wpis nowego stable wymaga zielonego CI i
  kwalifikacji urządzeniowej BlueStacks/X88 przed scalenieniem.

Workflow musi być dodany do `upstream-watchdog.json`,
`control-plane-schedules.json` i dokumentacji procesów cyklicznych. Opóźnienie
jest stanem procesu katalogu, a nie awarią dodatków Kodi.

## 7. Testy

### 7.1. Jednostkowe i bezpieczeństwa

- semantyka przedziałów Kodi: exact, minversion, dolna granica ABI, brak
  przecięcia, sufiksy i epoch;
- wybór dokładnego `major.minor`, revision oraz brak fallbacku;
- duplikat wpisu, prerelease w stable, zmieniony digest i nieznane pole;
- bezpieczna obsługa archiwum: traversal, symlink, duplikat, limit, DTD/entity,
  nierozwiązana zmienna `.in`;
- deterministyczny kandydat i no-op dla tego samego wydania;
- kandydat zmienia wyłącznie wskazany wpis katalogu;
- test dokumentacji oraz manifestów monitoringu.

### 7.2. Integracyjne

- wygenerowanie katalogu z dokładnego oficjalnego Kodi 21.2 i 21.3, w tym test,
  że allowlista materializuje wszystkie `.in` bez wyjątków;
- porównanie możliwości 21.3 z `addon.xml` wyciągniętym z faktycznie
  zainstalowanych APK BlueStacks i X88 oraz z plików jednego NUC/Flatpak;
- rozbieżność dystrybucji daje fail-closed dla mutacji i nigdy nie aktualizuje
  katalogu upstream;
- build stable/testing dla wszystkich profilów;
- pełny `tests/e2e/run.sh`;
- kontrola dry-run workflow oraz ręczny `workflow_dispatch` zakończony
  `NO_CHANGE` dla aktualnego stable.

### 7.3. Live E2E

- BlueStacks jako pierwszy canary: stable/default, kontrolowany kandydat i
  pełna regresja;
- X88 jako drugi canary: stable/default i pełna regresja;
- następnie rollout na pozostałe dostępne urządzenia;
- Flatpak: rzeczywisty reprobe wersji i katalogu na obu profilach NUC;
- QNAP: watchdog oraz panel muszą pokazać zdrowy nowy proces.

## 8. Migracja i rollback

1. Jeden bootstrap commit/PR dodaje katalog 21.2 i 21.3, policy schema v2,
   catalog/report schema, evaluator, integracje i testy. Nie utrzymuje
   podwójnego odczytu starego i nowego schematu.
2. Rollback musi przywrócić dokładnie cały bootstrap commit; nie wolno cofać
   tylko jednego manifestu albo konsumenta.
4. Katalog nie jest sekretem. Token GitHub pozostaje wyłącznie w sekretach
   workflow/QNAP i nigdy nie trafia do raportu.

## 9. Dokumentacja i release

Uzupełnić:

- `README.md` i `docs/architecture.md` o przepływ katalogu;
- `docs/kodi-operations.md` o `RUNTIME_CATALOG_MISS` i ręczną kwalifikację;
- `docs/scheduled-processes.md` o cron, no-op i diagnostykę;
- odtwarzalny raport w `docs/e2e-results/`.

Zmiana narzędzi i manifestów nie podnosi wersji dodatków ani repozytorium Kodi.
Nowy release dodatku jest potrzebny tylko wtedy, gdy zmienią się jego ZIP-y.

## 10. Kryteria akceptacji

- aktualne Kodi 21.2/21.3 przechodzą bez ręcznie zakodowanej gałęzi wersji;
- symulowany wpis Kodi 22 istnieje wyłącznie jako fixture i jest konsumowany
  bez zmiany kodu;
- nieznany runtime zatrzymuje mutację czytelnym `RUNTIME_CATALOG_MISS`;
- ponowne odkrycie Kodi 21.3 jest deterministycznym `NO_CHANGE`;
- stabilny prerelease jest niemożliwy;
- katalog upstream zgadza się z BlueStacks, X88 i NUC/Flatpak;
- CI, build, BlueStacks, X88, dostępna flota i QNAP są zielone;
- PR jest scalony, `main` czysty, a workflow cykliczny przechodzi ręczny no-op.

Pełny rollout jest wymagany dla bootstrap migration. Przyszły `NO_CHANGE` albo
data-only PR bez zmiany ZIP-ów nie powoduje rolloutu ani wydania dodatków.
