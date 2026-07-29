# Plan cyklicznej synchronizacji źródeł mwoDevelop Kodi

Status: realizacja w toku; plan domknięcia do pełnego release

Data bazowa: 2026-07-25

Ostatnia aktualizacja: 2026-07-29

Repo nadrzędne: `mwoDevelop/kodi`

Lokalizacja robocza: `/home/mwo/projects/kodi`

Raporty review i decyzje:

- `docs/UPSTREAM_SYNC_PLAN_REVIEW.md` — review architektury bazowej;
- `docs/UPSTREAM_SYNC_FULL_RELEASE_REVIEW_2026-07-29.md` — niezależny review
  planu domknięcia do pełnego release.

## 0. Stan realizacji na 2026-07-29

| Obszar | Stan | Dowód / luka |
|---|---|---|
| Control plane | zakończony | advisory source actions są oddzielone od content-addressed `testing_lock_candidate`; pełne testy lokalne, CI i deterministyczny E2E są zielone |
| WatchNixtoons2 | zakończony | writer waliduje exact tree/base/autora, odświeża target przed pushem i jawnie zapewnia check exact head SHA; rzeczywisty update oraz kolejne no-op przeszły |
| Umbrella | zakończony | content-addressed replay patch stacku, protected paths i osobny writer są na `main`; staging drill i live discovery/no-op przeszły |
| mwoScrapers/providerzy | zakończony | policy działa per provider; observation state jest poza ZIP-em; provenance-only PR przeszedł rzeczywisty prepare → writer → CI → merge → no-op; moduł wydany jako `0.1.6` |
| Testing/stable | zakończony | snapshot schema 2 `82ff8e948aa0aa05e3c486707602c29e7bb5adde333d537298e7839d202b87a1` został certyfikowany, a exact payload wypromowany do stable bez rebuilda |
| Ochrona branchy | zakończona dla v1 | wszystkie cztery default branche wymagają PR, jednego approval i checka exact head `e2e`/`test`; brak bypass actorów |
| E2E urządzeń | brama release zaliczona, rollout rozszerzony w toku | chroniona certyfikacja exact snapshotu przeszła na BlueStacks i Sony; po promocji X88 przeszedł wyszukiwanie oraz odtwarzanie Umbrella i WatchNixtoons2 |
| Pełny release mechanizmu | stabilizacja końcowa | pozostały dodatkowe post-release smoke na urządzeniach, gdy będą wolne, bezpieczna polityka wygaszenia repo `testing` oraz tag/release `upstream-sync-v1.0.0`; repo nie wolno odinstalowywać, dopóki test migracji nie wykaże zachowania `addon_data` |

Pełny release w tym dokumencie oznacza wydanie operacyjnie kompletnego
mechanizmu synchronizacji. Nie oznacza bezwarunkowego automatycznego scalania
obcego kodu ani automatycznej promocji kanału `stable`.

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

## 3. Aktualny stan i problemy do usunięcia

### 3.1 Umbrella

Repo ma jeden `downstream-patches.yml`, skrypt `tools/rebuild_downstream.py`
oraz testy odtwarzające zaakceptowany upstream i downstreamowy patch stack.
Centralny discovery poprawnie klasyfikuje aktualny stan jako no-op.

Brakuje jednak odpowiednika bezpiecznego workflow WatchNixtoons2:

- przygotowania content-addressed candidate bundle bez prawa zapisu;
- replay patch stacku na dokładnym upstream SHA;
- zaufanego writera walidującego bundle i allowlistę;
- odnawialnego brancha i PR-a bez rebase/force-pushowania gałęzi produktowej;
- quarantine dla konfliktu, rewrite oraz zmian chronionych ścieżek;
- rzeczywistego cyklu update i drugiego, idempotentnego no-op.

### 3.2 WatchNixtoons2

Workflow `mwodevelop-watchnixtoons2-update.yml` działa codziennie i rozdziela:

- discovery/prepare bez sekretów zapisu;
- walidowany, content-addressed candidate;
- zaufany writer, który nie wykonuje kodu kandydata;
- stały branch `automation/watchnixtoons2-upstream`;
- PR oraz wymagany check `test`.

Rzeczywista aktualizacja do downstreamowej wersji `0.26.1` została scalona,
a kolejne harmonogramy zakończyły się no-op. Do pełnego release pozostaje
utrzymanie tego adaptera jako referencyjnego wzorca, monitoring opóźnionych
runów oraz włączenie jego merge do centralnej aktualizacji locka `testing`.

### 3.3 mwoScrapers

Rozdzielenie audytu przypiętych artefaktów od discovery działa. Aktualny stan
Coco, Magneto i Viper jest raportowany bez importowania obcego kodu. Nadal
brakuje:

- małego, walidowanego PR-a dla zmiany wyłącznie provenance przy identycznym
  SHA-256 zaakceptowanych bajtów;
- trwałej disposition dla kandydatów odrzuconych lub quarantined;
- pełnej kwalifikacji zmienionych bajtów bez automatycznego importu;
- połączenia zaakceptowanego merge grupy moduł + wrapper z PR-em locka
  `testing`.

Monitorowane Coco, Viper i Magneto nie są tym samym co kod aktualnie
zaakceptowanych providerów Torrentio i Comet. Monitoring źródła nie oznacza
akceptacji ani importu jego kodu.

### 3.4 Repozytorium Kodi

Kanały `testing` i `stable` mają niezależne locki, deterministyczne artefakty
i rozdzielone workflow publikacji. Promocja stable wskazuje dokładny testing
candidate i zmienia stable lock przez PR. Ten model pozostaje obowiązujący:

- komponent nie publikuje się sam do repo Kodi;
- merge locka w repo nadrzędnym może opublikować wyłącznie `testing`;
- `stable` jest ręczną promocją dokładnie tych samych bajtów;
- promocja nie przebudowuje ZIP-ów.

Brakującym elementem jest writer, który po zaakceptowanym merge komponentu
otwiera lub aktualizuje minimalny PR do `manifests/locks/testing.json`,
walidując commit, wersję, SHA ZIP-a i atomowość release group.

Workflow promocji stable musi dodatkowo jawnie uruchamiać allowlistowany check
na branchu PR-a, zamiast zakładać, że PR utworzony przez `GITHUB_TOKEN`
samoczynnie wygeneruje zdarzenie CI.

### 3.5 Ochrona branchy, submoduły i promocja stable

Rulesety są już aktywne na `kodi/main` i `ch.repo/master`, a promocja stable
została zmigrowana na PR. Każdy kolejny branch produktowy objęty writerem musi
otrzymać wymagany PR i właściwe required checks przed włączeniem zapisu.

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
        ├── git_patch_stack.py
        ├── vendored_kodi_addon.py
        ├── provider_feed.py
        └── kodi_repository.py

tests/
└── upstream_sync/
    ├── fixtures/
    ├── test_engine.py
    ├── test_git_patch_stack.py
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

Jedna globalna akcja `open_or_update_pr` jest niewystarczająca: PR komponentu
i PR locka testing mają innych właścicieli i inne granice zaufania. Wynik
zawiera zatem typowaną intencję oraz jej właściciela:

- `noop`;
- `component_candidate` — repo-local writer komponentu;
- `provenance_only_candidate` — repo-local writer observation state;
- `testing_lock_candidate` — writer w `kodi`;
- `open_or_update_issue`;
- `quarantine`;
- `stop`.

Policy nie jest wyprowadzane wyłącznie z osi content/provenance. Zaufany,
walidowany profil polityki adaptera deklaruje dozwolone przejścia, np.:

- `git_patch_stack + content changed + fast_forward` → component candidate;
- `vendored_kodi_addon + content changed + fast_forward` → component
  candidate;
- `provider_feed + changed bytes` → quarantine;
- `provider_feed + identical accepted bytes + healthy new provenance` →
  provenance-only candidate.

Core wykonuje tę tabelę bez instrukcji zależnych od nazw komponentów.
Adapter/provider nie może sam rozszerzyć praw zapisu poza profil zadeklarowany
w zaufanym manifeście.

Każdy wynik zawiera stare i nowe identyfikatory, wersję, SHA-256, listę
zmienionych ścieżek albo `unknown` oraz informację, czy upstream dotknął
ścieżek należących do naszych poprawek. Timeout lub `5xx` po retry ma stan
`transient_error`; deterministyczne `404/410` może od razu oznaczać
`unavailable`. Inne awarie przechodzą do `degraded` dopiero po kolejnych
runach, bez mutowania accepted state.

`provider_feed` zwraca osobny wynik i akcję dla każdego źródła oraz roll-up
wyłącznie do raportowania. Osiągalność accepted URL i observed URL jest
osobna; awaria jednego providera nie może zmienić disposition ani zatrzymać
bezpiecznej akcji innego.

### 4.4 Manifest źródeł

`manifests/upstreams.json` będzie wersjonowanym dokumentem ze schematem JSON.
Minimalna postać wpisu:

```json
{
  "schema": 1,
  "components": {
    "umbrella": {
      "enabled": true,
      "adapter": "git_patch_stack",
      "target": {
        "repository": "mwoDevelop/umbrellaplug.github.io",
        "branch": "main"
      },
      "upstream": {
        "repository": "umbrellaplug/umbrellaplug.github.io",
        "branch": "master"
      },
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
  strukturalny `.upstream/upstream-observations.lock.json` dla ostatniego
  zreviewowanego stanu zewnętrznych artefaktów;
- Rapideo i podobne importy: provenance obok importowanego dodatku.

Observation lock zostaje przeniesiony poza `resources/**` i jawnie wyłączony
z `components.json`, aby provenance-only PR nie zmieniał publikowanego ZIP-a.
Zapisuje osobno repository, ref, commit, version, URL i SHA-256. Nie stanowi
dowodu importu ani akceptacji kodu. Czas sprawdzenia należy do raportu, nie do
locka, aby no-op nie powodował churnu. Test wydania wymaga identycznego
`zip_sha256` przed i po bezpiecznej zmianie provenance-only.

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

1. uruchamia wyłącznie zaufane narzędzie z zaakceptowanego base SHA default
   brancha własnego repo;
2. ponownie sprawdza schemat, allowlistę, rozmiary i wszystkie SHA;
3. bezpiecznie materializuje bundle bez symlinków, submodułów i wyjścia poza
   root;
4. nie wykonuje żadnego pliku kandydata;
5. używa repo-local `GITHUB_TOKEN` dopiero po walidacji bundle;
6. zapisuje commit z trailerami `Candidate-ID`, `Upstream-SHA` i
   `Manifest-SHA256`.

GitHub App nie uczestniczy w write path v1. Kod writera komponentu nie jest
pobierany ani wykonywany z repo `kodi`.

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

Control plane w `kodi` wykonuje read-only discovery wszystkich źródeł i
reconcile commitów komponentów z lockiem testing. Write path jest lokalny dla
repozytorium, które ma zostać zmienione:

- workflow komponentu może tworzyć PR w tym samym repo przy użyciu własnego,
  minimalnego `GITHUB_TOKEN`;
- workflow `kodi` może tworzyć PR locka testing w `kodi`;
- żaden komponent nie otrzymuje sekretu pozwalającego pisać do innego repo;
- root control plane nie wykonuje kodu kandydata w jobie zapisującym.

To podejście jest już sprawdzone w WatchNixtoons2 i zostaje wzorcem dla
Umbrelli. GitHub App lub webhook może później skrócić opóźnienie, ale nie jest
warunkiem pełnego release v1. Polling target branch pozostaje źródłem prawdy,
a dispatch jest tylko wskazówką do ponownego odczytu allowlistowanego SHA.

## 6. Synchronizacja Umbrelli

Adapter: `git_patch_stack`.

### 6.1 Docelowe branche

- lokalny `refs/remotes/upstream/master` — efemeryczny dokładny upstream;
- istniejący `origin/upstream-master` — zachowany do audytu, lecz w MVP nie
  aktualizowany automatycznie przez App;
- `main` — zaakceptowany downstream;
- tymczasowe lokalne repo rekonstrukcji — bez tokenu zapisu;
- `automation/umbrella-upstream` — jedna odnawialna gałąź z finalnym, spłaszczonym
  commitem mającym parent aktualnego `main`;
- opcjonalne branche manualne do rozwiązywania konfliktów.

Brak automatycznego serwerowego mirrora pozwala nie przyznawać tokenowi prawa
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
`addon.xml` nie staje się ręcznym konfliktem przy każdym wydaniu, a writer nie
wymaga uprawnienia `Workflows`.

Force-push z `force-with-lease` jest dozwolony wyłącznie na rozpoznawalną
gałąź `automation/*`, nigdy na `main`, `master` ani branch mirrora.

### 6.3 Jeden manifest zmian downstream

Nie powstaje konkurencyjny `.mwodevelop/downstream-changes.yml`. Istniejący
`downstream-patches.yml` pozostaje jedynym manifestem i jest walidowany według
aktualnego schematu. Dla
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
obecny `6.7.81.18` daje się odtworzyć z zaakceptowanej bazy upstream albo jawnie opisać
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
12. Otworzyć lub zaktualizować
    `automation/watchnixtoons2-upstream`.

Legacy workflow bezpośrednio pushujący do `master` został usunięty. Referencyjny
workflow prepare/writer pozostaje jedynym cyklicznym write path dla dodatku.
Przed uznaniem go za ukończony writer musi dodatkowo porównywać exact tree,
parent/base SHA, trailery i autora istniejącego brancha z candidate bundle,
ponownie odczytywać target bezpośrednio przed pushem oraz wykonywać
`ensure-required-check` po każdym utworzeniu lub odświeżeniu PR-a, także gdy
branch nie wymagał ponownego pushu.

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

1. uruchamia osobny release-lock discovery, niezależny od upstream source
   policy;
2. porównuje publikowane drzewo target branch komponentu z exact artefaktem
   wskazanym przez `manifests/locks/testing.json`;
3. wymaga, aby commit był osiągalny z chronionego target branch i pochodził z
   zaakceptowanego PR-a;
4. buduje dokładny target commit i porównuje ZIP SHA z lockiem;
5. kończy no-op, jeśli commit się zmienił, ale publikowane bajty są identyczne;
6. jeśli bajty się zmieniły, wymaga wersji większej od testing i stable;
7. emituje typowaną akcję `testing_lock_candidate`;
8. otwiera jeden PR `automation/testing-lock-<component>`;
9. aktualizuje wyłącznie locki i niezbędne manifesty;
10. materializuje wszystkie exact locki do izolowanego katalogu, niezależnie od
   gitlinków submodułów;
11. uruchamia pełne testy repo Kodi;
12. po merge publikuje atomowy snapshot `testing`.

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

Docelowy bundle schema 2 rozdziela `channels/testing`, `promotion/stable` i
`site-shared`. Deployment stable składa Pages wyłącznie przez kopiowanie
zweryfikowanych, przygotowanych plików wybranego stable snapshotu oraz
aktualnie publikowanego testing snapshotu. Nie uruchamia
`checkout_locked_components.py`, `build_repo.py` ani kodu komponentów.
Zapobiega to zarówno rebuildowi stable, jak i cofnięciu nowszego testing przy
promocji starszego, nadal certyfikowanego snapshotu.

„Immutable” oznacza zakaz nadpisania nazwy assetu/tagu oraz obowiązkową
weryfikację SHA przy każdym użyciu; workflow może utworzyć brakujący asset,
ale nie może zastąpić istniejącego. V1 nie usuwa snapshotów automatycznie.
Ewentualna przyszła retencja może usuwać tylko niepromowane assety spełniające
jednocześnie oba limity wieku i liczby.

V1 serializuje certyfikację: tylko jeden snapshot ma stan `certifying`.
Następny kandydat komponentu może zostać zbudowany i zgłoszony w swoim repo,
ale centralny PR locka nie jest otwierany i publiczny testing nie jest
zastępowany do czasu certyfikacji albo jawnego odrzucenia aktualnego
snapshotu. Zmiany generatora i inne pushe do `main`, które zmieniłyby output,
również respektują tę blokadę: mogą przejść CI, ale publikacja jest odroczona
i wznawiana po zwolnieniu slotu.

Stan `certifying` jest reprezentowany przez GitHub Deployment dla środowiska
`testing-certification`, powiązany z dokładnym commit SHA i snapshot ID.
Wspólna concurrency group i ponowna kontrola Deployment przed publikacją
zapobiegają wyścigowi. Cykl certyfikacji ma stany
`published_testing → certifying → certified/rejected`; kolejkę zwalnia
`certified` albo `rejected`. `stable_promoted` jest niezależnym, późniejszym
stanem i nie blokuje kolejnych kandydatów.
Ręczne zamknięcie issue nie zwalnia kolejki. Jedno zarządzane issue jest tylko
widokiem dla człowieka i jest synchronizowane ze statusem Deployment.

Atestacja E2E zapisuje co najmniej:

- `snapshot_id`;
- commit i digest locka;
- wersję Kodi;
- zainstalowane ID, wersje i `installed.origin`;
- wynik instalacji/aktualizacji i testów funkcjonalnych;
- digest użytego ZIP-a repo;
- czas i identyfikator kontrolowanego urządzenia;
- jednorazowy challenge/nonce uruchomienia;
- exact head SHA i SHA-256 skryptów testowych;
- tożsamość chronionego runnera oraz czas ważności.

Produkcyjna atestacja v1 powstaje na chronionym self-hosted runnerze z etykietą
`kodi-device-e2e`, uruchamianym przez `workflow_dispatch` z dokładnym
`snapshot_id`. Runner pobiera nonce z runu, ma read-only dostęp do snapshotu i
LAN/ADB, ale nie ma `contents: write` ani Pages. Atestacja ma JSON Schema i
kanoniczny digest. Oddzielny job w chronionym environment weryfikuje nonce,
snapshot/head SHA, schemat, czas ważności, wynik i digest, odrzuca replay, a
następnie dołącza content-addressed atestację do Release. Lokalny JSON poza
tym workflow pozostaje wyłącznie raportem diagnostycznym. Writer atestacji
nie wykonuje kodu dodatku.

Promocja stable wskazuje dokładny `snapshot_id` i wymaga jego pozytywnej
atestacji. Nie może użyć „aktualnego testing”, jeżeli jest to inny snapshot.
Nowy schemat stable locka zapisuje również `source_snapshot_id`,
`source_index_sha256`, `source_artifact_manifest_sha256` i digest atestacji.
Migracja stable lock schema 1 → 2 jest osobnym PR-em przed pierwszą promocją
v1.

### 10.2 Rozdzielenie uprawnień publikacyjnych

Publikacja snapshotu składa się z trzech osobnych jobów:

1. `build-and-test` — `contents: read`, bez tokenu zapisu i sekretów publikacji;
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

Zmiana samego kodu certyfikacji może jednak wymagać nowej, niezmiennej
tożsamości kandydata mimo identycznych bajtów publicznego repo. W takim
przypadku operator jawnie uruchamia `workflow_dispatch` z
`force_snapshot=true`: workflow tworzy i publikuje nowy content-addressed
snapshot związany z aktualnym commitem, ale nadal pomija redeploy Pages.
Zwykły push z identycznym outputem pozostaje pełnym no-op publikacyjnym.

## 11. Wersjonowanie

Każdy adapter ma deklaratywną, testowaną politykę wersji właściwą dla
komponentu:

- Umbrella: `upstream_version.downstream_revision`; dla nowego upstreamu
  revision zaczyna się od `1`, a kolejna nasza zmiana zwiększa wyłącznie
  revision. Obecne `6.7.81.18` jest bazowym przypadkiem migracyjnym.
- WatchNixtoons2: ta sama polityka `upstream_version.downstream_revision`;
  obecne `0.26.1` mapuje upstream `0.26` i downstream revision `1`.
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

V1 nie wykonuje automatycznego bumpa upstreamowych prerelease
`~alpha/~beta`. Wykrywa je, waliduje porządek Kodi i kieruje do quarantine z
ręczną decyzją o downstreamowej wersji. Automatyczne mapowanie prerelease
wymaga osobnej polityki i fixture po v1.

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

Pełny release v1 używa repo-local `GITHUB_TOKEN` z minimalnymi uprawnieniami.
Każdy writer może pisać wyłącznie do repo, w którym działa:

- discovery i testy: `contents: read`;
- writer brancha/PR-a: `contents: write`, `pull-requests: write` oraz
  `actions: write` wyłącznie do jawnego uruchomienia allowlistowanego workflow
  testowego na branchu kandydata;
- reporter problemów: dodatkowo `issues: write`;
- deploy: tylko uprawnienia potrzebne danemu kanałowi.

Writer jest osobnym jobem, działa z zaufanego workflow na default branch,
waliduje candidate bundle i nie wykonuje plików kandydata. Zmiana
`.github/workflows/**`, submodułów lub innych chronionych ścieżek pochodząca
z upstream zatrzymuje automat.

Ponieważ push/PR wykonany standardowym `GITHUB_TOKEN` nie uruchamia
automatycznie kolejnych workflow z powodów ochrony przed rekurencją, writer po
utworzeniu albo aktualizacji PR-a wykonuje `ensure-required-check`: jawnie
wywołuje przez `workflow_dispatch` dokładnie wskazany, allowlistowany workflow
testowy, również gdy retry nie zmienił brancha. Root `test.yml`, Umbrella
`downstream-tests.yml` i mwoScrapers `test.yml` muszą otrzymać trigger
`workflow_dispatch` przed włączeniem odpowiadających writerów. Writer zapisuje
head SHA przed dispatch, a potem wymaga, aby run rozwiązał ref do tego samego
SHA i required context pochodził z allowlistowanego workflow. Nie wolno
przyjmować wyniku prepare jako zamiennika required check PR-a.

Przed włączeniem writera branch produktowy musi wymagać PR-a i odpowiedniego
required check. W v1 PR kodu komponentu, testing locka oraz stable promotion
wymaga dodatkowo minimum jednego approval właściciela/CODEOWNER; obecne
rulesety z `required_approving_review_count: 0` zostają utwardzone przed
release. Token automatyzacji nie dostaje bypassu rulesetu. PAT nie będzie
używany.

GitHub App pozostaje opcjonalnym rozszerzeniem po v1, jeśli potrzebny będzie
cross-repo dispatch lub krótszy czas reakcji. Nie może stać się warunkiem
poprawności: po zdarzeniu system ponownie odczytuje target branch i dokładny
SHA. Jeżeli App zostanie wdrożona, jej klucz pozostaje wyłącznie w chronionym
środowisku control plane, a uprawnienia ograniczają się do metadata,
contents/PR/issues bez secrets, deployments, Pages, administration i bypassu.

### 12.1 Zgodna z rulesetem promocja stable

Ochrona `kodi/main` jest już aktywna. Obecny model PR zostaje domknięty dwoma
izolowanymi krokami:

1. ręcznie uruchamiany workflow pobiera wskazany immutable `snapshot_id`,
   weryfikuje atestację E2E i otwiera PR aktualizujący stable lock;
2. merge tego PR-a uruchamia workflow deploymentu, który pobiera dokładny
   snapshot asset, ponownie weryfikuje manifest i publikuje przygotowany
   `promotion/stable` payload zawierający te same ZIP-y bez rebuilda.

Job weryfikujący snapshot/testujący payload ma wyłącznie read-only token.
Oddzielny writer dostaje contents/PR/actions write dopiero po walidacji
content-addressed bundle i nie wykonuje kodu komponentów.

`publish-testing` pomija deploy przy pushu zmieniającym wyłącznie stable lock,
aby nie ścigał się z deploymentem stable. Obowiązuje wariant PR bez bypassu
rulesetu; ewentualna przyszła App nie może być użyta do ominięcia tej bramy.

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
12. Token repo-local writera nie ma `Workflows`, `Deployments`, `Pages` ani
    bypassu rulesetu.
13. Zależności Python używane w build/test są instalowane z wersjonowanego
    locka z hashami; `pip install pytest` bez przypięcia nie jest dopuszczony
    w release workflow.

## 14. Harmonogram i idempotencja

GitHub cron jest statyczny i nie jest generowany z manifestu.
`reconcile-upstreams.yml` uruchamia codziennie o 04:20 UTC discovery wszystkich
tanich źródeł i reconcile. WatchNixtoons2 ma osobny repo-local slot 04:35 UTC;
analogiczny slot Umbrelli zostanie rozłożony w czasie. Manifest może wyłączać
komponent, lecz nie tworzy dynamicznego crona. Godzina nie jest traktowana
jako SLA GitHub Actions.

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

Alert „brak udanego harmonogramu przez 36 godzin” nie może być wystawiany
przez monitorowany cron. V1 uruchamia niezależny watchdog poza GitHub Actions
(preferowany kontener na QNAP), który odpytuje GitHub API o ostatni udany run
każdego workflow. In-repo watchdog może być dodatkowym sygnałem, ale jego
wspólna domena awarii jest jawnie udokumentowana.

## 16. Testy

### 16.1 Testy jednostkowe

- walidacja manifestu i allowlisty;
- klasyfikacja niezależnych osi discovery i decyzji policy engine;
- wersjonowanie zgodne z Kodi, w tym `6.7.81.18`, następny upstream, rebuild
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
- push brancha automatyzacji Umbrelli działa repo-local tokenem bez
  uprawnienia `Workflows`;
- ruleset blokuje bezpośredni push do branchy produktowych;
- promocja stable działa bez bypassu tokenu automatyzacji;
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
8. E2E instalacji/aktualizacji na minimalnej macierzy canary z sekcji 21;
9. zapis atestacji dla całego `snapshot_id`;
10. odtworzenie testu po odświeżeniu repo Kodi.

Urządzeniowe E2E jest obowiązkową bramą przed stable i działa na chronionym
self-hosted runnerze dostępnym wyłącznie dla workflow certyfikacji już
opublikowanego testing snapshotu. Lokalny skrypt pozostaje narzędziem
diagnostycznym i drillowym; sam nie może wystawić zaufanej atestacji.

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
  na Pages po sprawdzeniu jego manifestu jako containment;
- containment blokuje kolejne publikacje, ale nie obniża wersji już
  zainstalowanej w Kodi; równolegle zawsze powstaje emergency forward-revert
  z wyższą wersją;
- niepromowane snapshoty są zachowywane co najmniej 90 dni i co najmniej
  dziesięć ostatnich.

Po publikacji do stable:

- nie podmieniamy istniejącego ZIP-a;
- wydajemy emergency forward-revert z wyższą wersją;
- dokumentujemy wadliwy artefakt, SHA i snapshot ID;
- snapshot, który kiedykolwiek trafił do stable, nie podlega automatycznej
  retencji ani usunięciu.

## 18. Etapy realizacji

Status etapów:

| Etap | Stan | Najważniejszy brak |
|---|---|---|
| 0 — baseline | zakończony | utrzymywać tylko aktualny raport |
| 1 — read-only | zakończony | typowane akcje, policy per adapter i per-provider wynik są przetestowane live |
| 2 — bezpieczeństwo/writer | zakończony | przypięte zależności, exact-head dispatch, rulesety bez bypassu i approval=1 są aktywne |
| 3 — Umbrella | zakończony implementacyjnie | writer jest na `main`, testy 43/43 i live no-op przeszły |
| 4 — WatchNixtoons2 | zakończony implementacyjnie | exact tree/base/autor i ensure-required-check są na `master`; live no-op przeszedł |
| 5 — mwoScrapers | zakończony implementacyjnie | `0.1.6`, observation state poza ZIP, bezpieczny writer i rzeczywisty provenance PR przeszły |
| 6 — testing/stable | zakończony | publiczny snapshot schema 2 ma atestację, a stable zawiera exact payload bez rebuilda |
| 7 — adapter Kodi/Rapideo | odroczony | nie blokuje pełnego release v1 |
| 8 — rollout/E2E | brama release zaliczona, rozszerzony rollout w toku | BlueStacks + Sony mają chronioną atestację snapshotu; X88 przeszedł post-stable smoke oraz realny test selektywnego restore; pozostały ponowienia na wolnych urządzeniach i finalny release |

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

Kryterium zakończenia: wszystkie źródła można sklasyfikować per źródło bez
zapisu do GitHub i bez sekretów, a każda akcja ma jednoznaczny typ,
właściciela i dozwolony zakres mutacji.

### Etap 2 — bezpieczeństwo wydania, uwierzytelnianie i writer

Rezultat:

- migracja promocji stable do PR locka + deploy exact snapshot;
- rozdzielenie triggerów testing i stable;
- trzy joby o rozłącznych uprawnieniach: build/test, snapshot writer i Pages;
- maszynowy stan certyfikacji przez GitHub Deployment;
- schemat i chroniony writer atestacji E2E;
- materializowanie exact locków niezależnie od submodułów;
- czasowe wyłączenie legacy writerów przed aktywacją rulesetów;
- repo-local writer z minimalnym `GITHUB_TOKEN`;
- candidate bundle i kontrola `candidate_id`;
- walidowany job tworzący branch, PR i issue;
- rulesety wszystkich branchy produktowych bez bypassu tokenu automatyzacji;
- minimum jeden approval dla PR-ów v1;
- allowlistowany `workflow_dispatch` testów i walidacja exact head SHA;
- lock zależności Python z hashami;
- pełne SHA zewnętrznych Actions;
- test idempotencji PR-a.

Kryterium zakończenia: PR utworzony przez repo-local writer uruchamia wymagane
CI, a token zapisu nie jest dostępny w testach kandydata; ręczna promocja
stable nadal działa przy aktywnym rulesecie i nie przebudowuje snapshotu.

### Etap 3 — migracja Umbrelli

Rezultat:

- bootstrap i migracja istniejącego `downstream-patches.yml`;
- lokalny exact upstream ref bez automatycznego serwerowego mirrora;
- deklaratywna transformacja mechanicznych pól `addon.xml`;
- replay aktywnego patch stacku zamiast rebase całego downstreamu;
- finalny spłaszczony commit z parentem `main` i identycznym protected tree;
- test rewrite, konfliktu, no-op i retry;
- test przejścia z bazowego `6.7.81.18` na następny fixture upstream;
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
- usunięcie bezpośredniego pushowania upstream do `master`;
- walidacja exact tree, parenta/base, autora i trailerów brancha;
- trwałe disposition oraz `ensure-required-check` także przy retry.

Kryterium zakończenia: aktualny dodatek daje się odtworzyć z przypiętego
archiwum i naszych transformacji, z wyjątkiem jawnie opisanych plików
generowanych.

### Etap 5 — poprawa mwoScrapers

Rezultat:

- pełny audyt wszystkich providerów;
- rozpoznawanie availability/provenance drift;
- migracja regexowego YAML locka do walidowanego JSON;
- rozdzielenie observed i accepted import state;
- per-provider wynik oraz profile policy: changed bytes zawsze quarantine;
- przeniesienie observation lock poza publikowane `resources/**`;
- test, że provenance-only nie zmienia ZIP SHA;
- bootstrap modułu i wrappera do jednego commita zgodnie z
  `atomic_commit:true`; samo wyniesienie observation state zmienia tree
  modułu, dlatego otrzymuje uczciwą wersję `0.1.6`, podczas gdy niezmieniony
  wrapper zachowuje `0.1.1`;
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
- brak automatycznego usuwania snapshotów w v1; przyszła retencja nie może
  usunąć promowanych;
- serializowana certyfikacja całego delta stable→testing;
- rozdzielone `certified/rejected` od `stable_promoted`;
- stable lock schema 2 i deploy przygotowanego exact payload bez rebuilda;
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

- centralny harmonogram discovery oraz harmonogramy komponentowych writerów;
- zapisany odtwarzalny test lokalny;
- rzeczywisty E2E testing na wymaganych klasach urządzeń;
- atestacja pełnego snapshotu;
- instrukcja obsługi konfliktów i rewrite;
- dokument operacyjny dla ręcznej promocji stable.

Kryterium zakończenia MVP: każdy adapter przechodzi pełny staging drill
kandydat → PR → CI → retry/no-op, produkcyjne źródła przechodzą live
discovery/no-op, a cały snapshot repo Kodi i dodatków ma pozytywne E2E.
Naturalna produkcyjna zmiana upstream jest post-release canary, aby jej brak
nie blokował wydania bez końca. Adapter Rapideo i cache artefaktów nie blokują
MVP.

## 19. Bramy odbioru MVP i rozwiązania docelowego

MVP jest ukończony, gdy:

1. żaden cykliczny workflow nie pushuje do `main`/`master` komponentu;
2. każda zmiana kodu/provenance proponowana do akceptacji trafia do PR-a, a
   anomalie i brak licencji nie mutują branchy;
3. CI kandydata nie ma sekretów zapisu ani publikacji;
4. `candidate_id`, exact tree/base/autor, disposition i retry nie tworzą
   duplikatów PR-ów/issues ani osieroconych required checks;
5. rewrite i konflikt zatrzymują automat;
6. Umbrella ma jeden manifest patchy i odtwarzalną relację z upstreamem;
7. WatchNixtoons2 jest odtwarzalny z archiwum, transformacji i patchy;
8. mwoScrapers wykrywa martwy pin nawet przy identycznym SHA artefaktu;
9. observed provider state nie zmienia accepted import state bez kwalifikacji;
10. wrapper i moduł są koordynowane przez release group oraz przypięte do
    jednego atomic commit;
11. local i CI materializują exact locki niezależnie od gitlinków;
12. zmiana komponentu aktualizuje `testing` przez osobny PR;
13. cały testing ma immutable snapshot ID i odporną na replay atestację z
    chronionego runnera;
14. build jest deterministyczny, a identyczny output nie jest ponownie
    wdrażany;
15. istniejące `stable` pozostaje bajtowo niezmienne;
16. promocja stable pozostaje ręczna, pobiera exact snapshot bez rebuilda i
    nie cofa aktualnego testing;
17. branch rulesety blokują bezpośredni push tokenu automatyzacji i wymagają
    approval oraz checka exact head SHA;
18. pełny scenariusz jest zapisany w `tests/e2e/upstream_sync/run.sh`;
19. rzeczywiste repo Kodi oraz dodatki przechodzą test na wymaganej macierzy
    canary opisanej w sekcji 21.

Rozwiązanie docelowe dodatkowo może spełnić:

- monitoring/import Rapideo po decyzji licencyjnej;
- licencyjnie dozwolony cache upstreamowych artefaktów;
- bezpieczny webhook/relay skracający czas reakcji bez dystrybucji klucza App;
- równoległą certyfikację wielu adresowalnych snapshotów zamiast kolejki MVP.

## 20. Kolejność domknięcia

1. Domknąć komponentowy cykl Umbrelli według sprawdzonego wzorca
   WatchNixtoons2.
2. Utwardzić referencyjny writer WatchNixtoons2.
3. Rozdzielić typowane source actions od release-lock reconcile.
4. Przenieść provider observation state poza ZIP, znormalizować release group
   i dodać bezpieczny writer provenance-only/quarantine.
5. Zaimplementować osobny `testing_lock_candidate` writer w `kodi`.
6. Powiązać testing snapshot z autentyczną atestacją urządzeniową.
7. Zmigrować stable lock i deployment do exact snapshot bez rebuilda.
8. Wykonać staging drill każdego adaptera oraz live no-op.
9. Przeprowadzić okres obserwacji, containment/forward-revert i próbę awarii.
10. Utworzyć release mechanizmu synchronizacji i wykonać ręczną promocję
   dokładnego, certyfikowanego snapshotu do stable.

Writer legacy i nowy writer nie mogą działać równolegle dla tego samego
komponentu. Cutover jest atomowy: wyłączenie starego schedule, potwierdzenie
rulesetu i dopiero włączenie nowego write path.

## 21. Plan domknięcia do pełnego release

### 21.1 Pakiet A — Umbrella PR automation

1. Dodać job `prepare`, który pobiera dokładny upstream SHA i aktualny
   downstream base, uruchamia `tools/rebuild_downstream.py` w izolowanym
   katalogu oraz tworzy kanoniczny candidate bundle.
2. Walidować patch stack, protected tree, chronione ścieżki, symlinki,
   submoduły, limity rozmiaru i wersję wynikową.
3. Dodać osobny writer, który stosuje wyłącznie allowlistowane pliki, używa
   `force-with-lease` na stałym branchu automatyzacji oraz otwiera/aktualizuje
   jeden PR.
4. Dodać `workflow_dispatch` do zaufanego downstream testu, a writer po
   utworzeniu/aktualizacji PR-a zapewnia check dla exact head SHA także przy
   retry bez nowego pushu.
5. Konflikt, rewrite, zmiana workflow albo niejednoznaczna wersja mają
   kończyć się quarantine i jednym zarządzanym issue bez mutacji branchy.
6. Utwardzić aktywny ruleset Umbrella `main`: wymagany downstream test oraz
   minimum jeden approval.
7. Przejść fixture fast-forward, conflict, rewrite, retry i no-op, staging
   drill przez rzeczywisty PR oraz live discovery/no-op.

Kryterium odbioru: ten sam zestaw wejść daje ten sam `candidate_id`, tree i
PR; write token nie jest dostępny w prepare/test, a `main` zmienia się
wyłącznie przez zielony PR.

### 21.2 Pakiet B — hardening WatchNixtoons2

1. Walidować istniejący branch automatyzacji po exact tree, parent/base SHA,
   autorze i wszystkich trailerach, nie tylko po `Candidate-ID`.
2. Bezpośrednio przed pushem ponownie odczytać `master`; zmiana base odrzuca
   bundle i rozpoczyna nowe prepare.
3. Zapisywać disposition `rejected/superseded/quarantined` i nie proponować
   ponownie tego samego ID bez zmiany wejść.
4. Dodać `ensure-required-check`, które po każdym utworzeniu lub odświeżeniu
   PR-a weryfikuje check exact head SHA i w razie braku dispatchuje test,
   również gdy branch nie został ponownie wypchnięty.
5. Dodać fixture dla podmienionego brancha, nieudanego `gh pr create`, retry
   bez pushu i przesunięcia target base.

Kryterium odbioru: ręczna modyfikacja brancha zatrzymuje automat, retry
odtwarza brakujący PR/check, a ten sam bezpieczny kandydat nie generuje
churnu.

### 21.3 Pakiet C — provider provenance i quarantine

1. Zmienić discovery na wyniki per provider z osobną osią osiągalności
   accepted/observed URL oraz typowaną policy.
2. Wymusić w profilu `provider_feed`: nowe bajty zawsze quarantine; PR jest
   możliwy wyłącznie dla identycznego zaakceptowanego SHA i zdrowego nowego
   provenance.
3. Przenieść `upstream-observations.lock.json` do `.upstream/` poza
   publikowane `resources/**` i zaktualizować manifest/schema/testy.
4. Dodać writer obsługujący wyłącznie zmianę URL/commita przy identycznym
   SHA-256 wcześniej zaakceptowanego artefaktu.
5. Writer może zmienić tylko observation lock i raport provenance; nie może
   zmieniać aktywnego kodu providera ani `provider-provenance.yml`.
6. Nowe bajty, brak licencji, rewrite albo niedostępne źródło tworzą
   content-addressed quarantined candidate i issue, nigdy PR importujący kod.
7. Zapisać disposition, aby odrzucony kandydat nie był proponowany ponownie
   bez zmiany upstream/base/config.
8. Znormalizować locki modułu i wrappera do jednego osiągalnego commita
   repozytorium zgodnie z `atomic_commit:true`; tree wrappera pozostaje
   identyczne, natomiast moduł po wyniesieniu observation state jest wydany
   jako `0.1.6`.
9. Testować wszystkich providerów mimo awarii jednego oraz atomowo walidować
   grupę mwoScrapers module + wrapper.

Kryterium odbioru: kontrolowana zmiana provenance tworzy jeden mały PR,
powtórzenie jest no-op, późniejsze observation-only zmiany nie zmieniają ZIP
modułu `0.1.6`, a nowe bajty providera nie mogą trafić do brancha produktowego
bez ręcznej kwalifikacji.

### 21.4 Pakiet D — centralny testing-lock reconciler

1. Pozostawić upstream discovery jako advisory/reporting i dodać oddzielny,
   typowany release-lock discovery generujący wyłącznie
   `testing_lock_candidate`.
2. Dla target commit zbudować publikowany artefakt; jeśli jego SHA jest
   identyczne z lockiem, zakończyć no-op mimo nowszego commita.
3. Dla zmienionych bajtów sprawdzić osiągalność z chronionego default branch,
   zaakceptowany PR, monotoniczną wersję, deterministyczny ZIP i SHA-256.
4. Aktualizować tylko exact lock i niezbędne metadata. Dla mwoScrapers
   aktualizować moduł i wrapper atomowo zgodnie z `release-groups.json`.
5. Używać stałego brancha per komponent/release group, `candidate_id`,
   `force-with-lease` oraz najwyżej jednego otwartego PR-a.
6. Dodać `workflow_dispatch` do root `test.yml`; po utworzeniu/aktualizacji
   PR-a jawnie uruchomić allowlistowany `e2e` i zweryfikować exact head SHA.
7. Writer jest osobnym jobem z contents/PR/actions write; read-only discovery
   nie otrzymuje rozszerzonych uprawnień.
8. Merge PR-a locka publikuje immutable testing snapshot, o ile slot
   certyfikacji jest wolny; w przeciwnym razie publikacja jest kolejkowana.
9. No-op nie tworzy PR-a, commita, nowego assetu ani deploymentu.

Kryterium odbioru: merge komponentu prowadzi automatycznie najwyżej do
zielonego PR-a testing locka. Nie może sam zmienić stable ani przebudować
komponentu podczas promocji.

### 21.5 Pakiet E — atestacja i macierz E2E

Każdy release candidate musi mieć wspólny `snapshot_id` oraz wyniki:

- lokalnych testów jednostkowych, integracyjnych i deterministycznego builda;
- instalacji repo ZIP oraz aktualizacji dodatków z kanału testing;
- uruchomienia Umbrella, mwoScrapers i WatchNixtoons2;
- kontrolowanego wyszukiwania/odtwarzania Umbrella na co najmniej jednym
  emulatorze i jednym urządzeniu Android TV;
- testu Linux/Flatpak, jeżeli NUC jest osiągalny;
- wariantu VPN na Sony TV albo Bedroom TV, gdy urządzenie jest osiągalne;
- kontroli `installed.origin`, wersji dodatku i digestu repo ZIP.

Test produkcyjny uruchamia chroniony self-hosted runner
`kodi-device-e2e` dopiero dla opublikowanego testing snapshotu. Workflow
generuje jednorazowy nonce i wiąże atestację z `snapshot_id`, exact head SHA,
SHA skryptów, tożsamością runnera/urządzenia i czasem ważności. Osobny writer
odrzuca replay oraz raport dla innego snapshotu. Surowe logi Kodi nie są
uploadowane; raport przechodzi allowlistę pól i secret scan.

Minimalna brama canary dla pełnego release to:

1. BlueStacks jako odtwarzalny emulator;
2. jedno osiągalne urządzenie ARM Android TV;
3. NUC/Flatpak albo jawnie zapisane czasowe odstępstwo z terminem ponownego
   testu.

Niedostępność zewnętrznego providera lub Real-Debrid jest rozróżniana od
błędu dodatku przez retry, log resolvera i porównanie z urządzeniem
kontrolnym. Tokeny, credentiale i cache nie trafiają do artefaktu E2E.

Kryterium odbioru: atestacja JSON wskazuje dokładny snapshot, urządzenie,
wersję Kodi, wersje dodatków, nonce, exact skrypty, wyniki i digesty; nie
można jej ponownie użyć ani przypisać do innego snapshotu.

### 21.6 Pakiet F — polityka merge i promocji

Klasy zmian:

| Klasa | Automatyczne przygotowanie | Automerge po spełnieniu bram | Stable |
|---|---|---|---|
| kod Umbrella/WatchNixtoons2 | tak | nie w release v1 | ręcznie |
| nowe bajty providera | quarantine | nigdy | nie dotyczy |
| provenance-only, identyczny SHA | tak | nie w release v1 | nie publikuje ZIP-a |
| testing-lock po zaakceptowanym merge komponentu | tak | nie w release v1 | ręcznie |
| konflikt/rewrite/chroniona ścieżka | issue | nigdy | nie dotyczy |

W release v1 wszystkie PR-y wymagają minimum jednego approval i świadomego
merge. Auto-merge nie jest częścią v1. Można go zaprojektować po co najmniej
30 dniach obserwacji, trzech poprawnych zmianach danej klasy oraz teście
retry/no-op, wyłącznie dla provenance-only i testing-lock. Wymaga to osobnego
review polityki oraz path-scoped ruleset/CODEOWNERS, aby nie osłabić approval
dla kodu i stable.

Promocja stable zawsze pozostaje ręczna i wskazuje dokładny testing
`snapshot_id`, digest locka i pozytywną atestację. Wersja dodatku repozytorium
Kodi nie jest podnoszona wyłącznie z powodu wydania mechanizmu synchronizacji.
Workflow promocji po utworzeniu lub zmianie brancha jawnie uruchamia
allowlistowany `e2e` przez `workflow_dispatch`; merge jest możliwy dopiero po
required checku związanym z dokładnym head SHA i jednym approval.

### 21.7 Pakiet G — exact-snapshot stable

1. Wprowadzić snapshot bundle schema 2 z osobnymi
   `channels/testing`, `promotion/stable` i `site-shared`.
2. Zmigrować stable lock do schema 2 z `source_snapshot_id`,
   `source_index_sha256`, `source_artifact_manifest_sha256` i digestem
   zaufanej atestacji.
3. `promote-stable` przyjmuje `snapshot_id`, pobiera dokładny Release asset,
   weryfikuje inventory/digest/atestację i tworzy content-addressed bundle
   zmiany locka bez wykonywania kodu komponentów w jobie zapisującym.
4. `deploy-stable` pobiera wybrany stable snapshot oraz identyfikator aktualnie
   publikowanego testing snapshotu, kopiuje ich przygotowane payloady i
   publikuje Pages bez `checkout_locked_components.py` oraz `build_repo.py`.
5. Composer musi zachować nowszy testing przy promocji starszego,
   certyfikowanego stable snapshotu i odrzucić brak/kolizję pliku.
6. Dodać test dowodzący identyczności component ZIP-ów, indeksów stable i
   manifestu oraz brak drugiego builda w workflow deploymentu.
7. W v1 nie usuwać automatycznie snapshotów. Retencję wdrożyć dopiero z
   dowodem, że asset promowany nigdy nie może zostać usunięty.

Kryterium odbioru: stable Pages zawiera exact przygotowany payload wskazanego
certyfikowanego snapshotu, testing nie cofa się, a żaden krok promocji ani
deploymentu nie przebudowuje komponentu.

### 21.8 Pakiet H — obserwowalność, rollback i runbook

1. Zarządzane issue ma być zamykane po odzyskaniu zdrowia lub no-op bez
   aktywnego problemu.
2. Job summary zawiera accepted/observed SHA, klasyfikację, akcję,
   `candidate_id`, PR i snapshot.
3. Niezależny watchdog poza GitHub Actions (preferowany kontener QNAP)
   odpytuje heartbeat workflowów i tworzy alert po 36 godzinach.
4. Dokument operacyjny opisuje conflict, rewrite, supersede, reject,
   zatrzymanie jednego komponentu, forward-revert oraz containment przez
   ponowne wdrożenie wcześniejszego immutable snapshotu.
5. Próba awarii potwierdza, że błąd jednego adaptera nie blokuje raportu
   pozostałych i nie zmienia stable.
6. Próba containment potwierdza blokadę kolejnych publikacji i brak
   nadpisania ZIP-a, a próba forward-revert używa wyższej wersji.

### 21.9 Kolejność rollout i wydanie

1. `shadow`: wszystkie adaptery wykonują discovery/prepare bez zapisu przez
   minimum dwa harmonogramy.
2. `canary writer`: kolejno WatchNixtoons2 (już osiągnięte), Umbrella,
   provider provenance i testing-lock reconciler.
3. Dla każdego adaptera wykonać staging drill z kontrolowanym źródłem/forkiem,
   rzeczywistym PR-em/writerem i retry/no-op. Produkcyjne źródła przechodzą
   live discovery/no-op; pierwsza naturalna zmiana jest post-release canary i
   nie blokuje v1 bezterminowo.
4. Zbudować pełny testing snapshot i wykonać macierz E2E.
5. Odczekać co najmniej 24 godziny lub dwa kolejne harmonogramy bez nowej
   regresji, zależnie od tego, co trwa dłużej.
6. Wykonać próbę quarantine, zatrzymania komponentu,
   containment i forward-revert.
7. Utworzyć tag i GitHub Release `upstream-sync-v1.0.0` w `mwoDevelop/kodi`
   z release notes, digestami, raportem testów, atestacją E2E i runbookiem.
8. Ręcznie promować dokładny certyfikowany snapshot do stable i wykonać
   post-release smoke na minimalnej macierzy canary.

### 21.10 Definition of Done pełnego release

Pełny release jest ukończony dopiero, gdy:

1. Umbrella i WatchNixtoons2 potrafią przygotować idempotentny PR bez
   bezpośredniego pushu do brancha produktowego oraz walidują exact
   tree/base/autora/check;
2. provider provenance-only ma bezpieczny PR, nie zmienia ZIP SHA, a nowe
   bajty trafiają wyłącznie do quarantine;
3. merge każdego wspieranego komponentu tworzy albo aktualizuje właściwy PR
   testing locka przez osobny typ akcji;
4. mwoScrapers module i wrapper mają wspólny atomic commit;
5. wszystkie wymagane branche mają rulesety, minimum jeden approval i
   required check exact head SHA;
6. testing snapshot jest immutable, content-addressed i ma odporną na replay
   atestację z chronionego runnera;
7. macierz canary przechodzi instalację, aktualizację i test funkcjonalny;
8. drugi harmonogram dla niezmienionych wejść jest no-op;
9. konflikt, rewrite, niedostępność i błąd jednego źródła nie mutują accepted
   state ani stable;
10. promocja stable używa exact przygotowanego payloadu, bez rebuilda i bez
    cofnięcia testing;
11. certyfikacja zwalnia kolejkę niezależnie od późniejszej promocji stable;
12. containment, forward-revert, zatrzymanie komponentu, zewnętrzny watchdog
    i runbook zostały sprawdzone;
13. release workflow używa przypiętych zależności Python z hashami;
14. istnieje tag/release `upstream-sync-v1.0.0` z dowodami testów;
15. po promocji post-release smoke jest zielony, a otwarte problemy blokujące
    mają liczbę zero.
