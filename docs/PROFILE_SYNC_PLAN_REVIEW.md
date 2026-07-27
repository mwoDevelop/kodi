# Niezależny review planu synchronizacji profili Kodi

Data review: 2026-07-27

Przedmiot: `PROFILE_SYNC_PLAN.md`

Tryb: niezależny reviewer, bez prawa edycji plików

## 1. Zakres

Reviewer sprawdził plan pod kątem:

- spójności i braku sprzeczności między etapami;
- realnych ograniczeń dodatku `xbmc.service` na Kodi/Android;
- bezpieczeństwa sekretów, pairing i łańcucha zaufania;
- wersjonowania, CAS, canary, rollbacku i retencji;
- spójności SQLite z content-addressed blob store;
- integracji z istniejącym pipeline repozytorium Kodi;
- wykonalności na BlueStacks, Sony Android TV i QNAP ARMv7;
- odtwarzalnych testów deterministic oraz live E2E.

Review było read-only. Decyzje i zmiany wprowadził maintainer planu po
porównaniu uwag z bieżącymi plikami repozytorium.

## 2. Ustalenia P0 i decyzje

| ID | Ustalenie | Decyzja |
|---|---|---|
| P0-1 | Niemutowalna rewizja zawierała mutowalny `state: candidate`. | Stan kanału przeniesiono do osobnych, podpisanych wskaźników/zdarzeń. Zdefiniowano osobne CAS publish/promote/rollback i idempotency keys. |
| P0-2 | Jedna klasa na cały plik nie oddziela ustawień od tokenów w `settings.xml`. | Routine v2 jest default-deny i używa adapterów per setting. Scope disaster recovery zachowuje schema 1. Enrollment klienta jest zawsze device-local. |
| P0-3 | Usługa działająca w Kodi nie gwarantuje atomowego przywrócenia wszystkich plików. | Gwarancję ograniczono do crash-resilient, kompensacyjnego apply. Adaptery deklarują `hot_apply`, `next_start` lub `host_only`; raw restore pozostaje ścieżką hostową. |
| P0-4 | HTTPS i SHA-256 nie chronią przed przejętym QNAP ani MITM podczas pierwszego pairing. | Dodano weryfikowany bootstrap TLS, podpis rewizji publishera, podpis zdarzenia promotera, pinned public keys i monotoniczną generację kanału. |
| P0-5 | Rollback profilu nie może obiecywać downgrade'u kodu dodatków. | Profil używa constraints i origin, active wymaga kodu dostępnego w stable, a raport rozróżnia cofniętą konfigurację od pozostawionego nowszego kodu. |
| P0-6 | Candidate nie miał realnej ścieżki canary przed globalnym `active`. | Dodano exact assignment per urządzenie, dwustopniowy canary BlueStacks/Sony i podpisaną promocję hostową. |
| P0-7 | Etap bez sekretów wymagał RD playback na czystym consumerze. | Routine E2E rozdzielono od RD. Live RD w tym etapie wymaga hostowego pre-provision, a autonomiczny restore RD należy do etapu szyfrowanych sekretów. |
| P0-8 | Prywatny inventory hosta i registry QNAP nie miały rozdzielonej własności. | Inventory hosta przechowuje endpointy administracyjne; QNAP przechowuje enrollment i heartbeat. Reinstall tworzy nową generację enrollmentu. |

## 3. Ustalenia P1 i decyzje

| ID | Ustalenie | Decyzja |
|---|---|---|
| P1-1 | Brakowało semantycznej allowlisty i granicy multi-profile. | Dodano default-deny per setting; MVP obsługuje tylko domyślny profil Kodi. |
| P1-2 | Nie było protokołu spójności SQLite + blobs. | Dodano upload session, verify/finalize, WAL, transakcje, orphan TTL, leases i spójny backup. |
| P1-3 | Retencja kandydatów była potencjalnie bezterminowa. | Dodano TTL, quota liczby/bajtów i mały trwały audit record. |
| P1-4 | Integracja dodatku z głównym repo była niejednoznaczna. | Dodatek jest osobnym repo/submodułem i komponentem locków; serwer nie jest submodułem, a Compose pinuje image digest. |
| P1-5 | Limit odświeżenia repo mógł blokować wymagany kod. | Native updater pozostaje domyślny; brak wymaganej wersji pozwala na jeden wymuszony refresh i odroczenie apply. |
| P1-6 | Brakowało procesu aktualizacji serwera QNAP. | Dodano backup, preflight migracji, deploy po digescie, health check i rollback bez Watchtower. |
| P1-7 | Build ARMv7 nie dowodzi działania na QNAP. | Wymagany jest runtime smoke obrazu, SQLite i TLS na rzeczywistym QNAP ARMv7. |
| P1-8 | Graf błędnie uzależniał cały development od naprawy RAID. | Lokalny development może biec równolegle; zdrowy RAID blokuje tylko produkcyjne storage/deployment QNAP. |
| P1-9 | Brakowało feasibility gate dla bezpiecznego klucza na Androidzie. | Dodano spike Keystore/equivalent, reinstall, revocation, ARMv7/x86 i zakaz plaintextu w stagingu/journalu. |
| P1-10 | Test corrupt revision mylił preflight failure z rollbackiem po apply. | Rozdzielono zero-mutation validation failure od health failure i kompensacyjnego rollbacku; dodano crash/disk/network/schema testy. |

## 4. Elementy odrzucone lub odłożone

- promocja i admin w codziennym dodatku Kodi — odrzucone na rzecz hostowego
  admin CLI;
- kopiowanie całych mieszanych `settings.xml` jako portable — odrzucone;
- dokładny downgrade kodu dodatków przez profil — odrzucony;
- generyczna podmiana wszystkich plików Kodi przez `xbmc.service` — odrzucona;
- submodule serwera w repo nadrzędnym — odrzucony;
- automatyczny update kontenera z ruchomego tagu — odrzucony;
- automatyczna synchronizacja sekretów w pierwszym wydaniu — odłożona do czasu
  pozytywnego feasibility gate i osobnego E2E;
- P2P, SMB jako API, PostgreSQL, QPKG i automatyczna promocja — pozostają poza
  MVP zgodnie z pierwotną decyzją.

## 5. Niezależna weryfikacja maintainera

Lokalna kontrola potwierdziła, że obecna polityka schema 1:

- obejmuje kod dodatków i szerokie `userdata/addon_data/**`;
- jawnie zachowuje credentiale Umbrelli w disaster-recovery snapshot;
- wymaga zatrzymania Kodi przez host/ADB przed pełnym restore;
- ma istniejący mechanizm kontroli origin dodatków.

Potwierdza to potrzebę rozdzielenia schema 1 disaster recovery od nowego,
semantycznego routine sync. Oficjalna dokumentacja Kodi potwierdza także, że
service startuje wewnątrz procesu Kodi, instalacja dodatku jest operacją
asynchroniczną, a ingerencja w dane innych dodatków wymaga jawnej zgody i nie
powinna opierać się na bezwarunkowej podmianie plików.

## 6. Follow-up review po pierwszej korekcie

Reviewer ponownie sprawdził pełny plan. Wskazał trzy pozostające luki high i
siedem medium; wszystkie zostały uznane za zasadne:

| ID | Ustalenie follow-up | Zastosowana korekta |
|---|---|---|
| H1 | Assignment canary i raporty nie miały własnego podpisu. | Assignment/revocation podpisuje promoter, raport podpisuje klucz enrollmentu; promocja weryfikuje exact revision, nonce, generację i podpisane raporty. |
| H2 | Jeden „klucz urządzenia” mieszał uwierzytelnienie MVP z późniejszym szyfrowaniem sekretów. | Rozdzielono enrollment signing key od encryption key; przenośne podpisy są bramą MVP, a bezpieczny Keystore pozostaje bramą etapu sekretów. |
| H3 | Zakaz plaintextu „poza pamięcią” przeczył trwałym credentialom Umbrelli/RD. | Zakaz dotyczy dodatkowych kopii synchronizatora. Plan jawnie akceptuje plaintext w docelowym userdata i brak ochrony at-rest tych ustawień. |
| M1 | Nazwy `device_id`, logical device i enrollment były mieszane. | Host używa `logical_device_id`; instalacja ma `enrollment_id` i `enrollment_generation`; assignment API używa enrollmentu. |
| M2 | Assigned candidate mógł wygasnąć przez TTL/GC. | Assignment, wymagany raport i approval są GC roots; TTL zaczyna biec dopiero po rozstrzygnięciu. |
| M3 | Diagram umieszczał addon testing po E2E profilu. | Addon testing poprzedza device E2E; profile active i addon stable mają osobne ręczne promocje. |
| M4 | Harmonogram sugerował refresh repo przy każdym starcie. | Pozostawiono native updater Kodi; synchronizator wymusza refresh tylko dla niespełnionej zależności. |
| M5 | Stan `ACTIVE` był niejednoznaczny dla canary. | Stan nazwano `APPLIED`, a raport zawiera assignment kind i exact revision. |
| M6 | `next_start` mógł przegrać wyścig z inicjalizacją Kodi. | `next_start` używa tylko wspieranego API po starcie; wcześniejszy zapis jest `host_only`. |
| M7 | Retencja wszystkich historycznych active była bezterminowa. | Payload zachowuje ostatnie N i jawnie przypięte rewizje; reszta pozostawia mały audit record. |

Po tej korekcie nie pozostaje znana sprzeczność high ani medium w
kontrolowanym zakresie planu.

## 7. Wynik

Po korektach plan jest spójny jako architektura etapowa. Nie obiecuje już
niemożliwej globalnej atomowości ani rollbacku kodu, ma wykonalny canary,
oddziela profile routine od disaster recovery i definiuje zaufanie między
publisherem, promoterem, QNAP i klientem.

Otwarte pozostają dwie jawne bramy implementacyjne:

- przenośna implementacja enrollment signing i weryfikacji podpisów na Kodi
  ARMv7/x86 — blokuje MVP;
- bezpieczne przechowywanie osobnego encryption key na Kodi/Android — blokuje
  wyłącznie automatyczny restore sekretów.

Jeżeli druga brama nie przejdzie, szyfrowany hostowy backup pozostaje końcowym
mechanizmem sekretów; nie blokuje to MVP ustawień niesekretnych.
