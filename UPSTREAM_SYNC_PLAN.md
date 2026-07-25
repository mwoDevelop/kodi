# Plan cyklicznej synchronizacji źródeł mwoDevelop Kodi

Status: plan po niezależnym review, do realizacji

Data: 2026-07-25

Repo nadrzędne: `mwoDevelop/kodi`

Lokalizacja robocza: `/home/mwo/projects/kodi`

Raport review i decyzje: `docs/UPSTREAM_SYNC_PLAN_REVIEW.md`.

## 1. Cel

Zbudować odtwarzalny i bezpieczny mechanizm, który cyklicznie:

1. wykrywa zmiany w źródłach forków i importowanych dodatków;
2. przygotowuje izolowaną propozycję aktualizacji;
3. uruchamia testy bez dostępu do sekretów publikacyjnych;
4. wymaga review przed włączeniem obcego kodu do naszych gałęzi produktowych;
5. po zaakceptowaniu komponentu przygotowuje osobny PR aktualizujący kanał
   `testing` repozytorium Kodi;
6. nigdy nie promuje automatycznie zmian do `stable`.

Mechanizm ma być zgodny z OCP: dodanie kolejnego źródła tego samego rodzaju
powinno wymagać wpisu w manifeście, a nie zmian w głównym algorytmie.

## 2. Zakres

Pierwsza wersja obejmuje:

- Umbrella;
- WatchNixtoons2 (mwoDevelop);
- mwoScrapers wraz z wrapperem;
- źródła providerów CocoScrapers, ViperScrapers i Magneto;
- koordynację aktualizacji locka kanału `testing` w `mwoDevelop/kodi`.

Adapter repozytorium Kodi, potrzebny między innymi dla Rapideo, jest częścią
docelowego projektu, ale nie blokuje pierwszego wdrożenia. Rapideo nie będzie
opisywane jako fork, dopóki nie zostanie znalezione rzeczywiste repozytorium
Git ze źródłami.

Dokument opisuje migrację już działającego systemu, a nie budowę od zera.
W przypadku sprzeczności zastępuje wyłącznie następujące elementy `PLAN.md`:

- replay Umbrelli zostaje doprecyzowany o deklaratywną transformację pól
  mechanicznych i jeden istniejący manifest `downstream-patches.yml`;
- serwerowy mirror `upstream-master` nie jest aktualizowany automatycznie w
  MVP; dokładny upstream SHA pozostaje bazą synchronizacji;
- certyfikacja testing dotyczy całego adresowalnego snapshotu, a nie tylko
  pojedynczego komponentu;
- włączenie ochrony branchy wymaga wcześniejszej migracji obecnego workflow
  promocji stable.

Poza zakresem automatyzacji pozostają:

- bezwarunkowy automerge kodu upstream;
- automatyczna promocja do `stable`;
- automatyczne rozwiązywanie konfliktów semantycznych;
- wykonywanie kodu pobranego z upstream w jobie mającym prawo zapisu;
- zmiana sekretów Real-Debrid lub konfiguracji użytkownika Kodi.

## 3. Stan początkowy i problemy do usunięcia

### 3.1 Umbrella

Istniejący workflow działa codziennie, wykonuje rebase downstreamowej historii
na `upstream/master`, force-pushuje gałąź i tworzy PR. Wymaga poprawy, ponieważ:

- kolejne rebase'y przepisują identyfikatory downstreamowych commitów;
- istniejący `downstream-patches.yml` nie może zostać zastąpiony drugim,
  konkurencyjnym manifestem stanu;
- retry istniejącej gałęzi synchronizacyjnej nie jest w pełni idempotentny;
- PR tworzony przez standardowy `GITHUB_TOKEN` może wymagać ręcznego
  uruchomienia CI;
- workflow ma jednocześnie uprawnienia zapisu do contents, PR-ów i issues.

### 3.2 WatchNixtoons2

Istniejący workflow raz w tygodniu scala `upstream/master` bezpośrednio do
naszego `master` i wykonuje push bez PR. Należy go wycofać, ponieważ:

- omija review;
- push wykonany przez `GITHUB_TOKEN` nie gwarantuje uruchomienia kolejnego CI;
- używa ruchomego `actions/checkout@v4`;
- scalenie katalogu upstream nie aktualizuje automatycznie publikowanego
  `mwodevelop/plugin.video.watchnixtoons2.mwodevelop`;
- nasz dodatek jest kontrolowanym importem archiwum z innym ID, a nie zwykłym
  checkoutem oryginalnego katalogu.

### 3.3 mwoScrapers

Rozdzielenie audytu przypiętych artefaktów od discovery jest prawidłowe, ale:

- audyt przerwał się na niedostępnym URL-u Magneto;
- discovery nie zgłosiło zmiany, ponieważ wersja i SHA-256 artefaktu pozostały
  takie same, mimo że zmienił się osiągalny commit/URL;
- awaria jednego źródła powinna być raportowana razem z wynikami pozostałych;
- potrzebne jest rozróżnienie zmiany zawartości, zmiany provenance oraz
  pogorszenia dostępności przypiętego źródła.

Monitorowane Coco, Viper i Magneto nie są tym samym co kod aktualnie
zaakceptowanych providerów Torrentio i Comet. Monitoring źródła nie oznacza
akceptacji ani importu jego kodu.

### 3.4 Repozytorium Kodi

Kanały `testing` i `stable` mają niezależne locki i deterministyczne artefakty.
Ten model pozostaje obowiązujący:

- komponent nie publikuje się sam do repo Kodi;
- merge w repo nadrzędnym może opublikować wyłącznie `testing`;
- `stable` jest ręczną promocją dokładnie tych samych bajtów;
- promocja nie przebudowuje ZIP-ów.

### 3.5 Ochrona branchy, submoduły i promocja stable

W chwili sporządzenia review żadne z czterech repo nie ma aktywnego branch
protection ani rulesetu. Jednocześnie obecny `promote-stable.yml` commituje
`stable.json` i pushuje bezpośrednio do `kodi/main`. Włączenie wymogu PR bez
wcześniejszej migracji promocji zablokowałoby działający proces.

Repo nadrzędne zawiera trzy submoduły, ale release source of truth stanowią
locki kanałów. Lokalny E2E nie może zakładać, że gitlink submodułu zawiera
commit dopiero co wpisany do `testing.json`; musi materializować dokładne
locki do izolowanego katalogu tak jak CI.

## 4. Decyzje architektoniczne

### 4.1 Control plane

Repo `mwoDevelop/kodi` będzie centralnym control plane:

```text
manifests/
├── components.json
├── upstreams.json
├── release-groups.json
└── locks/
    ├── stable.json
    └── testing.json

tools/
└── upstream_sync/
    ├── __init__.py
    ├── cli.py
    ├── engine.py
    ├── models.py
    ├── reporting.py
    ├── candidate_bundle.py
    ├── versioning.py
    └── adapters/
        ├── __init__.py
        ├── git_fork.py
        ├── vendored_kodi_addon.py
        ├── provider_feed.py
        └── kodi_repository.py

tests/
└── upstream_sync/
    ├── fixtures/
    ├── test_engine.py
    ├── test_git_fork.py
    ├── test_vendored_kodi_addon.py
    ├── test_provider_feed.py
    ├── test_kodi_repository.py
    ├── test_candidate_bundle.py
    └── test_versioning.py

.github/workflows/
└── reconcile-upstreams.yml
```

`components.json` nadal opisuje budowanie i publikację. Nowy
`upstreams.json` opisuje wyłącznie relację ze źródłami zewnętrznymi, aby nie
mieszać odpowiedzialności. `release-groups.json` deklaruje elementy, które
muszą przejść koordynację razem, bez zacierania ich osobnych ID, wersji i
digestów. Pierwszą grupą jest moduł mwoScrapers wraz z wrapperem.

### 4.2 Kontrakt adaptera

Każdy adapter implementuje ten sam kontrakt:

```text
discover(config, observed_state, accepted_state) -> Discovery
prepare(discovery, workspace)                    -> Candidate
validate(candidate)                              -> Validation
report(candidate, validation)                    -> Report
```

Silnik odpowiada za:

- walidację manifestu;
- kolejność etapów;
- dry-run;
- idempotentne nazwy branchy i PR-ów;
- klasyfikację wyniku;
- raportowanie;
- wywołanie adaptera;
- brak zmian przy identycznym stanie.

Adapter odpowiada wyłącznie za semantykę danego rodzaju źródła. Silnik nie
może zawierać instrukcji warunkowych zależnych od nazw Umbrella,
WatchNixtoons2, Coco, Viper lub Magneto.

### 4.3 Wieloosiowy wynik discovery

Pojedynczy enum nie opisuje przypadku, w którym stary URL jest martwy, a nowy
commit udostępnia identyczne bajty. Wspólny model zawiera niezależne osie:

- content: `unchanged`, `changed`, `unknown`;
- provenance: `unchanged`, `changed`, `unknown`;
- availability: `healthy`, `degraded`, `unavailable`, `transient_error`;
- history: `fast_forward`, `rewritten`, `not_applicable`, `unknown`;
- prepare: `not_started`, `prepared`, `conflict`, `quarantined`;
- validation: `not_started`, `valid`, `invalid`.

Policy engine wyprowadza z nich akcję:

- `noop`;
- `open_or_update_pr`;
- `open_or_update_issue`;
- `quarantine`;
- `stop`.

Każdy wynik zawiera stare i nowe identyfikatory, wersję, SHA-256, listę
zmienionych ścieżek albo `unknown` oraz informację, czy upstream dotknął
ścieżek należących do naszych poprawek. Timeout lub `5xx` po retry ma stan
`transient_error`; deterministyczne `404/410` może od razu oznaczać
`unavailable`. Inne awarie przechodzą do `degraded` dopiero po kolejnych
runach, bez mutowania accepted state.

### 4.4 Manifest źródeł

`manifests/upstreams.json` będzie wersjonowanym dokumentem ze schematem JSON.
Minimalna postać wpisu:

```json
{
  "schema": 1,
  "components": {
    "umbrella": {
      "enabled": true,
      "adapter": "git_fork",
      "target_repo": "mwoDevelop/umbrellaplug.github.io",
      "target_branch": "main",
      "upstream_repo": "umbrellaplug/umbrellaplug.github.io",
      "upstream_branch": "master",
      "schedule_slot": "daily",
      "version_policy": "umbrella_downstream"
    }
  }
}
```

Szczegółowe parametry vendoringu i feedów znajdują się w obiektach adapterów.
Sekrety nigdy nie trafiają do manifestu.

### 4.5 Stan obserwowany, zaakceptowany i wydany

System utrzymuje trzy różne pojęcia:

- observed state — ostatni stan znaleziony w zewnętrznym repo/feedzie;
- accepted import state — dokładne źródło, licencja, pliki i digest faktycznie
  zaakceptowane w naszym kodzie;
- release state — commit, wersja i digest opublikowane w testing/stable.

Observed state trafia do raportu/issue i nie jest automatycznie commitem w
repo. Accepted import state zmienia się tylko razem z kodem lub
provenance-only PR-em dla identycznych, wcześniej zaakceptowanych bajtów.
Release state pozostaje w lockach kanałów.

Stan zaakceptowany jest przechowywany razem z komponentem:

- Umbrella: istniejący `downstream-patches.yml`, rozszerzony o wersję schematu,
  zaakceptowany upstream SHA, transformacje mechaniczne i digest patch series;
- WatchNixtoons2: istniejący `mwodevelop/upstream.json`, rozszerzony o format
  schematu, SHA źródłowego commita/feedu, licencję i inventory importu;
- mwoScrapers: `resources/provider-provenance.yml` dla aktywnych portów oraz
  strukturalny `resources/upstream-observations.lock.json` dla ostatniego
  zreviewowanego stanu zewnętrznych artefaktów;
- Rapideo i podobne importy: provenance obok importowanego dodatku.

`upstreams.lock.yml` zostanie zmigrowany do walidowanego
`upstream-observations.lock.json` zamiast parsera regexowego zależnego od
kolejności pól. Observation lock zapisuje osobno repository, ref, commit,
version, URL i SHA-256. Nie stanowi dowodu importu ani akceptacji kodu. Czas
sprawdzenia należy do raportu, nie do locka, aby no-op nie powodował churnu.

### 4.6 Tożsamość i cykl życia kandydata

`candidate_id` jest SHA-256 kanonicznego dokumentu zawierającego co najmniej:

- ID komponentu;
- downstream base SHA;
- dokładną tożsamość upstreamu;
- digest konfiguracji/manifestu;
- wersję adaptera;
- digest transformacji, overlay i patch series;
- politykę wersji;
- digest każdego pliku wynikowego.

Kandydat ma disposition:

- `open`;
- `merged`;
- `rejected`;
- `superseded`;
- `quarantined`.

Ręcznie odrzucony `candidate_id` nie jest ponownie proponowany. Zmiana
upstreamu, downstream base, konfiguracji albo adaptera tworzy nowe ID. Nowa
wersja upstreamu aktualizuje jeden otwarty PR, oznacza poprzedni kandydat jako
`superseded`, dodaje komentarz z różnicą i unieważnia wcześniejsze approvals.

Disposition jest odtwarzane z PR-a: Candidate-ID znajduje się w body, labelu i
trailerze commita, a stan PR-a rozróżnia open/merged/rejected. Nie tworzymy
commita w repo tylko po to, by zapisać odrzucenie. Superseded ID pozostają w
historii komentarzy PR-a.

Stały branch botowy jest aktualizowany tylko przez `force-with-lease`.
Writer weryfikuje oczekiwany head, autora i trailer poprzedniego commita.
Nieoczekiwana ręczna modyfikacja brancha zatrzymuje automat.
Bezpośrednio przed pushem writer ponownie odczytuje target branch. Jeśli jego
SHA różni się od base w candidate bundle, bundle jest odrzucany i discovery
zostaje ponowione; nie wolno publikować kandydata z nieaktualną bazą.

### 4.7 Granica discovery → writer

Discovery i prepare tworzą content-addressed candidate bundle:

```text
candidate/
├── candidate.json
├── candidate.json.sha256
├── files.sha256
├── report.md
└── tree/
```

`candidate.json` jest kanonicznym JSON-em ze schematem, limitami, source SHA,
base SHA i digestami wszystkich plików. Volatile czas, run ID i URL runu nie
wchodzą do dokumentu kanonicznego; mogą występować w job summary.

Writer:

1. uruchamia wyłącznie zaufany kod z default branch `kodi`;
2. ponownie sprawdza schemat, allowlistę, rozmiary i wszystkie SHA;
3. bezpiecznie materializuje bundle bez symlinków, submodułów i wyjścia poza
   root;
4. nie wykonuje żadnego pliku kandydata;
5. uzyskuje token App dopiero po walidacji bundle;
6. zapisuje commit z trailerami `Candidate-ID`, `Upstream-SHA` i
   `Manifest-SHA256`.

Bundle jest przekazywany między jobami jako artefakt o krótkiej retencji.
Artefakt nie jest źródłem wydania; po merge źródłem pozostaje commit
komponentu.

## 5. Przepływ synchronizacji

```text
cron / workflow_dispatch / reconcile awaryjny
                     |
                     v
       discovery bez sekretów i bez zapisu
                     |
          +----------+-----------+
          |                      |
      unchanged             zmiana/problem
          |                      |
        koniec             raport i kandydat
                                 |
                       walidacja bez sekretów
                                 |
                    +------------+------------+
                    |                         |
                  błąd                       OK
                    |                         |
             aktualizacja issue      branch i PR komponentu
                                              |
                                     CI z tokenem read-only
                                              |
                                      review i ręczny merge
                                              |
                                   reconcile repo `kodi`
                                              |
                                  PR locka kanału testing
                                              |
                              build/test/publish `testing`
                                              |
                              E2E Kodi/BlueStacks i review
                                              |
                             ręczna promocja do `stable`
```

W MVP jeden centralny workflow w `kodi` uruchamia wszystkie tanie discovery
raz dziennie i wykonuje reconcile komponentów z lockiem testing. Dostępny jest
również ręczny `workflow_dispatch`. Repo komponentów nie otrzymują prywatnego
klucza App i nie wysyłają `repository_dispatch`.

Natychmiastowe zdarzenie może zostać dodane później przez webhook GitHub App
lub centralny relay. Dispatch jest wtedy wyłącznie wskazówką do ponownego
odczytania allowlistowanego target branch/SHA, nigdy zaufanym poleceniem
publikacji.

## 6. Synchronizacja Umbrelli

Adapter: `git_fork`.

### 6.1 Docelowe branche

- lokalny `refs/remotes/upstream/master` — efemeryczny dokładny upstream;
- istniejący `origin/upstream-master` — zachowany do audytu, lecz w MVP nie
  aktualizowany automatycznie przez App;
- `main` — zaakceptowany downstream;
- tymczasowe lokalne repo rekonstrukcji — bez tokenu zapisu;
- `bot/sync-umbrella` — jedna odnawialna gałąź z finalnym, spłaszczonym
  commitem mającym parent aktualnego `main`;
- opcjonalne branche manualne do rozwiązywania konfliktów.

Brak automatycznego serwerowego mirrora pozwala nie przyznawać App uprawnienia
`Workflows`. Jeżeli upstream zmieni `.github/workflows/**`, `.gitmodules` albo
inny chroniony plik repo, automat kończy się quarantine przed pushem.

### 6.2 Algorytm

1. Pobrać dokładny HEAD `upstream/master`.
2. Odczytać zaakceptowaną bazę i aktywną serię z istniejącego
   `downstream-patches.yml`.
3. Jeśli brak zmiany, zakończyć bez zapisu.
4. Sprawdzić ancestry nowego HEAD względem zaakceptowanej bazy oraz względem
   ostatniego otwartego kandydata.
5. Jeśli upstream przepisał historię, nie tworzyć brancha ani commita.
6. Utworzyć lub zaktualizować jedno issue o `upstream_rewritten`.
7. Zatrzymać zmianę chronionych plików repo w quarantine.
8. W nieuprzywilejowanym temp repo odtworzyć tree od dokładnego nowego
   upstream SHA.
9. Zastosować deklaratywną transformację pól mechanicznych `addon.xml`:
   downstream name/provider, wersję, jawnie zarządzane zależności i metadata.
10. Odtworzyć tylko produktowy, uporządkowany patch stack według manifestu,
    weryfikując patch-id oraz wynik `range-diff`.
11. Wykryć nakładanie zmian upstream na owned paths każdej poprawki.
12. Przy konflikcie nie zgadywać rozwiązania; zapisać raport i quarantine.
13. Zastąpić wszystkie chronione pliki ich bajtowo identycznymi wersjami z
    aktualnego `main` i wymagać pustego diffu dla `.github/**`, `.gitmodules`
    oraz pozostałych repository-policy paths.
14. Zaktualizować w tree bazę, patch-id, wersję i digest całej serii.
15. Uruchomić test rzeczywistego przejścia wersji i zbudować deterministyczny
    ZIP bez tokenu zapisu.
16. Po walidacji utworzyć jeden finalny commit z parentem oczekiwanego
    `main`, tree z rekonstrukcji i trailerami kandydata.
17. Utworzyć albo zaktualizować jeden PR do `main`.

Nie wykonujemy `git rebase main upstream/master` ani zwykłego merge całej
historii. Temp tree jest rekonstrukcją: nowy czysty upstream + kontrolowana
transformacja + aktywne poprawki. Zdalny kandydat jest natomiast pojedynczym
commitem potomnym bieżącego `main`, więc nie przenosi do pushowanej historii
commitów zmieniających workflow. Dzięki temu typowa zmiana pierwszej linii
`addon.xml` nie staje się ręcznym konfliktem przy każdym wydaniu, a App nie
wymaga uprawnienia `Workflows`.

Force-push z `force-with-lease` jest dozwolony wyłącznie na rozpoznawalną
gałąź `bot/*`, nigdy na `main`, `master` ani branch mirrora.

### 6.3 Jeden manifest zmian downstream

Nie powstaje konkurencyjny `.mwodevelop/downstream-changes.yml`. Istniejący
`downstream-patches.yml` zostanie jawnie zmigrowany do nowego schematu. Dla
każdej zmiany zawiera:

- stabilny identyfikator;
- cel zmiany;
- commit i patch-id;
- owned paths;
- wymagane testy;
- zależności;
- status: `active`, `upstreamed`, `retired`;
- opcjonalny link do upstream issue/PR.

Manifest zapisuje też zaakceptowaną bazę upstream, digest transformacji
mechanicznej i digest uporządkowanej serii. Bootstrap musi zweryfikować, że
obecny `6.7.81.9` daje się odtworzyć z bazy `6.7.81` albo jawnie opisać
nieodtwarzalne historyczne commity przed pierwszym live sync.

Commity zarządzające `.github/workflows/**` i inną polityką repo zostają
wyłączone z product patch stacku i sklasyfikowane jako `repository_policy`.
Nie są replayowane przez automat; ich bieżące bajty są zawsze dziedziczone z
target `main` i mogą się zmienić tylko w osobnym, ręcznie przygotowanym PR.

## 7. Synchronizacja WatchNixtoons2

Adapter: `vendored_kodi_addon`.

### 7.1 Założenie

Publikowany dodatek jest kontrolowaną pochodną upstreamowego archiwum, z innym
ID i osobnymi poprawkami. Aktualizacja repo `ch.repo` nie jest równoznaczna z
aktualizacją naszej wersji dodatku.

### 7.2 Docelowy układ

```text
mwodevelop/
├── plugin.video.watchnixtoons2.mwodevelop/
├── patches/
│   ├── series
│   └── *.patch
├── overlays/
│   └── ...
├── transforms/
│   └── addon_identity.json
├── import-manifest.json
├── upstream.json
└── README.md

tools/
└── import_mwodevelop_watchnixtoons2.py
```

Transformacja ID, nazw i odwołań Kodi ma być deklaratywna lub zamknięta w
jednym importerze. Poprawki funkcjonalne mają być osobnymi patchami z testami.
Pliki binarne oraz w pełni downstream-owned trafiają do jawnego `overlays/`,
ponieważ tekstowy patch nie jest wiarygodnym mechanizmem ich przenoszenia.
`import-manifest.json` klasyfikuje każdy plik jako upstream, transform, patch,
overlay albo generated.

### 7.3 Algorytm

1. Odczytać upstreamowy indeks Kodi i wskazany addon.
2. Pobrać archiwum oraz obliczyć SHA-256.
3. Rozpoznać osobno zmianę wersji, zawartości i provenance.
4. Rozpakować archiwum do tymczasowego katalogu.
5. Odrzucić niebezpieczne ścieżki ZIP oraz nieoczekiwany root.
6. Zastosować transformację tożsamości dodatku.
7. Zastosować uporządkowaną serię downstreamowych patchy.
8. Zastosować overlay i sprawdzić, że nie nadpisuje niezadeklarowanych plików.
9. Znormalizować tryby plików oraz odrzucić symlinki i submoduły.
10. Zaktualizować `upstream.json`, inventory, licencję i wersję downstream.
11. Uruchomić testy strukturalne, importowe i deterministyczny build.
12. Otworzyć lub zaktualizować `bot/sync-watchnixtoons2`.

Obecny workflow bezpośrednio pushujący do `master` zostanie usunięty dopiero
po przejściu dry-run oraz kontrolowanego testu nowego adaptera.

## 8. Synchronizacja mwoScrapers i providerów

Adapter: `provider_feed`.

### 8.1 Rozdzielenie etapów

Pozostają dwa niezależne procesy:

- `audit` — sprawdza, czy wszystkie zreviewowane observation piny są osiągalne
  i zgodne;
- `discover` — szuka nowszych wersji, commitów, URL-i i artefaktów.

Żaden z nich nie importuje samodzielnie kodu do gałęzi produktowej.
Coco/Viper/Magneto są obserwowanymi źródłami referencyjnymi. Aktywne porty
Torrentio/Comet zachowują osobny `provider-provenance.yml`; observed lock nie
zastępuje tego manifestu.

### 8.2 Zmiany w audycie

Audyt:

1. sprawdza wszystkie źródła mimo błędu pojedynczego providera;
2. zapisuje zbiorczy JSON i Markdown;
3. osobno raportuje HTTP, commit, wersję, URL i SHA-256;
4. zwraca kod błędu dopiero po zapisaniu pełnego raportu;
5. redaguje dane mogące zawierać tokeny lub parametry użytkownika;
6. aktualizuje jedno issue per klasa problemu, zamiast tworzyć spam.
7. stosuje ograniczone retry i rozróżnia `404/410`, timeout, `429` i `5xx`;
8. zapisuje wynik każdego providera, nawet gdy inny zakończył się błędem.

### 8.3 Zmiany w discovery

Discovery uznaje za istotne:

- nową wersję;
- nowe bajty przy tej samej wersji;
- nowy osiągalny commit lub URL dla identycznych bajtów;
- martwy zaakceptowany URL;
- zniknięcie artefaktu;
- przepisanie historii źródłowego feedu.

Zmiana wyłącznie provenance z identycznym SHA-256 zreviewowanego artefaktu
tworzy mały PR aktualizujący observation lock. Nie zmienia kodu ani
`provider-provenance.yml`. Początkowo również wymaga ręcznego merge.

Nowe bajty Coco/Viper/Magneto aktualizują tylko observed report i tworzą
quarantined import candidate. Accepted import state może zostać zmieniony
dopiero razem z:

- potwierdzoną licencją i pełnym łańcuchem provenance;
- listą oraz SHA importowanych plików;
- portem do interfejsu mwoScrapers;
- kwalifikacją provider API;
- testami kontraktu i bezpieczeństwa;
- decyzją, czy provider jest domyślny, opt-in albo disabled.

Automerge provenance-only można rozważyć dopiero po zebraniu historii
bezbłędnych aktualizacji. Zmiana content nigdy nie otrzymuje automerge.

### 8.4 Atomowość

Kod mwoScrapers i wrapper są jednym komponentem wydawniczym:

- jeden commit źródłowy;
- jeden PR aktualizacyjny w repo komponentu;
- jeden PR locka `testing`;
- test kontraktu wrapper → `script.module.mwoscrapers`;
- brak publikacji niezgodnej pary.

`release-groups.json` deklaruje tę relację. Moduł i wrapper zachowują osobne
wersje oraz SHA. Jeśli bajty wrappera się nie zmieniły, jego wersja nie musi
zostać podniesiona, ale jego minimalna zależność od modułu zawsze jest
walidowana, a lock obu ID jest rozpatrywany atomowo.

### 8.5 Cache artefaktów

Trwały cache po SHA-256 nie jest wymagany w MVP. Może zostać dodany tylko po:

1. potwierdzeniu licencji konkretnego źródła;
2. zdefiniowaniu retencji i provenance;
3. upewnieniu się, że cache nie staje się niekontrolowanym kanałem publikacji;
4. dodaniu testu zgodności bajtów.

Jeśli redystrybucja nie jest dozwolona, przechowujemy wyłącznie metadata i
digest, bez kopii ZIP-a.

## 9. Adapter repozytorium Kodi i Rapideo

Adapter: `kodi_repository`.

Monitoruje:

- URL `addons.xml` i jego checksum;
- ID dodatku;
- wersję;
- URL archiwum;
- SHA-256 archiwum;
- datę i nagłówki pomocnicze jako metadata, nie jako tożsamość artefaktu.

Jeżeli publiczne repo Git nie jest znane, kandydat jest jawnie oznaczony jako
`source_archive_import`, nie jako fork. Importowany kod otrzymuje plik
provenance z dokładnym URL-em, wersją i digestem.

Uruchomienie adaptera dla Rapideo wymaga osobnej decyzji o publikowaniu naszej
wersji dodatku oraz potwierdzenia licencji. Sam monitoring źródła może zostać
uruchomiony wcześniej w trybie read-only.

## 10. Aktualizacja kanału testing

Po merge komponentu centralny reconcile:

1. porównuje target branch komponentu z `manifests/locks/testing.json`;
2. wymaga, aby commit był osiągalny z chronionego target branch i pochodził z
   zaakceptowanego PR-a;
3. sprawdza, czy zmienione bajty mają wersję większą od aktualnie publikowanej;
4. pobiera dokładny commit komponentu;
5. buduje ZIP deterministycznie;
6. oblicza SHA-256;
7. otwiera jeden PR `bot/bump-testing-<component>`;
8. aktualizuje wyłącznie locki i niezbędne manifesty;
9. materializuje wszystkie exact locki do izolowanego katalogu, niezależnie od
   gitlinków submodułów;
10. uruchamia pełne testy repo Kodi;
11. po merge publikuje atomowy snapshot `testing`.

Jeden PR dotyczy jednego niezależnego komponentu. mwoScrapers i wrapper są
wyjątkiem i zawsze występują razem. Jeżeli zmiana Umbrelli wymaga nowej wersji
kontraktu mwoScrapers, koordynator tworzy jawny, łączony kandydat.

Centralny workflow nie może sam zmieniać kodu dodatku ani automatycznie
podnosić jego wersji. Wersja i kod muszą być już zatwierdzone w repo
komponentu.

Lock kanału jest release source of truth. Gitlinki submodułów pozostają wygodą
developerską i mogą być aktualizowane osobnym PR-em, ale nie mogą wpływać na
bajty release. `tests/e2e/run.sh` otrzyma tryb, który zawsze uruchamia
`checkout_locked_components.py` do świeżego katalogu i przekazuje go jako
`KODI_COMPONENT_ROOT`.

### 10.1 Tożsamość snapshotu i certyfikacja

Po merge locka powstaje `snapshot_id`, obejmujący:

- commit repo `kodi` zawierający exact testing lock;
- SHA-256 kanonicznego testing locka;
- SHA-256 `testing/omega/addons.xml`;
- SHA-256 całego `artifact-manifest.sha256`;
- wersję generatora.

Pełny snapshot jest zapisywany jako immutable, content-addressed GitHub
Release asset. Promowane snapshoty są przechowywane bezterminowo; niepromowane
co najmniej 90 dni i co najmniej dziesięć ostatnich. Publiczny kanał
`testing` nadal wskazuje najnowszy snapshot.

Snapshot bundle zawiera:

- payload testing publikowany na Pages;
- channel-neutral ZIP-y komponentów;
- przygotowany deterministycznie `promotion/stable` payload z tymi samymi
  ZIP-ami komponentów i metadata właściwymi dla repo stable;
- locki, indeksy, provenance i pełny artifact manifest.

Zakaz rebuilda przy promocji dotyczy przede wszystkim ZIP-ów komponentów.
W MVP również stable payload jest przygotowany już podczas budowania
snapshotu, więc promocja może go skopiować i zweryfikować bez generowania
nowego indeksu. Jeżeli w przyszłości indeks stable będzie generowany podczas
promocji, musi być deterministyczny, a ZIP-y nadal muszą być kopiowane
bajtowo bez zmian.

„Immutable” oznacza zakaz nadpisania nazwy assetu/tagu oraz obowiązkową
weryfikację SHA przy każdym użyciu; workflow może utworzyć brakujący asset,
ale nie może zastąpić istniejącego. Retention usuwa tylko niepromowane assety
spełniające jednocześnie oba limity wieku i liczby.

MVP serializuje certyfikację: tylko jeden snapshot ma stan `certifying`.
Następny kandydat komponentu może zostać zbudowany i zgłoszony w swoim repo,
ale centralny PR locka nie jest otwierany i publiczny testing nie jest
zastępowany do czasu promocji albo jawnego odrzucenia aktualnego snapshotu.
Pozwala to przypisać BlueStacks E2E do całego delta stable→testing.

Stan `certifying` jest reprezentowany przez GitHub Deployment dla środowiska
`testing-certification`, powiązany z dokładnym commit SHA i snapshot ID.
Centralny reconcile wymaga maszynowego statusu `success` po promocji albo
`failure/inactive` po odrzuceniu, wystawionego przez chroniony workflow.
Ręczne zamknięcie issue nie zwalnia kolejki. Jedno zarządzane issue jest tylko
widokiem dla człowieka i jest synchronizowane ze statusem Deployment.

Atestacja E2E zapisuje co najmniej:

- `snapshot_id`;
- commit i digest locka;
- wersję Kodi;
- zainstalowane ID, wersje i `installed.origin`;
- wynik instalacji/aktualizacji i testów funkcjonalnych;
- digest użytego ZIP-a repo;
- czas i identyfikator kontrolowanego urządzenia.

Atestacja ma JSON Schema i kanoniczny digest. Test urządzenia działa bez
uprawnień zapisu i produkuje Actions artifact. Oddzielny job w chronionym
environment weryfikuje snapshot ID, schemat, wynik oraz digest, a następnie
dołącza atestację do Release asset. Lokalny JSON jest raportem diagnostycznym,
dopóki nie przejdzie kontrolowanego importu/review przez ten workflow. Writer
atestacji nie wykonuje kodu dodatku.

Promocja stable wskazuje dokładny `snapshot_id` i wymaga jego pozytywnej
atestacji. Nie może użyć „aktualnego testing”, jeżeli jest to inny snapshot.
Nowy schemat stable locka zapisuje również `source_snapshot_id`,
`source_index_sha256`, `source_artifact_manifest_sha256` i digest atestacji.

### 10.2 Rozdzielenie uprawnień publikacyjnych

Publikacja snapshotu składa się z trzech osobnych jobów:

1. `build-and-test` — `contents: read`, bez App key i sekretów publikacji;
   materializuje komponenty, wykonuje testy i tworzy content-addressed bundle;
2. `snapshot-writer` — `actions: read` i `contents: write`, nie checkoutuje
   ani nie wykonuje kodu komponentów; pobiera bundle, ponownie weryfikuje
   wszystkie digesty i tworzy brakujący Release asset bez prawa nadpisania
   istniejącego;
3. `pages-deploy` — `actions: read`, `pages: write` i `id-token: write`;
   publikuje dokładnie zweryfikowany payload z bundle.

Token zapisu nie może być dostępny w jobie uruchamiającym testy komponentów.
Między jobami przechodzi wyłącznie zweryfikowany bundle oraz jego digest.

### 10.3 Publikacja bez zbędnych wdrożeń

Obecny push do `main` uruchamia `publish-testing` dla każdej zmiany. W ramach
migracji workflow porównuje wynikowy `artifact-manifest.sha256` z publicznym
snapshotem i pomija deploy, jeśli bajty są identyczne. Zmiany generatora nadal
wywołują build, więc rzeczywista zmiana outputu nie zostanie przeoczona.

## 11. Wersjonowanie

Każdy adapter ma deklaratywną, testowaną politykę wersji właściwą dla
komponentu:

- Umbrella: `upstream_version.downstream_revision`; dla nowego upstreamu
  revision zaczyna się od `1`, a kolejna nasza zmiana zwiększa wyłącznie
  revision. Obecne `6.7.81.9` jest bazowym przypadkiem migracyjnym.
- WatchNixtoons2: ta sama polityka `upstream_version.downstream_revision`;
  obecne `0.25.2` mapuje upstream `0.25` i downstream revision `2`.
- mwoScrapers: własny SemVer; zaakceptowana zmiana kodu zwiększa co najmniej
  patch.
- wrapper: wersja rośnie tylko przy zmianie jego bajtów, metadata albo
  deklarowanej zależności. Sam release grupy nie wymusza sztucznego bumpa.

Jeżeli upstream zmieni bajty bez zmiany wersji, kandydat trafia do quarantine,
dopóki adapter nie wyznaczy jawnej kolejnej downstream revision. Jeżeli
upstream ma format, którego polityka nie potrafi jednoznacznie zmapować,
automat nie zgaduje wersji.

Porównanie nie może być leksykalne ani oparte bezpośrednio na PEP 440. Moduł
`versioning.py` implementuje i testuje porządek zgodny z Kodi, w tym wersje
czteroczłonowe i przykłady `~alpha/~beta`.

Wspólne wymagania:

- nowe bajty ZIP-a wymagają wersji większej niż obecne `testing` i `stable`;
- zmiana provenance bez zmiany bajtów nie wymusza publikacji nowego ZIP-a;
- synchronizacja nie może obniżyć wersji;
- build nie może modyfikować wersji poza repo komponentu;
- bump wykonuje adapter/importer w PR komponentu, centralny reconcile tylko go
  waliduje;
- wersja wynikowa jest zapisana w raporcie PR i locku;
- emergency rollback po publikacji odbywa się przez forward-revert z wyższą
  wersją, nie przez podmianę istniejącego ZIP-a.

## 12. Uwierzytelnianie i uprawnienia

Powstanie GitHub App przeznaczona wyłącznie do synchronizacji. Zostanie
zainstalowana tylko w repozytoriach objętych procesem. Jej client ID i klucz
prywatny znajdują się wyłącznie w chronionym środowisku repo `kodi`; nie są
kopiowane do repo komponentów.

Minimalne planowane uprawnienia:

- Metadata: read;
- Contents: read/write;
- Pull requests: read/write;
- Issues: read/write, jeśli alerty pozostają w issues.

Nie przyznajemy uprawnienia do secrets, deployments ani administration.
Zmiana `.github/workflows/**` pochodząca z upstream zatrzymuje automat i wymaga
ręcznego review; bot nie potrzebuje prawa do modyfikowania workflow.

Powyższa lista dotyczy App synchronizacyjnej. W repo `kodi` wbudowany
`GITHUB_TOKEN` dostaje `deployments: read` w reconcile oraz `deployments:
write` wyłącznie w chronionych workflow `promote/reject`, aby utrzymać
maszynowy stan certyfikacji. Snapshot writer otrzymuje `contents: write`, ale
jest osobnym jobem, który nie wykonuje kodu komponentów.

App synchronizacyjna nie może omijać branch protection. Wszystkie cztery
repozytoria muszą otrzymać ruleset wymagający PR-a i required checks przed
cutover writera. Wyjątki dotyczące promocji stable nie są przyznawane tej App.

Sekrety App:

- są dostępne tylko w chronionym jobie zapisującym;
- nie są dostępne w discovery ani testach kodu upstream;
- nie są przekazywane do procesów uruchamiających kod dodatku;
- nie są wypisywane w logach;
- token instalacyjny jest krótkotrwały.

PAT nie będzie używany.

### 12.1 Zgodna z rulesetem promocja stable

Przed ochroną `kodi/main` obecny bezpośredni push z `promote-stable.yml`
zostanie zastąpiony dwoma krokami:

1. ręcznie uruchamiany workflow pobiera wskazany immutable `snapshot_id`,
   weryfikuje atestację E2E i otwiera PR aktualizujący stable lock;
2. merge tego PR-a uruchamia workflow deploymentu, który pobiera dokładny
   snapshot asset, ponownie weryfikuje manifest i publikuje przygotowany
   `promotion/stable` payload zawierający te same ZIP-y bez rebuilda.

`publish-testing` musi pomijać deploy przy pushu zmieniającym wyłącznie stable
lock, aby nie ścigał się z deploymentem stable. Jeżeli techniczne ograniczenia
uniemożliwią wariant PR, dopuszczalna alternatywa to osobna App promocji z
wąskim bypass rulesetu wyłącznie w chronionym environment z ręcznym approval.
Nie wolno użyć App synchronizacyjnej ani szerokiego bypassu.

## 13. Bezpieczeństwo GitHub Actions

1. Wszystkie zewnętrzne Actions przypiąć pełnym SHA commita.
2. Każdy workflow deklaruje minimalne `permissions`.
3. Nie używać `pull_request_target` do wykonywania kodu kandydata.
4. CI PR-a działa z `contents: read` i bez sekretów publikacyjnych.
5. Job zapisujący nie wykonuje Pythonów ani skryptów pobranych z upstream.
6. Dane przekazywane z discovery do joba zapisującego przechodzą walidację
   schematu, długości, identyfikatorów repo i SHA.
7. Nazwy repo, branchy i plików są wybierane z allowlisty manifestu.
8. Zmiana workflow, submodułów, symlinków poza root lub niebezpiecznego ZIP-a
   wymaga ręcznej obsługi.
9. Branche produktowe wymagają PR-a i zielonych required checks.
10. Concurrency group zapobiega równoczesnej synchronizacji tego samego
    komponentu.
11. Build/test, snapshot writer i Pages deploy są osobnymi jobami o
    rozłącznych tokenach.
12. App synchronizacyjna nie ma `Workflows`, `Deployments`, `Pages` ani
    bypassu rulesetu.

## 14. Harmonogram i idempotencja

GitHub cron jest statyczny i nie jest generowany z manifestu. W MVP jeden
`reconcile-upstreams.yml` uruchamia codziennie o 04:20 UTC discovery wszystkich
tanich źródeł, a następnie reconcile. Manifest może wyłączać komponent, lecz
nie tworzy dynamicznego crona. Godzina nie jest traktowana jako SLA GitHub
Actions.

Jeżeli później koszt źródeł będzie różny, workflow może zawierać kilka
statycznych slotów, a `schedule_slot` w manifeście przypisze komponent do
jednego z nich. Nadal nie wolno kopiować sekretu do workflow komponentu.

Idempotencja:

- stała nazwa brancha botowego per komponent;
- maksymalnie jeden otwarty PR danego rodzaju;
- retry tego samego `candidate_id` aktualizuje PR zamiast tworzyć kolejny;
- ten sam pełny zestaw wejść `candidate_id` daje ten sam raport kanoniczny,
  tree i ZIP;
- volatile timestamp/run URL są wyłącznie w job summary;
- wynik policy `noop` nie tworzy commita, PR-a ani nowego issue;
- konflikt aktualizuje istniejące issue;
- ręcznie odrzucony candidate jest wyciszony, ale zmiana upstream/base/config
  tworzy nowy candidate;
- nowy candidate superseduje zawartość otwartego PR-a, dopisuje raport różnic
  i wymaga ponownego review;
- `force-with-lease` oraz kontrola poprzedniego Candidate-ID zapobiegają
  nadpisaniu ręcznej zmiany brancha botowego.

## 15. Monitoring i raportowanie

Każdy run zapisuje GitHub job summary z tabelą:

| Komponent | Accepted | Observed | Content | Provenance | Availability | History | Akcja |
|---|---|---|---|---|---|---|---|
| ID | SHA/wersja | SHA/wersja | stan | stan | stan | stan | noop/PR/issue/quarantine |

Alerty:

- jedno otwarte issue na komponent i klasę błędu;
- kolejny run dopisuje komentarz albo aktualizuje treść;
- pomyślny run po naprawie zamyka issue z odnośnikiem do PR/commita;
- raport nie zawiera całych URL-i z wrażliwym query stringiem;
- powtarzalna awaria centralnego reconcile nie wpływa na istniejące `stable`.

## 16. Testy

### 16.1 Testy jednostkowe

- walidacja manifestu i allowlisty;
- klasyfikacja niezależnych osi discovery i decyzji policy engine;
- wersjonowanie zgodne z Kodi, w tym `6.7.81.9`, następny upstream, rebuild
  tej samej wersji, `~alpha/~beta` i emergency forward-revert;
- nazwy branchy i PR-ów;
- `candidate_id`, disposition i supersede;
- redakcja logów;
- rozpoznanie zmiany provenance przy identycznym SHA;
- rozpoznanie zmiany zawartości przy identycznej wersji;
- rozdzielenie observed state od accepted import state;
- detekcja upstream rewrite;
- walidacja archiwów ZIP;
- deterministyczny raport bez pól volatile;
- candidate bundle, inventory i digesty;
- release groups;
- snapshot ID i atestacja E2E.

### 16.2 Testy integracyjne

Na tymczasowych lokalnych repozytoriach Git:

- fast-forward upstreamu;
- brak zmiany;
- upstream rewrite;
- czysty replay patch stacku;
- konflikt patcha lub transformacji;
- retry istniejącego brancha;
- aktualizacja istniejącego PR-a;
- przesunięcie target branch podczas przygotowania kandydata;
- ręczna modyfikacja brancha botowego;
- supersede otwartego PR-a i unieważnienie approvals;
- upstream zmienia owned path downstreamu;
- upstream zmienia `.github/workflows/**`;
- rekonstrukcja Umbrelli daje finalny commit z parentem target `main` i
  bajtowo identycznym chronionym tree;
- push Umbrelli działa tokenem App bez uprawnienia `Workflows`;
- ruleset blokuje bezpośredni push do branchy produktowych;
- promocja stable działa bez bypassu App synchronizacyjnej;
- job wykonujący kod komponentu nie ma tokenu `contents: write`;
- snapshot writer odrzuca podmianę istniejącego Release asset;
- ręczne zamknięcie issue nie zwalnia blokady certyfikacji;
- atestacja spoza chronionego workflow nie autoryzuje promocji;
- stable promotion publikuje przygotowany payload i identyczne ZIP-y.

Na fixture'ach feedów:

- nowa wersja i nowy SHA;
- nowy URL/commit z tym samym SHA;
- `404` zaakceptowanego URL-a i działający nowy URL;
- `404/410` bez alternatywy;
- przejściowe `429/5xx` i timeout po retry;
- uszkodzony ZIP;
- zip-slip;
- symlink i niebezpieczny tryb pliku;
- timeout jednego providera przy poprawnych pozostałych;
- zmiana artefaktu bez zmiany deklarowanej wersji;
- nowe observed bytes nie zmieniają accepted import locka.

### 16.3 Test odtwarzalności

Powstanie polecenie:

```bash
tests/e2e/upstream_sync/run.sh
```

Test:

1. tworzy izolowane lokalne remote'y i fixture feedów;
2. wykonuje discovery dwa razy;
3. wymaga no-op w drugim runie;
4. przygotowuje kandydat;
5. buduje go dwukrotnie;
6. porównuje SHA-256;
7. symuluje merge komponentu;
8. generuje PR locka testing;
9. materializuje locki bez korzystania z gitlinków submodułów;
10. generuje i ponownie weryfikuje snapshot ID;
11. wykonuje drugi build i wymaga identycznego manifestu;
12. potwierdza, że bajty istniejącego stable nie uległy zmianie;
13. symuluje stable promotion z dokładnego snapshot asset bez rebuilda.

Skrypt nie korzysta z prawdziwych sekretów ani nie zapisuje do GitHub.

### 16.4 Test rzeczywisty

Przed włączeniem harmonogramu każdy adapter przechodzi:

1. `--dry-run` na aktualnym upstream;
2. kontrolowany test z fixture'em nowej zmiany;
3. ręczny `workflow_dispatch`;
4. PR w rzeczywistym repo komponentu;
5. pełne CI komponentu;
6. PR locka testing;
7. publiczny smoke test repo Kodi;
8. E2E instalacji/aktualizacji w `BlueStacks1`;
9. zapis atestacji dla całego `snapshot_id`;
10. odtworzenie testu po odświeżeniu repo Kodi.

BlueStacks E2E jest obowiązkową bramą przed stable, ale nie zwykłym jobem PR na
GitHub-hosted runnerze. Może być wykonany lokalnie przez zapisany skrypt albo
na dedykowanym self-hosted runnerze dostępnym wyłącznie dla chronionego
workflow i bez wykonywania niezaakceptowanego kodu z PR.

## 17. Rollback i zatrzymanie

Każdy wpis manifestu ma `enabled`. Ustawienie `false` wyłącza synchronizację
jednego komponentu bez wyłączania pozostałych.

Przed merge:

- branch `bot/*` jest jednorazowy i może zostać usunięty;
- gałąź produktowa oraz repo Kodi pozostają bez zmian.

Po merge komponentu, ale przed publikacją:

- revert PR-a komponentu;
- zamknięcie PR-a locka testing.

Po publikacji do testing:

- nowy forward-revert komponentu z wyższą wersją;
- poprzedni stable pozostaje niezmieniony;
- odrzucenie `snapshot_id` zwalnia kolejkę certyfikacji;
- ręczny workflow może ponownie wdrożyć wcześniejszy immutable snapshot asset
  na Pages po sprawdzeniu jego manifestu;
- niepromowane snapshoty są zachowywane co najmniej 90 dni i co najmniej
  dziesięć ostatnich.

Po publikacji do stable:

- nie podmieniamy istniejącego ZIP-a;
- wydajemy emergency forward-revert z wyższą wersją;
- dokumentujemy wadliwy artefakt, SHA i snapshot ID;
- snapshot, który kiedykolwiek trafił do stable, nie podlega automatycznej
  retencji ani usunięciu.

## 18. Etapy realizacji

### Etap 0 — zapis baseline

Rezultat:

- aktualny stan branchy, remote'ów, workflow i locków w raporcie;
- zielone testy wszystkich komponentów;
- zapisane wyniki obecnych workflow;
- potwierdzone istniejące problemy Umbrelli, WatchNixtoons2 i Magneto.

Kryterium zakończenia: baseline można odtworzyć bez mutacji zdalnych repo.

### Etap 1 — kontrakt i silnik w trybie read-only

Rezultat:

- `manifests/upstreams.json` oraz JSON Schema;
- modele i kontrakt adaptera;
- CLI `discover --all --dry-run`;
- testy jednostkowe i fixture'y;
- raport JSON/Markdown.

Kryterium zakończenia: wszystkie źródła można sklasyfikować bez zapisu do
GitHub i bez sekretów.

### Etap 2 — bezpieczeństwo wydania, uwierzytelnianie i writer

Rezultat:

- migracja promocji stable do PR locka + deploy exact snapshot;
- rozdzielenie triggerów testing i stable;
- trzy joby o rozłącznych uprawnieniach: build/test, snapshot writer i Pages;
- maszynowy stan certyfikacji przez GitHub Deployment;
- schemat i chroniony writer atestacji E2E;
- materializowanie exact locków niezależnie od submodułów;
- czasowe wyłączenie legacy writerów przed aktywacją rulesetów;
- GitHub App z minimalnymi uprawnieniami;
- klucz App wyłącznie w chronionym środowisku `kodi`;
- candidate bundle i kontrola `candidate_id`;
- walidowany job tworzący branch, PR i issue;
- rulesety wszystkich branchy produktowych bez bypassu App synchronizacyjnej;
- pełne SHA zewnętrznych Actions;
- test idempotencji PR-a.

Kryterium zakończenia: PR utworzony przez App uruchamia wymagane CI, a token
nie jest dostępny w testach kandydata; ręczna promocja stable nadal działa
przy aktywnym rulesecie i nie przebudowuje snapshotu.

### Etap 3 — migracja Umbrelli

Rezultat:

- bootstrap i migracja istniejącego `downstream-patches.yml`;
- lokalny exact upstream ref bez automatycznego serwerowego mirrora;
- deklaratywna transformacja mechanicznych pól `addon.xml`;
- replay aktywnego patch stacku zamiast rebase całego downstreamu;
- finalny spłaszczony commit z parentem `main` i identycznym protected tree;
- test rewrite, konfliktu, no-op i retry;
- test przejścia z bazowego `6.7.81.9` na następny fixture upstream;
- wyłączenie starego workflow po przejściu kontrolowanego sync.

Kryterium zakończenia: dwa kolejne runy dla tego samego SHA dają jeden PR i
identyczny kandydat.

### Etap 4 — migracja WatchNixtoons2

Rezultat:

- odtwarzalny importer;
- jawne transformacje tożsamości;
- seria izolowanych downstream patchy;
- bezpieczna walidacja ZIP;
- PR aktualizacyjny;
- usunięcie bezpośredniego pushowania upstream do `master`.

Kryterium zakończenia: aktualny dodatek daje się odtworzyć z przypiętego
archiwum i naszych transformacji, z wyjątkiem jawnie opisanych plików
generowanych.

### Etap 5 — poprawa mwoScrapers

Rezultat:

- pełny audyt wszystkich providerów;
- rozpoznawanie availability/provenance drift;
- migracja regexowego YAML locka do walidowanego JSON;
- rozdzielenie observed i accepted import state;
- PR aktualizujący pin przy identycznym SHA i nowym osiągalnym URL-u;
- quarantine nowych bajtów bez kwalifikacji/licencji;
- test przypadku Magneto;
- atomowe testowanie modułu i wrappera.

Kryterium zakończenia: martwy przypięty URL nie jest raportowany jako
`unchanged`, a pozostali providerzy nadal są sprawdzani.

### Etap 6 — koordynacja testing

Rezultat:

- reconcile commitów komponentów z `testing.json`;
- jeden PR locka per komponent;
- weryfikacja wersji, commitów i SHA;
- materializacja exact locków;
- deterministyczny build;
- immutable snapshot ID i Release asset;
- workflow retencji bez prawa usunięcia promowanych snapshotów;
- serializowana certyfikacja całego delta stable→testing;
- publikacja wyłącznie testing oraz no-op deploy dla identycznych bajtów;
- test niezmienności stable.

Kryterium zakończenia: merge komponentu może doprowadzić do testing wyłącznie
przez zielony PR w repo `kodi`; stable pozostaje bajtowo identyczny.

### Etap 7 — opcjonalny adapter Kodi repository

Rezultat:

- read-only monitoring indeksu Kodi i ZIP-ów;
- fixture oraz testy adaptera;
- raport Rapideo bez udawania forka;
- decyzja licencyjna przed importem/publikacją.

Kryterium zakończenia: zmiana wersji lub bajtów Rapideo jest wykrywana i
raportowana z pełnym provenance.

### Etap 8 — rollout MVP i E2E

Rezultat:

- jeden centralny harmonogram aktywny;
- zapisany odtwarzalny test lokalny;
- rzeczywisty E2E testing w BlueStacks1;
- atestacja pełnego snapshotu;
- instrukcja obsługi konfliktów i rewrite;
- dokument operacyjny dla ręcznej promocji stable.

Kryterium zakończenia MVP: co najmniej jeden rzeczywisty cykl adapterów
Umbrella, WatchNixtoons2 i provider feed, drugi run no-op oraz pozytywny E2E
całego snapshotu repo Kodi i dodatków. Adapter Rapideo i cache artefaktów nie
blokują MVP.

## 19. Bramy odbioru MVP i rozwiązania docelowego

MVP jest ukończony, gdy:

1. żaden cykliczny workflow nie pushuje do `main`/`master` komponentu;
2. każda zmiana kodu/provenance proponowana do akceptacji trafia do PR-a, a
   anomalie i brak licencji nie mutują branchy;
3. CI kandydata nie ma sekretów zapisu ani publikacji;
4. `candidate_id`, disposition i retry nie tworzą duplikatów PR-ów/issues;
5. rewrite i konflikt zatrzymują automat;
6. Umbrella ma jeden manifest patchy i odtwarzalną relację z upstreamem;
7. WatchNixtoons2 jest odtwarzalny z archiwum, transformacji i patchy;
8. mwoScrapers wykrywa martwy pin nawet przy identycznym SHA artefaktu;
9. observed provider state nie zmienia accepted import state bez kwalifikacji;
10. wrapper i moduł są koordynowane przez release group;
11. local i CI materializują exact locki niezależnie od gitlinków;
12. zmiana komponentu aktualizuje `testing` przez osobny PR;
13. cały testing ma immutable snapshot ID i atestację;
14. build jest deterministyczny, a identyczny output nie jest ponownie
    wdrażany;
15. istniejące `stable` pozostaje bajtowo niezmienne;
16. promocja stable pozostaje ręczna i pobiera exact snapshot bez rebuilda;
17. branch rulesety blokują bezpośredni push App synchronizacyjnej;
18. pełny scenariusz jest zapisany w `tests/e2e/upstream_sync/run.sh`;
19. rzeczywiste repo Kodi oraz dodatki przechodzą test w BlueStacks1.

Rozwiązanie docelowe dodatkowo może spełnić:

- monitoring/import Rapideo po decyzji licencyjnej;
- licencyjnie dozwolony cache upstreamowych artefaktów;
- bezpieczny webhook/relay skracający czas reakcji bez dystrybucji klucza App;
- równoległą certyfikację wielu adresowalnych snapshotów zamiast kolejki MVP.

## 20. Kolejność pierwszych zmian

Pierwsza seria implementacyjna powinna być mała i łatwa do review:

1. zapisać baseline oraz dodać manifest, schemat, modele i pełny dry-run;
2. zbudować adaptery i testy lokalnie bez writera;
3. zmigrować promocję stable, exact-lock E2E i triggery publikacji tak, aby
   można było bezpiecznie włączyć rulesety;
4. skonfigurować GitHub App, candidate bundle, writer i rulesety;
5. wykonać kontrolowany cutover Umbrelli, WatchNixtoons2 i mwoScrapers zgodnie
   z etapami 3–5, po jednym komponencie;
6. uruchomić centralne PR-y locka testing i serializowaną certyfikację
   snapshotu;
7. dopiero po rzeczywistym E2E włączyć centralny harmonogram.

Do chwili przejścia dry-run i testów integracyjnych obecne workflow nie są
usuwane. Nie mogą jednak działać równolegle z nowym writerem dla tego samego
komponentu; przełączenie odbywa się atomowo przez wyłączenie starego schedule
i włączenie nowego. Legacy workflow WatchNixtoons2 pushujący bezpośrednio do
`master` zostaje wyłączony przed aktywacją rulesetu, nawet jeśli jego nowy
writer zostanie włączony dopiero w późniejszym etapie.
