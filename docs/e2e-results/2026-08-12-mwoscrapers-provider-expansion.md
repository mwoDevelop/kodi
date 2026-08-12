# Kwalifikacja sześciu providerów MwoScrapers 0.2.0

Data: 2026-08-12 (Europe/Warsaw)

## Zakres

Zakwalifikowano jeden zbiorczy kandydat `script.module.mwoscrapers` 0.2.0 z
providerami Torrentio, Comet, Torz/StremThru, MediaFusion, EZTV i Pirate Bay API.
Adaptery nie otrzymują danych Real-Debrid; rozwiązanie źródła pozostaje zadaniem
Umbrella. BlueStacks i X88 Pro były jedynymi urządzeniami laboratoryjnymi zgodnie z
planem. Pozostała flota nie została zaktualizowana przed wydaniem zbiorczym.

Artefakt końcowy:

- SHA-256 ZIP: `35b10986237140bbd1d9525615eca1c20f06126fefe2a35703d768465462359b`;
- commit komponentu: `2c24bc35db600ae9f7a3210b178633995c2eda70`;
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
- czas rozwiązania po finalnym limicie wyniósł około 13 s na BlueStacks oraz 29 s
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

- MwoScrapers: `59 passed`, Ruff bez błędów, walidator dodatku widzi 6 providerów;
- repo główne: `455 passed`;
- odtwarzalny `tests/e2e/run.sh`: dwa identyczne buildy repo i `455 passed`;
- sanitizowany live probe wszystkich providerów: healthy;
- dzienny workflow `probe-provider-health.yml` zapisuje tylko status, czas i liczbę
  wyników oraz jest objęty watchdogiem QNAP.

## Decyzja wydaniowa

Kandydat spełnia bramkę wydania zbiorczego do kanału testing. Promocja tego samego
artefaktu do stable i rollout pozostałej floty wymagają trzech kolejnych udanych
dziennych uruchomień health probe. Nie należy omijać tej bramki ani publikować
wariantów per urządzenie.
