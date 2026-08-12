# Plan rozszerzenia providerów MwoScrapers

Status: ukończony — fundament i cztery nowe adaptery zostały wdrożone jako jeden
zbiorczy MwoScrapers 0.2.0. Ten sam artefakt przeszedł aktualny health probe oraz
pełną certyfikację E2E na BlueStacks i X88, został wypromowany do stable i wdrożony
na wszystkie osiągalne urządzenia. Nie obowiązuje kalendarzowa bramka kolejnych dni.

Orchestrator scalony przed promocją pozostaje zgodny z bieżącym stable: wybiera
kontrakt diagnostyczny na podstawie wersji modułu w locku stable, a nie na podstawie
samej obecności kodu kandydata w `main`.

Strategia wdrożenia: **lab-first, jeden zbiorczy release dla floty**. BlueStacks i
X88 Pro są jedynymi urządzeniami kwalifikacyjnymi podczas dodawania providerów.
Pozostałe urządzenia zachowywały poprzedni stable aż cały wybrany zestaw przeszedł
testy na obu urządzeniach laboratoryjnych; rollout floty rozpoczął się dopiero po
atomowej promocji locka stable.

## 1. Cel i granice

Celem pierwszego wydania jest zwiększenie liczby kwalifikowanych providerów z 2
(`torrentio`, `comet`) do maksymalnie 6, bez pogorszenia poprawności wyników i bez
tworzenia zależności od QNAP, VPN albo konkretnego serwisu pośredniczącego.

Granice odpowiedzialności pozostają niezmienne:

- MwoScrapers wyszukuje i normalizuje metadane źródła, magnet oraz infohash;
- Umbrella scala, filtruje i przekazuje wyniki do resolvera;
- Real-Debrid jest używany dopiero przez warstwę resolvera Umbrella;
- provider nie może otrzymać tokenu Real-Debrid ani zwracać rozwiązanego URL media;
- QNAP relay może być opcjonalną trasą transportową, ale jego awaria lub wyłączenie
  nie może wyłączyć wyszukiwania;
- nowe źródła są domyślnie wyłączone lub oznaczone jako `testing` do czasu przejścia
  bramek kwalifikacyjnych.

## 2. Skąd bierzemy informacje o providerach

### Źródła obserwacyjne już kontrolowane przez projekt

Projekt ma przypięte po commicie i SHA-256 archiwa:

- CocoScrapers: `not-coco-joe/repository.cocoscrapers`;
- ViperScrapers: `OldManJax/repository.oldsalt`, dodatek
  `script.module.viperscrapers`.

Ich deklaracje znajdują się w:

- `mwoscrapers/.upstream/upstream-sources.json`;
- `mwoscrapers/.upstream/upstream-observations.lock.json`.

Archiwa służą do bezpiecznej inwentaryzacji nazw providerów, protokołów i zachowania.
Nie są importowane ani wykonywane podczas skanu, a ich pliki nie będą kopiowane do
MwoScrapers bez oddzielnej analizy licencji i jawnej decyzji. Preferowana jest własna
implementacja na podstawie publicznego kontraktu protokołu i własnych fixture.

Obecna inwentaryzacja daje między innymi następujących kandydatów:

- wspólnych lub podobnych w Coco/Viper: BitSearch, Comet, Kickass2, LimeTorrents,
  MediaFusion, Nyaa, PirateBay, TorrentGalaxy i Torrentio;
- obserwowanych w Coco: 1337x, EZTV, Knaben, Prowlarr, TorrentDownload,
  TorrentProject2 i YTS;
- obserwowanych w Viper: AIOStreams, Bitmagnet, DMM, Meteor, Rutor, TorrentsDB,
  Torz/StremThru i Zilean.

Magneto pozostaje wycofanym źródłem obserwacyjnym: przypięty artefakt został usunięty
upstream i nie jest podstawą nowej implementacji.

### Preferowane źródła pierwotne

Dla każdego wybranego providera należy dodatkowo przypiąć oficjalne repozytorium,
wersję/protokół i licencję, jeżeli takie źródło istnieje. Pierwszymi sprawdzonymi
kandydatami są:

- MediaFusion: `https://github.com/mhdzumair/MediaFusion`;
- StremThru/Torz: `https://github.com/muniftanjim/stremthru`.

Provider bez stabilnego publicznego kontraktu, akceptowalnej licencji lub bezpiecznego
trybu bez danych debrid nie przechodzi kwalifikacji.

## 3. Rekomendowana kolejność

### Fala 1: kolejka maksymalnie czterech dodatkowych adapterów

Kolejność wdrażania, po jednym providerze na PR:

1. **MediaFusion** — adapter Stremio JSON; tylko publiczny tryb P2P/metadanych bez
   integracji debrid.
2. **Torz/StremThru** — wyłącznie tryb zwracający metadane torrent/infohash bez
   magazynu debrid; odrzucić lub odłożyć, jeżeli taki kontrakt nie jest dostępny.
3. **EZTV** — źródło uzupełniające dla seriali poprzez strukturalny publiczny JSON.
4. **Pirate Bay API** — strukturalne publiczne JSON jako zamiennik YTS, którego DNS
   nie był dostępny podczas kwalifikacji.

MediaFusion i Torz są kandydatami pierwszego wyboru ze względu na możliwość użycia
wspólnego, strukturalnego kontraktu. EZTV i Pirate Bay pozostają warunkowe: jeżeli etap
kwalifikacji wykaże niestabilność, brak źródła pierwotnego albo nieakceptowalne
warunki, zastępujemy je kolejno przez Nyaa, PirateBay API, BitSearch i Knaben. Nie
wdrażamy providera tylko po to, aby osiągnąć liczbę sześciu. Do wspólnego wydania
trafiają wyłącznie kandydaci, którzy faktycznie działają oraz poprawiają pokrycie lub
odporność względem Torrentio i Comet.

Kolejka nie oznacza z góry zatwierdzonego zestawu. Każdy kandydat przechodzi lejek:

1. źródło pierwotne, licencja i granica bez debrid;
2. test kontraktu publicznego endpointu z hosta;
3. implementacja i testy offline;
4. test bieżącego, kumulatywnego kandydata na BlueStacks;
5. ten sam kandydat i identyczny SHA artefaktu na X88 Pro;
6. przyjęcie do zestawu albo odrzucenie i przejście do następnego kandydata.

Provider, który działa tylko na jednym z dwóch urządzeń, wymaga specjalnej
konfiguracji niezgodnej z granicami projektu albo istotnie obniża trafność, nie jest
promowany do wspólnego wydania.

### Fala 2: po ocenie pierwszego wydania

Kandydaci: BitSearch, Nyaa, PirateBay API i Knaben. Providerzy zależni od parsowania
HTML (na przykład 1337x, LimeTorrents lub TorrentGalaxy) pozostają wyłączeni
domyślnie i wymagają dłuższej obserwacji, ponieważ częściej zmieniają markup,
uruchamiają ochronę antybotową albo różnie zachowują się za VPN.

### Oddzielna klasa opt-in

Prowlarr/Torznab, Bitmagnet i Zilean mogą później działać jako prywatne endpointy
użytkownika. Nie będą domyślne, wymagane ani powiązane na stałe z QNAP. Adresy i
dane dostępowe muszą pozostać w prywatnej konfiguracji urządzenia.

AIOStreams, DMM i każdy provider wymagający danych debrid lub wykonujący rozwiązywanie
linków są poza zakresem MwoScrapers.

## 4. Projekt zgodny z OCP

### 4.1. Deskryptor providera

Wprowadzić statyczny deskryptor zawierający co najmniej:

- identyfikator i moduł adaptera;
- rodzinę protokołu (`stremio_json`, `structured_json`, później `torznab`);
- obsługiwane typy: film, serial, odcinek, pack;
- publiczny endpoint oraz opcjonalny endpoint użytkownika;
- status `testing`/`qualified`, ustawienie domyślne i limity czasu/wyników;
- informację o możliwości użycia relay;
- referencję do rekordu pochodzenia i licencji.

Registry nadal pozostaje jawny i statyczny — bez automatycznego importowania plików z
katalogu. Dodanie providera ma wymagać nowego adaptera, deskryptora, wpisu provenance
i testów, ale nie zmiany Umbrella ani resolvera.

### 4.2. Małe adaptery protokołów

Wydzielić współdzielone, testowalne elementy:

- klient Stremio stream JSON;
- walidację strukturalnego JSON;
- normalizację magnet/infohash, jakości, rozmiaru, seederów i odcinka;
- limity rozmiaru odpowiedzi, przekierowań i czasu;
- bezpieczne fallback endpointów oraz izolację awarii/circuit breaker.

Adapter konkretnego providera ma zawierać wyłącznie mapowanie endpointu, możliwości i
różnic formatu. Nie tworzymy jednego dużego modułu z rozgałęzieniami po nazwie
providera.

### 4.3. Spójność konfiguracji

Test kontraktowy musi gwarantować zgodność pomiędzy registry, ustawieniami Kodi,
deskryptorami i `provider-provenance.yml`. Provider nie może pojawić się w interfejsie
bez implementacji ani działać bez jawnego ustawienia.

## 5. Etapy realizacji i bramki

### Etap 0 — kwalifikacja i bezpieczeństwo

1. Przypiąć commit/tag, SHA-256, licencję i publiczny kontrakt źródła pierwotnego.
2. Zachować Coco/Viper wyłącznie jako obserwację porównawczą.
3. Uruchomić istniejącą bramkę malware, skan sekretów, analizę statyczną oraz kontrolę
   bezpieczeństwa archiwów; nie wykonywać kodu upstream.
4. Dla każdego kandydata zapisać: wymagane credentiale, sprzężenie z debrid, typy
   treści, rate limit, stabilność, ryzyko VPN/regionu i zasady użycia.
5. Odrzucić kandydata niespełniającego granic z rozdziału 1.

**Wyjście:** osobny rekord decyzji dla każdego zakwalifikowanego providera.

### Etap 1 — fundament OCP

1. Dodać deskryptory i współdzielone adaptery protokołów.
2. Zachować kompatybilny kontrakt `mwoscrapers.sources()` dla Umbrella.
3. Dodać izolację błędu, limity i redagowaną telemetrię per provider.
4. Dodać test parytetu registry/settings/provenance.

**Wyjście:** Torrentio i Comet przechodzą dotychczasowe testy bez zmiany zachowania.

### Etap 2 — implementacja i kwalifikacja laboratoryjna fali 1

Dla każdego providera oddzielnie:

1. przygotować własne fixture poprawnych, pustych, błędnych i zbyt dużych odpowiedzi;
2. zaimplementować cienki adapter bez kodu debrid;
3. zbudować lokalny, identyfikowalny artefakt kandydata z commitem i SHA-256; nie
   tworzyć jeszcze wydania stable ani rolloutu floty;
4. zainstalować kumulatywny artefakt na BlueStacks, włączyć nowego providera i
   wykonać jego testy oraz regresję dotychczas zaakceptowanych providerów;
5. dokładnie ten sam artefakt i ustawienia zainstalować na X88 Pro i powtórzyć testy,
   w tym próbę z docelowym VPN;
6. po sukcesie na obu urządzeniach zaakceptować providera do kumulatywnego zestawu;
   po porażce poprawić i powtórzyć oba testy albo usunąć go z zestawu;
7. pozostawić zmianę logicznie niezależną od kolejnych adapterów, nawet jeżeli kilka
   takich zmian znajdzie się w jednym zbiorczym wydaniu.

BlueStacks i X88 mogą podczas tego etapu mieć nowszą wersję laboratoryjną niż reszta
floty. Sony TV, Bedroom TV i NUC nie są aktualizowane po dodaniu kolejnych providerów.
Nie publikujemy osobnego release dla każdego providera.

### Etap 3 — CI i testy bezpieczeństwa

Każdy adapter musi pokrywać:

- poprawność mapowania filmu, serialu, odcinka i packa;
- odrzucanie błędnego magnet/infohash i niedopasowanego tytułu/odcinka;
- timeout, HTTP 4xx/5xx, błędny JSON, redirect, limit odpowiedzi i SSRF;
- deduplikację oraz normalizację jakości, rozmiaru i seederów;
- awarię jednego providera bez zatrzymania pozostałych;
- brak sekretów, URL media i danych Real-Debrid w requestach, wynikach i logach;
- pracę bez QNAP relay oraz poprawny fallback z opcjonalnego relay.

Zaplanowany live probe ma zapisywać wyłącznie status, czas, liczbę wyników i zgodność
kontraktu, bez nazw magnetów i URL treści. Zmiana bajtów obserwowanego upstream nadal
ma trafiać do kwarantanny i wymagać review.

### Etap 4 — zamrożenie zestawu i pełne E2E laboratoryjne

Macierz testowa obejmuje filmy, seriale, konkretne odcinki, animację, starszy tytuł i
tytuł nieanglojęzyczny. Po zakończeniu dodawania providerów zamrozić jeden zestaw,
ustawienia i SHA artefaktu. Pełne E2E wykonać wyłącznie na:

1. BlueStacks;
2. X88 Pro.

Na X88 test wykonać także z docelowym tunelem VPN. Dla każdej próby zebrać
zredagowane wyniki per provider: dostępność, czas, liczba poprawnie dopasowanych
wyników i przyczyna odrzucenia. Kryteria sukcesu:

- każdy promowany provider dostarcza poprawnie dopasowane wyniki dla właściwej części
  macierzy i nie zwraca wyników z błędnego odcinka;
- Umbrella rozwiązuje przynajmniej jeden wynik przez skonfigurowany Real-Debrid;
- wyłączenie/odłączenie QNAP nie zmienia listy aktywnych providerów i nie blokuje
  wyszukiwania;
- awaria pojedynczego providera nie blokuje pozostałych;
- oba urządzenia używają identycznego SHA dodatku i logicznie tej samej konfiguracji;
- ponowna instalacja tego samego kandydata na obu urządzeniach jest idempotentna.

Nie przechodzimy do wydania, gdy choć jeden zaakceptowany provider nie przeszedł
pełnej regresji na obu urządzeniach. W takim przypadku provider jest poprawiany albo
usuwany z zamrożonego zestawu, a pełne E2E zaczyna się ponownie.

### Etap 5 — jedno wydanie zbiorcze i rollout pozostałej floty

1. Zwiększyć wersję modułu MwoScrapers i, jeśli wymaga tego zależność, wrappera.
2. Opublikować **jedno wydanie testing zawierające cały zamrożony zestaw** i
   potwierdzić jego instalację oraz regresję na BlueStacks i X88 Pro.
3. Promować ten sam zestaw do stable po pełnym E2E laboratoryjnym oraz co najmniej
   jednym aktualnym, udanym live probe obejmującym wszystkie włączane providery.
   Wynik nie może być starszy niż okno świeżości watchdog (`36h`). Bramka jest
   oparta na działaniu i kompletności bieżącej próby, a nie na liczbie dni
   obserwacji. Provider oparty o kruche parsowanie HTML wymaga osobnej, jawnej
   decyzji ryzyka, ale nie narzuca zwłoki całemu zestawowi.
4. Dopiero po promocji rozpocząć aktualizację pozostałych urządzeń. Wszystkie dostają
   ten sam stable lock i tę samą konfigurację providerów; nie tworzymy wydań ani
   wariantów per urządzenie.
5. Rollout pozostałej floty wykonać wspólnym orchestratorem
   `tools/kodi_ops.py rollout`. Urządzenia mogą być aktualizowane sekwencyjnie dla
   ograniczenia ryzyka, ale jest to wdrożenie jednego wydania, nie osobny release dla
   każdego urządzenia.
6. Na każdym dostępnym urządzeniu wykonać smoke: załadowanie Umbrella, obecność
   providerów, wyszukanie kontrolnego filmu i odcinka oraz rozwiązanie co najmniej
   jednego wyniku przez Real-Debrid. Pełna macierz pozostaje wykonana na BlueStacks i
   X88; smoke wykrywa różnice platformy i konfiguracji.
7. Po przejściu całej dostępnej floty powtórzyć rollout i wymagać `NO_CHANGE`.
8. Rollback polega na wyłączeniu wadliwego providera lub cofnięciu całego stable locka
   do poprzedniego zbiorczego wydania. Nie budujemy awaryjnego wariantu tylko dla
   pojedynczego urządzenia.

Urządzenie chwilowo niedostępne pozostaje na poprzednim stable i otrzymuje dokładnie
ten sam zbiorczy release przy następnym rolloucie; jego niedostępność nie powoduje
wydania kolejnej wersji.

## 6. Utrzymanie po wydaniu

- utrzymać codzienny discovery/audyt przypiętych źródeł i kwarantannę zmian treści;
- dodać dzienny health probe providerów bez przechowywania treści wyników;
- prowadzić scorecard: pokrycie, trafność, dostępność, opóźnienie i poziom duplikacji;
- automatycznie izolować provider po serii błędów, nie usuwać pozostałych wyników;
- nie rozszerzać relay na dowolny proxy; nowe ścieżki wymagają jawnej allowlisty i
  osobnego testu braku zależności od QNAP.

## 7. Szacunek i decyzja rekomendowana

- fundament OCP i testy regresji: 1–2 dni;
- kwalifikacja i implementacja fali 1: 3–5 dni;
- kumulatywne testy BlueStacks i X88: 1–2 dni;
- zbiorczy release oraz rollout pozostałej floty: 1–2 dni;
- aktualny health probe przed stable: bez dodatkowej zwłoki kalendarzowej;
- fala 2, dopiero po ocenie danych: dodatkowe 3–6 dni.

Rekomendacja: zaakceptować cel **do 6 kwalifikowanych providerów**, implementować i
kwalifikować je kolejno na BlueStacks oraz X88, ale wydać i wdrożyć na pozostałą flotę
jedną ustabilizowaną paczkę. Prywatne/self-hosted źródła pozostają opt-in. Nie kopiować
masowo wszystkich providerów Coco/Viper; większa liczba bez kwalifikacji zwiększyłaby
liczbę błędnych wyników, opóźnienia, ryzyko blokad VPN i koszt przyszłych merge.
