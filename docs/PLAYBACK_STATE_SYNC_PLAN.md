# Plan synchronizacji stanu odtwarzania

Status: zaimplementowany i zakwalifikowany na BlueStacks/X88; release w toku po
naprawie bramy originów i deterministycznym przywracaniu RD w canary.

## 1. Cel i decyzje projektowe

Celem jest spójny stan `watched`, `playcount`, `lastplayed` i `resume` na urządzeniach
Kodi bez kopiowania `MyVideos*.db` i bez tworzenia drugiego źródła prawdy tam, gdzie
dodatek ma własną usługę konta.

Obowiązują następujące decyzje:

1. WatchNixtoons2 i Rapideo korzystają z nowego stanu LWW przechowywanego przez
   Profile Sync na QNAP.
2. Umbrella pozostaje oparta na Trakt, a YouTube na natywnej zdalnej historii konta
   YouTube. Profile Sync wymusza i obserwuje konfigurację tych mechanizmów, ale nie
   kopiuje ich historii do QNAP.
3. Konflikt jednego elementu rozstrzyga monotoniczna rewizja nadana przez serwer:
   ostatni zaakceptowany zapis zastępuje cały poprzedni rekord. Event zawiera
   `based_on_revision`; stary event oparty na zastąpionej rewizji przegrywa w całości
   z bieżącym rekordem serwera (`SUPERSEDED_BY_REMOTE`). Nie ma merge pól, sumowania
   `playcount`, CRDT ani prób odtwarzania utraconego lokalnego stanu.
4. Zegar urządzenia jest wyłącznie informacyjny i nie bierze udziału w rozstrzyganiu
   konfliktu. Zapobiega to wygrywaniu błędnie ustawionego zegara Androida.
5. Klient journaluje zmianę przed pull, a następnie pobiera stan serwera. Wysyła tylko
   zdarzenia powstałe względem zapamiętanej rewizji danego rekordu, nigdy pełną lokalną
   bazę. Stare urządzenie uruchomione po długiej przerwie nie może nadpisać serwera
   samym swoim snapshotem ani starym journale'em.
6. Enrollment otrzymuje od serwera niezmienny `playback_scope_id`. Klient nie wybiera
   scope i nie wyprowadza go z kanału release; wszystkie domowe urządzenia należą do
   tego samego prywatnego zakresu niezależnie od czasowego kanału testowego.

## 2. Zakres i źródła prawdy

| Zakres | Źródło prawdy | Działanie Profile Sync |
|---|---|---|
| WatchNixtoons2 | QNAP playback state | dwukierunkowy LWW |
| Rapideo | QNAP playback state dla obejrzenia/resume; konto Rapideo dla wyszukiwań i plików | dwukierunkowy LWW tylko dla odtwarzania |
| Umbrella | Trakt | wymuszenie trybu, audyt autoryzacji i telemetria bez sekretów |
| YouTube | konto YouTube | włączenie historii zdalnej, zachowanie lokalnego cache i audyt |
| Pozostałe pliki Kodi | poza pierwszym releasem | kontrakt pozostaje rozszerzalny przez adapter |

OpenSubtitles, mwoScrapers, repozytoria, Real-Debrid i stan techniczny samego Profile
Sync nie są historią odtwarzania i nie wchodzą do tego zakresu.

Fen Light i YouTube2KodiLibrary są wycofane. Androidowy preflight usuwa kod oraz
`addon_data` obu dodatków; nie powstaje dla nich adapter ani migracja historii.

## 3. Kontrakt `playback-state-lww-v1`

Jeden rekord ma mały, zamknięty kontrakt:

```json
{
  "namespace": "watchnixtoons2",
  "content_key": "sha256:<64-hex>",
  "state": "unwatched|in_progress|watched",
  "playcount": 0,
  "resume_seconds": 0,
  "duration_seconds": 0,
  "lastplayed_utc": null,
  "event_id": "evt:<losowy-id>",
  "based_on_revision": 41
}
```

`content_key` jest deterministycznym hashem stabilnej tożsamości dostawcy, nie URL-em
strumienia. Serwer nie przechowuje tytułów, nazw plików, adresów ani tokenów. Klient
utrzymuje prywatną lokalną mapę `content_key -> bieżąca ścieżka Kodi`.

Zapis `unwatched` jest tombstone'em z `playcount=0` i `resume_seconds=0`. Tombstone'y
nie są kasowane w pierwszym releasie, aby stare urządzenie nie przywróciło obejrzenia.
Limit per gospodarstwo domowe wynosi 20 000 rekordów, payload 256 rekordów i 512 KiB.

Inwarianty są walidowane: `unwatched` ma zerowy playcount i resume, `in_progress` ma
dodatnie resume mniejsze od duration, a `watched` ma playcount co najmniej 1 i zerowe
resume. Czasy są ograniczonymi liczbami całkowitymi.

Serwer zapisuje rekord atomowo i nadaje rosnący `server_revision`. Event zostaje
przyjęty tylko wtedy, gdy `based_on_revision` jest bieżącą rewizją danego klucza albo
klucz jeszcze nie istnieje. Event oparty na starszej rewizji zwraca
`SUPERSEDED_BY_REMOTE` wraz z całym aktualnym rekordem. Nowa jawna czynność użytkownika
wykonana po pull tworzy event oparty na bieżącej rewizji i może ją zastąpić.

Powtórzony `event_id` z identycznym digestem jest idempotentnym `NO_CHANGE`; ten sam ID
z innym dokumentem daje `409`. Namespace są wersjonowane, np.
`watchnixtoons2.playback.v1` i `rapideo.playback.v1`.

## 4. Cykl synchronizacji i konflikty

Każde urządzenie przechowuje w lekkiej lokalnej bazie SQLite dodatku:

- ostatni zastosowany `server_cursor`;
- append-only journal niepotwierdzonych lokalnych zdarzeń;
- cache wszystkich pobranych rekordów, także `PENDING_IDENTITY_MAPPING`;
- mapę stabilnych kluczy do lokalnych ścieżek;
- identyfikatory już potwierdzonych zdarzeń.

Cykl przebiega zawsze w kolejności:

1. podczas `OnAVStart` zarejestruj stabilną tożsamość, a podczas odtwarzania okresowo
   zapisz czas i długość;
2. przed pull, na `OnStop`/`OnEnd`, atomowo zapisz lokalny event wraz z
   `based_on_revision` do journalu;
3. pobierz zmiany serwera po `server_cursor` i trwale zapisz cały zwrócony cache;
4. przesuń cursor dopiero w tej samej transakcji co cache; brak lokalnego mapowania nie
   usuwa rekordu i nie blokuje pozostałych elementów;
5. dla kluczy bez lokalnego eventu zastosuj cały rekord z serwera; dla kluczy dirty
   zachowaj event do rozstrzygnięcia przez serwer;
6. wyślij journal w kolejności powstania i obsłuż per event `APPLIED`, `NO_CHANGE` albo
   `SUPERSEDED_BY_REMOTE`;
7. zastosuj cały rekord zwrócony przez serwer, ponownie pobierz wynikowy stan i
   potwierdź wspólny cursor;
8. dopiero wtedy usuń potwierdzone albo zastąpione wpisy journalu.

Playback ma osobny lekki harmonogram: zdarzenie wyzwala synchronizację po
`OnStop`/`OnEnd`, dodatkowo następuje ona przy starcie Kodi oraz co 5 minut. Nie
skraca to sześciogodzinnego cyklu assignment/heartbeat/sekretów. Operacja działa poza
ścieżką odtwarzania, ma timeout i nie blokuje filmu. Awaria sieci pozostawia journal
do bezpiecznego replay.

Konflikt testowy jest celowo prosty: dwa świeże eventy utworzone po pull wygrywają w
kolejności przyjęcia przez serwer. Stary event, którego `based_on_revision` zostało już
zastąpione, przegrywa z rekordem zdalnym. Nie istnieje dialog konfliktu ani merge.

Pierwsze uruchomienie nie importuje automatycznie całej zastanej bazy urządzenia.
Administrator jawnie wybiera `--seed-device`; operacja preview/approve/apply pokazuje
enrollment, liczbę rekordów i digest snapshotu. Dopiero zatwierdzony kwalifikowany
snapshot staje się pierwszą rewizją. Pozostałe urządzenia wykonują pull-only bootstrap.
Brak jawnego seeda oznacza pusty stan serwera, bez masowego nadpisania.

## 5. Adaptery

### 5.1 WatchNixtoons2

- Stabilna tożsamość powstaje z wersjonowanego, kanonicznego względnego URL strony
  materiału, typu i wariantu językowego. Sezon/odcinek są metadanymi kontrolnymi, nie
  podstawowym ID; domena, parametry strumienia i podpisane URL-e są odrzucane.
- Fork przekazuje zredagowany `content_key` usłudze przez jawny, walidowany kontrakt
  notification/registration. Nie zakładamy, że niestandardowa właściwość ListItem
  przetrwa rozwiązanie URL.
- Adapter Profile Sync zapisuje zdarzenia odtwarzacza i stosuje `playcount`/resume
  przez publiczne API Kodi. Dla adresu, którego Kodi jeszcze nie zna w lokalnej bazie,
  zachowuje cały rekord jako oczekujący zamiast zgłaszać awarię. WatchNixtoons2 czyta
  ten zredagowany lokalny cache podczas budowania listy; po utworzeniu wpisu przez Kodi
  natywny zapis jest ponawiany. Nie ma bezpośrednich zapisów do bazy Kodi.
- `recently_watched.dat` nie wchodzi do pierwszego releasu: zawiera tytuły i URL-e oraz
  jest stanem nawigacyjnym, nie playback.
- Nie wykonujemy bezpośrednich zapisów SQL do `MyVideos*.db`.

### 5.2 Rapideo

- Historia wyszukiwania i lista plików pozostają po stronie konta Rapideo.
- Przypięta wtyczka otrzymuje z API stabilne `file.id`, ale gubi je, wystawiając jako
  ścieżkę wyłącznie zmienny `download_url`. Nazwa i rozmiar nie są tożsamością.
- Oczekiwanym rozwiązaniem jest odizolowany wrapper/fork z trasą
  `plugin://.../play/<file-id>`, która dopiero przy playbacku pobiera aktualny URL.
  `content_key` powstaje z wersjonowanego identyfikatora konta/scope i `file.id`.
- Kwalifikacja najpierw udowadnia bezpieczne użycie istniejącego tokenu. Jeżeli tego
  nie da się zrobić, adapter Rapideo pozostaje `DISABLED/UNSUPPORTED` i fail-closed;
  nie blokuje releasu adaptera WatchNixtoons2 i niczego nie zgaduje.

### 5.3 Umbrella/Trakt

- Zarządzana polityka wymusza `indicators.alt=1`, `scrobble.source=1` i
  `markwatched.percent=85` dla zgodnego zakresu wersji.
- Wersjonowany heartbeat raportuje wyłącznie: wersję, włączony dodatek, wybrany backend
  historii i boolean autoryzacji Trakt. Serwer waliduje zamknięty schemat i zachowuje
  jego zredagowaną postać dla Control Plane. Token, login i historia nie opuszczają
  urządzenia.
- Test BlueStacks/X88 odtwarza kontrolowaną treść, a następnie potwierdza stan na drugim
  urządzeniu przez Umbrella. QNAP nie zapisuje rekordu playback dla tego namespace.

### 5.4 YouTube

- Jeden właściciel ustawień — aktywny, wersjonowany adapter sesji — ustawia
  `kodion.history.local=true` i `kodion.history.remote=true`.
- Wersjonowany heartbeat raportuje boolean aktywnej sesji oraz wartości obu
  przełączników bez danych konta. Serwer zachowuje zredagowany dokument, nie tylko jego
  digest, aby Control Plane mógł pokazać rzeczywisty stan.
- Test BlueStacks/X88 potwierdza pojawienie się kontrolowanego filmu w zdalnej historii
  i jego widoczność na drugim urządzeniu. Lokalny `history.sqlite` pozostaje cache i
  nie jest kopiowany.

## 6. Backend QNAP i API

Zmiana trafia do `mwoDevelop/kodi-profile-sync-server` jako addytywna migracja SQLite:

- przypisany przez serwer `playback_scope_id` enrollmentu i flaga
  `playback_state_enabled`;
- `playback_state(scope_id, namespace, content_key, document, server_revision)`;
- `playback_events(scope_id, enrollment_id, event_id, request_sha256,
  accepted_revision, result, document)`;
- licznik rewizji w pojedynczej transakcji `BEGIN IMMEDIATE`.

API konsumenckie używa obecnego TLS, enrollmentu i Bearer tokenu:

```text
GET  /v1/enrollments/{id}/playback-state?after={cursor}
POST /v1/enrollments/{id}/playback-events
```

POST wymaga `Idempotency-Key` będącego digestem kanonicznego batcha, zgodności
enrollmentu z tokenem, włączonej flagi i capability `playback_state_lww_v1`. Scope jest
zawsze wyprowadzany z enrollmentu. Ten sam klucz/event z innym digestem zwraca `409`.
Batch ma atomową walidację, a wynik per event jawnie rozróżnia `APPLIED`, `NO_CHANGE` i
`SUPERSEDED_BY_REMOTE`. Obowiązują allowlista namespace, rate limit, limit per scope i
metryki wielkości tabeli; historia eventów nie jest usuwana w pierwszym releasie, ale
ma limit i alert przed rolloutem floty.

Read-only integration API udostępnia Control Plane tylko liczność, najwyższą rewizję,
czas ostatniego zapisu, licznik pending/conflict/error i stan per urządzenie, bez
`content_key`. Statusy to `HEALTHY`, `PENDING_MAPPING`, `CONFLICT_REMOTE_WON`,
`DISABLED` i `ERROR`.

Stare klienty i stara baza działają bez nowej capability. Migracja zwiększa
`DATABASE_SCHEMA_VERSION` i aktualizuje readiness, walidatory backupu/restore oraz
test odtworzenia nowego backupu. Rollback klienta wyłącza capability i pozostawia
nieużywane tabele; rollback starszego obrazu serwera jest dopuszczony dopiero po
sprawdzeniu jego zgodności ze zwiększonym `user_version`. Przed wdrożeniem wykonywany
jest online backup, próbny restore offline i `PRAGMA integrity_check`.

## 7. Implementacja etapami

1. **Czyszczenie legacy** — Fen Light i YouTube2KodiLibrary we wspólnym inwentarzu
   Android/Flatpak, test idempotencji i brak odniesień instalacyjnych.
2. **Kontrakt i backend** — walidatory, migracja, API LWW, idempotencja, limity,
   testy konkurencji i replay.
3. **Klient wspólny** — capability, osobny scheduler playback, API client, lokalna
   SQLite, journal-before-pull, cache pending mapping, bootstrap i telemetria.
4. **WatchNixtoons2** — stabilna tożsamość, jawna rejestracja zdarzenia oraz
   kwalifikowane watched/resume; `recently_watched` pozostaje poza MVP.
5. **Rapideo** — kwalifikacja dostępu do stabilnego `file.id` oraz odizolowany wrapper;
   brak bezpiecznej tożsamości pozostawia adapter wyłączony.
6. **Umbrella i YouTube** — zarządzane ustawienia, self-healing w Profile Sync i
   privacy-bounded health.
7. **Control Plane i dokumentacja** — redacted status, feature flag, runbook seeda,
   konfliktów, rollbacku i przykładów wywołań.
8. **Release/deploy** — backup/restore QNAP, kompatybilny serwer z capability domyślnie
   wyłączoną, osobne wersje Profile Sync i zmienionych dodatków; capability jest
   włączana najpierw wyłącznie dla BlueStacks/X88. Obraz serwera QNAP jest wdrażany
   istniejącym `tools/qnap_images.py`, a repo Kodi istniejącym procesem publikacji.

## 8. Testy i kryteria akceptacji

Najpierw testy jednostkowe i loopback, następnie wyłącznie BlueStacks i X88:

1. preflight usuwa oba dodatki legacy i drugi przebieg zwraca `NO_CHANGE`;
2. preview/approve/apply seeda BlueStacks przenosi watched, unwatched i resume
   WatchNixtoons2 na X88;
3. odtworzenie na X88 przenosi wynik na BlueStacks;
4. dwa świeże konflikty po pull potwierdzają kolejność serwera, a event oparty na
   starej rewizji zwraca `SUPERSEDED_BY_REMOTE`;
5. reset do unwatched jest tombstone'em i nie odradza się po uruchomieniu starego
   journalu;
6. zerwane połączenie po przyjęciu POST i przed odpowiedzią nie duplikuje eventu, a
   ponowienie tego samego ID z inną treścią daje `409`;
7. ponowne uruchomienie klienta zachowuje journal, cache nierozpoznanych mapowań i
   cursor; późniejsze poznanie mapowania stosuje zachowany rekord;
8. Rapideo przechodzi watched/resume w obie strony albo zostaje fail-closed przed
   publikacją bez zgadywania tożsamości;
9. Umbrella/Trakt i YouTube remote history przechodzą z ograniczonym timeoutem test
   krzyżowy między urządzeniami, po czym kontrolny stan zewnętrzny jest przywrócony;
10. logi, raporty, API integracyjne i panel nie zawierają tytułów, URL-i ani sekretów;
11. pełne testy każdego zmienionego repo, `git diff --check`, compose smoke, restore
    nowego backupu i E2E istniejących favourites/Profile Sync/sekretów pozostają
    zielone;
12. artefakty E2E pochodzą z dokładnych commitów przeznaczonych do publikacji; po
    deployu QNAP health jest `healthy`, migracja jest idempotentna, a ponowny sync
    obu urządzeń zwraca `NO_CHANGE` przy tym samym cursorze.

Rollout pozostałej floty nie rozpoczyna się, dopóki wszystkie powyższe kryteria dla
BlueStacks i X88 nie przejdą. Niedostępność jednego z dwóch urządzeń blokuje promocję,
ale nie uzasadnia osłabienia testu ani ręcznego wpisania sukcesu.

## 9. Wynik implementacji canary

Stan z 2026-08-31:

- Fen Light i YouTube2KodiLibrary są wyłącznie na liście wycofanych dodatków;
  powtórny preflight obu urządzeń zwrócił `NO_CHANGE`;
- backend QNAP działa na schemacie 7 i udostępnia jeden prywatny scope domowy;
- Profile Sync 1.3.3 oraz WatchNixtoons2 0.30.3 przeszły testy na BlueStacks i X88;
- odłożony zapis dla nieznanej jeszcze ścieżki Kodi nie degraduje zdrowia procesu,
  a stan jest widoczny na liście dodatku;
- zapis X88 został odczytany na BlueStacks, po czym kontrolowany konflikt dwóch
  eventów opartych na tej samej rewizji zakończył się pełnym nadpisaniem rekordem
  zaakceptowanym jako pierwszy; X88 zgłosił `SUPERSEDED_BY_REMOTE`;
- Rapideo pozostaje świadomie fail-closed, Umbrella używa Trakt, a YouTube historii
  konta; nie powstało dla nich równoległe źródło historii na QNAP.
- na obu canary wymuszono zgodną politykę Umbrella i lokalną/zdalną historię YouTube;
  heartbeat jest zredagowany. Sama autoryzacja Trakt wymaga późniejszego działania
  użytkownika i pozostaje jawnie `false`.

Zredagowany, odtwarzalny raport znajduje się w
`docs/e2e-results/2026-08-31-playback-state-sync-canary.md`.
