# Niezależna recenzja planu QNAP Control Plane i autonomicznej konwergencji Kodi

Data recenzji: 2026-08-13

Recenzowany dokument:
[`QNAP_CONTROL_PLANE_DEVICE_CONVERGENCE_PLAN.md`](../QNAP_CONTROL_PLANE_DEVICE_CONVERGENCE_PLAN.md)

## 1. Zakres i metoda

Recenzja porównuje plan z rzeczywiście istniejącymi kontraktami i granicami:

- serwera `kodi-profile-sync-server`, w szczególności assignment schema 2,
  enrollment, podpisy, idempotency i SQLite;
- dodatku `service.mwodevelop.profilesync`, w szczególności harmonogramu,
  capability gate, journalu, rollbacku i lokalnego stanu;
- hostowego rolloutu stable, polityki routine/disaster recovery oraz locków
  artefaktów;
- wdrożeń QNAP ARMv7 i ich aktualnego cyklu życia w Container Station;
- wymagań bezpieczeństwa sekretów, podpisów, UI, migracji, recovery i pełnego
  release.

To jest review projektu, a nie review gotowej implementacji. Obecny kod nie
zawiera jeszcze control plane, secret store ani autonomicznego zarządzania kodem
dodatków.

## 2. Werdykt

Kierunek architektoniczny jest właściwy: QNAP jako stale dostępny control plane,
urządzenia działające w modelu pull, brak rutynowej zależności od ADB/SSH i
pozostawienie GitHub jako źródła kodu oraz publikacji. Rozszerzenie istniejącego
Profile Sync zamiast tworzenia drugiego agenta również jest rozsądne.

Plan nie powinien jednak wejść w fazę mutującą urządzenia ani importującą sekrety,
dopóki nie zostanie zamkniętych pięć uwag P0. Najważniejsze niespójności to:

1. autonomiczny kontroler nie ma wykonalnego modelu podpisywania krótkotrwałych
   assignmentów;
2. natywne automatyczne aktualizacje Kodi mogą ominąć fale QNAP zaraz po publikacji
   stable;
3. profil, lock dodatków i koperty sekretów nie mają jednego atomowego,
   podpisanego punktu odniesienia;
4. plan zakłada kontrolę dokładnego artefaktu, której sam natywny updater Kodi nie
   dowodzi;
5. self-update działającej usługi i zgodność klienta N-1 nie mają wykonalnego
   protokołu przejścia.

Po zastosowaniu zmian rekomendowanych poniżej plan jest spójny i nadaje się do
realizacji etapowej. Read-only pierwszy przyrost może rozpocząć się wcześniej,
pod warunkiem że nie tworzy jeszcze assignmentów i nie przyjmuje sekretów.

## 3. Podsumowanie priorytetów

| ID | Priorytet | Uwaga | Bramka |
|---|---|---|---|
| P0-1 | P0 | Brak autonomicznej, ograniczonej władzy podpisywania assignmentów i obsługi ich wygaśnięcia | przed mutującym rolloutem |
| P0-2 | P0 | Stable auto-update Kodi omija fale QNAP | przed rolloutem kodu dodatków |
| P0-3 | P0 | Brak jednego immutable convergence bundle i atomowego publish | przed importem sekretów i desired state |
| P0-4 | P0 | Podpisany digest locka nie dowodzi bajtów faktycznie zainstalowanego dodatku | przed autonomiczną instalacją dodatków |
| P0-5 | P0 | Circular self-update Profile Sync i brak protokołu N-1 -> N | przed wydaniem Device Agenta |
| P1-1 | P1 | Heartbeat nie utrwala capability/platformy, a schema desired state nie ma lifecycle | przed capability-aware assignment |
| P1-2 | P1 | Rollback jest sagą kompensacyjną, nie globalną transakcją | przed deklaracją pełnej konwergencji |
| P1-3 | P1 | Model sekretów i ich rotacji/recovery jest niepełny | przed usunięciem plaintextu z localhost |
| P1-4 | P1 | QNAP jest control-plane SPOF bez jawnego RPO/RTO i cold restore | przed produkcyjnym cutoverem |
| P1-5 | P1 | Offline/deferred nie obsługuje wygaśnięcia, supersession i wielu zaległych rolloutów | przed pełną flotą |
| P1-6 | P1 | WebAuthn/signer wymaga stabilnego originu, bootstrapa i jednoznacznego modelu zatwierdzenia | przed mutującym UI |
| P1-7 | P1 | Pairing i consumer API wymagają dodatkowej ochrony przed nadużyciem w LAN | przed przejęciem enrollmentów przez UI |
| P1-8 | P1 | Append-only audit na tym samym QNAP nie jest odporny na administratora/roota | przed uznaniem audytu za dowód |
| P1-9 | P1 | Brak jednej własności inventory i bezpiecznego cutoveru `.env` | przed usunięciem hostowego źródła prawdy |
| P1-10 | P1 | GitHub App i atestacje nie mają kompletnego kontraktu weryfikacji supply chain | przed dispatch z UI |
| P2-1 | P2 | Osobne repo control plane zwiększa koszt wersjonowania kontraktów | decyzja ADR |
| P2-2 | P2 | Szacunek nie zawiera bufora na Kodi API, WebAuthn ARMv7 i migracje sekretów | aktualizacja harmonogramu |

## 4. Uwagi P0

### P0-1 — autonomiczny rollout nie ma wykonalnego modelu podpisywania assignmentów

**Dowód.** Plan jednocześnie wymaga autonomicznego pull rolloutu
([plan, sekcja 3](../QNAP_CONTROL_PLANE_DEVICE_CONVERGENCE_PLAN.md#3-decyzja-architektoniczna))
i świeżego zatwierdzenia operatora dla każdego podpisu, przy zachowaniu obecnego
offline signera ([plan, sekcja 4](../QNAP_CONTROL_PLANE_DEVICE_CONVERGENCE_PLAN.md#4-zasady-nienaruszalne),
[sekcja 5.4](../QNAP_CONTROL_PLANE_DEVICE_CONVERGENCE_PLAN.md#54-administracyjne-api-i-ui)).
Obecny serwer jawnie nigdy nie podpisuje assignmentów
(`kodi-profile-sync-server/src/profile_sync_server/store.py:1213-1227`), a assignment
schema 2 jest ważny maksymalnie siedem dni
(`kodi-profile-sync-server/src/profile_sync_server/store.py:160-171`). Urządzenie
wracające po dłuższej przerwie nie może więc zastosować starego `DEFERRED`.

**Skutek.** Bez klucza online QNAP nie odnowi assignmentu urządzenia offline i nie
zrealizuje autonomii. Umieszczenie pełnego klucza promotora na QNAP usunęłoby
dotychczasową granicę bezpieczeństwa i dało przejętemu NAS możliwość zatwierdzenia
dowolnego profilu.

**Rekomendowana zmiana tekstu planu.** Dodać ADR `trust-and-signing` przed
`desired-state-v1` i wybrać dokładnie jeden z modeli:

1. preferowany: offline root/promoter zatwierdza immutable `release_intent_id`,
   dokładny digest convergence bundle, kanał i maksymalny zbiór urządzeń; osobny,
   rotowalny **online assignment key** na QNAP może wyłącznie wystawiać
   krótkotrwałe assignmenty związane z tym intentem, enrollmentem i falą;
2. alternatywny: każda fala wymaga podpisu urządzenia operatora, a system nie jest
   nazywany autonomicznym dla urządzeń wracających po wygaśnięciu podpisu.

Klucz online nie może mieć roli `promote`, `admin`, `revision` ani podpisywać innego
digestu. Serwer musi wymuszać delegację kryptograficznie, nie tylko przez UI.
Reissue po heartbeat ma zachowywać intent i generację, ale otrzymywać nowy nonce i
termin. Kompromitacja klucza online ma mieć procedurę revocation, rotacji i
odtworzenia. Test negatywny musi dowieść, że klucz assignment nie może podpisać
promocji lub innego bundle.

### P0-2 — native auto-update Kodi jest sprzeczny z falami QNAP

**Dowód.** Plan pozostawia standardowe automatyczne aktualizacje Kodi, publikuje kod
wyłącznie do stable i równocześnie oczekuje fal BlueStacks -> X88 -> reszta
([plan, sekcje 4, 5.6 i 5.7](../QNAP_CONTROL_PLANE_DEVICE_CONVERGENCE_PLAN.md)).
Po opublikowaniu nowszej wersji w jednym globalnym stable Kodi może zaktualizować
wszystkie urządzenia, zanim QNAP przydzieli ich falę. Obecny hostowy rollout nie
jest dowodem przeciwnego zachowania: pobiera dokładne ZIP-y według locka i instaluje
je przez host/ADB (`tools/kodi_android_stable_rollout.py:176-220`), czego docelowy
agent ma nie robić.

**Skutek.** Kontroler fal staje się tylko obserwatorem. Błąd kodu może dotrzeć do
całej floty przed sukcesem canary, a osobne statusy `addon rollout` nie odzyskają
utraconej bramy.

**Rekomendowana zmiana tekstu planu.** Przed fazą E dodać ADR
`addon-update-channel-strategy` i jawnie rozdzielić dwa dopuszczalne modele:

- **model rekomendowany:** testing/candidate służy wyłącznie podpisanym canary,
  po ich sukcesie następuje publikacja stable; stable jest globalną falą i QNAP
  raportuje jej konwergencję, ale nie udaje, że może ją dawkować per urządzenie;
- **model prawdziwie falowy:** automatyczne aktualizacje zarządzanych dodatków są
  jawnie wyłączone polityką, agent instaluje dokładny zatwierdzony artefakt per
  assignment, a użytkownik otrzymuje opis konsekwencji i ścieżkę recovery.

Nie wolno łączyć obu modeli. Jeśli pozostaje natywny auto-update, kryteria release
mają mówić `testing canary -> stable global -> fleet verification`, a nie
`stable per-device waves`.

### P0-3 — brak jednego atomowego convergence bundle

**Dowód.** Control plane ma łączyć profil z lockiem, secret store pozostaje osobno,
a Profile Sync nadal jest właścicielem rewizji i assignmentów
([plan, sekcje 5.1-5.3](../QNAP_CONTROL_PLANE_DEVICE_CONVERGENCE_PLAN.md)). Nie ma
jednego identyfikatora wiążącego dokładne:

- `profile_revision_id`;
- lock/repository snapshot;
- wersje adapterów;
- `secret_set_version` i digest każdej koperty;
- rollout/wave/policy.

Istniejący raport wiąże się z `assignment_id`, enrollmentem, generacją kanału i
`revision_id`, ale nie z przyszłym lockiem ani zestawem sekretów
(`kodi-profile-sync-server/src/profile_sync_server/store.py:1313-1405`).

**Skutek.** Awaria między zapisem dwóch usług może opublikować profil odnoszący się
do brakującej koperty albo raportować sukces rewizji mimo innego kodu dodatku.
Idempotency key per endpoint nie zapewnia atomowości między dwiema bazami i
kontenerami.

**Rekomendowana zmiana tekstu planu.** Wprowadzić immutable, content-addressed
`convergence_bundle_v1` i stan `PREPARING -> READY -> ASSIGNED`. Bundle musi zawierać
digest całego dokumentu i dokładne identyfikatory wszystkich wyżej wymienionych
składników. Najpierw należy zapisać oraz zweryfikować wszystkie rewizje, artefakty i
koperty, potem jednym CAS opublikować gotowy bundle, a dopiero potem wystawić
assignment. Nie wolno nadpisywać kopert używanych przez bundle. Raport urządzenia
musi wiązać `bundle_id`, `assignment_id`, wszystkie zastosowane digests oraz osobne
statusy code/profile/secrets/health. GC nie usuwa składnika bundle aktywnego,
przypisanego, raportowanego ani objętego retencją rollbacku.

Globalnej atomowości na urządzeniu nie należy obiecywać: to jest crash-resilient
saga z jednoznacznym journalem i raportem częściowym.

### P0-4 — native repo nie dowodzi dokładnych bajtów wskazanych przez lock

**Dowód.** Lock stable posiada SHA-256 ZIP każdego zarządzanego dodatku
(`manifests/locks/stable.json`), a plan chce raportować digest locka. Natywny updater
Kodi pobiera jednak indeks i ZIP z tego samego originu; sam wynik `ID/version/origin`
nie dowodzi, że zainstalowane bajty odpowiadają podpisanemu `zip_sha256`. Plan
zabrania alternatywnego instalatora ZIP i przewiduje tylko weryfikację stanu po
instalacji ([plan, sekcja 5.6](../QNAP_CONTROL_PLANE_DEVICE_CONVERGENCE_PLAN.md#56-kodi-device-agent)).

**Skutek.** Przejęcie GitHub Pages/repozytorium może podać zmienione ZIP i indeks o
tej samej wersji. Podpis desired state chroni intencję, ale nie wymusza artefaktu,
który faktycznie pobrał Kodi.

**Rekomendowana zmiana tekstu planu.** ADR supply-chain musi określić realną granicę
zaufania i jedną weryfikowalną ścieżkę:

- podpisać offline manifest release zawierający SHA-256 ZIP i tożsamość repo;
- agent przed instalacją lub bezpośrednio po niej musi uzyskać dowód bajtów zgodny
  z tym manifestem; jeżeli Kodi API nie udostępnia pobranego ZIP, należy
  kwalifikować deterministyczny tree digest zainstalowanego katalogu albo uznać,
  że dokładny pin jest niewykonalny z natywnym updaterem;
- raport nie może nazywać statusu `VERIFIED`, jeśli sprawdzono tylko ID, wersję i
  origin; taki status ma być `ORIGIN_VERSION_ONLY`;
- weryfikacja atestacji GitHub musi wiązać repository, workflow identity, commit,
  artifact digest i publiczne bajty, a nie tylko powodzenie runu.

Jeśli nie da się uzyskać dowodu exact bytes bez instalatora zarządzanego, plan musi
jawnie wybrać zaufanie do GitHub Pages + Kodi updater jako ograniczenie MVP.

### P0-5 — circular self-update i klient N-1

**Dowód.** Plan nakazuje działającej usłudze zaktualizować samą siebie i „zrestartować
usługę” przed dalszym apply ([plan, sekcja 5.6](../QNAP_CONTROL_PLANE_DEVICE_CONVERGENCE_PLAN.md#56-kodi-device-agent)).
Obecny `xbmc.service` ładuje moduły raz w procesie Kodi (`profile-sync-addon/service.py`),
a runtime wykonuje pętlę co sześć godzin
(`profile-sync-addon/resources/lib/mwoprofilesync/runtime.py:44-82`). Obecny klient
rozumie tylko assignment schema 2 i revision schema 2/3, a brak capability kończy
się błędem przed apply
(`profile-sync-addon/resources/lib/mwoprofilesync/sync.py:130-159, 245-347`).

**Skutek.** Podmieniony kod dodatku nie staje się automatycznie kodem bieżącego
procesu. Stary agent może nie rozumieć instrukcji, która ma go zaktualizować, albo
kontynuować apply starym kodem po asynchronicznym update.

**Rekomendowana zmiana tekstu planu.** Dodać osobny dwufazowy protokół bootstrap:

1. stabilny, minimalny `agent_bootstrap_v1`, rozumiany co najmniej przez klienta
   N-1, zawiera tylko minimalną wersję, dozwolony origin i expected digest;
2. agent zleca natywny update, zapisuje `UPGRADE_PENDING`, kończy bieżący przebieg
   bez stosowania bundle i nie próbuje przeładowywać własnych modułów;
3. dopiero nowa instancja usługi po restarcie Kodi potwierdza wersję/capability,
   czyści `UPGRADE_PENDING` i pobiera normalny assignment;
4. timeout kończy się `CLIENT_UPGRADE_REQUIRED` albo
   `CLIENT_UPGRADE_REQUIRES_USER`, bez mutacji pozostałych składników;
5. N-2, nieznany schemat oraz niezgodne Kodi/Python mają jawny runbook ręcznego
   bootstrapu.

Przed wpisaniem konkretnego builtina jako kontraktu należy wykonać spike na Kodi
Android i Flatpak: odświeżenie repo, instalacja zależności, update włączonego
`xbmc.service`, restart Kodi, błędny ZIP i brak UI. Samo istnienie nazw
`UpdateAddonRepos`/`UpdateLocalAddons` nie jest dowodem bezpiecznej, synchronicznej
instalacji.

## 5. Uwagi P1

### P1-1 — schema i capabilities nie mają kompletnego lifecycle

Obecny heartbeat odbiera `client_version` i `client_capabilities`, lecz serwer
utrwala tylko `last_seen_at`
(`kodi-profile-sync-server/src/profile_sync_server/store.py:796-818`). Plan chce
wybierać fallback według capabilities, więc control plane nie ma jeszcze
autorytatywnego stanu do takiej decyzji.

Dodać:

- osobne, wersjonowane schematy `desired_state`, `convergence_bundle`,
  `secret_envelope`, `convergence_report`, `rollout_plan` i `audit_event` do
  `manifests/schema-lifecycle.json`;
- persist ostatniego podpisanego/uwierzytelnionego heartbeat capability snapshot z
  timestampem, bez używania self-reportu do przyznawania uprawnień;
- macierz server N/N-1, agent N/N-1, DB schema, assignment/revision/bundle schema;
- expand/contract migrations, mixed-version E2E, downgrade/read-only i fail-closed
  dla nieznanego schematu;
- zasadę, że starszy agent nigdy nie dostaje bundle, którego nie rozumie.

### P1-2 — apply nie jest i nie będzie globalną transakcją

Aktualny applier ma fsyncowany journal i kompensuje ustawienia/favourites
(`profile-sync-addon/resources/lib/mwoprofilesync/apply.py:281-387`). Nie obejmuje
jednak kodu dodatków, skutków ubocznych ich startu, zewnętrznej rotacji tokenu ani
stanu utrzymywanego przez Kodi w pamięci. Stwierdzenie o „transakcyjnym apply” w
opisie stanu wyjściowego jest zbyt szerokie.

Zmienić terminologię na `journaled, crash-resilient, compensating apply`. Dodać
preflight wszystkich składników przed pierwszą mutacją, kolejność
agent/repo/addons/settings/secrets/health, barrier po restarcie Kodi oraz jawne
stany `PARTIAL`, `ROLLBACK_PENDING`, `ROLLBACK_REQUIRES_HOST` i
`CODE_UPDATED_CONFIG_REVERTED`. Nie promować bundle po częściowym raporcie.

### P1-3 — secret lifecycle, rotacja i recovery są niepełne

Plan prawidłowo oddziela sekret od rewizji i przyznaje, że root QTS może go
odczytać. Należy jeszcze doprecyzować:

- „odszyfrowuje tylko urządzenie” dotyczy koperty dystrybucyjnej; proces secret
  store i root QTS mają dostęp do plaintextu w przyjętym threat modelu;
- klucz koperty jest generowany na urządzeniu, a nie „otrzymywany” od serwera;
- wymagania dla storage klucza na Android/Flatpak, zachowanie przy braku hardware
  keystore oraz zakaz dołączania go do portable/disaster-recovery profile;
- reinstall tworzy nową parę kluczy/enrollment i nową kopertę; stare koperty oraz
  token są revoke, lecz stary ciphertext pozostaje przez retencję audytową;
- rotacja wspólnego sekretu ma stany `PREPARED -> DISTRIBUTING -> VERIFIED ->
  RETIRE_OLD`, osobne koperty per enrollment i okres współistnienia starej wersji;
- adapter nie nadpisuje działającego tokenu przed preflightem; jeżeli usługa nie
  pozwala sprawdzić credentialu bez aktywacji, raportuje ograniczenie i zachowuje
  lokalny slot rollback;
- off-QNAP recovery kit zawiera zaszyfrowany spójny secret DB + KEK metadata +
  restore instructions, a odzyskanie jest ćwiczone od pustego hosta;
- usunięcie plaintextu z localhost następuje dopiero po dwóch niezależnie
  zweryfikowanych kopiach recovery i pełnym restore drill.

### P1-4 — QNAP jako SPOF wymaga kontraktu degraded mode i cold restore

Zachowanie ostatniego dobrego stanu na urządzeniu jest poprawne, ale awaria QNAP
blokuje pairing, rotacje, nowe assignmenty i administrację. Backup na tym samym NAS
nie rozwiązuje utraty urządzenia ani KEK.

Dodać RPO/RTO, szyfrowany backup poza QNAP, minimalny cold-standby Compose bundle,
DNS/certyfikat po restore, procedurę odtworzenia na zastępczym hoście oraz test
utraty całego QNAP. W degraded mode Kodi ma dalej odtwarzać z lokalnymi tokenami,
nie ma usuwać konfiguracji z powodu TTL, a UI ma jawnie pokazywać stale/offline.

### P1-5 — `DEFERRED` potrzebuje supersession i semantyki zakończenia

Plan nie określa, co zrobić, gdy urządzenie wraca po terminie albo ominęło kilka
rolloutów. Dodać:

- `eligible`, `temporarily_offline`, `deferred`, `expired`, `superseded`,
  `retired` i `excluded_with_reason`;
- jedno bieżące desired intent per enrollment; nowszy active superseduje starsze
  nieaplikowane plany zamiast odtwarzania całej kolejki;
- świeży assignment generowany po heartbeat tylko dla nadal zatwierdzonego intentu;
- rozdzielenie `rollout completed for required online set` od
  `fleet fully converged`;
- jawny deadline i decyzję operatora dla urządzenia nieobecnego, bez wiecznego
  blokowania kanału i bez cichego pominięcia.

### P1-6 — UI/WebAuthn i signer wymagają wykonalnego bootstrapu

WebAuthn nie jest mechanizmem „odblokowania klucza” samym w sobie. Plan powinien
zdefiniować stabilną nazwę DNS/RP ID, certyfikat zaufany przez przeglądarkę, NTP,
origin, rejestrację pierwszego operatora, co najmniej dwa passkeys, recovery codes i
test przeglądarek używanych do QNAP. Użycie rozszerzenia WebAuthn PRF do wyprowadzania
klucza wymaga osobnego spike; bez niego passkey zatwierdza challenge, a dedykowany
signer egzekwuje politykę.

Rozdzielenie `operator`/`approver` nie oznacza automatycznie zasady dwóch osób.
Należy jawnie wybrać: jedna osoba z re-auth w instalacji domowej albo wymuszona
różna tożsamość przy two-person approval. Mutujące UI nie może być bramą odzyskania,
jeżeli utracono jedyną passkey.

### P1-7 — pairing wymaga rate limit i potwierdzenia tożsamości urządzenia

Obecny kod używa ośmiocyfrowego, jednorazowego kodu i generacji enrollmentu, co jest
dobrą bazą (`kodi-profile-sync-server/src/profile_sync_server/store.py:674-770`).
Plan powinien dodatkowo wymagać rate limit per IP i globalnie, krótkiego TTL,
ograniczonej liczby aktywnych kodów, backoffu, audytu prób, unieważnienia kodu po
sukcesie i pokazania operatorowi fingerprintu klucza oraz deklarowanej tożsamości
urządzenia do potwierdzenia. Kod pairing nie może autoryzować roli administracyjnej.

### P1-8 — audit powinien być tamper-evident i eksportowany poza QNAP

`append-only` w SQLite na tym samym QNAP nie chroni przed rootem QTS ani restore
starego backupu. Dodać hash chain/HMAC lub podpisane okresowe checkpointy,
monotoniczny sequence, wykrywanie braków oraz cykliczny eksport zredagowanych
checkpointów poza QNAP. Dokumentacja ma nazywać to `tamper-evident`, nie
`tamper-proof`.

### P1-9 — cutover inventory wymaga jednej macierzy własności

Plan uznaje QNAP za kanoniczny inventory, lecz pozostawia host jako bootstrap i
break-glass. Należy spisać per pole właściciela: logical ID/enrollment/capabilities na
QNAP, endpoint ADB/SSH z TTL jako opcjonalna informacja operacyjna, a dane dostępu
break-glass wyłącznie w zaszyfrowanym recovery kit. CLI hosta po cutover domyślnie
czyta redacted inventory przez QNAP i nie mutuje lokalnego `.env`. Trzeba zostawić
minimalną, udokumentowaną ścieżkę odkrycia QNAP po utracie DNS/control plane.

### P1-10 — GitHub App i atestacje wymagają kontraktu allowlist

Allowlista powinna wiązać owner/repository, dokładny workflow path/ref, dozwolone
inputy, branch/ref i maksymalną częstotliwość. QNAP nie powinien akceptować samego
statusu `success`; weryfikuje issuer GitHub OIDC/attestation, subject/repository,
workflow identity, commit, artifact SHA-256 i publiczny digest. Dispatch i odczyt
atestacji powinny używać osobnych minimalnych instalacyjnych uprawnień, jeśli GitHub
na to pozwala. GitHub outage nigdy nie unieważnia ostatniego lokalnego stable.

## 6. Uwagi P2 i korekty redakcyjne

### P2-1 — granice repozytoriów

Osobny proces i osobna powierzchnia uprawnień są ważniejsze niż osobne repo. Przed
utworzeniem czwartego repo należy ADR-em porównać monorepo z
`kodi-profile-sync-server` kontra osobne `kodi-control-plane`, uwzględniając
wersjonowanie OpenAPI, obrazu, migracji i wspólne E2E. Nie łączyć jednak admin UI z
consumer listenerem ani nie współdzielić bezpośrednio tabel SQLite.

### P2-2 — koszt

Szacunek 25-53 dni nie uwzględnia ryzyka spike Kodi API/self-update, WebAuthn na
ARMv7, cross-service protocol, migracji realnych credentiali i off-box disaster
recovery. Po zamknięciu ADR P0 należy wykonać ponowną estymację; rozsądny jest bufor
30-50% oraz osobne kryterium stop/go po każdym spike.

Dodatkowo w sekcji stanu wyjściowego należy zastąpić „apply transakcyjny” przez
„journaled apply z kompensacyjnym rollbackiem”. W kryteriach release dopisać, że
`NO_CHANGE` musi dotyczyć tego samego `bundle_id`, nie tylko rewizji profilu.

## 7. Rekomendowana korekta kolejności realizacji

1. **Faza 0A — kontrakty przed kodem:** threat model oraz ADR trust/signing,
   addon update strategy, supply-chain/exact bytes, secret envelope, schema
   lifecycle i inventory ownership.
2. **Faza 0B — spiki go/no-go:** self-update N-1 -> N na Android/Flatpak,
   install/update przez Kodi API, HPKE/AEAD na ARMv7/x86 i WebAuthn na docelowej
   przeglądarce/QNAP.
3. **Faza 1 — read-only control plane:** fleet/status/GitHub, mTLS CLI,
   tamper-evident audit, backup i ARMv7; bez sekretów i mutacji.
4. **Faza 2 — bundle i serwer:** immutable convergence bundle, capability
   heartbeat, constrained assignment signer/delegation, prepare/CAS/report oraz
   mixed-version migrations.
5. **Faza 3 — secret store shadow:** import, koperty, rotacja, off-QNAP recovery i
   test izolacji; localhost nadal źródłem wykonania.
6. **Faza 4 — agent settings/secrets:** najpierw audit, potem BlueStacks/X88,
   journal/saga/rollback i drugi przebieg `NO_CHANGE` dla exact bundle.
7. **Faza 5 — dodatki:** realizacja wyłącznie według wybranego ADR kanałów;
   testing canary lub prawdziwe fale z wyłączonym auto-update.
8. **Faza 6 — UI i migracja kontroli:** mutujące RBAC/WebAuthn, GitHub App,
   pause/resume/supersession, cutover inventory i usunięcie plaintextu dopiero po
   restore drill.
9. **Faza 7 — bootstrap i pełny release:** czysta instalacja, offline/expired,
   utrata QNAP, pełna flota, dokumentacja i niezależny security review bez P0/P1.

## 8. Wymagane uzupełnienie dokumentacji

Plan wymienia dokumentację ogólnie, ale pełny release powinien mieć jawny backlog
dokumentacyjny. Dodać do każdej fazy obowiązek aktualizacji dokumentacji w tym samym
PR co zmiana kontraktu lub operacji.

### 8.1 Nowa dokumentacja control plane

Utworzyć indeks `docs/control-plane/README.md` i co najmniej:

- `architecture.md` — granice GitHub/QNAP/Profile Sync/agent/host, diagramy trust i
  data flow;
- `threat-model.md` — aktywa, aktorzy, kompromitacja QNAP, LAN, GitHub i urządzenia,
  jawne ograniczenia ochrony przed rootem QTS;
- `signing-and-trust.md` — root/promoter/online assignment/device/GitHub
  attestation, delegacja, rotacja i revocation;
- `desired-state-and-schemas.md` — bundle, assignment, envelope, report, migracje,
  kompatybilność N/N-1 i supersession;
- `qnap-install.md` — Container Station, ARMv7, digest obrazu, UID/GID, ACL,
  wolumeny, DNS/TLS, firewall i widoczność w GUI;
- `admin-ui-cli.md` — bootstrap operatora, passkeys/TOTP/recovery, role, re-auth,
  allowlistowane akcje i zredagowane przykłady;
- `github-app.md` — instalacja, minimalne uprawnienia, allowlista workflow,
  attestation verification i rotacja klucza;
- `secrets.md` — klasyfikacja, import shadow, envelope, device key, rotacja,
  revocation, redaction i ograniczenia threat modelu;
- `device-bootstrap.md` — czysta instalacja Android/Flatpak, pairing, fingerprint,
  N-1 upgrade i scenariusz wymagający użytkownika;
- `rollout.md` — audit/apply, testing/stable strategy, canary, pause/resume/cancel,
  offline/deferred/expired/superseded, `NO_CHANGE` i interpretacja raportów;
- `backup-restore-dr.md` — RPO/RTO, backup poza QNAP, KEK/recovery key, restore od
  pustego hosta, rollback obrazu + schema oraz cykliczny drill;
- `incident-response.md` — utrata passkey, klucza assignment, GitHub App,
  enrollmentu, urządzenia albo QNAP; revocation i break-glass;
- `troubleshooting.md` — certyfikat/czas, brak heartbeat, upgrade pending,
  częściowy apply, provider/VPN versus control-plane oraz bezpieczne dane do raportu;
- wersjonowane OpenAPI i przykłady payloadów pozbawione sekretów.

### 8.2 Aktualizacja istniejącej dokumentacji

W tych samych etapach aktualizować:

- główne `README.md` i `docs/README.md` jako nawigację;
- `docs/kodi-operations.md` — host jako wrapper QNAP i break-glass;
- `docs/kodi-private-profile.md` — nowa własność inventory/sekretów oraz co nadal
  jest device-local;
- `docs/scheduled-processes.md` — agent checks, backup, restore drill, watchdog,
  certificate/key rotation i ich alarmy;
- `docs/qnap-images.md` i `deploy/qnap-control-plane/README.md` — build/deploy/status
  czwartego obrazu;
- `docs/schema-lifecycle.md` i `manifests/schema-lifecycle.json` — wszystkie nowe
  schematy i zasady usuwania compatibility;
- README serwera i dodatku Profile Sync — consumer/admin surface, capability,
  upgrade, envelopes i stany convergence;
- `docs/e2e-results/README.md` — format zredagowanych dowodów z rolloutów i restore.

### 8.3 Bramy dokumentacji

Każdy przykład operacji musi być wykonywalny w dry-run/smoke na fixture bez
produkcyjnych sekretów. CI powinno sprawdzać linki, zgodność przykładów OpenAPI,
brak placeholderów udających działającą konfigurację, brak sekretów/canary secret i
`tests/test_documentation.py`. Release wymaga przejścia operatora od pustego QNAP i
czystego Kodi wyłącznie na podstawie runbooków.

## 9. Uwagi odrzucone lub warunkowe

- **Odrzucono obowiązkowy zewnętrzny enterprise KMS.** Dla domowego QNAP może być
  nieproporcjonalny. KEK + zaszyfrowany off-box recovery jest dopuszczalny, jeśli
  threat model jawnie przyjmuje, że root QTS może odczytać live secrets.
- **Odrzucono obowiązkową wysoką dostępność QNAP.** Urządzenia zachowują ostatni
  działający stan. Wymagane są natomiast RPO/RTO, backup poza NAS i cold restore;
  brak HA nie może być mylony z brakiem recovery.
- **Odrzucono przenoszenie ADB/SSH do QNAP.** Pull agent poprawnie usuwa tę rutynową
  zależność. ADB/SSH pozostają lokalnym, ograniczonym break-glass.
- **Odrzucono drugi dodatek administracyjny Kodi.** Rozszerzenie Profile Sync jest
  prostsze i ma mniejszą powierzchnię zaufania, pod warunkiem rozwiązania P0-5.
- **Odrzucono kopiowanie `addons/` pomiędzy urządzeniami.** Repo Kodi pozostaje
  właściwym kanałem kodu; snapshot disaster recovery jest osobnym, hostowym scope.
- **Warunkowo zaakceptowano WebAuthn.** Jest właściwy dla UI, ale dopiero po spike
  RP ID/TLS/browser i po dodaniu odzyskania operatora. MVP może użyć CLI po mTLS.
- **Warunkowo zaakceptowano osobne repo `kodi-control-plane`.** Wymaga ADR i
  automatycznych testów zgodności kontraktów; osobny proces/uprawnienia są
  obowiązkowe niezależnie od granicy repo.
- **Odrzucono automatyczny merge/promote przez QNAP.** GitHub review i zielone bramy
  pozostają właściwą granicą publikacji stable.

## 10. Warunek przyjęcia planu po poprawkach

Plan można uznać za wewnętrznie spójny po:

1. wyborze wykonalnego signing/delegation modelu i obsługi expired assignments;
2. wyborze jednej strategii aktualizacji dodatków bez pozornych fal stable;
3. dodaniu immutable convergence bundle i prepare/CAS/report boundary;
4. zdefiniowaniu dowodu exact artifact albo jawnego ograniczenia zaufania;
5. dodaniu dwufazowego self-update i macierzy schema/capability N/N-1;
6. uzupełnieniu secret rotation/recovery, offline supersession i QNAP cold restore;
7. rozpisaniu wskazanego backlogu dokumentacji oraz testów dokumentacji.

Do tego czasu dozwolone są ADR-y, spiki i read-only control plane. Import sekretów,
mutujące UI i rollout kodu urządzeń pozostają zablokowane.
