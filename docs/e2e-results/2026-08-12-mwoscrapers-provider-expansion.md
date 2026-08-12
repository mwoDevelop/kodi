# Kwalifikacja sześciu providerów MwoScrapers 0.2.0

Data: 2026-08-12 (Europe/Warsaw)

## Zakres

Zakwalifikowano jeden zbiorczy kandydat `script.module.mwoscrapers` 0.2.0 z
providerami Torrentio, Comet, Torz/StremThru, MediaFusion, EZTV i Pirate Bay API.
Adaptery nie otrzymują danych Real-Debrid; rozwiązanie źródła pozostaje zadaniem
Umbrella. BlueStacks i X88 Pro były jedynymi urządzeniami laboratoryjnymi zgodnie z
planem. Pozostała flota nie została zaktualizowana przed wydaniem zbiorczym.

Artefakt końcowy:

- wersja stable: `0.2.0`;
- SHA-256 ZIP: `23238732672279d5d4c0fda3869cf89a0e5be8133eed09478781f6aa18d9e73d`;
- commit komponentu: `eeef07bcf7152d205410cf2b700fda5688ba082d`;
- 26 wpisów archiwum;
- ta sama paczka zainstalowana na obu urządzeniach;
- ponowna instalacja oraz konfiguracja zakończyły się `ok=true`,
  `changed=false`, bez czyszczenia cache.

## Macierz providerów

Na obu urządzeniach uruchomiono cztery przypadki filmowe (animacja, starszy film,
tytuł nieanglojęzyczny), dwa konkretne odcinki i nieistniejący S99E99. Każdy
provider zwrócił wyniki dla deklarowanych możliwości, a przypadek negatywny zwrócił
zero. EZTV zgodnie z deskryptorem obsługuje wyłącznie odcinki.

Comet i Torz są ograniczone do 100 wyników, MediaFusion do 50, a pozostałe adaptery
do 100. Ograniczenia są częścią statycznego deskryptora i chronią Umbrella przed
niepotrzebnym przetwarzaniem tysięcy duplikatów.

## Umbrella i Real-Debrid

Na obu urządzeniach:

- Umbrella 6.7.81.20 znalazła kontrolny tytuł;
- konto Real-Debrid odpowiedziało jako aktywne premium;
- kandydat „Big Buck Bunny” został rozwiązany i odtwarzany przez co najmniej 15 s;
- czas rozwiązania końcowego artefaktu wyniósł 12,729 s na BlueStacks oraz 28,949 s
  na X88 Pro.

„Sintel” został odtworzony na BlueStacks, natomiast na X88 wyczerpał kontrolowany
limit z powodu kolejnych odpowiedzi `no_playable_url`/`infringing_file`. Drugi tytuł
potwierdził poprawne działanie tego samego resolvera i konta RD na X88; nie uznano
pojedynczego niedostępnego zestawu torrentów za awarię transportu.

## VPN i niezależność od QNAP

X88 używa docelowego tunelu VPN. Publiczny Torrentio odpowiada dla tego wyjścia HTTP
403, dlatego preferowany jest relay metadanych `192.168.1.39:18766`. Próba z
niedostępnym relay potwierdziła fallback do publicznego endpointu, a niezależny
Comet nadal zwrócił 100 wyników. Pozostałe cztery nowe źródła również używają
publicznych endpointów. Awaria QNAP może więc wyłączyć lokalną trasę Torrentio na
tym konkretnym wyjściu VPN, ale nie zatrzymuje wyszukiwania MwoScrapers jako całości.

## Regresja i automatyzacja

- MwoScrapers: `68 passed`, Ruff bez błędów, walidator dodatku widzi 6 providerów;
- repo główne po poprawkach promocji: `475 passed`;
- odtwarzalny `tests/e2e/run.sh`: dwa identyczne buildy repo i `475 passed`;
- sanitizowany live probe wszystkich providerów: healthy;
- dzienny workflow `probe-provider-health.yml` zapisuje tylko status, czas i liczbę
  wyników oraz jest objęty watchdogiem QNAP.

Niezależny review PR wykrył i zamknięto trzynaście luk przed wydaniem:

- znaki diakrytyczne są rozkładane bez pozostawiania łączących znaków Unicode,
  dzięki czemu np. `Pokémon` pasuje do nazwy wydania `Pokemon`;
- normalizacja zachowuje alfanumeryczne znaki Unicode oraz transliteruje typowe
  niedekomponujące się litery łacińskie, m.in. `Æ`, `Ł`, `Ø` i `Œ`;
- wdrożenie watchdoga wyprowadza oczekiwany, dokładny zbiór workflow z manifestu,
  zamiast używać historycznej stałej pięciu pozycji;
- sonda urządzenia wymaga dokładnie sześciu providerów i pełnych 42 unikalnych
  przypadków, więc niepełny lub zduplikowany raport nie może dać fałszywego sukcesu.
- gate wymaga dodatniego wyniku dla każdego wspieranego przypadku filmowego i
  odcinka, a nie tylko dowolnego jednego wyniku danego typu;
- produkcyjny rollout Android używa tej samej pełnej sondy sześciu providerów,
  zamiast historycznej diagnostyki ograniczonej do Torrentio i Comet;
- po zaakceptowanym wywołaniu `RunScript` host tylko czeka na raport do końca
  deadline'u i nie uruchamia równoległych kopii macierzy co 15 sekund;
- EZTV zachowuje nadrzędne dopasowanie pól `season`/`episode`, a dla niepełnych
  rekordów lub mirrorów używa ścisłego fallbacku `SxxExx` z nazwy wydania.
- EZTV sprawdza do dziesięciu stron w kolejności hierarchicznej obejmującej
  krańce i środek, zamiast systematycznie pomijać środkowy zakres wyników.
- konstrukcja kolejności stron zatrzymuje się na limicie przed rozwinięciem
  niezaufanego `torrents_count`, więc zawyżona wartość nie zużywa pamięci Kodi;
- porównanie same-origin normalizuje domyślne porty HTTP/HTTPS, zachowując
  odrzucanie rzeczywistych przekierowań między originami.
- raport urządzenia jest publikowany atomowym `os.replace`, a polling traktuje
  niepełny JSON jako stan `not ready` zamiast przerywać kwalifikację;
- builder odrzuca output ZIP wewnątrz źródeł komponentu, zapobiegając włączeniu
  poprzedniego kandydata do kolejnego artefaktu przy szerokich wzorcach plików.

## Decyzja wydaniowa

Aktualny health probe `31626132595` zakończył się sukcesem dla commita końcowego, a
certyfikacja urządzeń `31635027591` przeszła na BlueStacks i X88. Nie stosuje się już
bramki trzech kolejnych dni: jeden świeży, kompletny sukces oraz E2E obu urządzeń
laboratoryjnych wystarczają do promocji.

Snapshot `6315b949ad04a7c9f8a6ea544e6bce00304ccbb7d7895192cebe2294a9666421`
został atomowo wypromowany do stable. Publiczny smoke potwierdził 44 pliki repo oraz
ZIP 0.2.0 o powyższym SHA-256. Pełny rollout `8441b0f801cc436b9bf23f9a5725b5b9`
potwierdził na BlueStacks, X88 i Sony: `providers=pass`, działający Real-Debrid,
Rapideo, zbieżny Profile Sync, osiem favourites i brak brakujących artwork. Bedroom
TV oraz oba profile NUC były w tej próbie niedostępne i pozostają do uzgodnienia tym
samym stable przy najbliższym osiągalnym rolloucie; nie wymaga to nowego wydania.

Podczas promocji poprawiono również generyczny rollout kanałów: niezmienione dodatki
zachowują origin stable, migracja dotyczy tylko rzeczywiście zmienionych artefaktów,
a nieaktualny indeks repo Kodi jest odświeżany przed przypisaniem originu. Dwa pełne
CI poprawki przeszły przed scaleniem.

Końcowy przebieg idempotencji `514e1828b2914cbab470ab029da73c2b` zwrócił
`NO_CHANGE` na BlueStacks, X88 i Sony oraz ponownie `providers=pass`, zdrowy
Real-Debrid, działające Rapideo i `475 passed`. QNAP uzgodnił trzy zdrowe usługi bez
zmian. Jednorazowy wcześniejszy błąd transportu adaptera OpenSubtitles został
odtworzony jako poprawne `VIP_REQUIRED`; orchestrator otrzymał jeden ograniczony,
fail-closed retry tego adaptera, zweryfikowany dwoma pełnymi przebiegami CI.
