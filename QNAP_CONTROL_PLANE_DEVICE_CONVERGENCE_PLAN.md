# Plan przeniesienia administracji na QNAP i autonomicznej konwergencji Kodi

Status: plan po niezależnym review; do realizacji etapowej po zamknięciu ADR i
spike'ów fazy 0

Data: 2026-08-13

Repo nadrzędne: `mwoDevelop/kodi`

Powiązane źródła prawdy:

- `PROFILE_SYNC_PLAN.md`;
- `docs/kodi-operations.md`;
- `docs/kodi-private-profile.md`;
- `docs/scheduled-processes.md`;
- `manifests/locks/stable.json`;
- `manifests/kodi-profile-policy.json`;
- `manifests/kodi-default-addons.json`.

Niezależny review:

- `docs/QNAP_CONTROL_PLANE_DEVICE_CONVERGENCE_PLAN_REVIEW.md`.

Decyzja po review:

- przyjęto wszystkie P0 i P1: delegated signing, globalny stable po testing canary,
  immutable bundle/CAS, exact-artifact proof, bootstrap N-1, lifecycle schematów,
  saga rollback, pełny secret lifecycle, cold restore, supersession, WebAuthn
  bootstrap, pairing hardening, tamper-evident audit, inventory ownership i ścisłą
  allowlistę GitHub App;
- warunkowo pozostawiono WebAuthn i osobne repo control plane do rozstrzygnięcia
  przez spiki/ADR;
- nie wprowadzamy obowiązkowego enterprise KMS ani HA, drugiego dodatku Kodi,
  rutynowego ADB/SSH, kopiowania `addons/` ani automatycznego merge/promote.

## 1. Cel

Plan obejmuje dwa powiązane rezultaty:

1. przeniesienie bieżącej administracji, sekretów i sterowania rolloutem z
   pojedynczego hosta roboczego na stale działający QNAP;
2. doprowadzenie każdej instalacji Kodi do samodzielnego, bezpiecznego i
   powtarzalnego uzgadniania dodatków, ustawień oraz przypisanych sekretów.

Docelowo host deweloperski nie jest wymagany do rutynowego działania. Pozostaje
narzędziem developmentu, awaryjnego odzyskiwania i pierwszego bootstrapu, ale nie
źródłem prawdy konfiguracji ani harmonogramu rolloutu.

## 2. Stan wyjściowy i ograniczenia

Obecne rozwiązanie dostarcza większość potrzebnych prymitywów:

- GitHub jest control plane kodu, CI, skanów i publikacji repozytorium Kodi;
- QNAP uruchamia Profile Sync, provider relay i watchdog;
- Profile Sync pobiera podpisane rewizje przy starcie i co sześć godzin;
- rewizje są niemutowalne, przypisania podpisane, a apply jest journalowany,
  crash-resilient i używa kompensacyjnego rollbacku w granicach adaptera;
- repozytorium Kodi stable jest jedynym źródłem kodu dodatków mwoDevelop;
- hostowy `tools/kodi_ops.py` nadal przechowuje prywatny inventory, składa pełny
  rollout, publikuje profil i wykonuje diagnostykę ADB/SSH;
- sekrety i adresy znajdują się głównie w lokalnych `.env` i `.kodi-private/`;
- routine Profile Sync celowo nie synchronizuje kodu dodatków ani wszystkich
  poświadczeń.

Istotne ograniczenia:

- QNAP nie ma stabilnej trasy administracyjnej do BlueStacks działającego na
  pętli zwrotnej Windows/WSL;
- ADB i SSH nie powinny stać się publicznym ani stale uprzywilejowanym API;
- Kodi może aktualizować dodatki z repo, ale czysta instalacja nadal wymaga
  minimalnego bootstrapu repozytorium i klienta Profile Sync;
- rollback profilu nie jest równoznaczny z downgrade'em kodu dodatku;
- QNAP bez zewnętrznego KMS nie zapewni pełnej ochrony sekretów przed
  administratorem/rootem QTS. Może jednak zapewnić szyfrowanie danych, ścisłe ACL,
  audyt i ograniczenie sekretów per urządzenie.

## 3. Decyzja architektoniczna

Zostaje przyjęty model hybrydowy z rozdzieleniem odpowiedzialności:

```text
GitHub
  kod -> CI/skan -> testing -> zatwierdzenie -> stable repo/GitHub Pages
                                      |
                                      v
QNAP Kodi Control Plane
  - magazyn sekretów
  - inventory logiczne bez zależności od IP
  - Profile Sync i podpisane desired state
  - kontroler fal rolloutu
  - API/UI operatora i audyt
  - stan raportów urządzeń
                                      |
                         pull przy starcie i cyklicznie
                                      |
                                      v
Kodi Device Agent (rozszerzony Profile Sync)
  - kontrola repo stable
  - uzgodnienie dodatków przez Kodi repo
  - zastosowanie ustawień i sekretów per urządzenie
  - lokalny health check i rollback konfiguracji
  - podpisany raport do QNAP

Host deweloperski
  - development i lokalne E2E
  - pierwszy bootstrap / reinstall / break-glass
  - brak rutynowej roli control plane
```

Nie przenosimy obecnego hostowego rolloutu 1:1 do kontenera QNAP. Zastępujemy go
rolloutem typu pull: QNAP publikuje podpisany stan docelowy i steruje falami, a
każde urządzenie samo pobiera pracę, wykonuje ją lokalnie i odsyła podpisany raport.

Stan docelowy jest publikowany jako jeden niemutowalny, content-addressed
`convergence_bundle_v1`. Bundle atomowo wiąże dokładną rewizję profilu, release
manifest dodatków, wersje adapterów, wersję zestawu sekretów i koperty per
enrollment, politykę oraz rollout. Składniki przechodzą `PREPARING -> READY`, a
assignment może wskazać wyłącznie bundle w stanie `READY` opublikowany jednym CAS.

## 4. Zasady nienaruszalne

1. Kod dodatków pochodzi wyłącznie z `repository.mwodevelop` stable albo z
   oficjalnego repo Kodi wskazanego w polityce.
2. Profile Sync nie kopiuje katalogów `addons/` pomiędzy urządzeniami.
3. QNAP nie buduje i nie podpisuje kodu; zleca workflow GitHub i weryfikuje ich
   dokładne SHA, artefakty oraz atestacje.
4. Publiczny GitHub nie otrzymuje sekretów użytkownika, tokenów urządzeń ani
   prywatnego inventory.
5. Zwykły klient Kodi nie otrzymuje uprawnień `admin`, `promote`, `backup` ani
   dostępu do sekretów innych urządzeń.
6. IP jest informacją operacyjną, nie tożsamością. Podstawą pozostają
   `logical_device_id`, `enrollment_id` i monotoniczna generacja enrollmentu.
7. Każda akcja mutująca ma idempotency key, plan, audit event i jawny wynik.
8. Stable dodatków i aktywna rewizja profilu wymagają jawnego zatwierdzenia.
   Kod przechodzi `testing canary -> stable global -> fleet verification`.
   Profile, ustawienia i sekrety mogą być dawkowane falami per urządzenie. Plan nie
   nazywa globalnego auto-update stable falą per urządzenie.
9. Sekrety nie pojawiają się w logach, raportach E2E, URL-ach, telemetryce ani
   payloadzie wspólnej rewizji profilu.
10. ADB/SSH pozostają bootstrapem i break-glass; rutynowa synchronizacja nie może
    od nich zależeć.
11. Awaria QNAP nie może zablokować działającej konfiguracji Kodi ani usunąć
    ważnych tokenów. Urządzenie zachowuje ostatni poprawny stan i ponawia później.
12. Awaria pojedynczego urządzenia zatrzymuje jego falę zgodnie z polityką, ale
    nie niszczy konfiguracji urządzeń już zdrowych.
13. Operacje destrukcyjne, takie jak reinstall Kodi, pozostają poza zdalnym UI w
    pierwszym wydaniu. Wymagają odrębnego trybu break-glass i potwierdzenia celu.
14. Consumer API Profile Sync nigdy nie posiada klucza promotora ani kluczy
    administracyjnych. Podpisywanie jest osobnym procesem i wymaga świeżego,
    audytowalnego zatwierdzenia operatora.
15. Offline root/promoter podpisuje dokładny `release_intent_id`, digest bundle,
    kanał, maksymalny zbiór urządzeń i ograniczenia czasowe. Rotowalny online
    assignment key QNAP może podpisywać wyłącznie krótkotrwałe assignmenty związane
    z tym intentem, enrollmentem i falą; kryptograficznie nie ma roli `promote`,
    `revision`, `admin` ani prawa zmiany digestu.
16. Globalnego apply na urządzeniu nie opisujemy jako transakcji. Jest to saga z
    preflightem, barierami restartu, journalem i jawnymi stanami częściowymi.

## 5. Docelowe moduły

### 5.1 `kodi-control-plane` na QNAP

Nowa aplikacja Compose w Container Station, logicznie rozdzielona od istniejących
usług. Preferowana struktura:

```text
deploy/qnap-control-plane/
  compose.yaml
  env.example
  README.md

../kodi-control-plane/
  src/control_plane/
    api/
    auth/
    audit/
    devices/
    desired_state/
    github/
    rollouts/
    secrets/
    workers/
  migrations/
  tests/
```

Pierwsze wdrożenie może używać jednego obrazu z osobnymi procesami `api` i
`worker`, ale granice modułów muszą umożliwiać późniejsze rozdzielenie bez zmiany
kontraktu API.

Odpowiedzialności:

- prywatny rejestr urządzeń i ich możliwości, bez obowiązkowego endpointu ADB/SSH;
- przechowywanie zaszyfrowanych sekretów oraz mapowania sekret -> urządzenie/profil;
- tworzenie desired state łączącego aktywną rewizję profilu z lockiem dodatków;
- przygotowanie wszystkich składników bundle i atomowa publikacja jego head przez
  CAS dopiero po potwierdzeniu ich dostępności;
- sterowanie rolloutem etapami i ocena podpisanych raportów;
- zlecanie dozwolonych workflow GitHub i weryfikacja wyniku;
- administracyjne API/UI oraz tamper-evident audit log z eksportowanymi
  checkpointami;
- backup aplikacyjny i restore drill.

Control plane nie proxy'uje streamów, Real-Debrid ani zwykłego ruchu providerów.

### 5.2 Rozszerzony `kodi-profile-sync-server`

Istniejący serwer pozostaje właścicielem:

- enrollmentu, heartbeatów i podpisanych raportów;
- rewizji profili, blobów i assignmentów;
- report-gated promotion.

Należy dodać wersjonowane kontrakty integracyjne, nie bezpośrednie współdzielenie
tabel SQLite:

- API/service layer do pobrania zredagowanego stanu floty przez control plane;
- idempotentne tworzenie assignmentu desired state;
- osobny typ raportu `convergence-report`;
- możliwość powiązania rollout ID i wave ID z assignmentem;
- persistence uwierzytelnionego snapshotu `client_version`, capabilities,
  platformy i czasu heartbeat; self-report nie przyznaje uprawnień ani tagów;
- constrained delegation: walidacja, że online assignment key działa wyłącznie w
  granicach wcześniej podpisanego release intentu;
- administracyjne eventy zapisane w audycie bez treści sekretów.

Admin API Profile Sync nadal nie powinno być wystawione bezpośrednio do LAN. Dostęp
ma wyłącznie control plane przez prywatną sieć Compose lub unix socket.

Assignment zachowuje krótki TTL. Gdy urządzenie wraca po jego wygaśnięciu, control
plane może wystawić świeży nonce i termin wyłącznie dla nadal aktywnego intentu,
tego samego bundle, enrollmentu i jego bieżącej generacji. Revocation online key
natychmiast blokuje reissue, ale nie unieważnia ostatniego dobrego stanu urządzenia.

### 5.3 Magazyn sekretów QNAP

Sekrety należy oddzielić od zwykłych rewizji profilu i bazy enrollmentów.

Minimalny model:

- rekord posiada `secret_id`, typ, wersję, zakres, daty utworzenia/rotacji i
  zaszyfrowany payload;
- payload jest szyfrowany AES-256-GCM kluczem danych, a klucz danych kluczem KEK;
- KEK znajduje się w pliku `0400` na dedykowanym, szyfrowanym udziale QNAP,
  montowanym read-only tylko do procesu secrets;
- backup bazy nie jest użyteczny bez osobnego backupu KEK;
- backup KEK jest zaszyfrowany kluczem recovery przechowywanym poza QNAP;
- UI nigdy nie zwraca istniejącej wartości sekretu; pozwala tylko ustawić, obrócić,
  sprawdzić użycie i unieważnić;
- logowanie filtruje wartości przed serializacją, a testy zawierają canary secret,
  którego obecność w logach powoduje błąd.

Zakresy sekretów:

- `global-user`: np. konto OpenSubtitles, jeżeli jest wspólne;
- `service`: GitHub App, klucze backupu i integracje administracyjne;
- `device-class`: tylko gdy jawnie uzasadnione;
- `device`: token Rapideo/Real-Debrid lub enrollment przeznaczony dla konkretnego
  urządzenia.

Sekret dla Kodi jest wydawany jako zaszyfrowana koperta per enrollment. Podczas
parowania urządzenie generuje lokalną parę/klucz koperty i przekazuje wyłącznie
materiał publiczny; serwer publikuje blob możliwy do odszyfrowania wyłącznie przez
to urządzenie. Wspólna rewizja profilu zawiera tylko
odwołania i digesty, nigdy plaintext. Rotacja enrollmentu unieważnia stare koperty.

Klucz urządzenia nie należy do portable ani disaster-recovery profile. Android
używa hardware-backed storage, gdy jest dostępny; brak takiej możliwości musi być
jawnie raportowany i kwalifikowany per model. Flatpak używa prywatnego katalogu
`0700`/pliku `0600` właściwego konta. Reinstall zawsze tworzy nowe enrollment i
kopertę, po czym unieważnia stary token; stary ciphertext pozostaje tylko przez
retencję audytową.

Rotacja wspólnego sekretu jest sagą
`PREPARED -> DISTRIBUTING -> VERIFIED -> RETIRE_OLD`. Stara i nowa wersja mogą
współistnieć przez ograniczony czas, a działający lokalny token nie jest usuwany
przed preflightem i sukcesem nowej wersji. Dwie niezależnie zweryfikowane,
zaszyfrowane kopie recovery oraz pełny restore drill są bramą usunięcia plaintextu
z localhost.

W threat modelu „tylko urządzenie odszyfrowuje kopertę” dotyczy koperty
dystrybucyjnej. Proces secrets i root QTS mają techniczną możliwość dostępu do
plaintextu live; plan nie obiecuje ochrony przed przejętym rootem QNAP.

Przed implementacją należy wybrać i spisać ADR dla mechanizmu kopert. Preferencja:
X25519/HPKE z biblioteką dostępną i przetestowaną na Android BoringSSL oraz
Linux/OpenSSL. Jeżeli zgodność Kodi tego nie umożliwi, wariantem przejściowym jest
losowy klucz AEAD provisionowany w zweryfikowanym TLS podczas parowania. Nie wolno
wyprowadzać klucza szyfrowania przez proste ponowne użycie klucza Ed25519.

### 5.4 Administracyjne API i UI

Interfejs działa tylko w LAN po zweryfikowanym HTTPS. Nie jest publikowany przez
UPnP, port forwarding ani publiczny reverse proxy.

WebAuthn wymaga stabilnej lokalnej nazwy DNS/RP ID, certyfikatu zaufanego przez
przeglądarkę, poprawnego NTP i stałego originu. Bootstrap operatora rejestruje co
najmniej dwie passkeys oraz recovery codes. W instalacji domowej dopuszczamy jedną
tożsamość z ponownym uwierzytelnieniem; nie nazywamy tego two-person approval.

Autoryzacja:

- lokalne konto operatora z WebAuthn/passkey; awaryjnie hasło + TOTP;
- krótka sesja, CSRF protection, rate limiting i ponowne uwierzytelnienie dla
  operacji wysokiego ryzyka;
- role co najmniej `viewer`, `operator`, `approver`, `break-glass`;
- oddzielenie akcji przygotowania od zatwierdzenia promocji;
- dostęp CLI przez mTLS lub krótkotrwały token wydany po logowaniu, nie przez
  długowieczny bearer zapisany w shell history.

Signer promocji jest osobną granicą procesu. Preferowany wariant wykorzystuje
sprzętowe WebAuthn do zatwierdzenia dokładnego digestu planu w UI, ale właściwy
offline root/promoter podpisuje `release_intent` po stronie urządzenia operatora.
QNAP przechowuje ograniczony online assignment key, nie root/promoter private key.
Klucze nie są montowane do API, workera ani kontenera Profile Sync. ADR musi opisać
format export/import podpisu i jednoznaczne związanie go z zatwierdzonym challenge;
do czasu zakończenia review obowiązuje dotychczasowy signer offline.

WebAuthn samo w sobie nie wyprowadza ani nie odblokowuje klucza. Domyślny model to
podpis challenge przez passkey i osobna egzekucja polityki przez signer. Użycie
WebAuthn PRF wymaga odrębnego spike i nie jest założeniem MVP.

Dozwolone akcje pierwszego wydania:

- stan usług, floty, heartbeatów i bieżącej rewizji;
- utworzenie kodu pairing i unieważnienie dokładnego starego enrollmentu;
- ustawienie lub rotacja sekretu bez możliwości jego późniejszego odczytu;
- utworzenie kandydata konfiguracji i pokazanie zredagowanego diffu;
- przypisanie kandydata do urządzeń testowych;
- rozpoczęcie/pauza/wznowienie/anulowanie dalszych fal rolloutu;
- promocja profilu dopiero po wymaganych raportach i ponownej autoryzacji;
- uruchomienie dozwolonego `workflow_dispatch` GitHub;
- backup, weryfikacja integralności i kontrolowany restore drill do izolowanego
  środowiska;
- eksport zredagowanego raportu diagnostycznego.

Poza UI pozostają: dowolne komendy shell, dowolne workflow/repo GitHub, bezpośredni
SQL, masowe kasowanie enrollmentów, reinstall systemu/Kodi i odczyt sekretów.

Pairing ma rate limit per IP i globalnie, backoff, krótki TTL, limit aktywnych
kodów, jednorazowość oraz audyt prób. Przed zatwierdzeniem UI pokazuje logical ID,
generację i fingerprint nowego klucza urządzenia. Pairing nigdy nie nadaje roli
administracyjnej.

Audit jest tamper-evident, nie tamper-proof: monotoniczny sequence, hash chain,
podpisane checkpointy i wykrywanie braków. Zredagowane checkpointy są cyklicznie
eksportowane poza QNAP, aby restore starej bazy albo root QTS nie mógł po cichu
przepisać całej historii.

### 5.5 Integracja GitHub

QNAP używa dedykowanej GitHub App z minimalnymi uprawnieniami zamiast osobistego PAT.

GitHub App może:

- odczytywać workflow, commity, release i atestacje;
- uruchamiać jawnie dozwolone workflow `workflow_dispatch`;
- opcjonalnie tworzyć PR z kandydatem locka.

Allowlista wiąże owner/repository, dokładny workflow path i ref, dozwolone inputy,
branch/ref oraz limit częstotliwości. Sam wynik `success` nie wystarcza. Control
plane weryfikuje issuer atestacji, subject/repository, workflow identity, commit,
artifact SHA-256 i digest bajtów publicznych. Dispatch i odczyt mogą używać
oddzielnych instalacji/uprawnień, jeżeli pozwala na to GitHub.

Nie może samodzielnie zatwierdzać ani scalać PR. Publikacja stable nadal odbywa się
po review i zielonych bramkach GitHub. Control plane po publikacji sprawdza dokładny
commit, digest publicznych bajtów oraz podpisaną atestację, a dopiero potem tworzy
desired state dla urządzeń.

Awaria GitHub nie unieważnia ostatniego lokalnego stable ani działających ustawień.

### 5.6 Kodi Device Agent

Nie tworzymy drugiego konkurencyjnego dodatku. Rozszerzamy
`service.mwodevelop.profilesync` o moduł desired-state/convergence z adapterami OCP.

Moduły klienta:

```text
resources/lib/mwoprofilesync/
  sync/                 # istniejące assignment/revision/report
  secrets/              # koperty per enrollment
  repositories/         # kontrola repo stable i pochodzenia
  addons/               # desired add-ons i stan w Kodi
  adapters/             # ustawienia dodatków i Kodi
  health/               # testy poinstalacyjne bez ujawniania treści
  convergence/          # journal, retry, rollback konfiguracji, raport
```

Desired state zawiera co najmniej:

- wersję schematu i monotoniczną generację;
- minimalną wersję Device Agenta, wymagane capabilities i wersję fallback
  zrozumiałą dla starszego klienta;
- dokładny aktywny `profile_revision_id`;
- `bundle_id`, `release_intent_id`, digest locka/release manifestu oraz
  `secret_set_version`;
- listę wymaganych repozytoriów i dodatków;
- dla dodatku: ID, pochodzenie, wersję minimalną lub dokładną, politykę włączenia
  i wymagany adapter konfiguracji;
- referencje do sekretów przypisanych urządzeniu;
- kolejność apply i health checks;
- deadline, rollout ID, wave ID i politykę retry;
- podpis ograniczonego assignment key wraz z dowodem delegacji release intentu.

Podpisany release manifest zawiera dla każdego zarządzanego dodatku SHA-256 ZIP,
tożsamość repo, wersję i deterministyczny manifest plików. Agent po instalacji
liczy digest dokładnie oczekiwanych plików w katalogu dodatku, odrzuca brak lub
zmianę pliku i dopuszcza wyłącznie jawnie opisane pliki generowane. Sam status
ID/version/origin jest raportowany jako `ORIGIN_VERSION_ONLY`, nigdy `VERIFIED`.
Jeżeli spike wykaże, że natywny updater nie pozwala uzyskać wiarygodnego dowodu
bajtów/drzewa, MVP musi jawnie przyjąć granicę zaufania GitHub Pages + Kodi updater
albo przejść na zarządzaną instalację dokładnego artefaktu; nie wolno raportować
pozornego exact pinning.

Algorytm konwergencji urządzenia:

1. opóźnienie startowe i heartbeat;
2. pobranie oraz weryfikacja podpisanego assignmentu;
3. sprawdzenie monotoniczności, zgodności tagów i deadline;
4. obsługa `agent_bootstrap_v1` rozumianego przez N-1: zlecenie aktualizacji
   Profile Sync z dozwolonego repo, zapis `UPGRADE_PENDING` i zakończenie przebiegu
   bez stosowania bundle;
5. pobranie desired state i kopert sekretów przez zweryfikowany TLS;
6. po restarcie Kodi nowa instancja usługi potwierdza wersję/capabilities i dopiero
   wtedy czyści `UPGRADE_PENDING`; N-2 lub nieznany schemat zwraca
   `CLIENT_UPGRADE_REQUIRES_USER` bez pozostałych mutacji;
7. preflight wszystkich składników, zapis lokalnego journalu i backup zmienianych
   ustawień;
8. sprawdzenie obecności wyłącznie zatwierdzonych repozytoriów;
9. `UpdateAddonRepos`/`UpdateLocalAddons`, instalacja lub aktualizacja wymaganych
   dodatków przez Kodi, bez ręcznego zapisu `Addons*.db`;
10. weryfikacja ID, wersji, pochodzenia, stanu włączenia i dowodu plików;
11. zastosowanie ustawień oraz sekretów przez allowlistowane adaptery;
12. dla zmian `next_start` zapis bariery `RESTART_REQUIRED`, zakończenie bieżącego
    procesu i kontynuacja health checku dopiero w nowej instancji Kodi;
13. lokalne testy zdrowia; przy błędzie rollback ustawień i zachowanie poprzednich
    działających tokenów;
14. podpisany raport wiążący bundle, assignment, digests code/profile/secrets i
    osobne statusy, bez wartości sekretów;
15. trwałe oznaczenie konwergencji; kolejne uruchomienie ma zwrócić `NO_CHANGE` dla
    tego samego `bundle_id`.

Kodi zachowuje własny standardowy mechanizm automatycznych aktualizacji repo. Agent
jest warstwą kontroli i naprawy driftu, nie alternatywnym instalatorem ZIP. Dla
wersji minimalnej może zaakceptować nowszą wersję stable; dokładne przypięcie jest
używane dla canary i krytycznych zależności. Downgrade wymaga jawnej polityki i
dostępności starszego artefaktu w repo; nie jest obiecywany jako rutynowy rollback.

Pierwsza wersja `agent_bootstrap_v1` musi zostać rozprowadzona i zweryfikowana
obecnym hostowym rolloutem na całej flocie, zanim QNAP wyśle pierwszy nowy bundle.
Nie zakładamy, że obecny klient 1.0.3 rozumie przyszłą instrukcję bootstrap.

### 5.7 Kontroler rolloutu

Kontroler na QNAP zastępuje rutynową część `tools/kodi_ops.py`:

1. weryfikuje dostępność Profile Sync, stan backupu, release intent i podpisane
   artefakty;
2. materializuje wszystkie składniki bundle, weryfikuje je i publikuje `READY`
   jednym CAS;
3. dla profilu/ustawień/sekretów wystawia assignment dla BlueStacks i czeka na
   podpisany sukces;
4. następnie analogicznie kwalifikuje X88 i pozostałe fale Android TV/NUC;
5. dla kodu dodatków najpierw certyfikuje dokładnego kandydata z testing na
   BlueStacks i X88, potem wymaga review/publikacji stable, a następnie obserwuje
   globalną konwergencję floty; nie obiecuje dawkowania stable per urządzenie;
6. zatrzymuje odpowiednią fazę po błędzie deterministycznym lub przekroczeniu
   polityki;
7. urządzenia mają jawne stany `eligible`, `temporarily_offline`, `deferred`,
   `expired`, `superseded`, `retired` i `excluded_with_reason`;
8. po heartbeat offline urządzenia online key wystawia świeży assignment tylko dla
   nadal zatwierdzonego bieżącego intentu. Nowszy active superseduje starsze
   nieaplikowane plany zamiast odtwarzać całą kolejkę;
9. rozróżnia `completed_for_required_online_set` od `fleet_fully_converged`, a
   deadline nieobecnego urządzenia wymaga jawnej decyzji operatora;
10. kończy rollout dopiero po raportach i wymaganym okresie obserwacji określonym w
   polityce konkretnej zmiany, bez stałego wymogu wielodniowego oczekiwania;
11. zapisuje zredagowany raport i audit trail.

Rollout dodatków i rollout profilu mogą korzystać z jednego planu, ale muszą mieć
oddzielne statusy. Pozwala to odróżnić np. poprawną aktualizację kodu od błędu
credential adaptera.

Bundle i jego składniki są niemutowalne. Garbage collector nie usuwa składnika
aktywnego, przypisanego, raportowanego, objętego rollbackiem ani retencją audytową.
Raport `PARTIAL`, `ROLLBACK_PENDING`, `ROLLBACK_REQUIRES_HOST` albo
`CODE_UPDATED_CONFIG_REVERTED` nigdy nie spełnia bramki promocji.

### 5.8 Lifecycle kontraktów i kompatybilność

Do `manifests/schema-lifecycle.json` należy dodać osobne formaty:

- `desired_state`;
- `convergence_bundle`;
- `release_intent` i `assignment_delegation`;
- `secret_envelope`;
- `convergence_report`;
- `rollout_plan`;
- `audit_event`.

Macierz zgodności obejmuje server N/N-1, agent N/N-1, DB schema oraz wszystkie
powyższe schematy. Migracje są expand/contract, testowane w mixed-version E2E i
mają tryb downgrade/read-only. Starszy agent nigdy nie dostaje bundle, którego nie
rozumie; nieznany schemat jest fail-closed bez częściowego apply. Usunięcie readera
lub migratora wymaga spełnienia polityki retencji opisanej w schema lifecycle.

## 6. Migracja z localhost na QNAP

Migracja ma być stopniowa i odwracalna.

### Etap 0 — ADR i spiki go/no-go

Przed kodem mutującym należy zatwierdzić ADR: trust/delegated signing, strategia
kanałów dodatków, supply-chain/exact bytes, secret envelope, lifecycle schematów,
własność inventory i granica repozytoriów. Następnie wykonać spiki na rzeczywistych
platformach:

- N-1 -> N dla uruchomionego `xbmc.service` na Android i Flatpak;
- install/update/restart/błędny ZIP przez Kodi bez UI;
- X25519/HPKE lub wybrany AEAD na ARMv7, Android i x86;
- WebAuthn z docelowym DNS/TLS, przeglądarką i QNAP.

Negatywny wynik zmienia projekt przed importem sekretów, a nie po wdrożeniu.

### Etap A — inventory i klasyfikacja

1. Utworzyć narzędzie, które odczytuje lokalne `.env` i `.kodi-private/`, ale
   wypisuje tylko nazwy kluczy, typ, właściciela i miejsce użycia.
2. Podzielić dane na: sekret, prywatny inventory, cache operacyjny, recovery,
   historyczny artefakt i dane zbędne.
3. Usunąć duplikaty i zdefiniować kanoniczne nazwy sekretów.
4. Nie importować ulotnych adresów ADB jako tożsamości; mogą być opcjonalnym
   atrybutem diagnostycznym z TTL.
5. Zapisać macierz własności: QNAP posiada logical ID, enrollment, capabilities,
   desired state i historię; endpoint ADB/SSH jest opcjonalny i wygasa; break-glass
   credentials należą wyłącznie do zaszyfrowanego recovery kit.
6. Po cutover hostowe CLI domyślnie pobiera zredagowany inventory z QNAP i nie
   mutuje lokalnego `.env`. Osobny runbook opisuje minimalne odkrycie QNAP po utracie
   DNS/control plane.

### Etap B — control plane tylko do odczytu

1. Wdrożyć obraz przypięty digestem w Container Station.
2. Podłączyć read-only stan Profile Sync, GitHub App i status trzech usług QNAP.
3. Udostępnić UI statusu bez możliwości mutacji.
4. Dodać backup, restore do izolowanego katalogu i test utraty procesu.

### Etap C — import sekretów w trybie shadow

1. Wykonać online backup QNAP i zaszyfrowany eksport lokalnych danych recovery.
2. Importować sekrety jednokierunkowo przez CLI po mTLS; wartości nie mogą wracać w
   odpowiedzi.
3. Zweryfikować per rekord digest/HMAC i możliwość użycia przez izolowany adapter,
   bez ujawnienia plaintextu.
4. Przez okres przejściowy lokalny host pozostaje źródłem wykonania, ale porównuje
   tylko obecność/wersję sekretu QNAP.
5. Po kwalifikacji przełączyć publishera na QNAP, unieważnić stare tokeny
   administracyjne i usunąć plaintext z localhost. Zachować wyłącznie zaszyfrowany,
   offline recovery export.

### Etap D — autonomiczne ustawienia i sekrety

1. Wydać Device Agent z obsługą desired state bez zarządzania kodem dodatków.
2. Przetestować ustawienia niesekretne na BlueStacks i X88.
3. Dodać koperty sekretów oraz adaptery Rapideo, OpenSubtitles i Umbrella/RD.
4. Wykazać, że każde urządzenie odszyfrowuje tylko własny payload.
5. Wykazać `NO_CHANGE` dla tego samego bundle, retry po braku sieci, rollback po
   błędnym sekrecie i brak wycieku do logów.

### Etap E — autonomiczne dodatki przez repo

1. Rozszerzyć desired state o repo i dodatki.
2. Najpierw tryb `audit`: raport driftu bez instalacji.
3. Opublikować dokładnego kandydata testing i wykonać `apply` najpierw na
   BlueStacks, potem X88, pojedynczo dla repo, Profile Sync, MwoScrapers, Umbrella,
   WatchNixtoons2, Rapideo i usług napisów.
4. Sprawdzić instalację zależności, origin, aktualizację nowszej wersji, restart
   Kodi, manifest plików oraz idempotentny drugi przebieg.
5. Dopiero po pełnym canary wykonać review i publikację stable. Stable jest
   globalną aktualizacją; QNAP obserwuje i raportuje pozostałą flotę.

### Etap F — rollout QNAP i interfejs administracyjny

1. Zaimplementować niezmienny plan, fale, pause/resume/cancel i timeouts.
2. Udostępnić allowlistowane akcje operatorskie.
3. Przenieść publikację profilu, assignmenty i ocenę raportów z hosta.
4. Zintegrować dozwolone workflow GitHub App.
5. Po kwalifikacji usunąć rutynową rolę hosta; hostowe komendy mają zostać
   wrapperem API QNAP albo narzędziem break-glass.

### Etap G — czysta instalacja i bootstrap

Minimalny bootstrap pozostaje jawny:

1. zainstalować Kodi ze sklepu/Flatpak;
2. dodać źródło `https://mwodevelop.github.io/kodi/repo`;
3. zainstalować `repository.mwodevelop` i Profile Sync;
4. wpisać jednorazowy kod pairing z UI QNAP.

Od tego momentu urządzenie samo instaluje wymagane dodatki i konfigurację. Dalszym
usprawnieniem może być mały kod QR/deep link z adresem serwera i kodem pairing, ale
nie może zawierać długowiecznego tokenu. Pełny zero-touch na czystym Androidzie
wymagałby zarządzania urządzeniem/MDM i pozostaje poza MVP.

## 7. Testy i bramy E2E

### 7.1 Testy bezpieczeństwa

- threat model oraz ADR dla kluczy i szyfrowania kopert;
- sekrety nie występują w logach, raportach, backup metadata ani odpowiedziach UI;
- klient jednego urządzenia nie pobiera sekretu innego urządzenia;
- replay starego assignmentu, raportu i koperty jest odrzucany;
- online assignment key nie może podpisać promocji, rewizji, innego bundle ani
  urządzenia poza zakresem release intentu;
- utracony/revoked enrollment nie może pobierać desired state;
- admin API odrzuca brak WebAuthn/mTLS, CSRF, nadmiarowe role i dowolne workflow;
- skan obrazu i zależności, SBOM, podpis obrazu i przypięty digest;
- negatywny test uszkodzonego backupu i brakującego KEK.
- skan canary secret obejmuje logi, audit, backup metadata, artefakty CI i raporty.

### 7.2 Testy funkcjonalne canary

Kolejność obowiązkowa:

1. BlueStacks;
2. X88 Pro 20;
3. dopiero po ich sukcesie Sony TV, Bedroom TV i oba profile NUC.

Na każdym canary sprawdzić:

- uruchomienie Kodi z pustym cache;
- aktualizację repo i dodatków przez Kodi;
- wersje, origin, wymagane zależności i signed file manifest/exact tree proof;
- zastosowanie skóry, favourites i artwork;
- Umbrella + MwoScrapers na kilku filmach i odcinkach;
- zgodność wyników resolvera w granicach zmienności providerów;
- Real-Debrid, Rapideo, OpenSubtitles.com i alternatywę `.org`;
- VPN oraz fallback Torrentio/QNAP;
- `NO_CHANGE` dla tego samego bundle przy drugim przebiegu;
- urządzenie offline, restart Kodi w połowie apply, brak QNAP i rollback błędnych
  ustawień;
- upgrade Profile Sync N-1 -> N, `UPGRADE_PENDING`, restart oraz ręczny fallback
  dla N-2;
- podpisany raport i poprawne przejście fali.

### 7.3 Test czystej instalacji

Na nowej instancji BlueStacks wykonać wyłącznie minimalny bootstrap. Bez hostowego
kopiowania profilu urządzenie ma samodzielnie:

- sparować się;
- zainstalować wymagane dodatki z repo stable;
- pobrać ustawienia i własne koperty sekretów;
- odtworzyć favourites/artwork bez cache;
- przejść test funkcjonalny i kolejny przebieg `NO_CHANGE` dla tego samego bundle.

### 7.4 Testy QNAP

- restart kontenera i całego QNAP;
- odtworzenie kolejki rolloutów po restarcie;
- backup online i restore do izolowanego projektu Compose;
- awaria Profile Sync, GitHub i DNS bez utraty planu;
- odnowienie certyfikatu TLS, rotacja GitHub App i KEK;
- test ARMv7 na rzeczywistym QNAP;
- kontrola widoczności aplikacji w Container Station;
- watchdog monitorujący również cykliczny backup i zdrowie control plane;
- utrata całego QNAP i cold restore na pustym, zastępczym hoście z zachowaniem
  DNS/certyfikatu albo kontrolowaną rotacją zaufania.

## 8. Rollback i recovery

- rollout można zatrzymać przed następną falą;
- aktywna konfiguracja może wskazać poprzednią, nadal przechowywaną rewizję;
- klient przechowuje lokalny backup zmienianych ustawień i journal;
- kod dodatku nie jest automatycznie downgrade'owany bez jawnego, dostępnego
  artefaktu i osobnej zgody;
- control plane ma aplikacyjny backup SQLite/blob/secrets metadata oraz osobny
  backup KEK;
- restore produkcyjny wymaga zatrzymania writerów, integralności, zgodności schematu
  i ponownego health checku;
- hostowe `tools/kodi_reinstall.py` oraz zaszyfrowany recovery kit pozostają
  ostatnią ścieżką break-glass, dopóki czysta instalacja nie zostanie wielokrotnie
  zakwalifikowana.

Docelowe parametry po cutover: RPO maksymalnie 24 godziny i RTO maksymalnie 4
godziny od dostępności zastępczego hosta Docker. Codzienny zaszyfrowany backup poza
QNAP zawiera spójny secret DB, Profile Sync epoch, KEK metadata, konfigurację
Compose i instrukcję restore. Brak QNAP przełącza system w degraded mode: Kodi
zachowuje lokalne tokeny i odtwarzanie, nie usuwa konfiguracji z powodu TTL, a nowe
pairing, rotacje i rollouty są jawnie niedostępne.

## 9. Zmiany w repozytoriach

### `mwoDevelop/kodi`

- manifest desired-state i polityka rolloutów;
- Compose i cykl życia obrazu control plane;
- rozszerzenie `tools/qnap_images.py` o nową usługę;
- wrapper CLI do control plane zamiast bezpośrednich mutacji;
- E2E, dokumentacja operacyjna i schemat lifecycle;
- aktualizacja watchdoga i `docs/scheduled-processes.md`.

### `mwoDevelop/kodi-profile-sync-server`

- kontrakt integracyjny control plane;
- convergence assignments/reports i audit hooks;
- koperty sekretów lub bezpieczne delegowanie do secrets service;
- migracje, backup epoch i testy transportu.

### `mwoDevelop/service.mwodevelop.profilesync`

- desired-state engine;
- repo/add-on reconciliation przez publiczne API Kodi;
- adaptery sekretów i ustawień;
- health checks, journal, retry i zredagowane raporty;
- UI statusu lokalnego i ręczne `Sync now`, bez funkcji administracyjnych.

### Nowe `mwoDevelop/kodi-control-plane`

- LAN-only API/UI, RBAC i WebAuthn;
- magazyn sekretów;
- fleet/rollout controller;
- GitHub App integration;
- audit, backup i worker.

Jeżeli po prototypie okaże się, że control plane jest mały i silnie związany z
Profile Sync, może zostać osobnym pakietem w repo serwera, ale nadal jako oddzielny
proces i powierzchnia uprawnień. Nie należy łączyć admin UI z consumer API Kodi.

## 10. Plan uzupełnienia dokumentacji

Dokumentacja jest częścią każdej fazy i musi zostać zmieniona w tym samym PR co
kontrakt, schemat lub operacja. Nie odkładamy jej na koniec wdrożenia.

### 10.1 Nowy indeks control plane

Utworzyć `docs/control-plane/README.md`, prowadzący co najmniej do:

- `architecture.md` — granice GitHub/QNAP/Profile Sync/agent/host, trust i data
  flow;
- `threat-model.md` — aktywa, aktorzy, QNAP root, LAN, GitHub, przejęte urządzenie
  i jawne ograniczenia;
- `signing-and-trust.md` — offline root/promoter, release intent, constrained
  online assignment key, device keys, atestacje, rotacja i revocation;
- `desired-state-and-schemas.md` — bundle, assignment, envelope, report,
  kompatybilność N/N-1, CAS, GC i supersession;
- `qnap-install.md` — Container Station, ARMv7, digest obrazu, UID/GID, ACL,
  wolumeny, DNS/TLS/NTP, firewall i widoczność w GUI;
- `admin-ui-cli.md` — pierwszy operator, passkeys/TOTP/recovery, role, re-auth,
  allowlistowane akcje i zredagowane przykłady;
- `github-app.md` — instalacja, minimalne uprawnienia, allowlista workflow,
  atestacje i rotacja klucza;
- `secrets.md` — klasyfikacja, shadow import, envelope, klucz urządzenia, rotacja,
  revocation, redaction i recovery;
- `device-bootstrap.md` — czysty Android/Flatpak, pairing/fingerprint,
  `agent_bootstrap_v1`, N-1/N-2 i przypadki wymagające użytkownika;
- `rollout.md` — audit/apply, testing canary, stable global, konfiguracja falowa,
  pause/resume/cancel, offline/deferred/expired/superseded i interpretacja raportów;
- `backup-restore-dr.md` — RPO/RTO, backup poza QNAP, KEK, cold restore od pustego
  hosta oraz cykliczny drill;
- `incident-response.md` — utrata passkey, assignment key, GitHub App,
  enrollmentu, urządzenia albo QNAP;
- `troubleshooting.md` — TLS/czas, heartbeat, upgrade pending, częściowy apply,
  provider/VPN versus control plane i bezpieczne dane diagnostyczne;
- wersjonowane OpenAPI i przykładowe payloady bez sekretów.

### 10.2 Aktualizacja istniejących dokumentów

W odpowiednich fazach aktualizować razem:

- główne `README.md` i `docs/README.md`;
- `docs/kodi-operations.md` — host jako wrapper API QNAP i break-glass;
- `docs/kodi-private-profile.md` — własność inventory/sekretów i device-local state;
- `docs/scheduled-processes.md` — agent checks, backup, restore drill, watchdog,
  rotacje certyfikatów/kluczy i alarmy;
- `docs/qnap-images.md` oraz `deploy/qnap-control-plane/README.md` — cykl życia
  czwartego obrazu;
- `docs/schema-lifecycle.md` i `manifests/schema-lifecycle.json`;
- README serwera i dodatku Profile Sync — powierzchnie API, capabilities, upgrade,
  envelopes i convergence states;
- `docs/e2e-results/README.md` — format zredagowanych dowodów rollout/restore.

Po cutover tabela źródeł prawdy w `docs/README.md` ma wskazywać QNAP jako właściciela
logicznego inventory i sekretów, a lokalne `.env` wyłącznie jako przejściowe
bootstrap/break-glass do czasu jego usunięcia.

### 10.3 Bramy dokumentacji

- każdy przykład działa w dry-run/smoke na fixture bez sekretów produkcyjnych;
- CI sprawdza linki, przykłady OpenAPI, schema fixtures i brak sekretów/canary
  secret;
- `tests/test_documentation.py` pozostaje obowiązkowy;
- każda faza ma zaktualizowany diagram, runbook, rollback i troubleshooting;
- pełny release wymaga testu operatorskiego: od pustego QNAP i czystego Kodi do
  działającego systemu wyłącznie na podstawie runbooków.

## 11. Kryteria pełnego release

Release jest gotowy dopiero, gdy:

1. żaden rutynowy rollout ani sync nie wymaga uruchomionego localhost;
2. QNAP przechowuje kanoniczny inventory logiczny, sekrety i historię rolloutów;
3. plaintext sekretów został usunięty z lokalnego `.env`, a recovery jest
   zaszyfrowane i sprawdzone;
4. czysta instancja BlueStacks po minimalnym bootstrapie samodzielnie osiąga pełną
   konwergencję;
5. BlueStacks i X88 przechodzą testing canary, publikacja stable ma poprawną
   atestację, a następnie dostępna flota przechodzi globalną weryfikację kodu oraz
   falową konwergencję konfiguracji;
6. drugi przebieg na każdym urządzeniu kończy się `NO_CHANGE` dla tego samego
   `bundle_id`;
7. restart QNAP i Kodi, brak sieci i przerwany apply nie powodują utraty działającej
   konfiguracji;
8. GitHub CI, skany, testy ARMv7, testy serwera, klienta i całego repo są zielone;
9. obrazy są przypięte digestem, widoczne w Container Station i zdrowe;
10. dokumentacja opisuje bootstrap, UI/CLI, backup, restore, rotację sekretów,
    rollout, pause/resume, awarię i break-glass;
11. niezależny review bezpieczeństwa nie ma otwartych uwag P0/P1;
12. nie wydajemy nowej wersji dodatku lub obrazu, jeżeli jego bajty nie uległy zmianie.

## 12. Kolejność realizacji i przybliżony koszt

| Faza | Rezultat | Szacunek |
|---|---|---:|
| 0 | ADR, threat model i spiki go/no-go Kodi/crypto/WebAuthn | 4–8 dni |
| 1 | Control plane read-only, auth, audit, backup i QNAP Compose | 4–7 dni |
| 2 | Bundle, delegowany signer, lifecycle schematów i mixed-version | 5–10 dni |
| 3 | Magazyn sekretów, import shadow, koperty i off-box recovery | 5–10 dni |
| 4 | Device Agent: bootstrap N-1, ustawienia, sekrety i saga rollback | 5–9 dni |
| 5 | Testing canary, repo/add-ons i exact-artifact proof | 5–9 dni |
| 6 | Kontroler fal konfiguracji, UI administracyjne i GitHub App | 5–10 dni |
| 7 | Czysta instalacja, pełna flota, cold restore i release | 4–8 dni |

Bazowy szacunek wynosi około 37–71 dni roboczych. Z buforem 30–50% na Kodi API,
WebAuthn ARMv7, realne credentiale i cold restore należy planować około 48–105 dni.
Po spike'ach fazy 0 estymacja jest aktualizowana. MVP read-only + CLI po mTLS,
immutable bundle i trzy najważniejsze adaptery, bez pełnego UI, należy szacować na
około 22–40 dni roboczych.

## 13. Pierwszy przyrost implementacyjny

Pierwszy bezpieczny przyrost powinien być mały i nie zmieniać urządzeń:

1. dodać threat model oraz ADR-y trust/signing, kanałów dodatków, exact bytes,
   secret envelope, lifecycle schematów, inventory i granicy repo;
2. utworzyć skeleton `kodi-control-plane` z endpointami read-only `health`, `fleet`
   i `rollouts`;
3. wdrożyć go na QNAP jako czwartą aplikację kontrolowaną przez
   `tools/qnap_images.py`;
4. zasilić wyłącznie zredagowanym stanem istniejącego Profile Sync oraz GitHub;
5. dodać mTLS CLI i tamper-evident audit;
6. wykonać restart, backup/restore drill i test ARMv7;
7. dopiero po review bezpieczeństwa rozpocząć import sekretów.

Taki przyrost daje widoczny panel stanu i podstawę API, ale nie rozszerza jeszcze
powierzchni mutacji ani nie naraża sekretów.
