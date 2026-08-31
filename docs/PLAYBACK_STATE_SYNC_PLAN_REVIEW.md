# Niezależny audyt planu synchronizacji stanu odtwarzania

Data audytu: 2026-08-31  
Audytowany dokument: `docs/PLAYBACK_STATE_SYNC_PLAN.md`  
Werdykt: **kierunek jest zasadny, ale plan wymaga poprawek blokujących przed implementacją**.

Audyt porównał plan z bieżącym kodem `kodi`, `profile-sync-addon` i
`kodi-profile-sync-server`, a także ze stabilnym API JSON-RPC Kodi. Decyzja, aby
WatchNixtoons2 i Rapideo korzystały z QNAP, a Umbrella i YouTube z własnych usług
kontowych, jest poprawna. Nie należy jednak rozpoczynać implementacji kontraktu w
obecnym brzmieniu.

## Uwagi krytyczne — do zastosowania przed implementacją

### K1. LWW, stary journal i tombstone są obecnie logicznie sprzeczne

Plan definiuje LWW jako kolejność przyjęcia przez serwer, a po pull każe wysłać cały
journal. W takim modelu stary, niepotwierdzony event urządzenia offline dostanie nową
rewizję i pokona nowszy stan serwera. Tym samym nie można jednocześnie zagwarantować,
że stare urządzenie nie odtworzy stanu skasowanego tombstone'em. Test 5 w obecnej
postaci nie może deterministycznie przejść.

Należy zachować prostą semantykę bez merge, ale dodać do eventu
`based_on_revision`. Po pull:

- jeśli rekord serwera dla klucza nie zmienił się od `based_on_revision`, event może
  zostać przyjęty i wówczas ostatni zapis przyjęty przez serwer wygrywa;
- jeśli serwer ma nowszą rewizję tego klucza, klient porzuca starszy lokalny event,
  stosuje cały rekord serwera i raportuje `SUPERSEDED_BY_REMOTE`;
- nowa jawna akcja użytkownika wykonana już po pull tworzy nowy event i może wygrać.

Jest to proste nadpisanie całego rekordu, a nie finezyjny merge. Regułę należy
zaimplementować po stronie serwera jako atomowy warunek, nie wyłącznie jako dobrą
wolę klienta.

### K2. Kolejność „pull, potem wykryj stan lokalny” może skasować niewysłaną zmianę

Jeżeli zmiana lokalna nie trafiła wcześniej do journalu, krok 1 nadpisze ją stanem
serwera, zanim krok 2 ją wykryje. Samo `Player.OnStop` nie zawiera pozycji resume, a
po zakończeniu player może już nie odpowiadać na `Player.GetProperties`.

Plan powinien wymagać:

1. rejestracji stabilnej tożsamości przy rozpoczęciu/rozwiązaniu playbacku;
2. okresowego zapisu czasu i długości podczas aktywnego odtwarzania;
3. utworzenia lokalnego eventu przed uruchomieniem pull po `OnStop`/`OnEnd`;
4. osobnej obserwacji jawnego „mark watched/unwatched” albo jawnego ograniczenia MVP,
   jeśli Kodi nie wystawi wiarygodnego zdarzenia;
5. lekkiej lokalnej bazy SQLite w katalogu dodatku na cursor, cache, mapowania i
   journal. Rozbudowywanie wspólnego `state.json` do 20 000 rekordów byłoby kosztowne
   i nie zapewni jednej transakcji dla cursora i journalu.

Playback co 5 minut musi mieć osobny harmonogram w usłudze. Bieżący `KodiRuntime`
wykonuje pełny cykl assignment/heartbeat/sekretów domyślnie co 6 godzin; nie należy
skracać tego interwału do 5 minut i odpytywać całego control plane.

### K3. Brakuje wspólnego, serwerowego zakresu synchronizacji

Projektowane tabele nie zawierają `playback_scope_id`. Stan per enrollment nie będzie
wspólny, natomiast stan globalny nie ma poprawnej granicy autoryzacji. Kanał release
nie może pełnić roli zakresu użytkownika: BlueStacks i X88 mogą chwilowo działać na
różnych kanałach podczas testu, a historia nadal ma być wspólna.

Serwer powinien przypisać enrollment do niekontrolowanego przez klienta
`playback_scope_id` i używać klucza `(scope_id, namespace, content_key)`. W obecnym,
jednorodzinnym wdrożeniu może to być jeden scope skonfigurowany przez serwer, ale
endpoint zawsze musi wyprowadzać go z uwierzytelnionego enrollmentu. Limit 20 000
rekordów również musi obowiązywać per scope.

### K4. Cursor nie może zgubić rekordów bez znanego mapowania lokalnego

Nowe urządzenie może pobrać rekord WatchNixtoons2/Rapideo zanim odwiedzi odpowiadający
mu katalog. Jeżeli podniesie cursor i odrzuci nierozpoznany rekord, nigdy nie zastosuje
go po późniejszym poznaniu ścieżki.

Klient musi zachować zredagowany cache pobranych rekordów, także
`PENDING_IDENTITY_MAPPING`, a cursor może zostać podniesiony dopiero po trwałym
zapisaniu tego cache. Pojawienie się mapowania uruchamia read-after-write apply.
Nierozpoznanie elementu nie może blokować synchronizacji pozostałych kluczy.

### K5. WatchNixtoons2 wymaga twardszego kontraktu tożsamości i kwalifikacji API Kodi

Parser sezonu/odcinka w forku obsługuje niejednorodne tytuły, multi-episode, materiały
bez numeru oraz warianty dub/sub. Sam zestaw sezon/odcinek nie jest bezkolizyjny.
Stabilnym wejściem powinien być wersjonowany, znormalizowany względny URL strony
materiału plus typ i wariant językowy; sezon/odcinek mogą być metadanymi kontrolnymi,
nie podstawowym ID. Hash powinien być domenowo rozdzielony i wersjonowany.

Nie ma też dowodu, że niestandardowa właściwość `ListItem` będzie dostępna usłudze po
rozwiązaniu URL. Fork powinien przekazywać zredagowany `content_key` do Profile Sync
przez jawny, walidowany notification/registration contract. Następnie na BlueStacks i
X88 trzeba zakwalifikować `Files.GetFileDetails`/`Files.SetFileDetails` dla **dokładnej**
ścieżki `plugin://` oraz wykonać read-after-write dla playcount i resume. Publiczne API
Kodi deklaruje te metody, ale jego działanie zależy od obecności dokładnej ścieżki w
bazie wideo; fallback nie może wykonywać bezpośredniego SQL.

### K6. Rapideo ma stabilniejsze ID niż przewiduje plan, ale oficjalny element je gubi

Kod przypiętej wersji Rapideo 1.5.0 otrzymuje z `/files/get` pola `id`, nazwę, rozmiar
i `download_url`, lecz jako ścieżkę odtwarzania wystawia wyłącznie zmienny
`download_url`. Normalizacja nazwy i rozmiaru nie rozwiązuje tożsamości; duplikaty są
realne, a playcount zapisany dla czasowego URL nie będzie przenośny.

Etap Rapideo nie powinien traktować wrappera jako mało prawdopodobnego fallbacku.
Kwalifikacja powinna rozstrzygnąć to przed backendem, a oczekiwanym wariantem jest
odizolowany wrapper/fork z trasą `plugin://.../play/<file-id>`, która dopiero przy
playbacku pobiera aktualny URL. `content_key` powinien powstawać ze stabilnego ID
serwera i wersjonowanego identyfikatora konta/scope. Jeżeli nie da się tego zrobić bez
bezpiecznego uzgodnienia oficjalnego tokenu, Rapideo ma zostać fail-closed i nie może
blokować wydania samego WatchNixtoons2.

### K7. `recently_watched.dat` przeczy deklarowanej prywatności i rozszerza MVP

Plik zawiera jawne `name` i względny `url`, podczas gdy plan deklaruje, że serwer nie
przechowuje tytułów ani adresów. Whole-document LWW tej listy jest też osobnym stanem
nawigacyjnym, nie stanem watched/resume.

Należy usunąć go z pierwszego releasu. Ewentualny późniejszy adapter może wysyłać
wyłącznie uporządkowane `content_key`, o ile lokalne mapowanie potrafi odbudować listę,
albo jawnie zmienić model prywatności. Nie należy maskować tego jako części kontraktu
playback.

### K8. Idempotencja musi wiązać identyfikator z dokładną treścią żądania

Obecna serwerowa tabela `idempotency` wiąże klucz tylko z nazwą operacji i odpowiedzią.
Ponowne użycie klucza z innym body mogłoby zwrócić dawny sukces. Plan musi wymagać:

- deterministycznego `Idempotency-Key` będącego digestem kanonicznego batcha;
- unikalności eventu w co najmniej `(scope_id, enrollment_id, event_id)`;
- porównania digestu dokumentu przy replay; ta sama nazwa z inną treścią to `409`,
  nie `NO_CHANGE`;
- atomowego przyjęcia batcha albo jawnego wyniku per event, bez nieokreślonego stanu
  częściowego;
- allowlisty namespace, limitów pól, rate limitu oraz metryk rozmiaru tabeli eventów.

Historia idempotencji jest potencjalnie nieograniczona. Pierwszy release może jej nie
usuwać, ale musi mieć limit/alert i opisaną politykę retencji przed pełnym rolloutem.

### K9. Telemetria Umbrella/YouTube nie jest jeszcze możliwa przez obecny heartbeat

Bieżący klient raportuje tylko zdrowie instalacji Umbrella. Serwer nie waliduje ani nie
zapisuje dokumentu `addon_health`; zapisuje jedynie jego SHA-256 w heartbeat. Control
Plane nie może więc pokazać booleanu autoryzacji Trakt ani ustawień historii YouTube.

Plan musi objąć wersjonowany, zamknięty schemat health, jego walidację i zredagowany
zapis po stronie serwera oraz aktualizację integration API/Control Plane. Nie wolno
raportować tokenu, loginu, channel ID, tytułów ani URL-i.

Umbrella słusznie pozostaje poza QNAP playback state. Należy zarządzać
`indicators.alt=1`, `scrobble.source=1`, `markwatched.percent=85` i potwierdzić
autoryzację Trakt oraz działający resume/scrobble na bieżącej wersji. YouTube słusznie
powinien używać `kodion.history.remote=true`; jeden moduł powinien być właścicielem
tych ustawień (preferowany istniejący, wersjonowany adapter sesji), aby revision i
Secret Broker nie pisały konkurencyjnie.

### K10. Migracja i rollout wymagają pełnego kontraktu wersji

Migracja zwiększy `DATABASE_SCHEMA_VERSION`, a walidatory backupu dopuszczają dziś
tylko wybrane wersje. Plan powinien jawnie objąć wszystkie narzędzia backup/restore,
readiness, integracyjne snapshoty oraz test restore nowego backupu. Przed canary:

1. backup QNAP i próba restore offline;
2. wdrożenie kompatybilnego wstecznie serwera bez włączania capability;
3. publikacja Profile Sync i ewentualnego forka/wrappera;
4. jawne włączenie capability tylko na BlueStacks/X88;
5. możliwość natychmiastowego wyłączenia adaptera bez kasowania danych;
6. rollback klienta i obrazu serwera z pozostawieniem addytywnych tabel.

Testy nie powinny zależeć od niezatwierdzonego, zmiennego kodu: obrazy i ZIP-y użyte w
E2E muszą pochodzić z dokładnych commitów/artefaktów, które następnie zostaną
opublikowane.

## Zasadne usprawnienia

1. Doprecyzować inwarianty rekordu: `unwatched` oznacza playcount/resume zero,
   `in_progress` wymaga dodatniego resume mniejszego od duration, a `watched` zeruje
   resume i ma playcount co najmniej 1. Wartości czasu muszą mieć granice i typ integer.
2. Użyć namespace z wersją, np. `watchnixtoons2.playback.v1` i
   `rapideo.playback.v1`; migracja algorytmu tożsamości nie może reinterpretować
   starych hashy.
3. Seed powinien być operacją preview/approve/apply ze wskazanym enrollmentem,
   digestem snapshotu i raportem liczby rekordów. Pusty backend pozostaje pull-only,
   dopóki seed nie zostanie jawnie zatwierdzony.
4. Test konfliktu powinien pokrywać trzy przypadki: dwa świeże eventy po pull
   (kolejność serwera wygrywa), stary event oparty na starszej rewizji (remote wygrywa)
   oraz ponowienie dokładnie tego samego eventu (NO_CHANGE).
5. E2E usług zewnętrznych powinno zapisywać stan kontrolnej treści przed testem i
   przywracać go po teście. Polling Trakt/YouTube musi mieć jawny timeout, a dowody mają
   być zredagowane.
6. Cleanup Fen Light i YouTube2KodiLibrary powinien mieć wspólny inventory dla Android
   i Flatpak. Referencje do historycznych certyfikatów mogą pozostać, ale manifesty,
   instalatory, polityki, fixture'y bieżącego rolloutu oraz katalogi `addon_data` nie.
7. Dodać `playback_state_enabled` jako feature flag per enrollment/scope i osobne
   statusy `HEALTHY`, `PENDING_MAPPING`, `CONFLICT_REMOTE_WON`, `DISABLED`, `ERROR`.
8. Rozdzielić testy backendu i klienta od testów dostępności zewnętrznego katalogu
   WatchNixtoons2/Rapideo. Awaria providera nie może fałszywie wyglądać jak błąd LWW.

## Uwagi odrzucone lub niekonieczne

1. **CRDT, merge pól, sumowanie playcount i dialog konfliktu** — niepotrzebne. Pełny
   rekord LWW z prostym warunkiem rewizji spełnia wymaganie użytkownika lepiej.
2. **Synchronizacja `MyVideos*.db` lub bezpośrednie SQL** — należy nadal odrzucić;
   grozi to zależnością od wersji Kodi i korupcją bazy.
3. **QNAP jako drugi backend historii Umbrella albo YouTube** — nieuzasadnione.
   Trakt i zdalna historia YouTube pozostają właściwymi źródłami prawdy.
4. **Zegar urządzenia jako rozstrzygnięcie konfliktu** — odrzucone słusznie. Może być
   wyłącznie informacją diagnostyczną.
5. **Szyfrowanie każdego rekordu aplikacyjnego ponad obecny TLS** — nie jest warunkiem
   MVP w prywatnym wdrożeniu QNAP. Hash jest pseudonimem, nie pełną anonimizacją; ważne
   są redakcja integration API, ograniczenia dostępu, backup i nieprzechowywanie
   tytułów/URL-i.
6. **Blokowanie releasu WatchNixtoons2 do czasu rozwiązania Rapideo** — niepotrzebne.
   Adaptery muszą być niezależnie przełączalne i Rapideo może pozostać fail-closed.

## Minimalna poprawiona kolejność realizacji

1. Domknąć cleanup legacy i test idempotencji na Androidzie; dodać odpowiednik do
   inwentarza Flatpak przed pełnym rolloutem floty.
2. Zamrozić kontrakt scope, `based_on_revision`, rekordów, batch-idempotency i lokalnej
   bazy; dopiero wtedy implementować backend.
3. Zrobić loopback backend/klient obejmujący konflikt, stary journal, tombstone,
   utratę odpowiedzi POST, nieznane mapowanie i restart procesu.
4. Zakwalifikować na BlueStacks i X88 exact-path JSON-RPC oraz mechanizm przechwycenia
   resume. Brak kwalifikacji blokuje adapter, nie prowadzi do SQL.
5. Wdrożyć WatchNixtoons2 jako pierwszy adapter. Rapideo dopiero po stabilnej trasie
   opartej na `file.id`.
6. Osobno wdrożyć wymuszenie/audyt Trakt i remote history YouTube.
7. Wykonać konfliktowe E2E BlueStacks/X88, regresję favourites/Profile Sync/sekretów,
   backup/restore QNAP i drugi przebieg `NO_CHANGE`.
8. Dopiero po zielonych dowodach utworzyć commity/PR-y, CI, niezmienne release'y i
   wdrożyć serwisy. Pozostała flota pozostaje poza tym etapem.

Po zastosowaniu K1–K10 plan będzie spójny z prostą zasadą „nowszy zaakceptowany stan
zastępuje cały starszy rekord”, bez ukrytych merge i bez ryzyka przywrócenia stanu ze
starego urządzenia.
