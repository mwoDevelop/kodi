# Kwalifikacja sześciu providerów MwoScrapers 0.2.0

Data: 2026-08-12 (Europe/Warsaw)

## Zakres

Zakwalifikowano jeden zbiorczy kandydat `script.module.mwoscrapers` 0.2.0 z
providerami Torrentio, Comet, Torz/StremThru, MediaFusion, EZTV i Pirate Bay API.
Adaptery nie otrzymują danych Real-Debrid; rozwiązanie źródła pozostaje zadaniem
Umbrella. BlueStacks i X88 Pro były jedynymi urządzeniami laboratoryjnymi zgodnie z
planem. Pozostała flota nie została zaktualizowana przed wydaniem zbiorczym.

Artefakt końcowy:

- SHA-256 ZIP: `6b50015ed1bc0f3a447c2532108f79ae15fcef5c0a05baa65fc3e9f335d7f54f`;
- commit komponentu: `a26a9dc7c002bb13cf538ce31f254c71e7a2fa59`;
- 31 plików;
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
- repo główne: `462 passed`;
- odtwarzalny `tests/e2e/run.sh`: dwa identyczne buildy repo i `462 passed`;
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

Kandydat spełnia bramkę wydania zbiorczego do kanału testing. Promocja tego samego
artefaktu do stable i rollout pozostałej floty wymagają trzech kolejnych udanych
dziennych uruchomień health probe. Nie należy omijać tej bramki ani publikować
wariantów per urządzenie.
