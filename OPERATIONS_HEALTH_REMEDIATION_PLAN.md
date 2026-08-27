# Plan przywrócenia wiarygodnego monitoringu usług i procesów cyklicznych

Status: zakres bazowy wdrożony; korekty po audycie produkcyjnym z 27 sierpnia
2026 r. zaplanowane w sekcjach 13-21

Data bazowa: 26 sierpnia 2026 r.

Ostatnia aktualizacja planu: 27 sierpnia 2026 r.

Wynik realizacji i identyfikatory dowodów znajdują się w
[`docs/e2e-results/2026-08-26-operations-health-remediation.md`](docs/e2e-results/2026-08-26-operations-health-remediation.md).

## 1. Cel

Przywrócić jednoznaczny, odporny na chwilowe problemy zewnętrzne obraz zdrowia:

- publicznych providerów MwoScrapers;
- obserwatora upstream na QNAP;
- urządzeń korzystających z Profile Sync;
- cyklicznych workflow GitHub Actions.

Zmiana ma usuwać fałszywe alarmy bez ukrywania rzeczywistych awarii. Panel musi
osobno pokazywać zdrowie procesu monitorującego, wynik obserwowanej zależności,
świeżość danych i dostępność urządzenia. Nie wolno uznawać pustego wyniku jednego
tytułu za dowód uszkodzenia adaptera ani uznawać poprawnie działającego watchdoga
za zepsuty kontener tylko dlatego, że wykrył błąd monitorowanego workflow.

## 2. Stan wyjściowy i potwierdzone luki

Punktem odniesienia jest przebieg
[`32935018048`](https://github.com/mwoDevelop/script.module.mwoscrapers/actions/runs/32935018048):

- Torrentio, Comet, MediaFusion i EZTV zwróciły wyniki;
- Torz nie zwrócił filmu testowego, ale zwrócił odcinek;
- PirateBay nie zwrócił filmu ani odcinka;
- adaptery nie zgłosiły wyjątku, a jedynie zero wyników;
- ten sam stały film i odcinek są obecnie jedynymi próbkami audytu;
- pusty wynik dowolnej próbki kończy cały workflow kodem błędu;
- Docker healthcheck watchdoga sprawdza zagregowane zdrowie workflow zamiast
  żywotności samego obserwatora;
- Profile Sync uruchamia się przy starcie Kodi i pracuje co 6 godzin, lecz po
  błędzie także czeka pełny interwał zamiast wykonać krótki retry;
- Control Plane agreguje heartbeat według najnowszego wpisu całej floty. Nie
  wylicza osobnego wyniku świeżości dla każdego aktywnego urządzenia;
- kontrola GitHub porównuje ostatni start dokładnie z najnowszym oknem cron.
  Best-effort scheduler GitHub może przekroczyć 20-minutowy `grace_seconds`, mimo
  że poprzedni przebieg zakończył się sukcesem.

## 3. Zasady projektowe

1. **Oddzielić obserwator od obserwowanego stanu.** Liveness/readiness kontenera,
   kompletność kolekcji GitHub i wynik workflow są trzema osobnymi sygnałami.
2. **Nie maskować rzeczywistych awarii.** Retry i kilka próbek redukują flapping,
   ale błąd kontraktu, brak odpowiedzi albo brak wyników dla całego zestawu nadal
   tworzą alert.
3. **Nie wyłączać automatycznie providera po jednym przebiegu.** Zmiana statusu lub
   domyślnego włączenia wymaga diagnozy kontraktu oraz E2E na BlueStacks i X88.
4. **Ograniczyć telemetrię.** Raporty mogą zawierać status HTTP jako klasę,
   zredagowany typ błędu, liczniki, czasy i histogram powodów odrzucenia. Nie mogą
   zawierać magnetów, hashy, URL-i treści, wyników wyszukiwania ani sekretów.
5. **Zachować OCP.** Próbki i polityki zdrowia trafiają do deklaratywnego katalogu,
   a wspólna sonda i bazowe transporty przyjmują opcjonalny, domyślnie wyłączony
   sink diagnostyczny. Nie dopisujemy wyjątków nazwanych `torz` lub `piratebay` do
   wspólnego algorytmu.
6. **Nie opierać zaliczenia na wielodniowym oczekiwaniu.** Kontrolowane powtórzenia
   w jednym przebiegu, testy urządzeń i ręczny cykl watchdoga są wystarczającymi
   bramami. Naturalny kolejny cykl jest obserwacją po wydaniu, nie blokadą release.
7. **Wdrażać tylko immutable artefakty.** QNAP używa digestów ze stable lock, a
   urządzenia wersji i SHA z locków kanału Kodi.
8. **Zmieniać kontrakty consumer-first.** Rozszerzenie payloadu watchdoga i
   katalogów Control Plane otrzymuje ograniczone okno zgodności N/N+1. Najpierw
   wdrażany jest tolerancyjny konsument, potem producent, a alias legacy jest
   usuwany dopiero po potwierdzonym końcowym no-op całej produkcji.
9. **Korelować dowody jednego incydentu.** Ten sam nieudany run zaobserwowany
   bezpośrednio przez Control Plane i przez watchdog ma tworzyć jeden incydent z
   dwoma źródłami, a nie dwa niezależne alarmy.

## 4. Zakres komponentów

| Repozytorium/komponent | Odpowiedzialność zmiany |
|---|---|
| `script.module.mwoscrapers` | wielopróbkowy audyt providerów, zredagowana diagnostyka i klasyfikacja wyniku |
| `service.mwodevelop.profilesync` | szybki retry po błędzie, trwały bezpieczny stan próby i sukcesu heartbeat |
| `kodi-profile-sync-server` | addytywne pola integracyjne oraz bezpieczny, transakcyjny plan/apply revocation starszych enrollmentów; bez zmiany sekretów i tokenów |
| `kodi-control-plane` | per-device heartbeat oraz tolerancja best-effort schedulera GitHub |
| `kodi` | katalogi polityk, watchdog QNAP, Compose, narzędzia deploy/status, dokumentacja i E2E |

## 5. Etap 0 — zamrożenie dowodów i testy odtwarzające błędy

1. Pobrać artefakty dwóch nieudanych oraz dwóch ostatnich udanych przebiegów
   `probe-provider-health.yml`; zapisać wyłącznie oryginalne JSON-y i ich SHA-256
   pod `.kodi-private/evidence/operations-health-20260826/`. Katalog ma mieć tryb
   `0700`, a pliki `0600`. Po utworzeniu sanitizowanych fixture surowe artefakty
   usunąć zgodnie z jawną retencją.
2. Dodać fixture odtwarzające:
   - częściowy sukces Torz: film `0`, odcinek `>0`;
   - pusty wynik PirateBay bez wyjątku;
   - wyjątek transportu, niepoprawny kontrakt i wszystkie próbki puste;
   - opóźniony, lecz udany run GitHub;
   - brak heartbeatów całej floty oraz mieszaną flotę fresh/stale/never-seen;
   - błąd pierwszej próby Profile Sync, po którym następuje sukces retry.
3. Zapisać zredagowany baseline Control Plane, `qnap_images.py status` i listę
   aktywnych urządzeń z prywatnego inventory. Nie kopiować `.env`, tokenów ani
   certyfikatów do raportu.
4. Przed zmianą schematów wykonać zgodną kopię SQLite Control Plane i zachować razem
   poprzedni obraz, stable lock oraz dokładny katalog schedules jako jeden zestaw
   rollbacku.

Brama: testy najpierw odtwarzają bieżące błędne klasyfikacje i nie wymagają dostępu
do publicznych providerów.

## 6. Etap 1 — wiarygodny audyt providerów MwoScrapers

### 6.1 Deklaratywne przypadki kontrolne

1. Zastąpić pojedynczy słownik `CASES` wersjonowanym katalogiem health-checków.
   Każda capability otrzyma co najmniej dwie różne próbki o stabilnym ID oraz
   jawne `minimum_successes`.
2. Próbkować tylko capability zadeklarowane przez provider. EZTV pozostaje
   sprawdzany wyłącznie dla odcinków.
3. Wprowadzić maksymalnie jedno ograniczone powtórzenie nieudanej próbki z krótkim
   jitterem. Łączny budżet czasu providera nie może przekroczyć budżetu workflow.
4. Walidować nie tylko liczbę, lecz również znormalizowany kontrakt wyników, nadal
   bez serializacji samych wyników.
5. Ustalić jawny globalny deadline, deadline per provider i maksymalną liczbę
   wywołań. Przekroczenie deadline musi nadal zapisać poprawny częściowy artifact
   schema 2 z reason code `PROBE_DEADLINE_EXCEEDED`; 10-minutowy timeout workflow
   pozostaje bezwzględną granicą.

### 6.2 Klasyfikacja i diagnostyka

Raport schema 2 ma rozdzielać:

- `PASS` — wymagane minimum próbek zwróciło poprawne wyniki;
- `PARTIAL` — co najmniej jedna próbka działa, ale nie wszystkie;
- `EMPTY` — wszystkie próbki danej capability zwróciły zero;
- `TRANSPORT_ERROR` — limit czasu, DNS, TLS lub HTTP bez ujawniania endpointu;
- `CONTRACT_ERROR` — odpowiedź istnieje, lecz nie spełnia kontraktu;
- `FILTERED_EMPTY` — transport zwrócił rekordy, ale wszystkie zostały bezpiecznie
  odrzucone podczas normalizacji.

Opcjonalny sink w bazowych klasach transportowych zbiera tylko liczbę endpointów,
rekordów wejściowych, znormalizowanych i odrzuconych oraz histogram stałych kodów
odrzucenia. W zwykłym Kodi sink pozostaje `None`, więc nie zmienia działania ani
wydajności providerów.

Agregacja jest deterministyczna:

| Poziom | Reguła |
|---|---|
| próbka | dokładnie jeden wynik: `PASS`, `EMPTY`, `TRANSPORT_ERROR`, `CONTRACT_ERROR`, `FILTERED_EMPTY` albo `DEADLINE_EXCEEDED` |
| capability | `CONTRACT_ERROR` i deadline są fail-closed; po osiągnięciu quorum pojedynczy `EMPTY`/`TRANSPORT_ERROR` daje `PARTIAL`; bez quorum obowiązuje najważniejszy reason code |
| provider | przechodzi tylko wtedy, gdy każda wymagana capability osiągnęła quorum; reason priority: contract/deadline, transport, filtered-empty, empty, partial, pass |
| workflow | oblewają go niezdrowi providerzy `qualified` włączeni domyślnie; provider `testing` jest raportowany i ostrzega, ale nie blokuje stable |

### 6.3 Polityka wyniku workflow

1. `PASS` wszystkich wymaganych capability kończy workflow sukcesem.
2. `PARTIAL` publikuje warning w Job Summary, ale nie oblewa workflow, jeżeli
   provider osiąga `minimum_successes` dla każdej deklarowanej capability.
3. `EMPTY`, `TRANSPORT_ERROR`, `CONTRACT_ERROR` albo `FILTERED_EMPTY` całej
   capability oblewa workflow i wymienia dokładny zredagowany reason code.
4. Po wdrożeniu sondy wykonać ręczny przebieg. Jeżeli Torz lub PirateBay nadal ma
   pełne `EMPTY`, osobno sprawdzić aktualny kontrakt upstream:
   - naprawić adapter i testy, jeśli kontrakt się zmienił;
   - w przeciwnym razie zachować provider w kodzie, ale przenieść go do `testing`
     albo wyłączyć domyślnie w następnym wydaniu. Nie traktować tego jako awarii
     Real-Debrid ani QNAP.

Brama: dwie deterministyczne serie fixture dają identyczny wynik. Dwa live probe
muszą zmieścić się w budżecie i spełnić quorum, ale nie muszą mieć identycznych
liczników ani identycznego `PASS`/`PARTIAL`; raport nie zawiera danych treści.

## 7. Etap 2 — rozdzielenie zdrowia watchdoga od wykrytych awarii

### 7.1 Docelowa semantyka

Raport ma rozdzielać:

- liveness procesu — proces watchdoga działa;
- `collection_state=READY|PARTIAL|ERROR` — kompletność i świeżość kolekcji GitHub;
- `monitored_state=HEALTHY|FAILED|UNKNOWN` — potwierdzony wynik obserwowanych
  workflow;
- `observer_ready` — raport ma poprawną strukturę, pełny oczekiwany katalog,
  świeży `checked_at` i kolekcję `READY`.

`api_error` nie może oznaczać `FAILED` dla workflow: wynik jest wtedy `UNKNOWN`, a
awaria dotyczy kolekcji. Czas przyszły przekraczający jawny limit clock skew jest
równie niepoprawny jak raport stary.

### 7.2 Migracja N/N+1

1. W okresie przejściowym zachować `schema: 2` i stare `healthy` jako alias
   `monitored_state == HEALTHY`. Addytywnie dodać nowe pola. Dzięki temu starszy
   konsument może najwyżej zachować dotychczasowy konserwatywny alarm, lecz nie
   ukryje awarii workflow.
2. Najpierw wydać Control Plane tolerujący stary payload oraz rozszerzone schema 2.
   Dopiero po jego wdrożeniu wydać watchdog i zmieniony Compose healthcheck.
3. `qnap_images.py status` ma prezentować nowe pola. `runtime_healthy` zachować jako
   oznaczony alias przez dokładnie jedną stabilną generację N+1; usunąć go dopiero,
   gdy wszystkie produkcyjne konsumenty i dokumentacja używają nowych nazw.
4. Kryterium zamknięcia okna: Control Plane, CLI, Compose i live QNAP przeszły E2E
   zarówno ze starym fixture, jak i nowym payloadem oraz końcowy stable no-op.

### 7.3 Healthcheck, alerty i korelacja

1. Docker healthcheck ma sprawdzać liveness, `observer_ready`, schema, kompletność
   oczekiwanego zestawu, świeżość i clock skew. Nie może wymagać
   `monitored_state=HEALTHY`.
2. Control Plane wystawia `WATCHDOG_REPORTED_FAILURE`, gdy kolekcja jest `READY`, a
   `monitored_state=FAILED`. Dla `PARTIAL|ERROR`, starego raportu i clock skew używa
   osobnych reason codes kolekcji, a zdrowie workflow pozostaje `UNKNOWN`.
3. Alert bezpośredniego collectora GitHub i dowód watchdoga korelować po
   `(repository, workflow, scheduled_run_id)`. Świeży collector jest źródłem
   głównym, a watchdog dodatkowym dowodem. Gdy collector jest stary lub
   niedostępny, watchdog staje się źródłem głównym. Osobny alert pozostaje tylko
   dla błędu samego watchdoga/kolekcji.
4. W API/UI incydent zawiera listę `evidence_sources`, ale nie jest liczony dwa
   razy w stanie ogólnym.
5. Zaktualizować testy payloadu, Control Plane, CLI i Compose: stary schema 2,
   rozszerzony schema 2, zdrowy obserwator + czerwony workflow, częściowo
   niedostępne API, pełny błąd API, stary/przyszły raport, uszkodzony JSON, pusty i
   niekompletny katalog oraz korelacja dwóch źródeł tego samego runu.

Brama: przy kontrolowanym nieudanym workflow kontener jest `healthy`, źródło usługi
watchdoga jest `OK`, a panel pokazuje jeden krytyczny incydent monitorowanego
workflow z dwoma źródłami dowodu.

## 8. Etap 3 — przywrócenie i utwardzenie heartbeatów Profile Sync

### 8.1 Diagnostyka floty przed zmianą

Dla każdego ID z `KODI_SYNC_DEVICES` sprawdzić bez modyfikacji:

- osiągalność właściwym transportem i tożsamość urządzenia;
- czy Kodi działa oraz czy `service.mwodevelop.profilesync` jest zainstalowany,
  włączony i uruchomiony;
- wersję dodatku, `server_url`, CA, interwał, tryb sekretów i aktywną generację
  enrollmentu, bez wyświetlania tokenu;
- lokalne `last_check_utc`, zredagowany typ ostatniego błędu oraz log usługi;
- czas systemowy, DNS/TLS i odpowiedź endpointu Profile Sync;
- serwerowe `last_seen_at` najwyższej generacji niezależnie od `revoked`; świeży
  heartbeat starszej generacji nie może maskować stanu najwyższej.

Urządzenie wyłączone jest `DEFERRED`, a nie naprawiane przez ponowny enrollment.
Re-enrollment jest dopuszczalny dopiero po potwierdzeniu uszkodzonego lub odwołanego
tokenu.

Prywatne inventory pozostaje źródłem oczekiwanego członkostwa floty. Podczas
wdrożenia należy wygenerować i zamontować read-only w Control Plane zredagowany
katalog monitoringu zawierający wyłącznie logiczne ID, oczekiwany kanał,
`monitoring_mode=always_on|on_demand|maintenance|retired` oraz progi. Nie wolno
przenosić do niego adresów, loginów, kluczy ani tokenów z `.env`.

### 8.2 Retry i obserwowalność dodatku

1. Zachować synchronizację przy starcie i interwał sukcesu 6 godzin.
2. Zdefiniować stałe bezpieczne klasy wyników:
   - retryable: transport, DNS, timeout TLS, HTTP `429` i `5xx`;
   - terminal wymagający interwencji lub zmiany konfiguracji: `401/403`, revoked
     enrollment, błędne URL/CA, niepoprawny kontrakt albo podpis;
   - normalny wynik bez błędu: `UNPAIRED`, `IDLE`, `NO_CHANGE` i poprawny apply.
3. Tylko po błędzie retryable zastosować bounded exponential backoff z jitterem:
   około 1, 5 i 15 minut, następnie maksymalnie 30 minut do pierwszego sukcesu.
   Błąd terminalny nie może generować okresowego ruchu co 30 minut.
4. Zapisać w publicznej, bezpiecznej części stanu:
   `last_attempt_utc`, `last_heartbeat_success_utc`, `last_cycle_success_utc`,
   `consecutive_failures`, `last_error_code` i `next_retry_utc`. Nie zapisywać
   komunikatu wyjątku, URL-a, certyfikatu ani tokenu.
5. `last_heartbeat_success_utc` oznacza przyjęcie heartbeat przez serwer;
   `last_cycle_success_utc` oznacza poprawne zakończenie całego cyklu wraz z
   assignmentem/apply/report. Wynik normalny bez assignmentu także kończy cykl.
6. Trwały `next_retry_utc` po restarcie musi tolerować cofnięcie lub skok zegara:
   przeterminowany termin daje jedną natychmiastową próbę, a czas zbyt daleko w
   przyszłości jest przeliczany z ograniczonego backoffu monotonicznego.
7. `sync-now` może ominąć oczekiwanie retryable, ale nie może omijać terminalnej
   blokady bez zmiany konfiguracji/enrollmentu ani tworzyć busy-loop.
8. Resetować backoff po sukcesie i dodać testy startu, klasy błędów, retry, manual
   sync, restartu, clock skew, suspend/resume, wyłączenia usługi oraz poprawnego
   przerwania przy zamykaniu Kodi.

### 8.3 Per-device wynik w Control Plane

1. Dla każdego logicznego ID najwyższa generacja jest autorytatywna niezależnie od
   `revoked`. Jeśli najwyższa generacja jest odwołana, wynik to `REVOKED`; starsza
   świeża i nieodwołana generacja nie może jej maskować ani zostać reaktywowana.
2. Wiele nieodwołanych generacji tworzy osobne ostrzeżenie bezpieczeństwa. Ten plan
   nie wykonuje automatycznego revocation.
3. Połączyć zredagowane expected inventory z rekordami backendu i udostępniać:
   logiczne ID, monitoring mode, oczekiwany kanał, najwyższą generację, wersję
   klienta, platformę, `last_seen_at`, wiek i stan `FRESH`, `STALE`, `NEVER_SEEN`,
   `UNENROLLED`, `MAINTENANCE`, `RETIRED` albo `REVOKED`.
4. Zachować podsumowanie floty, ale nie wyznaczać jego zdrowia przez maksimum
   `last_seen_at`. Docelowe liczniki `fresh_devices`, `stale_devices`,
   `maintenance` i `missing` wynikają wyłącznie z per-device rows oraz expected
   inventory. Legacy `online` może przez N/N+1 pozostać aliasem `fresh_devices`,
   lecz UI i dokumentacja nie mogą przedstawiać go jako dowodu osiągalności.
5. Dla `always_on` stosować jawne progi warning/failure z prywatnego katalogu. Dla
   `on_demand` wiek heartbeat jest informacją i nie degraduje systemu, chyba że
   istnieje niezakończony rollout/assignment lub czasowa deklaracja oczekiwanej
   dostępności. `maintenance` tłumi alert do jawnego terminu, a `retired` nie jest
   aktywnym celem.
6. Dodać reason codes m.in. `AGENT_STALE`, `AGENT_NEVER_SEEN`, `DEVICE_UNENROLLED`,
   `LATEST_ENROLLMENT_REVOKED`, `MULTIPLE_ACTIVE_GENERATIONS` i
   `FLEET_PARTIALLY_STALE`. Urządzenia nie mogą wzajemnie maskować swoich stanów.
7. Rozszerzyć GUI o tabelę per-device: logiczne ID, monitoring mode, stan, ostatni
   heartbeat, wiek i wersję klienta. Browser E2E ma potwierdzić brak enrollment ID,
   endpointów i tokenów w DOM oraz odpowiedziach BFF.
8. Przetestować: brakujące urządzenie inventory, never-seen, on-demand wyłączone,
   always-on stale, maintenance z terminem, retired, najwyższą revoked generację
   przy świeżej starszej oraz wiele aktywnych generacji.

Brama: po uruchomieniu `sync-now` każde dostępne urządzenie ma świeży, poprawnie
uwierzytelniony heartbeat, a symulowana flota mieszana daje prawidłowe liczniki i
osobne statusy.

## 9. Etap 4 — tolerancja best-effort GitHub Actions bez utraty alarmu

1. Nie zwiększać wyłącznie globalnego `grace_seconds` i nie wprowadzać drugiego,
   konkurencyjnego limitu czasu. Do każdego joba w katalogu dodać jedną politykę
   `missed_windows_warning` i `missed_windows_failure`, dobraną osobno dla zadań
   częstych i dziennych.
2. Okna wyliczać z kompletnej listy wyrażeń cron danego joba, również dla
   nieregularnych odstępów i dwóch wyrażeń tego samego dnia.
3. Wyliczać i prezentować niezależnie:
   - opóźnienie ostatniego startu względem właściwego okna cron;
   - liczbę miniętych okien;
   - wynik ostatniego scheduled run;
   - wynik nowszego ręcznego remediation run, bez udawania, że zastąpił scheduler.
4. Zwracać osobne `scheduler_condition`, `run_condition` i
   `freshness_condition` oraz listę `reason_codes`. Ustalić priorytet prezentacji,
   ale nie gubić np. jednoczesnego `LAST_RUN_FAILED` i zatrzymania kolejnych okien.
5. `EXPECTED_RUN_NOT_STARTED` zgłaszać dopiero przy progu failure. Próg warning ma
   dawać `SCHEDULE_DELAYED`, a pojedyncze zwykłe opóźnienie poniżej tego progu
   pozostaje informacją.
6. Nie łagodzić `LAST_RUN_FAILED`, `RUNNING_TOO_LONG`, `LAST_RUN_STALE` ani braku
   jakiegokolwiek scheduled run. Ręczny run zmienia wyłącznie stan remediation,
   nigdy `scheduler_condition`.
7. Dodać testy graniczne przed i po obu progach, opóźnionych runów, pominiętych
   okien, kilku wyrażeń cron, jobów dziennych, manualnego remediation, jednoczesnych
   przyczyn i zmian czasu UTC.
8. Dla `approve-umbrella-promotion.yml` dobrać progi z empirycznego rozkładu
   ostatnich co najmniej 30 scheduled runów, a nie z pojedynczego incydentu. Progi
   muszą obejmować cykl odświeżenia Control Plane, ale nie mogą zamienić freshness
   w wielogodzinne ślepe okno.

Brama: zarejestrowane opóźnienie z 26 sierpnia nie tworzy krytycznego fałszywego
alarmu, ale fixture z faktycznie zatrzymanym schedulerem nadal go tworzy.

## 10. Etap 5 — integracja, E2E, wydanie i rollout

### 10.1 Testy lokalne i CI

1. Uruchomić pełne testy `script.module.mwoscrapers`, dodatku Profile Sync,
   `kodi-profile-sync-server` i `kodi-control-plane`.
2. W głównym repo uruchomić pełny `pytest`, `tests/e2e/run.sh`, testy polityk
   Compose, katalogów Control Plane i dokumentacji.
3. Uruchomić kontenerowy E2E watchdoga z zasymulowanym zielonym i czerwonym
   workflow oraz wymusić natychmiastowy check bez oczekiwania 6 godzin.
4. Uruchomić ręcznie provider probe i pobrać jego schema-2 artifact.
5. Awarię sieci Profile Sync testować przez kontrolowany fault injection/testowy
   endpoint. Nie zmieniać NordVPN, routingu całego urządzenia ani produkcyjnego CA.

### 10.2 Kolejność wdrożenia

1. Scalić i opublikować zmiany MwoScrapers; nową wersję dodatku wydać tylko wtedy,
   gdy zmienia się instalowany kod adapterów lub runtime. Sama sonda CI nie wymaga
   wydania ZIP-a Kodi.
2. Scalić kompatybilnego konsumenta `kodi-control-plane`, zbudować jego
   wieloarchitekturowy obraz i przeprowadzić osobną promocję consumer-first:
   approval zmienionego obrazu, re-use approval niezmienionych usług,
   `qnap_candidate.py`, immutable candidate asset i standardowy PR aktualizujący
   jedyny `manifests/locks/qnap-stable.json`. Nie edytować locka ręcznie.
3. Wdrożyć consumer-first stable przez `tools/qnap_images.py` i potwierdzić, że
   odczytuje obecny payload watchdoga bez regresji.
4. Następnie scalić główne repo z producentem watchdoga, Compose, katalogami i CLI;
   ponownie wykonać build tylko zmienionych obrazów, approval/re-use, utworzenie
   kandydata, normalną promocję stable i deploy z pojedynczego QNAP stable locka.
5. Jeżeli zmienił się Profile Sync, wydać jeden kandydat dodatku i sprawdzić go
   najpierw na BlueStacks, potem na X88. Dopiero po obu sukcesach wykonać pełny
   rollout na pozostałe dostępne urządzenia przez `tools/kodi_ops.py rollout`.
6. Niedostępne urządzenia oznaczyć `DEFERRED`; nie obniżać dla nich wersji i nie
   tworzyć nowego enrollmentu w ciemno.
7. Powtórzyć rollout i wymagać `NO_CHANGE` dla każdego osiągalnego celu oraz dry-run
   `IN_SYNC` względem zatwierdzonego stable locka QNAP.

### 10.3 Końcowe E2E

- providerzy: wielopróbkowy probe oraz wyszukiwanie Umbrella/MwoScrapers na
  BlueStacks i X88 dla filmu i odcinka;
- Profile Sync: restart Kodi, startup heartbeat, wymuszony błąd sieci, szybki retry,
  sukces, synchronizacja oraz powtórny no-op;
- QNAP: wszystkie kontenery uruchomione, obserwator watchdog `healthy`, zgodność
  digestów ze stable lock;
- Control Plane: źródła świeże, per-device rows zgodne z backendem, alert providera
  nie jest błędnie przedstawiany jako awaria kontenera, a GUI przechodzi browser
  E2E i nie ujawnia prywatnych identyfikatorów enrollmentu;
- GitHub: ręczny i scheduled run są rozróżnione, a test zatrzymanego schedulera
  nadal generuje alert;
- dokumentacja: przykłady w `docs/scheduled-processes.md`,
  `docs/profile-sync-implementation.md`, `docs/control-plane/README.md` oraz wynik
  wdrożenia w `docs/e2e-results/`.

## 11. Rollback

- QNAP: przywrócić poprzednie immutable digesty z historii stable lock i wdrożyć
  wyłącznie zmienione usługi;
- Kodi: zachować poprzedni ZIP i lock Profile Sync/MwoScrapers; downgrade wymaga
  testu zgodności stanu lokalnego;
- Control Plane: zmiany API mają być addytywne i nie wymagają migracji niszczącej
  bazę. Przywracać atomowo zgodny zestaw: kopia SQLite, obraz Control Plane,
  watchdog oraz dokładny katalog schedules; nie łączyć starego parsera z nowym
  obowiązkowym polem katalogu;
- providerzy: cofnięcie statusu lub domyślnego włączenia nie usuwa konfiguracji
  użytkownika;
- harmonogramy: zachować poprzedni katalog, aby można było odtworzyć progi bez
  przebudowy obrazów aplikacyjnych.

## 12. Kryteria ukończenia

Plan jest ukończony dopiero, gdy jednocześnie:

1. probe providerów nie flappuje przez pojedynczy pusty tytuł, ale nadal oblewa
   pełną niedostępność capability lub uszkodzony kontrakt;
2. przy obecnej awarii providera watchdog pozostaje zdrowym kontenerem i przekazuje
   dokładny alert zależności;
3. każde dostępne urządzenie z inventory wysyła świeży heartbeat, a panel pokazuje
   status per urządzenie zamiast maksimum całej floty; urządzenie on-demand nie
   generuje trwałego alarmu tylko dlatego, że jest wyłączone;
4. Profile Sync ponawia retryable błąd startowy w minutach, nie po 6 godzinach, a
   błąd terminalny pozostaje zatrzymany do interwencji;
5. zwykłe opóźnienie GitHub nie daje `EXPECTED_RUN_NOT_STARTED`, lecz zatrzymany
   scheduler nadal jest wykrywany;
6. CI wszystkich zmienionych repozytoriów, pełne stare i nowe E2E, dostępne
   urządzenia oraz QNAP kończą się sukcesem; niedostępny transport urządzenia lub
   jawne wstrzymanie przez operatora daje udokumentowane `DEFERRED`, nie pozorny
   sukces;
7. ten sam nieudany run tworzy jeden incydent z bezpośrednim i watchdogowym źródłem
   dowodu, a błąd kolekcji daje `UNKNOWN` zamiast fałszywego `FAILED` workflow;
8. wszystkie commity są wypchnięte, PR-y scalone, wymagane wersje i obrazy wydane,
   a dokumentacja oraz datowany raport E2E odpowiadają stanowi produkcyjnemu.

## 13. Audyt produkcyjny z 27 sierpnia 2026 r.

Zakres bazowy planu został wdrożony, ale ponowna kontrola działającego panelu
ujawniła cztery luki wymagające osobnej korekty. Są to problemy obserwowalności i
klasyfikacji, a nie dowód awarii kontenerów Control Plane.

### 13.1 Potwierdzone fakty

1. Panel po odświeżeniu raportował `DEGRADED` i 13 otwartych alertów.
2. Jedenaście wpisów GitHub Actions odpowiadało rzeczywiście nieuruchomionym
   oknom cron:
   - osiem dziennych workflow nie otrzymało przebiegu z 27 sierpnia;
   - trzy częste workflow zatwierdzania przestały otrzymywać kolejne scheduled
     runs;
   - wszystkie workflow pozostawały `active` w GitHub API;
   - publiczny status GitHub nie zgłaszał awarii Actions.
3. `qnap-upstream-watchdog` działał jako zdrowy kontener i poprawnie propagował
   zatrzymanie trzech workflow. Osobny alert watchdoga dublował jednak te same
   przyczyny widoczne bezpośrednio w collectorze GitHub.
4. Źródło `github-schedules` przechodziło w `DEGRADED` z
   `GITHUB_TRANSPORT_ERROR`. Sonda wykonana wewnątrz produkcyjnego kontenera
   odtworzyła losowe `TimeoutError: The read operation timed out` dla części
   zapytań GitHub API.
5. Collector wykonuje do dwóch żądań dla każdego workflow i traktuje cały zestaw
   atomowo. Jeden timeout odrzuca kompletny nowy snapshot jedenastu zadań, mimo że
   pozostałe odpowiedzi były poprawne.
6. Cztery urządzenia `on_demand` miały stare heartbeat-y, lecz zgodnie z polityką
   ich indywidualna severity wynosiła `none`. Alert
   `FLEET_PARTIALLY_STALE` powstał faktycznie przez
   `MULTIPLE_ACTIVE_GENERATIONS` dla świeżych BlueStacks i X88. Backend błędnie
   zamienił dowolne ostrzeżenie floty na informację o nieświeżych urządzeniach.
7. W przeglądarce panel działał bez wyjątków JavaScript i nieudanych wywołań API.
   Jedynym błędem zasobu był kosmetyczny `404` dla `/favicon.ico`.
8. Certyfikat HTTPS QTS był wygasły. Jest to stan hosta QNAP, a nie błąd aplikacji
   Control Plane; plan nie może uzależniać dostępu LAN od instalacji prywatnego CA
   na każdym urządzeniu.

### 13.2 Decyzje

- Nie łagodzić alarmów zatrzymanego schedulera tylko dlatego, że ostatni run albo
  ręczny remediation run zakończył się sukcesem.
- Nie przedstawiać błędu transportu collectora jako błędu workflow.
- Nie przedstawiać ostrzeżenia enrollmentu jako starego heartbeat-u.
- Nie liczyć watchdoga i bezpośredniego collectora jako dwóch incydentów tej samej
  awarii.
- Nie wykonywać automatycznego revocation tokenów ani automatycznego dispatchu
  workflow na podstawie samego alertu.
- Zachować read-only charakter bieżącego dashboardu. Ewentualne akcje
  administracyjne muszą korzystać z istniejącego, audytowalnego mechanizmu z
  osobną autoryzacją i potwierdzeniem operatora.

## 14. Etap 6 — prawidłowa klasyfikacja floty i enrollmentów

### 14.1 Rozdzielenie osi stanu

W `kodi-control-plane` wynik urządzenia i floty należy rozdzielić na niezależne
osie oraz jawną politykę:

- `heartbeat_condition`: `FRESH`, `STALE`, `NEVER_SEEN`, `NOT_EXPECTED`;
- `monitoring_mode`: `ALWAYS_ON`, `ON_DEMAND`, `MAINTENANCE`, `RETIRED` — polityka
  z expected inventory, nie obserwacja sieci;
- opcjonalne `reachability_condition`: `REACHABLE`, `UNREACHABLE`, `UNKNOWN` —
  wyłącznie z niezależnego, uwierzytelnionego collectora o jawnym TTL i
  provenance; bez takiego źródła zawsze `UNKNOWN`;
- `enrollment_condition`: `OK`, `MULTIPLE_ACTIVE_GENERATIONS`,
  `LATEST_REVOKED`, `UNENROLLED`;
- `configuration_condition`: `OK`, `CHANNEL_MISMATCH`, `UNKNOWN`.

Nie wolno wyprowadzać `REACHABLE` ani `UNREACHABLE` z wieku heartbeat-u. Bieżąca
korekta nie wymaga nowego collectora osiągalności; pole pozostaje opcjonalne i
`UNKNOWN`, a dashboard nie może nazywać świeżego heartbeat-u stanem „online”.
Jeżeli rollout ma czasowo wymagać dostępności celu `on_demand`, orkiestrator tworzy
prywatne `availability_expectation` zawierające wyłącznie `operation_id`, logiczne
ID, `expected_until` i tożsamość audytową operatora. Oczekiwanie wygasa
automatycznie, Control Plane tylko je odczytuje, a brak aktywnego oczekiwania jest
równoważny `NONE`.

Stan ogólny floty ma wynikać z severity poszczególnych osi, a nie z samego faktu,
że lista `warnings` jest niepusta. W szczególności:

1. Stary heartbeat urządzenia `on_demand` pozostaje informacją i nie otwiera
   incydentu bez aktywnego rollout-u albo niewygasłego
   `availability_expectation`.
2. `MULTIPLE_ACTIVE_GENERATIONS` tworzy osobny alert bezpieczeństwa enrollmentu z
   logicznym ID urządzenia; nie zmienia `freshness_condition` na `STALE`.
3. `FLEET_PARTIALLY_STALE` może powstać wyłącznie wtedy, gdy co najmniej jedno
   urządzenie ma alarmową severity z osi heartbeat/availability.
4. Liczniki `online`, `stale_or_offline` i `fresh` pozostają opisem faktów, ale nie
   są samodzielnie severity.
5. API zachowuje przez jedno wydanie istniejące pola `state`, `severity` i
   `reason_codes` jako addytywne aliasy. Ich mapowanie na nowe osie definiuje
   wersjonowana macierz severity, aby starszy frontend nie przestał działać
   podczas wdrożenia consumer-first.

### 14.2 Kontrolowane uporządkowanie enrollmentów

1. Z Profile Sync pobrać identyfikatory logiczne, numery generacji, revocation i
   czas ostatniego użycia. Dokładny `enrollment_id` może istnieć tylko wewnątrz
   uprzywilejowanego procesu plan/apply i pliku `0600`; nie trafia do GUI,
   publicznego raportu ani logu. Nigdy nie eksportować tokenów.
2. Dla BlueStacks i X88 potwierdzić, że najwyższa generacja wysyła poprawny
   heartbeat i przechodzi `sync-now`.
3. Dodać host-only polecenie plan/apply, które tworzy content-addressed plan z
   logicznym ID, oczekiwaną najwyższą generacją, progiem świeżości, skrótem
   oczekiwanego aktywnego zbioru i dokładnymi starszymi generacjami docelowymi.
4. Dry-run zapisuje plan prywatnie i wyświetla wyłącznie zredagowane generacje oraz
   hash planu. Apply w jednej transakcji ponownie sprawdza CAS: najwyższa generacja
   nadal istnieje, jest nieodwołana i świeża, aktywny zbiór nie zmienił się, a
   wszystkie cele są od niej starsze. Niespełniony warunek kończy operację bez
   częściowego revocation.
5. Dopiero po sukcesie dry-run, ręcznym zatwierdzeniu hasha planu i potwierdzeniu
   najnowszej generacji jawnie zastosować revocation starszych generacji.
6. Powtórzyć heartbeat, synchronizację i dashboard. Operacja nie może zmieniać
   assignmentu, kanału ani sekretów bieżącej generacji.
7. Rozszerzyć najpierw backend i jego audit log, ponieważ obecne
   `revoke enrollment_id` jest bezwarunkowe i nie zapewnia CAS. Nie manipulować
   bezpośrednio bazą produkcyjną i nie wykonywać pętli pojedynczych revoke jako
   substytutu transakcyjnego apply.

Brama: BlueStacks i X88 mają po jednej aktywnej generacji, pozostają `FRESH`, a
panel nie pokazuje `FLEET_PARTIALLY_STALE`, gdy jedynymi starymi urządzeniami są
wyłączone cele `on_demand`.

## 15. Etap 7 — odporny i częściowy collector GitHub

### 15.1 Izolacja błędów, zapis i schema

Wybrany zostaje prostszy wariant bez nowej tabeli bazy: failure isolation per job,
merge z ostatnim snapshotem i jeden atomowy zapis całego źródła. Fizyczną
jednostką atomowości nadal jest `github-schedules`; pojedynczy job jest jednostką
zbierania i fallbacku.

1. Collector zwraca wynik albo zredagowany błąd oddzielnie dla każdego joba oraz
   oddzielnie dla jego odczytu scheduled i manual remediation.
2. Warstwa serwisu scala nowe wyniki z ostatnim poprawnym `jobs[]` w pamięci, a
   następnie zapisuje jeden kompletny snapshot w istniejącym rekordzie źródła.
   Nie jest wymagana migracja schematu SQLite.
3. Przez okres N/N+1 zachować top-level `schema: 1`, `jobs[]`,
   `latest_scheduled_run` i `latest_effective_run`. Payload rozszerzyć addytywnie
   o:
   - `collection_state=READY|PARTIAL|ERROR`;
   - `collected_jobs`, `failed_jobs`, `total_jobs`;
   - per-job `scheduled_observation_state=FRESH|LAST_SUCCESS|UNAVAILABLE` oraz
     `remediation_observation_state=FRESH|LAST_SUCCESS|UNAVAILABLE`;
   - osobne per-observation `last_attempt_at`, `last_success_at`, `error_code` i
     wiek dowodu.
4. Nie utrwalać komunikatu wyjątku, adresu z parametrami, nagłówków ani tokenu.
   Dozwolone są stałe kody: `TIMEOUT`, `DNS`, `TLS`, `HTTP_5XX`, `RATE_LIMITED`,
   `HTTP_4XX`, `INVALID_RESPONSE`.
5. Poprawnie zebrany scheduled run pozostaje świeżym dowodem schedulera mimo
   timeoutu odczytu manualnego. Fallback manualny nigdy nie wpływa na wynik ani
   świeżość scheduled runu.
6. Dla błędnej obserwacji można zachować jej ostatni sukces z jawnym
   `LAST_SUCCESS`; nie wolno przedstawiać go jako świeżego.
7. `PARTIAL` oznacza działający collector z niekompletną próbą, natomiast `ERROR`
   jest zarezerwowane dla braku jakiegokolwiek użytecznego wyniku albo błędu
   kontraktu całego źródła.
8. Release A dodaje tolerant reader oraz nowy writer wyłączony flagą
   `github_schedule_partial_collection_enabled=false`. Po live E2E starego
   formatu release B albo jawna, zreviewowana zmiana konfiguracji włącza writer.
   Addytywne schema 1 pozwala staremu obrazowi po rollbacku nadal odczytać pola
   legacy.

### 15.2 Retry, limity i połączenia

1. Dodać maksymalnie dwa ograniczone retry tylko dla timeout/DNS/TLS/HTTP `5xx` i
   secondary rate limit, z exponential backoff i jitterem.
2. Honorować `Retry-After` oraz nagłówki limitu GitHub. Primary rate limit nie może
   być obchodzony retry-loopem. Po secondary rate limit nie uruchamiać nowych
   żądań; zatrzymać aktywną równoległość i czekać tylko do globalnego deadline.
3. Ograniczyć równoległość do małej stałej, początkowo `3`, aby skrócić kolekcję
   bez przeciążania QNAP lub GitHub API.
4. Zdefiniować deadline per request, per job i dla całego cyklu. Cały cykl musi
   kończyć się wyraźnie przed kolejnym 15-minutowym odświeżeniem.
5. Rozważyć jedno zapytanie listujące runy repozytorium i lokalne grupowanie, jeśli
   zachowuje rozróżnienie scheduled/manual oraz zmniejsza liczbę połączeń. Decyzję
   oprzeć na teście kontraktu i liczbie żądań, nie na założeniu.
6. Dodać bezpieczne metryki: liczba prób, retry, timeoutów, czas kolekcji i liczba
   wyników z fallbacku. Nie logować URL-i ani odpowiedzi API.

### 15.3 Semantyka alarmów

- Niekompletna obserwacja tworzy alert collectora `GITHUB_COLLECTION_PARTIAL`, ale
  nie zmienia poprzedniego wyniku workflow na `FAILED`.
- Brak oczekiwanego scheduled runu pozostaje `SCHEDULE_DELAYED` lub
  `EXPECTED_RUN_NOT_STARTED`, jeżeli świeży albo jawnie oznaczony ostatni dowód
  nadal przekracza próg missed windows.
- Jeśli dowód jest zbyt stary, stan schedulera przechodzi w `UNKNOWN`, a nie w
  pozorny sukces ani porażkę workflow.
- Ręczny run pozostaje remediation evidence i nie zastępuje scheduled runu.

Brama: pierwszy timeout zakończony udanym retry daje `READY`, `retry_count=1` i
brak alertu kolekcji. Jeden job, którego wszystkie dopuszczone próby kończą się
timeoutem, daje `PARTIAL`; dziesięć pozostałych jobów aktualizuje dane, a
zatrzymany scheduler nadal jest widoczny niezależnie od stanu transportu.

## 16. Etap 8 — korelacja i licznik incydentów

W tym etapie incydenty pozostają deterministycznym, bieżącym widokiem wyliczanym
stateless. Plan nie obiecuje trwałego lifecycle, `first_seen_at`, `last_seen_at`
ani historii `RESOLVED/REOPEN`; taki store wymagałby osobnego projektu migracji
bazy.

1. Wprowadzić stabilny kanoniczny klucz bieżącego incydentu dla workflow:
   `(repository, workflow, condition_family)`. `outage_started_window`,
   `latest_missed_window` i `scheduled_run_id` są dowodami, nie częścią klucza.
   Kolejne pominięte okna aktualizują dowód bez mnożenia alertów.
2. Alert bezpośredniego collectora i `qnap-upstream-watchdog` łączyć w jeden
   incydent z `evidence_sources` oraz najświeższym autorytatywnym dowodem.
   Control Plane wyprowadza właściwe outage windows z jedynego autorytatywnego
   schedule catalogu, timestampu latest scheduled run i `checked_at` watchdoga;
   watchdog nie duplikuje definicji cron.
3. Osobny incydent watchdoga tworzyć tylko dla jego liveness, błędu kontraktu,
   starego raportu albo niekompletnej kolekcji, nie dla propagowanego wyniku tego
   samego workflow.
4. Dowód starego nieudanego runu watchdoga jest superseded, jeżeli świeży
   bezpośredni collector potwierdził późniejszy udany scheduled run. Nie może
   pozostać jako „unmatched” otwarty alert; jeżeli collector jest stary lub
   niedostępny, watchdog pozostaje źródłem głównym.
5. Licznik „Otwarte alerty” ma liczyć unikalne incydenty, a nie rekordy dowodów.
6. UI powinno umożliwiać rozwinięcie dowodów, aby użytkownik nadal widział, że ten
   sam problem potwierdziły dwa niezależne źródła.
7. Przez N/N+1 zachować dotychczasowe `fingerprint` jako alias wyliczony z nowego
   klucza. Ponieważ alerty nie są utrwalane, nie wykonywać pozornej migracji
   lifecycle. Testować stabilność fingerprintu w kolejnych missed windows oraz
   zmianę po przejściu do innej rodziny warunku.
8. Testy obejmują clock skew, opóźniony run, późniejszy sukces superseding stary
   dowód watchdoga oraz watchdog jako źródło główne przy niedostępnym collectorze.

Brama: trzy nieuruchomione workflow obserwowane przez collector i watchdog dają
trzy incydenty, nie sześć; awaria samego watchdoga nadal daje czwarty niezależny
incydent.

### 16.1 Kanoniczna macierz severity

1. Dodać wersjonowany i walidowany katalog
   `manifests/control-plane-severity-policy.json`, mapujący
   `(condition_axis, reason_code)` na severity, wpływ na `overall_state` i rodzinę
   incydentu. Kod nie może ponownie wyprowadzać severity wyłącznie z legacy
   `state`.
2. Minimalne reguły:
   - `SCHEDULE_DELAYED` i `GITHUB_COLLECTION_PARTIAL` — warning;
   - przekroczenie `missed_windows_failure` / `EXPECTED_RUN_NOT_STARTED` —
     critical, nawet jeśli legacy state nadal nazywa się `OVERDUE`;
   - `LAST_RUN_FAILED` — critical;
   - `MULTIPLE_ACTIVE_GENERATIONS` — osobny enrollment warning, z możliwością
     jawnego podniesienia polityką; nigdy freshness;
   - stare urządzenie `ON_DEMAND` bez expectation — informational/none;
   - błąd collectora nie zmienia severity ostatniego wyniku workflow.
3. Przy kilku warunkach zachować wszystkie `reason_codes`; najwyższa severity
   wyznacza ogólny kolor, ale nie usuwa mniej priorytetowych przyczyn.
4. Przetestować każdą regułę, granice missed windows, kolizje osi oraz zgodność
   legacy aliasów N/N+1.

## 17. Etap 9 — GUI, zasoby i diagnostyka operatora

1. W tabeli urządzeń pokazywać osobno heartbeat, `monitoring_mode`, enrollment i
   konfigurację. Opcjonalną reachability pokazywać tylko z provenance; bez
   collectora jako `UNKNOWN`, nigdy jako pochodną heartbeat-u. Dodać bezpieczne
   reason codes, bez numerów enrollment ID i bez tokenów.
2. Przy każdym źródle statusu wyświetlać `last_attempt`, `last_success`, świeżość,
   `collection_state` i zredagowany kod błędu. Fallback nie może wyglądać jak
   świeży `OK`.
3. Przy workflow pokazywać rozdzielnie:
   - stan schedulera;
   - wynik ostatniego scheduled runu;
   - nowszy ręczny remediation run;
   - świeżość dowodu i stan collectora.
4. Dodać względny, wersjonowany favicon w aplikacji webowej, tak aby przeglądarka
   nie żądała QTS-owego `/favicon.ico`.
5. Zachować działanie przycisku „Odśwież stan”, sygnalizować trwające odświeżanie
   i nie uruchamiać równoległych żądań po wielokrotnym kliknięciu.
6. Dodać browser E2E przez CDP obejmujący:
   - brak wyjątków JavaScript i błędów zasobów;
   - poprawną prezentację `READY`, `PARTIAL`, `ERROR`;
   - osobny alert enrollmentu;
   - jeden incydent z dwoma źródłami;
   - redakcję DOM, odpowiedzi BFF i accessibility snapshotu;
   - pięć przeładowań strony i pięć użyć przycisku odświeżania.
7. W dokumentacji wskazać, że certyfikat portu `443` jest własnością QTS i gateway
   LAN nadal go dziedziczy. Panel nie wymaga prywatnego CA/mTLS Control Plane po
   stronie przeglądarki, ale wygasły certyfikat QTS nadal może powodować
   ostrzeżenie i wymaga osobnej rotacji administracyjnej QTS.

## 18. Etap 10 — obsługa bieżących braków GitHub cron

1. Przed jakąkolwiek akcją ponownie sprawdzić GitHub API, stan workflow na
   domyślnej gałęzi, ostatnie scheduled/manual runs oraz publiczny status Actions.
2. Dla każdego brakującego workflow określić, czy ręczny dispatch jest
   idempotentny i chroniony concurrency, malware gate oraz approval gate.
3. Wykonać ręczne catch-up tylko dla workflow, których wynik jest potrzebny przed
   następnym naturalnym oknem. Nie wykonywać masowego dispatchu bez kwalifikacji.
4. Po catch-up zachować scheduler jako `DELAYED/FAILED`; ręczny sukces nie może
   wyczyścić informacji o pominiętym cron.
5. Obserwować następne naturalne okno. Jeżeli GitHub ponownie nie uruchomi cron,
   utworzyć osobny plan alternatywnego triggera z QNAP/GitHub API. Taki trigger
   musi korzystać z GitHub App lub minimalnego fine-grained tokenu, mieć
   deduplikację okna, audit log i nie omijać istniejących bram supply-chain.
6. Nie łączyć alternatywnego schedulera z read-only procesem renderującym
   dashboard. Akcja administracyjna i obserwacja pozostają osobnymi komponentami.

## 19. Testy i kolejność wdrożenia korekt

### 19.1 Testy przed wydaniem

1. `kodi-control-plane`:
   - unit/contract test osi floty, enrollmentów i agregacji;
   - timeout scheduled, manual i obu odczytów dla jednego, kilku i wszystkich
     jobów GitHub;
   - udany retry, wyczerpany retry, deadline, primary/secondary rate limit i
     fallback per observation;
   - korelacja collectora z watchdogiem;
   - zgodność API N/N+1 i stabilność kompatybilnego fingerprintu stateless.
2. `kodi-profile-sync-server`:
   - content-addressed plan revocation;
   - CAS dla zmienionej najwyższej generacji, freshness i aktywnego zbioru;
   - atomowy apply, pełny rollback transakcji i zredagowany audit log;
   - zakaz ujawnienia enrollment ID poza uprzywilejowanym planem/CLI.
3. `kodi`:
   - katalogi Control Plane i inventory;
   - testy Compose i immutable locków;
   - E2E dashboardu z fixture oraz live QNAP;
   - dry-run i audit revocation generacji;
   - pełne `tests/e2e/run.sh`, `git diff --check` i skan sekretów.
4. Test timeoutu uruchomić w izolowanym candidate containerze albo przez testowy
   proxy na osobnej sieci Compose QNAP. Fault injection nie może zmieniać sieci,
   DNS ani routingu produkcyjnego Control Plane.
5. Live GitHub sprawdza tylko zgodność aktualnych runów i źródeł. Nie jest fixture
   do deterministycznego CI.

### 19.2 Wdrożenie consumer-first — delta po zrealizowanym etapie bazowym 10.2

1. Release A: wydać `kodi-control-plane` z tolerant readerem i legacy writerem;
   nowa emisja pozostaje wyłączona flagą domyślną.
2. Zbudować wieloarchitekturowy obraz A przez istniejący workflow, zatwierdzić
   immutable digest, użyć re-use approval pozostałych usług i promować
   standardowym kandydatem QNAP; nie edytować stable locka ręcznie.
3. Wdrożyć A przez `tools/qnap_images.py deploy control-plane` i potwierdzić
   zgodność runtime digestu ze stable lockiem oraz E2E starego payloadu.
4. Zbudować i zatwierdzić zmieniony obraz `profile-sync` zawierający transakcyjne
   plan/apply revocation. Utworzyć kolejny kompletny kandydat QNAP z re-use approval
   niezmienionych usług, przeprowadzić zwykłą promocję i wdrożyć backend przed
   pierwszym dry-run revocation.
5. Release B: włączyć nowy writer przez zreviewowaną konfigurację/katalog przy
   zachowaniu tego samego addytywnego schema 1. Jeżeli wymaga to nowego obrazu,
   powtórzyć build/approval/candidate; jeżeli wyłącznie konfiguracji, wdrożyć ją
   przez standardowy reconcile z dokładnego scalonego commitu.
6. Następnie wdrożyć ewentualne rozszerzenie producenta watchdoga. Niezmienione
   obrazy mają użyć re-use approval.
7. Wykonać browser E2E na działającym QNAP, kontrolowany plan/apply enrollmentów,
   następnie ponowny deploy/no-op i `tools/qnap_images.py status`.
8. Rollout dodatków Kodi nie jest wymagany, jeśli nie zmieni się Profile Sync.
   Kontrolowane uporządkowanie enrollmentów wykonuje się per urządzenie dopiero po
   jego live heartbeat; niedostępny cel otrzymuje `DEFERRED`.

## 20. Rollback korekt

- Zachować poprzedni digest Control Plane, stable lock, katalogi i kompatybilną
  kopię SQLite przed wdrożeniem nowej korelacji.
- Nowe pola API są addytywne przez co najmniej jedną stabilną generację. Rollback
  obrazu nie może wymagać niszczącej migracji bazy.
- Przed revocation zapisać prywatny content-addressed plan i zredagowany snapshot
  generacji. Revocation tokenu jest celowo nieodwracalny; dlatego wykonuje się ją
  dopiero po przejściu CAS, potwierdzonym heartbeat najwyższej generacji i
  działającym recovery/enrollment path.
- Ręczny catch-up GitHub jest audytowalny i nie jest cofany. Rollback dotyczy kodu
  collectora, a nie historii GitHub Actions.
- Jeśli nowa korelacja błędnie scala niezależne incydenty, przywrócić poprzedni
  renderer/licznik, zachowując surowe dowody i nowe pola źródeł.

## 21. Kryteria ukończenia korekt po audycie

Korekta jest ukończona dopiero, gdy:

1. stary heartbeat urządzenia `on_demand` nie degraduje floty bez dodatkowego
   oczekiwania dostępności;
2. wiele aktywnych enrollmentów daje `MULTIPLE_ACTIVE_GENERATIONS`, a nie
   `FLEET_PARTIALLY_STALE`;
3. BlueStacks i X88 mają po jednej potwierdzonej aktywnej generacji albo jawny,
   uzasadniony wyjątek bez ukrywania alertu;
4. pierwszy timeout zakończony udanym retry daje `READY`; dopiero obserwacja,
   której wszystkie próby zostały wyczerpane, daje częściowy wynik, nie odrzuca
   danych pozostałych jobów i nie zmienia wyniku workflow na `FAILED`;
5. zatrzymany scheduler nadal jest wykrywany przy sprawnym transporcie, fallbacku
   i po ręcznym remediation runie;
6. collector i watchdog tworzą jeden incydent na workflow z dwoma źródłami, a
   licznik odpowiada liczbie niezależnych problemów;
7. panel przechodzi pięć przeładowań i pięć odświeżeń bez wyjątków, błędów API,
   `favicon.ico 404` i wycieku danych prywatnych;
8. wszystkie kontenery QNAP pozostają `healthy`, runtime digesty odpowiadają
   stable lockowi, pełne testy lokalne i CI są zielone, a drugi deploy kończy się
   no-op;
9. dokumentacja `docs/control-plane/`, `docs/scheduled-processes.md`,
   `docs/qnap-images.md` oraz datowany raport E2E opisują dokładnie wdrożoną
   semantykę i bieżące ograniczenia;
10. wszystkie zmiany są scalone i wypchnięte, wymagane obrazy wydane, a bieżące
    brakujące workflow zostały jawnie zakwalifikowane jako catch-up, oczekiwanie na
    następne okno albo osobny problem zewnętrzny.
