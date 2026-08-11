# Plan usunięcia kodu legacy z projektu Kodi

Status: readerzy produkcyjni wycofani; migratory offline i retencja pozostają aktywne

Data: 2026-08-11

Repozytorium nadrzędne: `mwoDevelop/kodi`

Raport review: [docs/LEGACY_REMOVAL_PLAN_REVIEW.md](docs/LEGACY_REMOVAL_PLAN_REVIEW.md)

## 1. Cel i zasada bezpieczeństwa

Usunąć należące do mwoDevelop produkcyjne ścieżki wykonawcze obsługujące
wyłącznie stare formaty, po przeniesieniu aktywnych danych do formatów
bieżących i udowodnieniu odtwarzalności backupów.

Proces rozdziela dwa terminy:

- **wycofanie readera produkcyjnego** — aplikacja i bieżące narzędzia nie
  przyjmują już starego formatu;
- **wycofanie migratora offline** — następuje później, dopiero gdy wygasł każdy
  backup wymagający tego migratora albo ma zweryfikowany bieżący odpowiednik.

Nie wolno usuwać migratora, fixture ani instrukcji recovery tylko dlatego, że
aktywne urządzenia nie używają już legacy. Przez cały okres retencji pozostają
w przypiętym, izolowanym zestawie migracyjnym offline z sumą kontrolną.

## 2. Źródło prawdy cyklu życia schematów

Numer `schema` jest lokalny dla typu dokumentu. Samo `schema: 1` nie oznacza
legacy. Docelowym źródłem prawdy będzie maszynowy plik
`manifests/schema-lifecycle.json`; generowany lub walidowany względem niego
`docs/schema-lifecycle.md` będzie widokiem dla operatora.

Stan początkowy, który należy odwzorować w manifeście:

| Format | Stan | Decyzja |
|---|---|---|
| rejestr urządzeń schema 1 | legacy | zmigrować, potem usunąć reader produkcyjny |
| rejestr urządzeń schema 2 | bieżący | pozostawić |
| konfiguracja reinstalacji schema 1 | legacy | zmigrować transakcyjnie razem z rejestrem |
| konfiguracja reinstalacji schema 2 | bieżąca | pozostawić |
| samodzielna polityka profilu schema 1 | legacy | zmigrować pliki używane przez writery i automatyzację |
| polityka profilu schema 2 | bieżąca | pozostawić |
| manifest grafik favourites schema 1 | do klasyfikacji per typ | nie uznawać automatycznie za legacy |
| snapshot disaster recovery schema 1 | bieżący kontener snapshotu | zachować; kwalifikować jego zawartość osobno |
| portable-state schema 1 | bieżący format paczki | poza zakresem |
| testing lock schema 1 | bieżący format kanału testing | poza zakresem |
| stable lock schema 2 | bieżący format promocji stable | poza zakresem |
| rewizja Profile Sync schema 2/3 | bieżąca | poza zakresem |
| lokalny stan i journal Profile Sync schema 1 | bieżący | poza zakresem |

Stary `policy_sha256` zapisany w niezmiennym snapshocie lub rewizji jest
historycznym dowodem. Nie należy przepisywać go ani interpretować jako osadzoną
politykę wymagającą migracji.

## 3. Zakres techniczny

### 3.1 Rejestr urządzeń i konfiguracja reinstalacji

Po migracji produkcyjny `load_registry()` oraz `load_config()` mają przyjmować
wyłącznie schema 2. Z kodu produkcyjnego można wtedy usunąć normalizację schema
1, stare definicje JSON Schema, stałe i komendy zgodnościowe.

Obecny `migrate_reinstall_config()` nie jest wystarczającą bazą do prostego
opakowania: odmawia działania przy istniejącym `devices.json`, nie daje no-op po
drugim uruchomieniu i zapisuje dwa dokumenty po kolei bez wspólnej transakcji.
Należy zastąpić go migracją dwóch dokumentów, która:

1. waliduje oba wejścia i wszystkie konflikty przed zapisem;
2. scala target z istniejącym registry v2 tylko przy zgodności kanonicznej
   tożsamości, endpointu i oczekiwanego modelu;
3. przy konflikcie kończy się fail-closed bez zmiany żadnego pliku;
4. zapisuje journal, pliki tymczasowe i atomowo zatwierdza oba dokumenty;
5. potrafi odzyskać stan po przerwaniu pomiędzy podmianami plików;
6. rozpoznaje już zmigrowany stan i zwraca no-op;
7. tworzy zweryfikowany backup przed pierwszą zmianą.

Reader i CLI schema 1 zostaną usunięte z produkcji po bramie przejściowej.
Ostatnia wersja migratora, fixture i instrukcja recovery pozostają w zestawie
offline przez pełny okres retencji.

### 3.2 Samodzielne polityki profilu schema 1

Kwalifikacji podlegają pliki polityki używane bezpośrednio przez writery i
automatyzację, a nie snapshoty tylko zawierające historyczny `policy_sha256`.
Migracja do schema 2 musi utworzyć poprawny, domyślnie zamknięty scope routine,
co najmniej:

```json
{
  "default": "excluded",
  "default_profile_only": true,
  "adapters": [],
  "device_local_paths": []
}
```

Przed zatwierdzeniem migrator porównuje decyzje include/exclude starej i nowej
polityki na reprezentatywnym korpusie ścieżek. Nie modyfikuje historycznych
manifestów snapshotów ani rewizji.

### 3.3 WatchNixtoons2

Legacy nie ogranicza się do URL-i w `favourites.xml` i miniaturek. Stary
snapshot może zawierać również:

- `addons/plugin.video.watchnixtoons2`;
- `userdata/addon_data/plugin.video.watchnixtoons2`;
- origin albo wersję starego repozytorium.

Snapshoty są content-addressed, dlatego nie wolno zmieniać ich w miejscu.
Migrator offline tworzy nowy artefakt i nowy snapshot ID, usuwa stare katalogi
dodatku i repozytorium, przepisuje wspierane dane użytkownika na
`plugin.video.watchnixtoons2.mwodevelop`, odświeża lokalne grafiki i przelicza
inventory oraz digesty. Dane bez zdefiniowanej transformacji oznacza jako
`nonportable`, zamiast kopiować je w ciemno.

Sidecar dowodowy zapisuje `migrated_from`, digest wejścia i wyjścia oraz raport
zmian bez sekretów. Nowy artefakt musi przejść verify i restore drill.
Oryginalny snapshot zostaje niezmiennym archiwum zimnym o stanie
`LEGACY_QUARANTINED` i nie może być standardowym źródłem automatycznego restore.

### 3.4 Fork Umbrella

Kwalifikacja dotyczy dokładnie downstreamowego pliku
`umbrella/omega/plugin.video.umbrella/resources/lib/downstream/version_policy.py`.
Nie łączyć jej z migracją control plane. Ewentualne usunięcie wykonać w osobnym,
małym PR forka dopiero po teście kontraktu na bieżącym upstreamie.

Inne zgodności upstreamowe, vendored i playcount pozostają poza zakresem, dopóki
nie zostanie wskazany konkretny symbol będący własnością downstream i dowód, że
jego kontrakt wejściowy wygasł.

## 4. Potwierdzony stan początkowy

Kontrola z 2026-08-11 bez odczytywania sekretów wykazała:

- `.kodi-private/devices.json` — schema 2;
- `.kodi-private/kodi-reinstall.json` — schema 2;
- `manifests/kodi-profile-policy.json` — schema 2;
- readery schema 1 nadal są wykonywalne i testowane;
- lokalne kopie `.schema1.bak` oraz backupy objęte retencją wymagają jeszcze
  pełnej kwalifikacji.

Stan roboczy hosta nie jest wystarczającym dowodem gotowości backupów, QNAP ani
urządzeń.

## 5. Etapy realizacji

Sekwencja: `freeze writers -> inventory -> migrate -> prove -> contract ->
remove production readers -> retire offline kit`.

### Etap 0 — zamrożenie writerów i manifest cyklu życia

1. Dodać `manifests/schema-lifecycle.json` oraz walidowany widok Markdown.
2. Dodać CI blokujące tworzenie nowych danych legacy poza fixture migratora.
3. Zidentyfikować i zablokować wszystkie writery starego formatu przed
   rozpoczęciem rolloutów.
4. Nadać każdemu typowi dokumentu własny klasyfikator; nie używać globalnego
   wyszukiwania `schema: 1`.

Brama: żaden bieżący proces nie potrafi utworzyć nowego legacy, a każdy format
ma właściciela, bieżącą wersję, reader i regułę retencji.

### Etap 1 — bezpieczna inwentaryzacja

Dodać read-only `tools/legacy_inventory.py`, ograniczony do jawnej allowlisty:

- `.kodi-private/`, w tym `.kodi-private/snapshots/`;
- `.device-backups/`;
- `portable-state/` i artefakty certyfikacji;
- backup produkcji QNAP pobrany przez istniejące `backup-production` i
  `download-production-backup`;
- konfiguracje urządzeń wskazanych w `.env`;
- jawnie wskazane lokalizacje off-NAS.

QNAP nie udostępnia obecnie ogólnego API listowania rewizji i backupów. Bazowy
wariant wykonuje spójny backup jednego epochu, pobiera go i analizuje offline:
SQLite otwiera read-only, a bloby weryfikuje po digestach. Jeżeli potrzebna
będzie enumeracja live, najpierw powstanie uwierzytelniony endpoint tylko do
odczytu z testem autoryzacji; plan nie zakłada jego istnienia.

Archiwa ZIP/TAR są klasyfikowane bez niekontrolowanej ekstrakcji: limity
rozmiaru i liczby wpisów, odrzucenie ścieżek absolutnych, `..`, symlinków i
urządzeń specjalnych. Raport zawiera wyłącznie typ, wersję, digest, stan
`CURRENT`, `LEGACY_QUARANTINED` albo `RETIRED` oraz zredagowaną lokalizację.

Brama: każdy znaleziony artefakt ma decyzję migracyjną, restore eligibility i
termin retencji.

### Etap 2 — przypięty zestaw migracyjny offline

1. Zaimplementować transakcyjną migrację registry/reinstall z journalem,
   recovery i fault injection.
2. Zaimplementować semantycznie równoważną migrację samodzielnej policy.
3. Zaimplementować pełną modernizację snapshotu WatchNixtoons2.
4. Udostępnić wspólny interfejs `migrate-legacy --dry-run` i `--apply`.
5. Zbudować niezmienny zestaw offline: kod migratorów, fixture, instrukcję,
   wersję runtime, SHA-256 i provenance. Zestaw przechowywać poza ścieżką
   produkcyjnego importu.

Każdy migrator jest idempotentny, używa trybu `0600`, odmawia nieznanego
formatu i nie ujawnia sekretów. Migratory oraz fixture pozostają dostępne do
osobnej, późnej bramy zakończenia retencji.

### Etap 3 — czysta rewizja QNAP i rollout canary

Kolejność zapobiega ponownemu rozpropagowaniu legacy przez Profile Sync:

1. wykonać spójny backup QNAP i inventory hosta, QNAP oraz archiwów;
2. zmigrować lokalne dane źródłowe używane przez publisher;
3. utworzyć nową, niezmienną i czystą rewizję QNAP bez promowania jej na
   `active`;
4. przypisać ją jako `candidate` do BlueStacks, potem X88 Pro;
5. przed każdą zmianą zweryfikować tożsamość urządzenia, zrobić świeży backup i
   przygotować sprawdzony rollback;
6. wykonać apply, report, E2E i drugi przebieg `NO_CHANGE` na canary;
7. po sukcesie promować rewizję i dopiero wtedy wyrównać Sony TV, Bedroom TV,
   `nuc-mwo` i `nuc-alek`;
8. archiwa off-NAS modernizować na końcu bez nadpisywania oryginałów.

Niedostępny target ma stan `PENDING` i blokuje usunięcie produkcyjnego readera,
chyba że zostanie formalnie wycofany z zarządzanego inventory.

### Etap 4 — wydanie przejściowe i dowód

Readery legacy nadal działają, ale emitują zredagowane ostrzeżenie i instrukcję
migracji. Brama wymaga łącznie:

1. każdy zarządzany target raportuje wersję przejściową i zero aktywnego legacy;
2. wszystkie aktywne i candidate assignments QNAP wskazują czyste rewizje;
3. pełny cykl `backup -> sync -> restore -> reconcile` nie odtwarza legacy;
4. audyt cykliczny pozostaje zero przez co najmniej dwa pełne cykle, a nie tylko
   pojedyncze uruchomienie;
5. poprzedni niezmienny obraz, świeże backupy i zestaw migratora offline są
   zachowane przez okres retencji.

### Etap 5 — usunięcie readerów produkcyjnych

Zmiany wykonać w małych, niezależnych PR:

1. usunięcie readera device registry schema 1;
2. usunięcie readera reinstall config schema 1;
3. usunięcie readera standalone profile policy schema 1;
4. przełączenie standardowego restore na odrzucanie
   `LEGACY_QUARANTINED` z instrukcją użycia zestawu offline;
5. opcjonalny, osobny PR Umbrella po kwalifikacji kontraktu upstream.

Z produkcji usunąć stare opcje CLI, stałe i komunikaty. Nie usuwać jeszcze
offline migratorów, ich fixture ani dowodów recovery.

### Etap 6 — zakończenie retencji i porządki

Oddzielna brama pozwala usunąć migrator danego typu dopiero, gdy każdy zachowany
backup:

- formalnie wygasł zgodnie z retencją; albo
- ma zweryfikowany bieżący odpowiednik, który przeszedł restore drill.

Dopiero wtedy można usunąć odpowiadające fixture i `.schema1.bak`, jawnie z
`--apply`, oraz zaktualizować lifecycle manifest. Datowane dowody migracji i E2E
pozostają historią projektu.

## 6. Strategia testów

### 6.1 Hermetyczna brama CI

- bieżące registry, reinstall i policy schema 2;
- klasyfikatory nie mylą aktualnych formatów schema 1 z legacy;
- transakcja dwóch plików: no-op, konflikt kanoniczny, recovery i fault
  injection po każdym możliwym kroku zapisu;
- zachowanie endpointów, ról, `principal_id` i `physical_host_id`;
- semantyczne porównanie decyzji starej i nowej policy;
- bezpieczne skanowanie ZIP/TAR i SQLite read-only;
- pełna modernizacja WatchNixtoons2: favourites, grafiki, katalog add-on,
  addon_data, origin repo, nowy snapshot ID i `migrated_from`;
- odrzucenie standardowego restore dla `LEGACY_QUARANTINED`;
- verify i restore nowego artefaktu;
- potwierdzenie, że restore starego snapshotu pozostaje niezależny od readera
  samodzielnej policy;
- brak sekretów w raportach i logach.

Polecenia bazowe:

```bash
.venv/bin/python -m pytest -q
tests/e2e/run.sh
```

`tests/e2e/run.sh` jest hermetycznym E2E build/repository i nie zastępuje testów
na urządzeniach.

### 6.2 Brama live release

BlueStacks jest pierwszym canary, X88 Pro drugim. Po sukcesie testy obejmują
Sony TV, Bedroom TV i oba profile NUC. Przed destrukcyjną reinstalacją zawsze:

1. potwierdzić serial/model/`physical_host_id`;
2. wykonać świeży backup i verify;
3. sprawdzić działającą ścieżkę rollbacku.

Na każdym celu potwierdzić wersje ze stable lock, identyczną aktywną rewizję,
favourites i miniaturki, brak starego ID WatchNixtoons2, Umbrella/MwoScrapers,
Rapideo, Profile Sync oraz drugi przebieg `NO_CHANGE`.

## 7. CI i kontrola regresji

`tests/test_legacy_boundaries.py` ma:

1. walidować produkcyjne readery i writery względem
   `manifests/schema-lifecycle.json`;
2. dopuszczać stare przykłady wyłącznie w przypiętym zestawie migracyjnym;
3. walidować wygenerowany `docs/schema-lifecycle.md`;
4. wymagać aktualizacji manifestu przy zmianie wersji lub terminu wycofania;
5. blokować aktywne/candidate rewizje QNAP oznaczone jako legacy.

Fixture legacy pozostają do czasu wycofania odpowiadającego im migratora
offline, nawet jeśli produkcyjny reader został już usunięty.

## 8. Rollback

Rollback kodu przywraca poprzedni niezmienny obraz, który czyta także bieżące
schema 2. Dane nie są standardowo obniżane do schema 1. Przy przerwaniu migracji
registry/reinstall recovery korzysta z journala i zweryfikowanego backupu obu
plików. Przy Profile Sync rollback przywraca poprzednie assignment oraz obraz,
nie promuje starej rewizji na inne urządzenia.

## 9. Główne ryzyka

| Ryzyko | Zabezpieczenie |
|---|---|
| migrator znika przed końcem retencji | osobny zestaw offline i oddzielna brama jego wycofania |
| zapisano tylko jeden z dwóch plików | journal, recovery i fault injection transakcji |
| stara rewizja QNAP ponownie rozsyła legacy | clean candidate przed promocją i kontrola wszystkich assignments |
| snapshot odtwarza cały stary add-on | nowy content-addressed artefakt i kwarantanna oryginału |
| policy schema 1 jest mylona ze snapshot schema 1 | klasyfikatory per typ i maszynowy lifecycle manifest |
| backupu QNAP nie da się wyliczyć przez API | spójny backup/download i analiza offline |
| test lokalny jest uznany za test urządzeń | osobne bramy hermetic CI i live release |
| log ujawni sekrety | raport tylko typ, digest, stan i zredagowana lokalizacja |

## 10. Kryteria ukończenia

Wycofanie produkcyjnego legacy jest zakończone, gdy:

1. wszystkie writery tworzą tylko bieżące formaty;
2. inventory nie znajduje aktywnego legacy na hoście, QNAP ani urządzeniach;
3. wszystkie aktywne i candidate assignments QNAP są bieżące;
4. każdy zarządzany target przeszedł live gate albo został formalnie wycofany;
5. pełny cykl backup/sync/restore/reconcile oraz hermetyczne CI przechodzą;
6. drugie uruchomienie daje no-op;
7. readery produkcyjne przyjmują wyłącznie bieżące formaty;
8. poprzedni obraz i zestaw migracyjny offline pozostają dostępne przez
   retencję.

Całkowite wycofanie migratora jest zakończone dopiero po wygaśnięciu lub
modernizacji wszystkich zachowanych backupów i udanym restore drill ich
bieżących odpowiedników.

## 11. Rekomendowana kolejność PR

1. lifecycle manifest, inventory i blokada writerów legacy;
2. transakcyjny zestaw migracyjny offline i jego testy;
3. clean QNAP candidate oraz rollout BlueStacks/X88;
4. promocja QNAP i rollout pozostałych urządzeń;
5. wydanie przejściowe i co najmniej dwa pełne cykle dowodowe;
6. osobne PR usuwające produkcyjne readery registry, reinstall i policy;
7. osobna zmiana standardowego restore i kwarantanny starych snapshotów;
8. po retencji osobne PR wycofujące migratory offline;
9. opcjonalny, niezależny PR Umbrella.

Taki podział utrzymuje OCP dla forków, ogranicza promień błędu i umożliwia
zatrzymanie procesu bez utraty możliwości recovery.
