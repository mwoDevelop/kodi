# Plan projektu Kodi: Umbrella, MwoScrapers i wspólne repozytorium dodatków

Status: finalny testing i E2E BlueStacks przeszły; promocja stable w toku
Data rozpoznania: 2026-07-24
Konto docelowe GitHub: `mwoDevelop`
Lokalny katalog nadrzędny: `/home/mwo/projects/kodi`

## 1. Cel i decyzja architektoniczna

Zbudować utrzymywalny projekt, który:

1. utrzymuje fork Umbrelli i regularnie pobiera zmiany z upstreamu;
2. rozwija własny pakiet providerów `script.module.mwoscrapers`;
3. rozwija przede wszystkim oryginalne adaptery do publicznych API, a porty
   z CocoScrapers, ViperScrapers i Magneto dopuszcza dopiero po pełnej
   kwalifikacji pochodzenia konkretnego pliku;
4. nakłada małą, odizolowaną i niezależną od providera poprawkę resolvera
   Real-Debrid w Umbrelli;
5. publikuje Umbrellę i jej techniczną zależność MwoScrapers przez jedno
   repozytorium Kodi, eksponując użytkownikowi przede wszystkim Umbrellę;
6. aktualizuje upstreamy cyklicznie, ale nie publikuje niesprawdzonego kodu;
7. pozwala odtworzyć pochodzenie każdego zaimportowanego pliku i łatwo
   wycofać wadliwe wydanie.

Najważniejszy podział odpowiedzialności:

```text
Coco / Viper / Magneto
          │
          ▼
 kontrolowany importer
          │
          ▼
      MwoScrapers
 wyszukiwanie, normalizacja wyniku
 pojedynczego providera i jego zdrowie
          │
          ▼
       Umbrella
 scalanie, deduplikacja między providerami,
 filtrowanie i sortowanie użytkownika
          │
          ▼
 downstream resolver policy
 rate limit, backoff i obsługa RD
          │
          ▼
      Real-Debrid API
```

MwoScrapers nie będzie sam wywoływał Real-Debrid. Łączenie scraperów i
resolvera w jednym dodatku zwiększyłoby sprzężenie, powieliło kod Umbrelli i
utrudniło ochronę tokenu RD.

MwoScrapers pozostaje osobnym komponentem kodowym, dodatkiem
`xbmc.python.module` i artefaktem Kodi. Nie jest jednak osobno promowanym
produktem użytkowym: podstawowa instrukcja każe zainstalować Umbrellę, a Kodi
automatycznie dobiera MwoScrapers jako wymaganą zależność. Moduł pozostaje
widoczny w zarządzaniu zależnościami Kodi. Real-Debrid nie jest osobnym
dodatkiem: klient, autoryzacja i resolver pozostają częścią Umbrelli.

## 2. Zakres i elementy poza zakresem

### W zakresie

- Kodi 21/Omega jako pierwsza obsługiwana wersja;
- fork Umbrelli;
- własny moduł providerów zgodny z interfejsem zewnętrznych providerów
  Umbrelli;
- poprawki obsługi kolejki źródeł i odpowiedzi Real-Debrid w Umbrelli;
- wspólne repozytorium Kodi z kanałami `testing` i `stable`;
- automatyczne wykrywanie aktualizacji trzech rodzin scraperów;
- test integracyjny na `BlueStacks1`.

### Poza pierwszym wydaniem

- zastępowanie całego systemu filtrowania i sortowania Umbrelli;
- resolver dla innych usług debrid niż Real-Debrid;
- wspieranie Kodi starszego niż Omega;
- automatyczna promocja zmian upstream bez review;
- równoczesne uruchamianie kilku kompletnych modułów scraperów;
- import providerów bez potwierdzonej licencji i pochodzenia.

## 3. Wyniki rozpoznania źródeł

### 3.1 Umbrella

- Upstream: <https://github.com/umbrellaplug/umbrellaplug.github.io>
- Domyślna gałąź: `master`.
- Stan początkowy:
  - commit `fb1fa4fe7fdab82091a6502da3f3610df2dcf71f`;
  - wersja `6.7.81`.
- Repozytorium zawiera kod i artefakty Matrix, Nexus oraz Omega.
- Nie publikuje tagów i nie ma workflow GitHub Actions, dlatego
  synchronizacja będzie śledziła commit `master`.

Umbrellę można utrzymywać jako prawdziwy fork GitHub.

### 3.2 CocoScrapers

- Pierwotne repo:
  <https://github.com/CocoJoe2411/repository.cocoscrapers>
- Fork będący bieżącym źródłem późniejszych wydań:
  <https://github.com/not-coco-joe/repository.cocoscrapers>
- Rozpoznana wersja: `1.0.39`.
- Pakiet udostępnia funkcję `cocoscrapers.sources()`.
- Rozpoznano 16 providerów torrentowych.
- Kod źródłowy dodatku jest publikowany wewnątrz ZIP-a, nie jako osobne
  repo każdego providera.

### 3.3 ViperScrapers

- Bieżący kanał:
  <https://github.com/OldManJax/repository.oldsalt>
- Rozpoznana wersja: `1.5.4`.
- Viper deklaruje, że jest forkiem CocoScrapers uzupełnionym scraperami
  rodziny Kodifitzwell i zachowuje zgodny interfejs.
- Rozpoznano 17 providerów.
- Bieżący kod jest publikowany w ZIP-ie wewnątrz większego repozytorium.

### 3.4 Magneto

- Bieżący manifest dystrybucyjny:
  <https://kodiyashimaru.github.io/repo/packages/addons.xml>
- Repo:
  <https://github.com/kodiyashimaru/repo>
- Rozpoznana wersja: `6.07.04`.
- Rozpoznano 23 providery torrentowe oraz integrację AIOStreams.
- Publicznie dostępny jest gotowy ZIP, ale nie znaleziono potwierdzonego
  kanonicznego repo kodu autora.

### 3.5 Wnioski z porównania

- Wszystkie trzy rodziny wystawiają funkcję `sources()` zgodną z mechanizmem
  zewnętrznych providerów Umbrelli.
- Siedem providerów występuje we wszystkich trzech rodzinach.
- Wszystkie providery Coco występują również w Viper lub Magneto.
- Wspólna nazwa providera nie oznacza identycznego kodu: po normalizacji
  namespace tylko 3 z 14 wspólnych modułów Viper/Magneto były identyczne.
- Nie wolno wybierać wariantu wyłącznie po dacie lub nazwie. Każdy port musi
  przejść test kontraktowy i porównanie zachowania.
- Manifest dodatku nie dowodzi samodzielnie prawa do portowania każdego
  zawartego pliku. Przed importem trzeba odtworzyć łańcuch pochodzenia i
  licencji konkretnego providera; brak kompletnego łańcucha blokuje import.

## 4. Docelowa topologia repozytoriów

### 4.1 GitHub

```text
mwoDevelop/kodi
├── główna orkiestracja
├── generator repozytorium Kodi
├── definicje repo stable/testing
├── przypięte wersje komponentów
└── publikacja GitHub Pages

mwoDevelop/umbrellaplug.github.io
└── prawdziwy fork umbrellaplug/umbrellaplug.github.io

mwoDevelop/script.module.mwoscrapers
├── nowy downstreamowy projekt pochodny GPL-3.0
├── API zgodne z CocoScrapers
├── wybrane i jawnie zaadaptowane providery
├── manifest pochodzenia każdego providera
└── komponent techniczny dystrybuowany przez to samo repo Kodi co Umbrella
```

`script.module.mwoscrapers` jest nowym projektem, a nie forkiem w rozumieniu
sieci forków GitHub. Źródłami importu pozostają trzy niezależne rodziny.

### 4.2 Lokalnie

```text
/home/mwo/projects/kodi/              # mwoDevelop/kodi
├── PLAN.md
├── README.md
├── umbrella/                         # submodule: fork Umbrelli
├── mwoscrapers/                      # submodule: własny moduł providerów
├── repository/
│   ├── repository.mwodevelop/
│   └── repository.mwodevelop.testing/
├── manifests/
│   ├── components.json                # katalog źródeł komponentów
│   ├── channels.json                  # definicje kanałów
│   └── locks/
│       ├── stable.json                # niezależne, niezmienne piny stable
│       └── testing.json               # piny aktualnego kandydata
├── tools/
├── tests/
└── dist/                             # generowane; bez ręcznej edycji
```

Oba komponenty wykonawcze będą osobnymi repozytoriami przypiętymi jako
submoduły. Repo główne będzie wskazywało dokładnie zweryfikowane commity.
Oddzielne repo Git MwoScrapers umożliwia niezależne testy, audyt pochodzenia i
wersjonowanie providerów; nie powstaje dla niego osobne repozytorium Kodi ani
osobna instrukcja instalacji dla użytkownika.

## 5. Projekt MwoScrapers

### 5.1 Tożsamość i kontrakt

- ID dodatku: `script.module.mwoscrapers`.
- Namespace Pythona: `mwoscrapers`.
- Własne wersjonowanie SemVer, początkowo `0.1.0`.
- Jawna wersja kontraktu API providera, początkowo `1`.
- Licencja projektu: GPL-3.0, z zachowaniem informacji o autorach portów.
- Publiczne API wejściowe wymagane przez Umbrellę:

```python
mwoscrapers.sources(specified_folders=None, ret_all=False)
```

Każdy provider zwraca parę `(nazwa, klasa_source)` zgodną z oczekiwaniami
Umbrelli. W Etapie 0 zostanie zamrożony pełny kontrakt z przypiętego commita
Umbrelli: `hasMovies`, `hasEpisodes`, `pack_capable`, `priority`, wymagane
metody filmu/serialu/odcinka, `sources(data, hostDict)`, typy pól, obsługa
wyjątków, timeouty i semantyka `ret_all`.

Zmiany kompatybilne zachowują numer kontraktu API. Zmiana łamiąca zwiększa
numer kontraktu i wymaga równoczesnego wydania Umbrelli oraz MwoScrapers.
Ponieważ Kodi interpretuje wersję zależności jako minimum, każda publikowana
para jest dodatkowo przypięta dokładnymi commitami i testowana z locka kanału;
nie wolno opublikować samodzielnej, niekompatybilnej wersji MwoScrapers.

Zgodność nazwy funkcji nie wystarcza do integracji. Fork Umbrelli wykorzysta
istniejący w upstreamie, ogólny mechanizm `external_provider`; nie należy go
wyodrębniać do downstreamowego `provider_adapter.py` bez konkretnego błędu,
ponieważ zwiększyłoby to patch stack i ryzyko konfliktów. Nazwa
`mwoscrapers` nie może być zakodowana w ogólnym loaderze ani w ścieżce
resolvera. Jedynym zamierzonym sprzężeniem dystrybucyjnym jest wymagana
zależność `script.module.mwoscrapers` w downstreamowym `addon.xml`.

Granica zaufania wymaga natomiast osobnej, małej polityki
`resources/lib/downstream/provider_context_policy.py`. Bezpośrednio przed
wywołaniem kodu zewnętrznego providera Umbrella przekaże sanitizowaną kopię
kontekstu, która:

- nigdy nie zawiera `debrid_token`, refresh tokenu, sekretu klienta ani
  rozwiązanego URL-a;
- może zawierać wyłącznie niewrażliwą nazwę aktywnej usługi debrid, jeśli
  provider potrzebuje jej do oznaczenia wyniku;
- zachowuje metadane filmu lub odcinka potrzebne do wyszukania źródeł;
- nie zmienia kontekstu używanego później wewnątrz resolvera Umbrelli.

`sources.py` ma zawierać tylko cienkie wywołanie sanitizera w każdym miejscu,
które przekazuje `data` zewnętrznemu providerowi. Do czasu wdrożenia i testu
tej polityki nie wolno importować nie w pełni zaufanego kodu providera ani
promować dodatku do stable.

Test instalacyjny potwierdzi:

1. instalację wyłącznie Umbrelli z repo i automatyczne dobranie MwoScrapers
   jako zależności;
2. wykrycie pustego rejestru MwoScrapers;
3. wybór MwoScrapers zamiast Coco/Viper/Magneto;
4. powrót do poprzedniego modułu bez utraty jego ustawień;
5. kontrolowany fallback przy pustym rejestrze lub wyjątku `sources()`;
6. poprawne fail-closed instalacji lub uruchomienia, gdy wymaganej zależności
   nie można zainstalować albo została wyłączona.

### 5.2 Układ kodu

```text
script.module.mwoscrapers/
├── addon.xml
├── LICENSE
├── NOTICE.md
├── lib/
│   └── mwoscrapers/
│       ├── __init__.py
│       ├── registry.py
│       ├── contract.py
│       ├── normalize.py
│       ├── health.py
│       ├── settings.py
│       └── providers/
│           └── torrents/
├── resources/
│   ├── settings.xml
│   └── provider-provenance.yml
└── tests/
```

Providerzy nie będą przechowywani w namespace `cocoscrapers`,
`viperscrapers` ani `magneto`. Porty będą jawnie dostosowane do wspólnego
API `mwoscrapers`, co zapobiega konfliktom, gdy oryginalny dodatek jest
równocześnie zainstalowany.

### 5.3 Zasady wyboru „najlepszego” wariantu

Dla każdej nazwy providera powstanie macierz kandydatów zawierająca:

- rodzinę i wersję źródłową;
- SHA-256 oryginalnego ZIP-a i pliku;
- datę importu;
- licencję i atrybucję;
- zgodność z kontraktem;
- jakość parsowania metadanych;
- poprawność BTIH;
- liczbę unikalnych wyników po deduplikacji;
- odsetek błędów i medianę czasu;
- zakres wymaganych lokalnych zmian.

Wybór nie będzie automatyczny. Automat przygotuje porównanie i PR, a
utrzymujący zaakceptuje jeden wariant.

Wstępni kandydaci do pierwszej kwalifikacji:

- wspólne: Torrentio, Bitsearch, Comet, MediaFusion, Nyaa, PirateBay,
  Kickass2;
- nowsze API/indexery: Torz, Zilean, DMM, Bitmagnet, Meteor;
- klasyczne źródła: TorrentDownload, EZTV, Knaben;
- infrastruktura użytkownika: Prowlarr;
- osobny eksperyment: AIOStreams.

Lista nie jest listą domyślnie włączonych providerów.

### 5.4 Normalizacja i granica deduplikacji

MwoScrapers będzie:

- normalizował hash BTIH do jednej postaci;
- ujednolicał nazwę providera, jakość, rozmiar, język i flagę pakietu;
- odrzucał elementy bez wystarczających danych do późniejszej identyfikacji;
- usuwał duplikaty zwrócone przez ten sam provider, o ile zachowuje to
  rozróżnienie filmu, odcinka, pliku i pakietu.

MwoScrapers nie będzie odtwarzał finalnego sortowania Umbrelli. Umbrella
pozostaje właścicielem scalenia wyników, deduplikacji między providerami,
filtrów i preferencji użytkownika, ponieważ `mwoscrapers.sources()` zwraca
klasy providerów, a nie wspólny zbiór ich wyników. Downstreamowa
deduplikacja Umbrelli zachowa listę providerów pochodzenia jako metadane
diagnostyczne i będzie idempotentna względem normalizacji MwoScrapers.

### 5.5 Konserwatywne wartości domyślne

Pierwsze wydanie nie włączy wszystkich providerów:

- maksymalnie 2–3 zakwalifikowane providery będą domyślnie aktywne;
- providery zwracające agregowane, masowe wyniki będą domyślnie wyłączone do
  czasu pomiaru wpływu na resolver;
- AIOStreams, Prowlarr i providery wymagające konfiguracji użytkownika będą
  opt-in;
- ustawienia pozwolą włączyć każdy zakwalifikowany provider osobno.

## 6. Import i cykliczne aktualizacje providerów

### 6.1 Manifest pochodzenia

`upstreams.lock.yml` w repo MwoScrapers będzie przechowywał dla każdego
źródła:

- URL repo lub feedu;
- ref/commit, jeżeli istnieje;
- wersję dodatku;
- URL ZIP-a;
- SHA-256 ZIP-a;
- listę zaimportowanych plików i ich SHA-256;
- deklarowaną licencję;
- datę ostatniego sprawdzenia.

Feed wskazuje URL i oczekiwaną wersję, ale autorytatywnym materiałem importu
jest dokładnie raz pobrany ZIP. Jego wewnętrzne ID i wersja muszą zgadzać
się z feedem; rozbieżność oznacza `quarantined` i issue. Dla plików z GitHub
manifest i ZIP będą pobierane z tego samego przypiętego commita, nigdy z
dwóch odczytów ruchomego `master`.

`provider-provenance.yml` będzie mapował każdy aktywny port na:

- najwcześniejsze znane źródło i właściciela praw;
- SPDX konkretnego pliku i zgodność licencji zależności;
- oryginalny URL, ścieżkę, commit albo ZIP+SHA-256;
- zachowane notices;
- listę lokalnych modyfikacji;
- Git blob SHA i patch-id commitów adaptacyjnych.

Brak pełnego łańcucha oznacza `license-blocked`, a nie warunkowy import.

### 6.2 Integralność pinów i wykrywanie nowych wersji

Obecny `check-provider-upstreams.yml` jest audytem integralności przypiętych
artefaktów: ponownie pobiera zapisane URL-e i potwierdza oczekiwane sumy. Nie
wolno opisywać go jako mechanizmu wykrywania nowych wydań.

Osobny `discover-provider-upstreams.yml`, uruchamiany raz dziennie i ręcznie:

1. odczytuje bieżące feedy Coco, Viper i Magneto;
2. porównuje wersję, URL i pełny commit SHA z przypiętym stanem;
3. pobiera ZIP do katalogu tymczasowego, przy czym odwołania GitHub
   `main/master` rozwiązuje najpierw do pełnego, niezmiennego commit SHA;
4. weryfikuje SHA-256, zgodność feed/ZIP, `addon.xml` i bezpiecznie
   inwentaryzuje archiwum bez importowania lub wykonywania jego kodu;
5. egzekwuje limity liczby plików, rozmiaru skompresowanego i
   rozpakowanego oraz współczynnika kompresji;
6. odrzuca ścieżki absolutne i `..`, symlinki, hardlinki, device files,
   archiwa zagnieżdżone, duplikaty nazw oraz kolizje Unicode/case i ścieżek
   Windows;
7. wykonuje skan licencji, zależności i niedozwolonych plików;
8. porównuje wyłącznie providery śledzone przez MwoScrapers;
9. generuje raport zmian względem przypiętego artefaktu;
10. otwiera issue lub PR na gałęzi `import/<rodzina>-<wersja>`;
11. nie scala i nie publikuje automatycznie.

Ingest działa bez sekretów, z `contents: read`, bez
`pull_request_target`. Osobny minimalny krok tworzy PR. Zewnętrzne GitHub
Actions są przypięte po pełnym commit SHA, a workflow ma concurrency lock.

Przed kwalifikacją przechowujemy publicznie tylko URL, sumę i raport.
Pełny źródłowy ZIP może być przechowany w ograniczonym dostępie na czas
review. Nie będzie publicznym release asset ani częścią Git bez osobnego
potwierdzenia prawa do redystrybucji i ustalonej retencji.

### 6.3 Adaptacja portów

- Importer nie będzie wykonywał niekontrolowanego globalnego
  search-and-replace.
- Zależności od modułów rodziny źródłowej będą mapowane przez jawny adapter
  albo portowane do wspólnego modułu.
- Każda zmiana importu będzie widoczna w diffie PR.
- Aktualizacja jednego providera nie może zmieniać innego bez osobnego
  uzasadnienia.
- Provider niespełniający kontraktu pozostanie na poprzedniej wersji lub
  zostanie oznaczony jako `quarantined`.
- Provider z niepełnym łańcuchem licencyjnym ma status `license-blocked` i
  jego kod nie może znaleźć się ani w branchu publikacyjnym, ani w ZIP-ie.

## 7. Strategia synchronizacji Umbrelli

Remoty:

```text
origin    https://github.com/mwoDevelop/umbrellaplug.github.io.git
upstream  https://github.com/umbrellaplug/umbrellaplug.github.io.git
```

Gałęzie:

- `upstream-master`: czysty fast-forward mirror `upstream/master`;
- `main`: zweryfikowany downstream z małym stosem poprawek;
- `sync/<data>-<sha>`: tymczasowa gałąź aktualizacji.

Workflow `sync-upstream.yml`:

1. działa raz dziennie i przez `workflow_dispatch`;
2. aktualizuje `upstream-master`;
3. kończy bez zmian, jeśli nie ma nowego commita;
4. przy non-fast-forward zatrzymuje się, tworzy alert i wymaga ręcznego
   zatwierdzenia nowej bazy;
5. odtwarza mały stos downstream na nowym upstreamie;
6. uruchamia testy;
7. otwiera jeden idempotentny PR z raportem zmian lub konfliktów;
8. nigdy nie publikuje bez review.

Manifest patch stacku zapisuje bazowy commit upstreamu, kolejność, temat,
patch-id i stan każdego downstreamowego patcha. Workflow ma concurrency
lock; ponowne uruchomienie aktualizuje ten sam branch/PR zamiast tworzyć
duplikaty.

## 8. Izolowana poprawka resolvera Umbrelli

### 8.1 Potwierdzony problem

Kontrolowany test na Kodi 21.2 wykazał:

- 40 znalezionych źródeł;
- 41 wywołań resolvera w około 12 sekund;
- 13 odpowiedzi Real-Debrid `infringing_file` (`35`);
- 28 odpowiedzi `too_many_requests` (`34`);
- ponowną próbę wybranego źródła przez duplikat kolejki;
- wyciszanie kodów `34` i `35` przez warstwę Real-Debrid;
- końcowy wyjątek `quote_from_bytes() expected bytes`, gdy
  `errorForSources()` otrzymuje `title=None`.

Rodzaj użytego providera może zmienić liczbę i jakość źródeł, ale nie usuwa
tych błędów. Poprawka musi być niezależna od MwoScrapers.

### 8.2 Granice zmiany

Preferowany nowy kod:

```text
plugin.video.umbrella/
└── resources/lib/downstream/
    ├── __init__.py
    ├── resolver_policy.py
    ├── resolver_types.py
    └── rd_transport_policy.py
```

`resolver_policy.py` będzie odpowiadał za:

- stabilną deduplikację kolejki prób;
- identyfikację próby po BTIH i wyborze pliku/odcinka, gdy dostępny;
- sesyjny negative cache dla `infringing_file`;
- klasyfikację wyniku;
- generation/attempt ID, aby spóźniony wątek poprzedniej próby nie mógł
  nadpisać wyniku bieżącej;
- bezpieczne logowanie bez tokenu, pełnego magneta i rozwiązanego URL-a.

Jeden współdzielony, thread-safe `rd_transport_policy.py` będzie obejmował
każde autoryzowane żądanie `_get/_post` wykonywane podczas `resolve_magnet`,
a nie tylko zmianę źródła. Wewnętrzny wynik transportu zachowa HTTP status,
`error_code`, nazwę błędu i `Retry-After`; publiczne metody Umbrelli nadal
zwrócą typy oczekiwane przez upstream.

Początkowe bezpieczniki, następnie strojenie na podstawie pomiaru:

- maksymalnie jedno równoległe autoryzowane żądanie RD na konto;
- minimalny odstęp 1 s pomiędzy rozpoczęciem żądań, zgodnie z ograniczeniem
  opisanym w istniejącym kliencie Umbrelli;
- najwyżej jedna ponowna próba żądania po kodzie `34`;
- `Retry-After` respektowany do 30 s; większa wartość kończy bieżącą akcję
  kontrolowanym komunikatem;
- przy braku nagłówka backoff 1 s z jitterem 250–750 ms;
- całkowity budżet resolvera dla jednej akcji użytkownika: 60 s;
- maksymalnie 8 unikalnych prób źródła w jednej akcji.

Limity będą konfigurowalne wewnętrznie, ale nie zostaną zwiększone bez
testu obciążenia i zredagowanego logu.

Cienkie punkty integracji:

1. `resources/lib/modules/sources.py`
   - budowa kolejki bez duplikowania pierwszego źródła;
   - użycie resolver policy;
   - wynik każdej próby zwracany lokalnie z attempt ID, bez współdzielonego
     zapisu do `self.url` przez spóźniony wątek;
   - bezpieczne przekazanie tytułu do `errorForSources()`;
   - ochrona przed `None`.
2. `resources/lib/debrid/realdebrid.py`
   - adapter transportu zachowujący nagłówki i klasyfikację kodów `34/35`;
   - kompatybilny wynik publicznych metod dla pozostałych wywołań.

Założenie projektowe: najwyżej dwa istniejące pliki upstreamu będą miały
zmiany funkcjonalne. Przekroczenie granicy wymaga ponownego review projektu.

### 8.3 Stos commitów

1. `fix: make no-sources fallback null-safe`;
2. `fix: deduplicate resolver attempt order`;
3. `feat: classify Real-Debrid resolver outcomes`;
4. `fix: isolate timed resolver attempts by generation`;
5. `feat: add transport-wide RD rate limiting and bounded backoff`;
6. `test: cover resolver policy, transport and fallback paths`.

Każdy commit będzie można osobno usunąć, jeśli upstream dostarczy
równoważną poprawkę.

## 9. Wersjonowanie i pochodzenie instalacji

ID:

- `plugin.video.umbrella` pozostaje bez zmian;
- nowy moduł ma ID `script.module.mwoscrapers`;
- oryginalne Coco, Viper i Magneto mogą współistnieć, ale nie są wymagane do
  działania MwoScrapers.

MwoScrapers używa własnego SemVer.

Wersja downstream Umbrelli otrzyma monotoniczną numeryczną rewizję
wyprowadzoną z wersji upstream, kandydat: `6.7.81.1`. Etap 0 musi potwierdzić
na Kodi porównywanie czteroczłonowej wersji, przejście do następnego
upstreamu i emergency forward-revert. Jeśli test nie przejdzie, zostanie
wybrana trzyczłonowa funkcja wersji przed pierwszą publikacją.

Testing publikuje kandydata o jego docelowej wersji, a stable promuje
dokładnie te same bajty. Nigdy nie wolno opublikować innych bajtów pod tym
samym `ID+version`.

Kanały nie mogą korzystać ze wspólnego ruchomego pinu komponentu. Każdy ma
własny lock mapujący `addon ID` na co najmniej: commit źródłowy, wersję,
SHA-256 ZIP-a i wersję kontraktu zależności. `stable` wskazuje niezmienny
artefakt wcześniej opublikowany i zweryfikowany w `testing`; późniejsza
publikacja testing nie może przebudować ani zmienić żadnego pliku stable.

Zachowanie `origin` Kodi nie będzie zakładane. Etap 0 sprawdzi na czystej
bazie Addons cztery przypadki: instalację Umbrelli z repo upstream,
instalację repo downstream, jawny wybór wersji downstream i następną
automatyczną aktualizację. Dopiero wynik tego testu stanie się instrukcją
migracji. MwoScrapers jest nowym ID i nie przejmuje pochodzenia innego
dodatku.

## 10. Wspólne repozytorium Kodi

### 10.1 Struktura publikacji

```text
https://mwodevelop.github.io/kodi/
├── repository.mwodevelop-1.0.0.zip
├── repository.mwodevelop.testing-1.0.0.zip
├── stable/omega/
│   ├── addons.xml
│   ├── addons.xml.sha256
│   ├── plugin.video.umbrella/
│   │   └── plugin.video.umbrella-<wersja>.zip
│   └── script.module.mwoscrapers/
│       └── script.module.mwoscrapers-<wersja>.zip
└── testing/omega/
    └── analogiczny układ
```

`repository.mwodevelop` będzie wskazywać wyłącznie `stable`.
`repository.mwodevelop.testing` będzie osobnym dodatkiem wskazującym
wyłącznie `testing`. Urządzenie produkcyjne nie będzie miało zainstalowanego
repo testing.

Oba indeksy muszą zawierać MwoScrapers, ponieważ Kodi potrzebuje jego
metadanych i ZIP-a do rozwiązania zależności Umbrelli. Dokumentacja i
podstawowa ścieżka UI wskazują jednak instalację Umbrelli; MwoScrapers nie
otrzymuje osobnego repo Kodi ani kroku ręcznej instalacji. Jego bezpośredni
ZIP pozostaje publiczny dla mechanizmu zależności, audytu i diagnostyki.

Każdy dodatek repo będzie miał jawny wpis:

```xml
<dir minversion="21.0.0" maxversion="21.99.0">
  <info compressed="false">.../addons.xml</info>
  <checksum>.../addons.xml.sha256</checksum>
  <datadir zip="true">.../</datadir>
  <hashes>false</hashes>
</dir>
```

Na GitHub Pages `addons.xml.sha256` jest tokenem zmiany indeksu i dowodem
audytowym, a nie kryptograficzną weryfikacją ZIP-a przez Kodi. `<hashes>`
pozostaje `false`, ponieważ Pages nie zapewnia wymaganego nagłówka
`content-sha256`. Manifest sum jest natomiast obowiązkowo sprawdzany przez
CI, workflow wdrożeniowy i test powdrożeniowy.

### 10.2 Generator

Generator w repo głównym:

1. czyta katalog komponentów i niezależny lock każdego kanału;
2. sprawdza ID, wersję, licencję i zależności;
3. tworzy deterministyczne ZIP-y z katalogiem ID w korzeniu;
4. generuje `addons.xml`;
5. generuje plik zmiany indeksu i manifest SHA-256 artefaktów;
6. buduje ZIP-y obu dodatków repozytorium;
7. buduje kompletny snapshot Pages z przypiętych manifestów obu kanałów;
8. sprawdza byte-for-byte niezmienność kanału, który nie jest promowany;
9. publikuje niezmienny artefakt CI;
10. po zatwierdzeniu wdraża dokładnie ten artefakt na GitHub Pages;
11. porównuje publiczne SHA-256 każdego pliku z manifestem.

Lock kanału ma postać logiczną:

```text
channel
└── addon ID
    ├── commit
    ├── version
    ├── zip_sha256
    └── dependency_contract
```

Przy publikacji testing generator musi odtworzyć stable wyłącznie z jego
locka lub skopiować jego niezmienny snapshot artefaktu. Test sekwencyjny
buduje `stable=A`, następnie `testing=B`, potem `testing=C` i wymaga, aby
każdy bajt `stable` nadal odpowiadał A.

Repo główne jest jedynym źródłem publikacji. Wygenerowane ZIP-y nie będą
ręcznie kopiowane pomiędzy repozytoriami. Publikacje mają concurrency lock,
a środowisko `stable` wymaga ręcznego zatwierdzenia.

## 11. Testy i bramy jakości

### 11.1 MwoScrapers

- test publicznego API `sources()`;
- test pełnego kontraktu klasy każdego providera względem minimalnego
  adaptera i przypiętego commita Umbrelli;
- fixtures odpowiedzi sieciowych bez zależności od żywych stron;
- walidacja BTIH, rozmiaru, jakości, języka i pakietu;
- test deduplikacji wyniku powtórzonego przez pojedynczy provider;
- test zachowania różnych odcinków/pliku w tym samym pakiecie;
- test izolacji awarii jednego providera;
- test timeoutu i anulowania;
- test, że provider quarantined nie jest ładowany;
- test zgodności ustawień z rejestrem providerów;
- skan licencji i atrybucji;
- skan sekretów.

### 11.2 Umbrella resolver

- sukces;
- `34 too_many_requests`;
- `35 infringing_file`;
- `Retry-After`;
- backoff bez nagłówka;
- powtórzony BTIH;
- różne pliki/odcinki w pakiecie;
- `title=None`;
- 40 unikalnych źródeł nie tworzy 41 prób;
- ten sam BTIH z kilku providerów tworzy jeden finalny klucz próby i
  zachowuje diagnostyczną listę pochodzenia;
- timeout próby i spóźniony sukces poprzedniego wątku;
- cancel/abort oraz thread-safe limiter i negative cache;
- wszystkie wywołania RD w `resolve_magnet()` przechodzą przez limiter;
- maksymalna liczba retry, prób źródła i budżet 60 s są egzekwowane;
- logi nie zawierają tokenu RD ani pełnego URL-a.

### 11.2a Granica zaufania Umbrella–provider

- istniejący upstreamowy mechanizm `external_provider` ładuje dowolny moduł
  zgodny z kontraktem, bez warunków specyficznych dla MwoScrapers;
- test podmienia moduł zgodny, pusty i rzucający wyjątek;
- provider-canary kończy test błędem, jeśli otrzyma `debrid_token` lub inny
  sekret;
- `provider_context_policy.py` zwraca kopię kontekstu bez sekretów i nie
  importuje kodu resolvera;
- brak lub wyłączenie wymaganej zależności jest testowane jako fail-closed
  Kodi, a nie wspierany fallback runtime;
- zmiana lub dodanie providera nie wymaga zmiany resolvera;
- konflikt rebase w cienkich wywołaniach sanitizera zatrzymuje automatyczną
  publikację.

### 11.3 Repozytorium Kodi

- parsowanie `addon.xml` i `addons.xml`;
- zgodność ID, wersji, nazwy katalogu i ZIP-a;
- brak ścieżek absolutnych oraz `..` w ZIP-ach;
- Kodi Addon-Checker tam, gdzie ma zastosowanie;
- deterministyczność ZIP-ów i sum;
- HTTP 200 dla indeksu, sum i pakietów;
- instalacja samej Umbrelli na czystym profilu Kodi 21.3 i potwierdzenie
  automatycznej instalacji MwoScrapers;
- stan bazy dodatków i log `CAddonInstallJob` przed i po czystej instalacji,
  dowodzące, że MwoScrapers nie był obecny i został dobrany jako zależność;
- instalacja na czystym profilu najnowszego Kodi 21.x;
- rzeczywiste odświeżenie indeksu repo i wykrycie nowej wersji;
- aktualizacja testing→stable bez zmiany bajtów;
- zachowanie ustawień i `origin` przy migracji/aktualizacji;
- emergency forward-revert i ręczny downgrade;
- sprawdzenie, że stable nie widzi artefaktów testing.

### 11.4 Kwalifikacja providerów

Provider może wejść do pierwszego wydania tylko, jeśli:

- przechodzi test kontraktowy i fixtures;
- nie wymaga nieudokumentowanych zależności;
- ma potwierdzone pochodzenie i licencję;
- po końcowej deduplikacji Umbrelli nie pozostawia powtarzających się kluczy;
- ma zmierzony marginalny yield i poprawne metadane względem pozostałych
  kandydatów;
- mieści się w budżecie 15 s na provider, ma timeout per request do 8 s i
  nie wykonuje więcej niż 3 równoległych żądań;
- nie loguje danych wrażliwych;
- przechodzi ograniczony test sieciowy na legalnej/public-domain treści
  testowej albo kontrolowanym lokalnym fixture.

Wyniki żywej sieci są sygnałem diagnostycznym, nie deterministycznym testem
CI.

## 12. Test integracyjny na `BlueStacks1`

### Przygotowanie

1. wykonać kopię ustawień Umbrelli, Magneto i bazy dodatków;
2. zapisać wersje i repozytoria pochodzenia;
3. nie usuwać danych uwierzytelniających;
4. zainstalować wyłącznie `repository.mwodevelop.testing`;
5. z repo testing zainstalować wyłącznie Umbrellę i potwierdzić w logu oraz
   bazie dodatków, że Kodi automatycznie zainstalował MwoScrapers;
6. pozostawić Magneto tylko jako opcjonalny baseline porównawczy;
7. przełączać tylko setting zewnętrznego providera Umbrelli.

Kopie profilu i logi pozostają lokalne, są zredagowane i nie trafiają do
artefaktów CI; tokeny i dane kont nie mogą być kopiowane do repo.

### Test porównawczy

Na tej samej treści i ustawieniach wykonać osobne przebiegi:

1. Magneto jako baseline;
2. Viper jako dodatkowy baseline, jeżeli jest zainstalowany;
3. MwoScrapers przed poprawką resolvera Umbrelli;
4. MwoScrapers po poprawce resolvera.

Zapisać:

- czas scraping/resolution;
- liczbę surowych i unikalnych źródeł;
- rozkład providerów;
- liczbę prób resolvera;
- kody `34` i `35`;
- liczbę duplikatów;
- wynik odtwarzania;
- zredagowany log.

### Kryteria akceptacji

- brak `quote_from_bytes() expected bytes`;
- brak podwójnej próby tego samego klucza źródła;
- `35` nie ponawia tego samego BTIH w sesji;
- `34` uruchamia kontrolowany backoff;
- awaria jednego providera nie przerywa całego scrapingu;
- MwoScrapers zwraca schemat zgodny z Umbrellą;
- czysta instalacja Umbrelli automatycznie instaluje zgodną wersję
  MwoScrapers bez osobnego działania użytkownika;
- pusty rejestr lub wyjątek MwoScrapers daje kontrolowany fallback, a
  brakująca lub wyłączona wymagana zależność blokuje uruchomienie fail-closed;
- żaden zewnętrzny provider nie otrzymuje tokenu ani sekretu Real-Debrid;
- działające kolejne źródło może zostać rozwiązane;
- cała akcja kończy się lub zwraca kontrolowany komunikat w budżecie 60 s;
- żaden provider nie przekracza własnego budżetu 15 s;
- logi są zredagowane.

## 13. Publikacja, promocja i rollback

- Workflow komponentów buduje artefakty, ale ich nie publikuje.
- Merge w repo głównym może opublikować wyłącznie kanał `testing`.
- Promocja do `stable` jest osobnym, ręcznym workflow wskazującym dokładny
  SHA-256 artefaktu z testing.
- Promocja nie przebudowuje ZIP-a.
- Każde stable otrzymuje tag, manifest źródeł i manifest sum.
- Repo Kodi zachowuje co najmniej poprzedni ZIP obu dodatków, ale nie
  traktuje niższej wersji jako automatycznego rollbacku.
- Przed instalacją wadliwej wersji rollback wdrożenia Pages przywraca
  wcześniejszy kompletny snapshot strony.
- Dla urządzeń, które już zainstalowały wadliwą wersję, normalnym
  rollbackiem jest emergency forward-revert: nowa, wyższa wersja z
  odwróconą zmianą.
- Ręczny downgrade awaryjny używa `Versions`/`Install from ZIP`, po czym
  wymaga przypięcia wersji albo wyłączenia auto-update do czasu
  forward-revert.
- Test rollbacku obejmuje urządzenie, na którym wadliwa wersja została już
  zainstalowana.
- Workflow synchronizacji upstream nigdy nie zapisuje bezpośrednio do
  `stable`.

## 14. Kolejność realizacji

### Etap 0 — proof-of-contract, legal i model wydania

- zamrozić pełny kontrakt Umbrella↔provider na przypiętym commicie;
- potwierdzić, że Umbrella jest właścicielem deduplikacji między
  providerami;
- odtworzyć łańcuch licencyjny pierwszych 2–3 konkretnych providerów;
- wykonać spike minimalnego repo Kodi na czystym profilu: wersjonowanie,
  `origin`, testing→stable, odświeżenie indeksu i emergency forward-revert;
- zatwierdzić threat model importera i workflow;
- zatwierdzić numeryczne limity providerów i transportu RD.

Wyjście: raport kontraktu, decyzje licencyjne, działający nieprodukcyjny
spike repo i zaakceptowany threat model. Bez tego nie rozpoczyna się importu
kodu ani publikacji.

### Etap 1 — repo główne

- zainicjalizować `/home/mwo/projects/kodi` jako repo Git;
- utworzyć `mwoDevelop/kodi`;
- dodać README, strukturę, licencję i pliki lock;
- włączyć ochronę głównej gałęzi.

### Etap 2 — fork Umbrelli

- utworzyć `mwoDevelop/umbrellaplug.github.io`;
- sklonować do `/home/mwo/projects/kodi/umbrella`;
- dodać remote `upstream`;
- przypiąć commit startowy;
- dodać workflow synchronizacji bez publikacji.

### Etap 3 — szkielet MwoScrapers

- utworzyć `mwoDevelop/script.module.mwoscrapers`;
- sklonować do `/home/mwo/projects/kodi/mwoscrapers`;
- wdrożyć addon manifest, API, registry, kontrakt i testy;
- dodać provenance i importer bez aktywnych portów;
- potwierdzić wykrycie pustego modułu przez ogólny adapter providerów
  Umbrelli.

### Etap 4 — bezpieczny importer

- pobrać i przypiąć trzy aktualne ZIP-y upstream;
- wdrożyć bezpieczną inwentaryzację archiwów bez wykonywania kodu;
- wdrożyć rozdział ingest/PR i minimalne uprawnienia;
- przetestować przypadki złośliwych i niejednoznacznych archiwów;
- potwierdzić quarantine przy rozbieżności feed/ZIP.

### Etap 5 — kwalifikacja pierwszych providerów

- wdrożyć i zakwalifikować maksymalnie 2–3 oryginalne adaptery publicznych
  API jako model podstawowy pierwszego wydania;
- utworzyć macierz porównawczą rodzin Coco/Viper/Magneto wyłącznie jako
  przyszłą ścieżkę warunkową;
- ewentualny port wykonać osobnym commitem dopiero po pełnej kwalifikacji
  licencyjnej konkretnego pliku;
- uruchomić testy kontraktowe, fixtures, normalizację per-provider oraz
  integracyjną deduplikację między providerami w Umbrelli.

Jakość scrapingu ocenia się niezależnie od skuteczności wadliwego resolvera;
wynik resolution nie wybiera providera przed naprawą resolvera.

### Etap 6 — wspólne repo Kodi

- utworzyć dodatki repo stable i testing;
- zaimplementować deterministyczny generator;
- dodać Umbrellę i MwoScrapers jako submoduły;
- zbudować i opublikować wyłącznie `testing`;
- przeprowadzić test czystej instalacji Umbrelli wraz z automatycznym
  rozwiązaniem zależności MwoScrapers.

### Etap 7 — testy reprodukujące resolver

- dodać fixtures i testy dla potwierdzonych błędów bez zmiany kodu
  produkcyjnego;
- odtworzyć kody `34/35`, duplikat pierwszego źródła, `title=None` oraz
  spóźniony wątek;
- zatwierdzić budżety i oczekiwane wyniki testów.

### Etap 8 — poprawka Umbrelli

- wdrożyć mały stos commitów z sekcji 8;
- zbudować kanał testing;
- nie zmieniać providerów w tym samym PR.

### Etap 9 — test integracyjny

- wykonać porównanie na `BlueStacks1`;
- zebrać log i metryki;
- naprawić regresje;
- zatwierdzić dokładne commity obu komponentów.

### Etap 9a — bramy przed stable

- wdrożyć `provider_context_policy.py` i usunąć sekrety debrid z kontekstu
  przekazywanego providerom;
- dodać niezależne locki stable/testing i test niezmienności stable;
- wdrożyć prawdziwe wykrywanie nowych wersji upstream oddzielone od audytu
  integralności przypiętych ZIP-ów;
- potwierdzić automatyczną instalację MwoScrapers jako zależności Umbrelli na
  czystym profilu wraz ze stanem bazy przed/po;
- uzupełnić testy `origin`, migracji, forward-revert i najnowszego Kodi 21.x;
- wykonać integracyjny test kodów RD `34/35` przez pełną ścieżkę
  `sources.py → realdebrid.py`;
- ujednolicić README ze stanem bram opisanym w tym planie;
- powtórzyć E2E od scrapingu do odtwarzania na finalnym buildzie przed
  promocją stable.

### Etap 10 — pierwsze stable

- wdrożyć chroniony, ręczny workflow promocji stable;
- wskazać dokładny immutable candidate z testing po SHA-256;
- skopiować ZIP-y i snapshot bez przebudowy komponentów;
- oznaczyć komponenty tagami;
- promować bez przebudowy zweryfikowany artefakt;
- sprawdzić publiczne URL-e i aktualizację Kodi;
- zachować komplet danych rollback.

### Etap 11 — utrzymanie

- codziennie wykrywać zmiany upstream;
- aktualizować wyłącznie przez PR;
- okresowo testować instalację repozytorium;
- kwartalnie przeglądać providerów, licencje i źródła;
- usuwać lub quarantinować providerów trwale niesprawnych.

## 15. Decyzje do zatwierdzenia

1. Główne repo: `mwoDevelop/kodi`.
2. Fork Umbrelli: `mwoDevelop/umbrellaplug.github.io`.
3. Nowy projekt providerów: `mwoDevelop/script.module.mwoscrapers`.
4. Dodatek stable: `repository.mwodevelop`.
5. Osobny dodatek testowy: `repository.mwodevelop.testing`.
6. Zachowanie ID Umbrelli i nowe, niekolidujące ID MwoScrapers.
7. GitHub Pages jako hosting repozytorium Kodi.
8. Model: automat przygotowuje PR, człowiek zatwierdza port i promocję.
9. Maksymalnie 2–3 providery domyślnie aktywne w pierwszym wydaniu.
10. Deduplikacja między providerami pozostaje w Umbrelli.
11. Limiter obejmuje transport wszystkich autoryzowanych żądań RD.
12. Rollback zainstalowanego wydania używa wyższej wersji forward-revert.
13. MwoScrapers pozostaje osobnym repo Git i modułem Kodi, ale nie otrzymuje
    osobnego repo Kodi ani ręcznej ścieżki instalacji.
14. Umbrella zachowuje upstreamowy ogólny loader providerów; downstream
    dodaje jedynie izolowaną sanitizację kontekstu bez sekretów.
15. Kanały stable/testing mają niezależne locki komponentów i artefaktów.
16. Breaking change kontraktu MwoScrapers wymaga równoczesnego wydania
    kompatybilnej Umbrelli.

Po zatwierdzeniu planu realizację należy prowadzić etapami. Każdy etap
kończy się działającym, zweryfikowanym rezultatem i nie wymusza rozpoczęcia
następnego.

## 16. Wynik audytu zewnętrznego

Niezależny reviewer sprawdził cały dokument pod kątem sensowności,
spójności, sprzeczności, wykonalności, bezpieczeństwa i publikacji. Audyt
nie edytował pliku. Przyjęto i włączono do planu:

- wszystkie cztery blockery: właściciela deduplikacji, położenie limitera
  RD, prawidłowy model rollbacku Kodi oraz bramę licencyjną per plik;
- pełniejszy kontrakt i jawne wykrywanie MwoScrapers przez Umbrellę;
- threat model importera, minimalne uprawnienia i rozbieżność feed/ZIP jako
  quarantine;
- atomowy pełny snapshot Pages, ochronę stable i jawne ograniczenie
  integralności przy hostingu na GitHub Pages;
- monotoniczne wersjonowanie, test `origin` i zakaz ponownej publikacji
  innych bajtów pod tym samym `ID+version`;
- ochronę przed spóźnionymi wątkami resolvera oraz mierzalne budżety;
- Etap 0 przed utworzeniem/importem kodu.

Opcjonalnych rozszerzeń SBOM/CycloneDX i osobnego canary nie wpisano jako
warunku pierwszego wydania; można je dodać po uruchomieniu deterministycznej
publikacji. Przechowywanie Git blob SHA, patch-id oraz kontrolę odświeżenia
repo uwzględniono już w podstawowym planie.

### 16.1 Ponowny audyt po decyzji o wydzieleniu MwoScrapers

Drugi niezależny audyt potwierdził sens osobnego repo Git i dodatku
`xbmc.python.module`, instalowanego automatycznie jako zależność Umbrelli z
tego samego repo Kodi. Przyjęto następujące uwagi:

- MwoScrapers jest osobnym artefaktem Kodi widocznym w zależnościach, ale nie
  osobno promowanym produktem użytkowym;
- istniejącego loadera `external_provider` nie refaktoryzuje się tylko dla
  OCP; pozostaje niezmienionym punktem rozszerzenia upstream;
- kontekst providera musi zostać zsanityzowany, ponieważ obecna Umbrella
  przekazuje w `data` również `debrid_token`;
- stable i testing wymagają niezależnych locków, a promocja stable osobnego
  workflow kopiującego dokładny artefakt bez przebudowy;
- wymagany MwoScrapers jest testowany przez czystą instalację samej Umbrelli;
  brak zależności jest fail-closed, nie wspieranym fallbackiem;
- status wdrożenia musi odróżniać przechodzące testy jednostkowe i istniejący
  playback E2E od jeszcze niewykonanych bram promocji.

Odrzucono rekomendację tworzenia `provider_adapter.py` wyłącznie dla OCP,
ukrywania MwoScrapers w `addons.xml`, scalania jego repo z Umbrellą,
oznaczania zależności jako opcjonalnej oraz przenoszenia resolvera
Real-Debrid do MwoScrapers.

## 17. Stan realizacji 2026-07-24

- Etap 0: częściowo zakończony; kontrakt, granice deduplikacji, threat model i
  polityki wydania są opisane. Test testing→stable jest odtwarzalny lokalnie,
  a `BlueStacks1` działa już na Kodi 21.3; testy `origin`, migracji i
  forward-revert pozostają otwarte.
- Etapy 1–4: repozytoria, fork, szkielet MwoScrapers, bezpieczna
  inwentaryzacja i audyt integralności przypiętych upstreamów działają.
  Oddzielny workflow discovery rozwiązuje ruchome feedy do pełnych commitów,
  porównuje je z lockiem i tworzy deduplikowane issue; nie publikuje kodu.
- Etap 5: zamiast kopiowania kodu z niepewnym łańcuchem licencyjnym wdrożono
  dwa oryginalne adaptery JSON: Torrentio domyślnie i Comet jako opt-in.
- Etap 6: deterministyczny generator, niezależne locki stable/testing,
  pobieranie dokładnych commitów i test niezmienności stable działają.
  Repo testing zawiera oba artefakty, lecz instrukcja instaluje wyłącznie
  Umbrellę. Finalny czysty test zależności czeka na publikację tego commita.
- Etapy 7–8: testy jednostkowe, polityki resolvera/transportu RD oraz
  integracyjny przebieg `sources.py → resolver_policy → RD transport` dla
  kodów `34/35` działają. Provider otrzymuje sanitizowany kontekst bez tokenu.
- Etap 9: zakończony na Kodi 21.3 w `BlueStacks1`. Ze stanu bez Umbrelli i
  MwoScrapers zainstalowano wyłącznie Umbrellę 6.7.81.7 z publicznego testing;
  Kodi automatycznie dobrał MwoScrapers 0.1.2. Następnie Torrentio zwróciło
  pięć źródeł, Real-Debrid rozwiązał wybrane źródło, a legalny film testowy
  `Sintel` był odtwarzany co najmniej 50 sekund.
- Etap 9a: zakończony; sanitizacja sekretów, locki kanałów, discovery, czysty
  test repo, test RD, rzeczywista automatyczna zależność i końcowy playback
  mają zapisane odtwarzalne testy lub raporty.
- Etap 10: ręczny workflow promocji exact testing candidate po SHA-256 jest
  wdrożony i testowany lokalnie. Publiczny stable pozostaje pusty do czasu
  przejścia finalnych bram urządzeniowych; workflow nie został jeszcze
  uruchomiony.

Zastosowanie OCP jest bramą przeglądu: nowa polityka downstream ma powstawać
w osobnym module z testami; zmiana kodu upstream jest dopuszczalna tylko jako
minimalne wywołanie tego rozszerzenia. Synchronizacja odtwarza mały stos
patchy na czystym `upstream-master` i zatrzymuje się przy konflikcie.
