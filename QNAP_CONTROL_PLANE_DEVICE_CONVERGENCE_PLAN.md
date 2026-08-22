# Plan przeniesienia administracji na QNAP i autonomicznej konwergencji Kodi

Status: w realizacji etapowej; read-only Control Plane, dashboard mTLS i bundle
v1 wydane, przeglądarkowe uwierzytelnianie administratora, trwała kolejka akcji
i magazyn sekretów zaplanowane

Data: 2026-08-21

Aktualizacja 2026-08-22 — realizacja przyrostu 3A2a:

- zachowujemy `HTTPS/mTLS :19443` jako dotychczasowy interfejs maszynowy oraz
  dodajemy osobny, nadal read-only interfejs przeglądarkowy
  `https://<QNAP>:19444/control-plane/`;
- przeglądarka nie przedstawia certyfikatu klienta. Dostęp jest ograniczony do
  jednej podsieci LAN, dokładnego `Host` i `Origin`, hasła oraz TOTP; sesja ma
  limit bezczynności i limit bezwzględny, CSRF używa double-submit cookie;
- osobny proces `control-plane-authz` ma własną bazę SQLite, szyfruje seed TOTP
  AES-GCM kluczem spoza bazy, przechowuje jednorazowe kody odzyskiwania i nie
  publikuje portu do LAN;
- proces `control-plane-web` jest BFF tylko do odczytu. Do core i authz łączy się
  dedykowanymi certyfikatami mTLS; certyfikat BFF ma w core allowlistę wyłącznie
  dla endpointów dashboardu;
- QTS 5.2 nie zapewnia potrzebnego routingu source-path, a publiczny urząd
  certyfikacji nie wystawi certyfikatu dla prywatnego IP. Dlatego ten przyrost
  świadomie nie używa QTS reverse proxy ani WebAuthn: przeglądarka pokaże
  ostrzeżenie dla lokalnego certyfikatu, ale nie wymaga instalacji CA;
- `tools/qnap_images.py browser-bootstrap` generuje na QNAP jednorazowy kod
  ważny maksymalnie 10 minut. `--reset` jest jawną ścieżką break-glass, która
  unieważnia operatora i sesje przed ponowną konfiguracją.

Aktualizacja 2026-08-21 — wydanie przyrostu 3A1:

- wydano `kodi-control-plane` 0.3.0 ze statycznym dashboardem read-only,
  wersjonowanymi endpointami statusu, katalogiem 13 harmonogramów, czterema
  źródłami statusu, provenance, freshness i alertami;
- obraz ARMv7/AMD64 przypięto digestem, promowano przez certyfikowany QNAP lock i
  wdrożono w Container Station; API oraz UI pozostają za mTLS, bez endpointów
  mutujących;
- cross-repo E2E potwierdził lifecycle bundle, odmowę klienta bez certyfikatu i
  odmowę mutacji, a Chrome przez CDP 9222 poprawnie wyrenderował stan `DEGRADED`;
- certyfikacja BlueStacks1/X88 przeszła z trwałym otwartym fixture resolvera,
  a proces promocji otrzymał testowany kontrakt `attestation_kind=device`;
- watchdog zapisuje kompletny, niezdrowy raport również przy błędzie GitHub API,
  zamiast kończyć proces przed publikacją statusu.

Aktualizacja 2026-08-21 — moduł administracyjny:

- nie tworzymy drugiego, konkurencyjnego panelu. Rozszerzamy istniejący
  `kodi-control-plane`, zachowując obecne read-only API mTLS jako kontrakt
  maszynowy i dodając osobny interfejs przeglądarkowy administratora;
- GUI pokazuje niezależne statusy floty, konfiguracji, dodatków, sekretów,
  rolloutów, usług QNAP, procesów cyklicznych, backupów, bezpieczeństwa i źródeł
  zewnętrznych. Status schedulera, ostatniego wykonania i świeżości danych nie są
  sprowadzane do jednego pola `healthy`;
- wszystkie rutynowe credentiale mogą docelowo przejść z lokalnego `.env` do
  szyfrowanego magazynu QNAP. Klucz recovery, offline root/promoter i materiały
  break-glass pozostają poza QNAP, aby przejęcie NAS nie dawało pełnej władzy;
- każda mutacja z GUI jest trwałą, idempotentną operacją: najpierw preflight i
  zredagowany plan, następnie jawne zatwierdzenie, wykonanie przez allowlistowany
  adapter, audit i weryfikacja wyniku;
- API/GUI nie otrzymuje Docker socketu, powłoki ani bezpośredniego SQL. W pierwszym
  release lokalny lifecycle własnego stosu QNAP pozostaje zarządzany przez
  `tools/qnap_images.py`; panel może go obserwować, ale nie wdrażać samego siebie;
- pierwszy następny przyrost to read-only dashboard na obecnych endpointach oraz
  trwały katalog harmonogramów. Import sekretów i akcje mutujące wchodzą dopiero
  po bramach auth, audit, backup/restore i testach wycieku canary secret.

Aktualizacja 2026-08-14:

- wydano i wdrożono read-only Control Plane, kontrakt integracyjny Profile Sync,
  mTLS, zredagowany cache, audit, backup/restore i monitoring QNAP;
- wydano `convergence_bundle_v1`: content addressing, exact-artifact evidence,
  stany `PREPARING/READY`, CAS head oraz kompatybilny restore schematu bazy 1;
- wydano `kodi-control-plane` 0.2.0 i `kodi-profile-sync-server` 0.5.0;
  kontrakty offline release intent, delegowanego assignmentu i raportu urządzenia
  są zaimplementowane i testowane, ale nie są jeszcze podłączone do trwałego
  magazynu ani sieciowego writer API;
- certyfikowany snapshot stable przeszedł canary BlueStacks/X88, publikację
  56 plików, rollout na trzy dostępne urządzenia Android i wdrożenie czterech
  zdrowych obrazów QNAP przypiętych digestem;
- sieciowe API pozostaje read-only, a writer bundle działa wyłącznie lokalnym CLI
  QNAP;
- w toku pozostają utrwalenie i egzekwowanie release intent/delegowanego
  assignmentu, magazyn sekretów, Device Agent, autonomiczne dodatki, kontroler
  fal/UI i clean bootstrap.

Repo nadrzędne: `mwoDevelop/kodi`

Powiązane źródła prawdy:

- `PROFILE_SYNC_PLAN.md`;
- `YOUTUBE_DEFAULT_ADDON_PLAN.md`;
- `docs/kodi-operations.md`;
- `docs/kodi-private-profile.md`;
- `docs/scheduled-processes.md`;
- `manifests/locks/stable.json`;
- `manifests/kodi-profile-policy.json`;
- `manifests/kodi-default-addons.json`.

Niezależny review:

- `docs/QNAP_CONTROL_PLANE_DEVICE_CONVERGENCE_PLAN_REVIEW.md`.
- `docs/QNAP_ADMIN_MODULE_PLAN_REVIEW_2026-08-21.md` — challenge rozszerzenia o
  GUI, authz, operacje, statusy, harmonogramy, sekrety i recovery.
- `docs/YOUTUBE_DEFAULT_ADDON_PLAN_REVIEW.md` — review rozszerzenia YouTube,
  modelu OAuth i granicy release 1/release 2.

Decyzja po review:

- przyjęto wszystkie P0 i P1: delegated signing, globalny stable po testing canary,
  immutable bundle/CAS, exact-artifact proof, bootstrap N-1, lifecycle schematów,
  saga rollback, pełny secret lifecycle, cold restore, supersession, WebAuthn
  bootstrap, pairing hardening, tamper-evident audit, inventory ownership i ścisłą
  allowlistę GitHub App;
- osobne repo `mwoDevelop/kodi-control-plane` zostało utworzone i pozostaje
  właściwą granicą modułu; WebAuthn na docelowym QNAP/DNS/TLS nadal wymaga spike
  i ADR przed włączeniem mutacji w GUI;
- nie wprowadzamy obowiązkowego enterprise KMS ani HA, drugiego dodatku Kodi,
  rutynowego ADB/SSH, kopiowania `addons/` ani automatycznego merge/promote.
- review panelu z 2026-08-21 zamknął nowe luki: authz grant niezależny od DB web,
  późny `CUTOVER_COMMITTED`, remote reconciliation zamiast obietnicy exactly-once,
  `recovery_bundle_v1`, prywatny writer mTLS Profile Sync, zewnętrzny audit anchor,
  status provenance i ograniczony QTS deployd przed pełnym cutover.

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

Istniejąca aplikacja Compose w Container Station pozostaje jedynym modułem
administracyjnym. Jej repozytorium `mwoDevelop/kodi-control-plane` należy rozwijać
modułowo, zamiast umieszczać UI i sekrety w repo serwera Profile Sync. Preferowana
struktura docelowa:

```text
deploy/qnap-control-plane/
  compose.yaml
  env.example
  README.md

../kodi-control-plane/
  src/kodi_control_plane/
    api/                 # wersjonowane REST API, bez renderowania UI
    web/                 # statyczny frontend i backend-for-frontend
    auth/
    audit/
    devices/
    desired_state/
    github/
    operations/          # plan, approval, kolejka, lease, retry, kompensacje
    rollouts/
    schedules/           # katalog i obserwacja zadań cyklicznych
    secrets/
    status/              # normalizacja, freshness i agregaty dashboardu
    workers/             # allowlistowane adaptery wykonawcze
  migrations/
  tests/
```

Jeden przypięty digest obrazu uruchamia osobne procesy/kontenery Compose:

- `control-plane-web` — LAN HTTPS, sesje operatora, GUI i read/write API; nie ma
  KEK, klucza GitHub App, sekretów urządzeń ani uprawnień wykonawczych;
- `control-plane-authz` — prywatny verifier WebAuthn/RBAC, właściciel rejestru
  operatorów i klucza grantów; wystawia krótkotrwały podpisany grant związany z
  `plan_digest`, aktorem, rolą, nonce, terminem, policy version i preconditions;
- `control-plane-worker` — pobiera operacje przez trwałą kolejkę i wykonuje tylko
  zarejestrowane adaptery po niezależnej weryfikacji grantu; nie nasłuchuje w LAN;
- `control-plane-secrets` — broker kopert i rotacji z dostępem do KEK; przyjmuje
  wyłącznie uwierzytelnione, schematowane wywołania z prywatnej sieci/Unix socketu
  i nigdy nie zwraca wartości do GUI;
- obecny read-only interfejs mTLS może początkowo pozostać w `web`, ale ma osobny
  listener, politykę i namespace od przeglądarkowego API.

Na słabszym QNAP procesy mogą używać tego samego obrazu, lecz zachowują osobnych
użytkowników, mounty i powierzchnie sieciowe. `web` i `worker` mogą technicznie
współdzielić bazę operacyjną SQLite WAL, ale baza nie jest granicą zaufania:
rekord kolejki bez ważnego grantu `authz` jest niewykonalny, a worker ponownie
sprawdza preconditions i fencing token. Authz ma osobną bazę operatorów/credentiali
i klucz podpisujący, których `web` nie montuje. Secret broker ma osobną bazę
ciphertext/metadata oraz KEK. Komunikacja używa typowanych requestów, workload mTLS
i opaque `secret_ref`; sama obecność w prywatnej sieci Compose nie jest tożsamością.
Broker zwraca kopertę urządzenia, krótkotrwały token albo wynik allowlistowanej
operacji, nie długowieczny plaintext. Rozdzielenie procesów jest granicą
bezpieczeństwa, nie wymaganiem wielu repozytoriów.

Test bezpieczeństwa musi wykazać, że bezpośrednie dopisanie lub zmiana rekordów
`approval`/`operation` przez fixture skompromitowanego `web` nie prowadzi do
wykonania bez poprawnego, niewygasłego grantu związanego z tym samym planem.

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

Admin API Profile Sync nadal nie może być wystawione bezpośrednio do LAN. Plan
wybiera wykonalną ścieżkę: osobny writer listener mTLS w prywatnej sieci
`mwodevelop-control`, na innym porcie niż read-only integration API i consumer API.
Certyfikat klienta zawiera minimalne scope per akcja; listener obsługuje wyłącznie
wersjonowane kontrakty pairing/revoke, publish revision, create/reissue assignment
oraz report evaluation. Nie udostępnia generycznej mutacji ani SQL. Port nie jest
publikowany na hoście QNAP, a test Compose odrzuca jego obecność w `ports`.

Obecny loopback admin Profile Sync pozostaje break-glass dla lokalnego CLI i nie
jest trasą dla osobnego kontenera Control Plane. Unix socket nie jest wariantem
MVP; jego ewentualne wprowadzenie wymagałoby wspólnego mountu, peer credentials i
osobnego ADR zamiast niejawnego wyboru w czasie implementacji.

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

- `global-user`: np. konto OpenSubtitles lub wspólne klucze API YouTube, jeżeli
  są wspólne;
- `service`: GitHub App, klucze backupu i integracje administracyjne;
- `device-class`: tylko gdy jawnie uzasadnione;
- `device`: token Rapideo/Real-Debrid, sesja OAuth YouTube lub enrollment
  przeznaczony dla konkretnego urządzenia.

Po cutover QNAP przechowuje wszystkie **rutynowo używane** credentiale projektu:
Real-Debrid, Rapideo, OpenSubtitles, sesje OAuth YouTube, credentiale serwisowe VPN,
GitHub App, certyfikaty integracyjne, online assignment key oraz klucze techniczne
backupu/alertów. Importer ma mapować istniejące nazwy z `.env` do typowanego
rejestru, nigdy zapisywać całego `.env` jako blob. Hasło konta Google nie jest
obsługiwanym mechanizmem logowania dodatku YouTube i nie trafia do magazynu tylko
dlatego, że istnieje lokalnie.

Poza QNAP pozostają: offline root/promoter, klucz odblokowujący recovery backup,
co najmniej jedna passkey operatora oraz prywatne klucze urządzeń. Credentiale
ADB/SSH używane wyłącznie do reinstalacji są zaszyfrowanym zestawem break-glass,
nie zależnością rutynowych zadań panelu. Jest to celowe ograniczenie sformułowania
„wszystkie credentiale”: przejęty QNAP nie może jednocześnie odszyfrować backupu,
podpisać dowolnego stable i przejąć każde urządzenie.

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

#### 5.4.1 Widoki i model statusu

GUI ma być narzędziem operatorskim, a nie tylko wizualizacją surowych JSON-ów.
Każdy status pokazuje: stan, `observed_at`, `last_success_at`, źródło, próg
`stale_after`, bezpieczny `reason_code` i link do zredagowanego dowodu. `UNKNOWN`
oraz `STALE` są osobnymi stanami, nigdy zielonym `OK`. Agregaty nie ukrywają
częściowego błędu: dashboard może być `DEGRADED`, gdy Kodi działa, ale np. backup
albo harmonogram jest nieaktualny.

Planowane widoki:

1. **Dashboard** — liczba urządzeń online/offline/stale, aktywny bundle i rewizja,
   rollouty, krytyczne alerty, świeżość backupu, zdrowie usług QNAP, GitHub/Pages
   oraz najbliższe i spóźnione zadania cykliczne.
2. **Urządzenia** — `logical_device_id`, nazwa, platforma, generacja enrollmentu,
   ostatni heartbeat, wersja Kodi/Device Agenta, capabilities, aktywne repo i
   dodatki, `bundle_id`, `profile_revision_id`, wersja zestawu sekretów, drift i
   niezależne wyniki `code/profile/secrets/health`. IP/ADB/SSH jest tylko ulotnym
   atrybutem diagnostycznym z TTL.
3. **Rollouty i konfiguracja** — kandydat, zredagowany diff, release intent,
   exact-artifact evidence, kanał, fale, urządzenia wymagane/deferred, wyniki,
   blokady, historia pause/resume/cancel i kryterium zakończenia.
4. **Procesy cykliczne** — wspólny katalog GitHub Actions cron, workerów QNAP,
   watchdoga, backupów, rotacji oraz lokalnych synchronizacji urządzeń. Dla każdego
   procesu osobno: `scheduler_seen`, `last_started`, `last_completed`, wynik,
   czas trwania, `next_expected`, dopuszczalne opóźnienie i liczba kolejnych
   błędów. Dzięki temu działający scheduler z niesprawnym zadaniem nie jest
   raportowany tak samo jak zadanie, które w ogóle się nie uruchomiło.
5. **Usługi i zależności** — Control Plane, worker, secret broker, Profile Sync,
   provider relay, upstream watchdog, GitHub API, GitHub Pages, publiczne repo
   Kodi, DNS, NTP/TLS oraz stan przestrzeni/bazy QNAP. Provider relay jest
   oznaczony jako opcjonalny i nie może obniżać zdrowia wyszukiwania, jeśli działa
   bezpośredni fallback. Bez osobnego, uwierzytelnionego adaptera QTS panel zna
   tylko przestrzeń własnego wolumenu aplikacji; nie przedstawia jej jako zdrowia
   RAID, dysków ani całego NAS.
6. **Repozytoria i release** — stable/testing, commit i digest locka, wersje
   dodatków, atestacja, skan malware/SBOM, publikacja Pages, drift działających
   obrazów QNAP względem `qnap-stable.json` wraz z klasą jakości dowodu oraz
   dostępność artefaktów rollbacku.
   Bez Docker socketu panel nie dowodzi faktycznie uruchomionego digestu. Podpisany
   receipt zapisany atomowo przez `tools/qnap_images.py` (projekt, digest, czas,
   generation, wynik health) daje status `DEPLOYMENT_RECEIPT_VERIFIED`, a metadane
   usługi `SERVICE_SELF_REPORTED`; razem nadal nie są `RUNTIME_VERIFIED`. Brak
   świeżego receiptu daje `UNKNOWN/STALE`. Bieżący runtime potwierdza zewnętrzne
   `qnap_images.py status`/`docker inspect` albo przyszły ograniczony host collector.
   Receipt podpisuje deployment identity spoza QNAP, a panel ma tylko klucz
   publiczny i odrzuca rollback generation.
7. **Sekrety** — wyłącznie metadane: typ, zakres, wersja, właściciel, urządzenia
   używające, utworzono/obrócono/wygasa, stan kopert i ostatni bezpieczny probe.
   Nie ma przycisku „pokaż”, eksportu plaintextu ani wartości w DOM/API.
8. **Backup i recovery** — ostatni poprawny backup, digest, kopia off-box,
   weryfikacja, wiek ostatniego izolowanego restore drill, RPO/RTO oraz obecność
   recovery material bez jego odczytu.
9. **Bezpieczeństwo i audit** — spójność hash chain, eksport checkpointu, wygasanie
   certyfikatów/kluczy, stan GitHub App, nieudane logowania/pairing, skany obrazów,
   otwarte alerty i historia zatwierdzeń.
10. **Operacje** — trwała kolejka z aktorem, plan digest, stanem, postępem,
    terminem, retry, wynikiem, kompensacją i możliwością anulowania tylko w
    zdefiniowanym safe point.

Przed implementacją powstaje wersjonowana macierz pochodzenia:

```text
status field -> owner -> adapter -> auth -> observed_at -> stale_after
             -> trust level -> fallback -> reason codes
```

Macierz odróżnia podpisany raport urządzenia, self-report diagnostyczny,
obserwację GitHub, deployment receipt, rzeczywisty runtime QTS i cache ostatniego
sukcesu. Desired state nigdy nie jest przedstawiany jako observed state. Status,
którego nie dostarcza jeszcze żaden kontrakt, pozostaje `NOT_IMPLEMENTED/UNKNOWN`,
a nie jest syntetyzowany z nazwy urządzenia lub starego raportu.

Wszystkie terminy manifestu są UTC. Czas ścienny służy do deadline/TTL, a czas
monotoniczny do lokalnych duration/lease. Niezgodny NTP albo skok czasu ustawia
`CLOCK_UNTRUSTED`, blokuje nowe granty, pairing, rotacje i publikacje, ale nie
wyłącza read-only dashboardu ani działającej konfiguracji Kodi.

Katalog procesów cyklicznych jest wersjonowany w repo jako manifest, natomiast
run history i alerty są danymi runtime QNAP. GitHub cron pozostaje wykonawcą
zadań supply-chain; QNAP go obserwuje z zewnątrz i może wykryć brak uruchomienia.
Procesy lokalne QNAP używają trwałego schedulera z blokadą pojedynczego wykonania,
lease i idempotency key. Urządzenie raportuje swój `last_sync`/`next_sync`, ale
QNAP nie zakłada, że może je obudzić.

Wpis harmonogramu zawiera repo, workflow, event, cron UTC, grace/jitter, timeout,
owner, dependency, retry policy i indywidualny próg stale. CI porównuje manifest z
rzeczywistym `on.schedule` workflow YAML oraz `manifests/upstream-watchdog.json`,
aby uniknąć trzech rozjechanych źródeł prawdy. Jeden globalny próg 36 godzin nie
jest poprawny dla procesu uruchamianego co 15 minut. Dla lokalnych zadań QNAP
manifest jest źródłem schedulera; dla GitHub jest walidowanym katalogiem/monitorem.

Alert ma severity, fingerprint, first/last seen, licznik, stan
`OPEN/ACKNOWLEDGED/RESOLVED` i link do źródła. Identyczne zdarzenia są deduplikowane;
powrót do zdrowia zamyka alert, ale nie usuwa historii. Pierwszy release pokazuje
alerty w GUI, a opcjonalny kolejny adapter może wysłać e-mail/webhook z użyciem
credentialu z secret store i bez danych wrażliwych.

Panel nie może wiarygodnie monitorować własnej całkowitej awarii. Loopback `/ready`
pozostaje wyłącznie healthcheckiem kontenera. `qnap-upstream-watchdog` zostaje
dołączony do `mwodevelop-control` i używa dedykowanego read-only certyfikatu mTLS,
aby sprawdzać prywatny observer endpoint Control Plane, świeżość schedulera i
backupów bez czytania jego DB. Compose nie publikuje tego endpointu do LAN.
Całkowita niedostępność QNAP wymaga opcjonalnego zewnętrznego dead-man checku poza
NAS; brak takiego checku jest jawnie pokazanym ograniczeniem, nie zielonym statusem
generowanym przez sam panel.

#### 5.4.2 Akcje administratorskie

Akcje są pogrupowane ryzykiem, a nie prezentowane jako dowolne polecenia:

- **niski poziom ryzyka, operator:** odśwież status, ponów bezpieczny probe,
  zakolejkuj `Reconcile at next poll` dla jednego urządzenia, przelicz drift,
  zweryfikuj audit lub backup, ponów bezpieczną rekonsyliację, wygeneruj
  zredagowany bundle diagnostyczny. Model pull nie obiecuje natychmiastowego
  `Sync now`: urządzenie odbiera żądanie przy następnym heartbeat/poll i QNAP go
  nie budzi ani nie otwiera połączenia do Kodi;
- **średni poziom ryzyka, operator + potwierdzenie planu:** wygeneruj pairing,
  utwórz kandydata profilu, przypisz canary, rozpocznij/pauzuj/wznów/anuluj falę,
  uruchom dokładny allowlistowany `workflow_dispatch`, ustaw/obróć sekret i
  wykonaj izolowany restore drill;
- **wysoki poziom ryzyka, ponowne WebAuthn i rola approver:** opublikuj aktywną
  rewizję po spełnieniu bramek, zatwierdź exact bundle/release intent, unieważnij
  konkretny enrollment lub wersję sekretu, obróć klucz online assignmentu;
- **break-glass poza zwykłym GUI:** produkcyjny restore, reinstalacja Kodi/systemu,
  odzyskanie KEK/offline root, zmiana zaufanego DNS/CA i wymuszone cofnięcie kodu.

Lista dozwolonych workflow i parametrów jest wersjonowanym manifestem. UI wybiera
akcję i pola z tego manifestu; nie przyjmuje nazwy repo, ścieżki workflow, refu,
komendy ani URL-u podanych dowolnie przez operatora.

#### 5.4.3 Kontrakt trwałej operacji

Plan i operacja mają osobne, niesprzeczne lifecycle:

1. `POST /api/v1/action-plans` tworzy preflight bez skutków ubocznych i zwraca
   `plan_id`, canonical JSON, digest, wpływ, wymagane bramki, safe points,
   `expires_at`, policy/manifest version, oczekiwane generacje zasobów oraz
   przewidywaną kompensację;
2. plan przechodzi `DRAFT -> PREFLIGHTED -> AWAITING_APPROVAL -> APPROVED` albo
   `EXPIRED`. Operator zatwierdza dokładny digest, a dla operacji wysokiego ryzyka
   ponownie uwierzytelnia się WebAuthn; authz wydaje podpisany grant;
3. dopiero ważny `APPROVED` może utworzyć przez `POST /api/v1/operations` operację
   `QUEUED` z `Idempotency-Key`, grantem i auditem;
4. worker weryfikuje grant, fencing token i aktualne preconditions. Drift daje
   `PLAN_STALE`, a nie próbę wykonania. Następnie przechodzi przez
   `PREFLIGHT_RECHECK -> DISPATCHING -> RUNNING -> VERIFYING` do `SUCCEEDED`,
   `FAILED`, `PARTIAL`, `CANCELLED`, `COMPENSATION_REQUIRED` albo
   `UNKNOWN_REQUIRES_RECONCILIATION`;
5. wynik zawiera wyłącznie zredagowany output i link do dowodu. Postęp GUI może
   używać SSE, ale prawdą pozostaje zapis w bazie, nie otwarte połączenie.

Operacje na SQLite używają WAL, krótkich transakcji, unique constraint dla
idempotency key i CAS dla stanów. Worker nie wykonuje arbitralnych pluginów:
adaptery są rejestrowane w kodzie, wersjonowane i testowane. Długie operacje mają
timeout, heartbeat lease i jawne safe points; `cancel` nigdy nie przerywa zapisu
secret store, publikacji CAS ani migracji bazy w połowie.

System nie obiecuje exactly-once dla skutków zewnętrznych. Adapter deklaruje klasę
`pure`, `idempotent`, `reconcilable` albo `at_most_once`. Kolejka używa
transactional outbox i monotonicznego fencing tokenu. Dla `workflow_dispatch`
deterministyczny `operation_id` jest obowiązkowym inputem, trafia do concurrency
key oraz wyniku/artefaktu, aby po timeoutcie worker najpierw odnalazł istniejący
run. Analogiczny connector-specific correlation jest wymagany dla innych API.
Po crashu między przyjęciem remote a lokalnym commitem stan przechodzi przez
`REMOTE_ACCEPTED` albo `UNKNOWN_REQUIRES_RECONCILIATION`; nigdy nie następuje ślepy
retry. Jeżeli zewnętrzny system nie udostępnia korelacji ani bezpiecznego inspect,
operacja `at_most_once` wymaga ręcznego rozstrzygnięcia przed kolejną próbą.

`cancel` zapisuje `CANCEL_REQUESTED`. Dopiero adapter w safe point może zakończyć
`CANCELLED`; operacja już zaakceptowana zewnętrznie może pozostać
`CANCEL_REQUESTED`/`VERIFYING`, jeżeli remote API nie wspiera anulowania.

Bazy SQLite muszą leżeć na lokalnym systemie plików wolumenu QNAP z poprawnym
POSIX locking; SMB/NFS i katalog synchronizowany sieciowo są zabronione. Bramka
ARMv7 obejmuje współbieżnych writerów, WAL checkpoint, `fsync`, pełny dysk,
power-cut/restart oraz odzyskanie lease. Migracje wykonuje jeden migration leader
w maintenance/read-only mode i strategią expand/contract. Jeżeli kwalifikacja
filesystemu nie przejdzie, jeden proces staje się wyłącznym właścicielem DB i
udostępnia prywatne API zamiast współdzielonego pliku.

Każda tabela eventowa ma limit rozmiaru i wersjonowaną retencję. Read-only polling
dashboardu trafia do metryk/access logu z samplingiem, a nie dopisuje każdego GET
do tamper-evident audit chain. Audit zachowuje logowania i ich błędy, odczyt
sekretnej metadata/eksportu, plan/approval/mutację, zmianę polityki, backup/restore
i akcje break-glass. Dzięki temu odświeżanie GUI nie tworzy contention ani
nieograniczonego wzrostu bazy.

#### 5.4.4 Endpoint i kontrakt GUI

Docelowy origin to stabilna nazwa LAN, np. `https://kodi-admin.home.arpa`, z
certyfikatem zaufanym przez urządzenie operatora. QTS reverse proxy może zakończyć
TLS i kierować ruch na port panelu opublikowany wyłącznie na loopback QNAP; aplikacja
nadal wykonuje własne WebAuthn, sesje, CSRF i RBAC oraz ufa nagłówkom proxy tylko z
jednego jawnego adresu. Dostęp po surowym IP nie jest wspieranym originem WebAuthn.
Obecny port `19443` pozostaje osobnym read-only API mTLS dla CLI/integracji.

MVP wybiera jeden transport: TLS kończy się w QTS, a QTS -> web używa HTTP wyłącznie
po loopback QNAP. Nie zakładamy jednocześnie drugiego, nieopisanego TLS upstream.
Spike musi potwierdzić, że Container Station respektuje bind loopback i QTS może
osiągnąć port. Aplikacja ma ścisłą allowlistę `Host`, `Origin`, RP ID, adresu proxy
oraz `X-Forwarded-Proto/Host`; żądanie bez zgodnego zestawu jest odrzucane.

Pierwszego operatora nie może zarejestrować pierwszy klient LAN. Lokalny CLI po
mTLS tworzy jednorazowy bootstrap token w authz, zapisany `0400`, z TTL maksymalnie
10 minut i przypięty do oczekiwanego originu. Dopiero jego podanie w flow WebAuthn
pozwala zarejestrować dwie passkeys i wygenerować jednokrotnie recovery codes.
Po sukcesie token jest atomowo niszczony, bootstrap przechodzi trwale w
`DISABLED`, a endpoint zwraca 404. Ponowne otwarcie wymaga lokalnego break-glass,
jest audytowane i nie może nastąpić przez zwykłą sesję GUI.

Minimalne wersjonowane endpointy przeglądarkowego API:

```text
GET  /api/v1/dashboard
GET  /api/v1/devices[/<logical_device_id>]
GET  /api/v1/schedules[/<schedule_id>/runs]
GET  /api/v1/services
GET  /api/v1/releases
GET  /api/v1/rollouts[/<rollout_id>]
GET  /api/v1/secrets                  # tylko metadane
GET  /api/v1/operations[/<operation_id>]
GET  /api/v1/alerts
GET  /api/v1/audit
POST /api/v1/action-plans
POST /api/v1/operations
POST /api/v1/operations/<id>/cancel
POST /api/v1/secrets                  # set/rotate bez read-back
POST /api/v1/pairing-codes
```

Szczegółowe typy akcji są discriminated union w OpenAPI/JSON Schema; nie istnieje
generyczny endpoint `exec`. Frontend jest statycznym artefaktem z tego samego
podpisanego obrazu, bez CDN i kodu third-party. Obowiązują CSP bez `unsafe-inline`,
cookies `Secure`, `HttpOnly`, `SameSite=Strict`, rotacja session ID, krótki idle
timeout i blokada cache dla odpowiedzi administracyjnych. UI korzysta wyłącznie z
API — każda operacja ma odpowiednik CLI mTLS oparty na tym samym kontrakcie i
polityce, aby automatyzacja nie obchodziła kontroli GUI.

Docelowy zakres pierwszego pełnego release:

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

Panel pierwszego wydania nie zarządza lifecycle swoich kontenerów i nie montuje
`/var/run/docker.sock`. Upgrade/deploy czterech aplikacji QNAP pozostaje
zewnętrzną, przypiętą digestem operacją `tools/qnap_images.py`.

Przed pełnym cutover należy jednak usunąć rutynową zależność od workstation przez
osobny `mwodevelop-qnap-deployd` działający jako minimalna usługa hosta QTS, nie
kontener web. Executor ma dostęp do zarządzanego demona Container Station, ale
przyjmuje wyłącznie podpisany deployment intent dla stałej listy projektów i
digestu obecnego w zatwierdzonym `qnap-stable.json`; nie przyjmuje polecenia,
ścieżki Compose, env, URL-u ani argumentów powłoki. Niezależnie weryfikuje grant,
policy generation, podpis artefaktu, health, rollback i zapisuje antyrollback
receipt. Socket/API executora jest dostępne tylko workerowi, nie `web`, a executor
potrafi zakończyć lub cofnąć self-upgrade po zatrzymaniu starego Control Plane.
`tools/qnap_images.py` pozostaje klientem/biblioteką i ścieżką break-glass.

Pairing ma rate limit per IP i globalnie, backoff, krótki TTL, limit aktywnych
kodów, jednorazowość oraz audyt prób. Przed zatwierdzeniem UI pokazuje logical ID,
generację i fingerprint nowego klucza urządzenia. Pairing nigdy nie nadaje roli
administracyjnej.

Audit jest tamper-evident, nie tamper-proof: monotoniczny sequence, hash chain,
checkpointy i wykrywanie braków. Obecny HMAC z kluczem na QNAP chroni głównie
przed przypadkowym uszkodzeniem; root QTS może odczytać klucz i wygenerować nowy
HMAC. Dlatego najwyższy `sequence/head_sha256` jest cyklicznie zakotwiczany w
niezależnym append-only/WORM miejscu poza QNAP, które nie pozwala credentialowi NAS
usunąć ani przepisać poprzedniego anchora. Restore i każdy nowy anchor muszą
kontynuować ostatni zewnętrzny head. Dopiero porównanie z tym anchorem wykrywa
złośliwy rollback QNAP; plan nie przypisuje takiej własności samemu lokalnemu HMAC.

### 5.5 Integracja GitHub

QNAP używa dedykowanej GitHub App z minimalnymi uprawnieniami zamiast osobistego PAT.

Secret broker przechowuje private key App i podpisuje JWT; worker otrzymuje
wyłącznie krótkotrwały installation token dla jawnego installation ID/repo i
minimalnych permissions. Token żyje tylko w pamięci procesu, nie trafia do DB,
audit, logu ani kolejki, ma ograniczony cache krótszy od TTL i jest odświeżany po
401/wygaśnięciu bez logowania wartości. Read-only obserwacja oraz dispatch używają
oddzielnych App/instalacji, chyba że ADR i test uprawnień dowiodą równoważnej
separacji. Rotacja private key zachowuje okres dwóch kluczy i jawne unieważnienie.

GitHub App może:

- odczytywać workflow, commity, release i atestacje;
- uruchamiać jawnie dozwolone workflow `workflow_dispatch`;
- opcjonalnie tworzyć PR z kandydatem locka.

Allowlista wiąże owner/repository, dokładny workflow path i ref, dozwolone inputy,
branch/ref oraz limit częstotliwości. Sam wynik `success` nie wystarcza. Control
plane weryfikuje issuer atestacji, subject/repository, workflow identity, commit,
artifact SHA-256 i digest bajtów publicznych. Dispatch i odczyt mogą używać
oddzielnych instalacji/uprawnień, jeżeli pozwala na to GitHub.

Macierz GitHub App zapisuje dla każdej App: installation ID, owner/repo, dokładne
permissions, dozwolone endpointy, token TTL, limity/rate-limit policy i procedurę
rotacji. Workflow dostępny z GUI musi przyjmować `operation_id` i walidować go jako
correlation/concurrency key; bez tego nie kwalifikuje się do automatycznego retry.

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

1. **Wykonane:** wdrożyć obraz przypięty digestem w Container Station, read-only
   API mTLS, zredagowany stan Profile Sync/GitHub, audit, backup/restore oraz
   `convergence_bundle_v1` z lokalnym writerem CLI.
2. Dodać manifest katalogu procesów cyklicznych i adaptery statusu dla GitHub
   Actions, watchdog, Profile Sync, pozostałych usług QNAP, backupów i lokalnych
   heartbeatów urządzeń.
3. Zaimplementować normalizację `OK/DEGRADED/FAILED/UNKNOWN/STALE` z osobnym
   scheduler health, run result i freshness; dodać reguły alertów oraz ich
   deduplikację/acknowledgement.
4. Udostępnić przeglądarkowy dashboard read-only pod stabilnym HTTPS/WebAuthn,
   pozostawiając obecne API mTLS bez zmiany kontraktu.
5. Rozdzielić procesy/mounty `web`, `worker` i `secrets`; worker na tym etapie
   wykonuje wyłącznie read-only refresh/probe, a secret broker używa fixture bez
   produkcyjnych wartości.
6. Dodać backup, restore do izolowanego projektu Compose, restart całego stosu,
   test ARMv7 i skan, że frontend/API/audit nie zawierają canary secret.

### Etap C — import sekretów w trybie shadow

1. Wykonać typowany inventory nazw z lokalnego `.env`/`.kodi-private`, online
   backup QNAP i zaszyfrowany eksport lokalnych danych recovery; raport inventory
   nie zawiera wartości.
2. Wdrożyć secret broker z envelope encryption, osobnym KEK mountem `0400`, ACL,
   metadanymi wersji/rotacji i zakazem read-back przez web/worker.
3. Importować sekrety jednokierunkowo przez CLI po mTLS; wartości są przekazywane
   przez stdin/plik `0600`, nigdy argument, URL, shell history ani JSON odpowiedzi.
4. Zweryfikować per rekord digest/HMAC i możliwość użycia przez izolowany adapter,
   bez ujawnienia plaintextu. Skan canary obejmuje DB, logi, audit, backup,
   diagnostykę, HTML/JS i historię operacji.
5. Przez okres przejściowy lokalny host pozostaje źródłem wykonania, ale porównuje
   tylko obecność/wersję sekretu QNAP. Dwie niezależne, zaszyfrowane kopie i
   udany cold restore są bramą cutover.
6. Etap C kończy się stanem `SHADOW_VERIFIED`. Lokalny host nadal wykonuje
   produkcyjne operacje i zachowuje dotychczasowy plaintext; QNAP nie staje się
   źródłem prawdy tylko na podstawie poprawnego importu. Obowiązuje dual-read bez
   dual-write: każda zmiana sekretu ma jednego writer-a i jest ponownie importowana
   do shadow z nową wersją.

### Etap D — autonomiczne ustawienia i sekrety

1. Wydać Device Agent z obsługą desired state bez zarządzania kodem dodatków.
2. Przetestować ustawienia niesekretne na BlueStacks i X88.
3. Dodać koperty sekretów oraz adaptery Rapideo, OpenSubtitles i Umbrella/RD.
   Kontrakt adaptera YouTube można przygotować na ręcznie zainstalowanym canary,
   ale produkcyjny apply nie może go uruchamiać przed instalacją i weryfikacją
   dodatku w etapie E. Hasło Google nie jest obsługiwanym credentialem.
4. Wykazać, że każde urządzenie odszyfrowuje tylko własny payload.
5. Wykazać `NO_CHANGE` dla tego samego bundle, retry po braku sieci, rollback po
   błędnym sekrecie i brak wycieku do logów.

### Etap E — autonomiczne dodatki przez repo

1. Rozszerzyć desired state o repo i dodatki.
2. Najpierw tryb `audit`: raport driftu bez instalacji.
3. Opublikować dokładnego kandydata testing i wykonać `apply` najpierw na
   BlueStacks, potem X88, pojedynczo dla repo, Profile Sync, MwoScrapers, Umbrella,
   WatchNixtoons2, Rapideo, YouTube i usług napisów.
   Dla oficjalnego YouTube kandydatem jest rewizja manifestu kwalifikacji i
   oficjalny artefakt, a nie kopia opublikowana w testing mwoDevelop.
4. Sprawdzić instalację zależności, origin, aktualizację nowszej wersji, restart
   Kodi, manifest plików oraz idempotentny drugi przebieg.
   Kolejność dla YouTube jest obowiązkowa: instalacja -> restart -> sprawdzenie
   schematu -> ustawienia API -> restart -> device flow albo
   `AUTHORIZATION_REQUIRED` -> health.
5. Dopiero po pełnym canary wykonać review i publikację stable. Stable jest
   globalną aktualizacją; QNAP obserwuje i raportuje pozostałą flotę.

### Etap F — rollout QNAP i interfejs administracyjny

1. Wdrożyć trwały model `action_plan`/`operation`, kolejkę SQLite WAL, worker lease,
   idempotency, retry, safe points, kompensacje i recovery po restarcie QNAP.
2. Najpierw udostępnić wyłącznie akcje niskiego ryzyka i wykazać, że ten sam plan
   przez GUI oraz CLI mTLS daje ten sam audit i wynik `NO_CHANGE` przy powtórzeniu.
3. Zaimplementować niezmienny rollout plan, fale, pause/resume/cancel, timeouts,
   supersession i odrębne statusy code/profile/secrets/health.
4. Udostępnić allowlistowane akcje operatorskie według klas ryzyka, re-auth i
   dokładnego digestu planu; brak generycznego `exec`/URL/workflow/ref.
5. Przenieść publikację profilu, assignmenty i ocenę raportów z hosta.
6. Zintegrować GitHub App jako osobne adaptery read/dispatch z minimalnymi
   uprawnieniami i weryfikacją atestacji; panel nie merge'uje PR.
7. W MVP zachować lifecycle własnego stosu QNAP poza GUI i bez Docker socketu.
   Panel pokazuje receipt/self-report i jawne `RUNTIME_UNVERIFIED`; wiarygodny live
   drift nadal ustala `tools/qnap_images.py status`.
8. Przed pełnym cutover wdrożyć i niezależnie zaudytować ograniczony host-side
   `mwodevelop-qnap-deployd`, w tym self-upgrade, rollback i odmowę dowolnego
   digestu/projektu/parametru. Docker/QTS socket nigdy nie trafia do web/workera.
9. Po kwalifikacji usunąć rutynową rolę hosta; hostowe komendy mają zostać
   wrapperem API QNAP albo narzędziem break-glass.
10. Dopiero gdy wszystkie produkcyjne adaptery działają z QNAP, dostępna flota ma
   zweryfikowane koperty i `NO_CHANGE`, operacje przechodzą bez localhost, a
   rollback oraz `recovery_bundle_v1` zostały odtworzone, zapisać audytowalny punkt
   `CUTOVER_COMMITTED`.
11. Po `CUTOVER_COMMITTED` unieważnić stare credentiale administracyjne, usunąć
    rutynowy plaintext z localhost i pozostawić wyłącznie zaszyfrowany offline
    recovery export. Cofnięcie przed tym punktem wraca do hosta; po nim wymaga
    kontrolowanego recovery, nie ukrytego dual-write.

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
- IDOR: operator nie może zmienić `logical_device_id`, `secret_id`, `plan_id` ani
  `operation_id` w URL/payloadzie i uzyskać szerszego zakresu;
- testy XSS/CSP, session fixation, rate limit, CORS, nagłówków reverse proxy,
  ponownego WebAuthn oraz timeoutu sesji;
- secret broker odrzuca wywołania bez workload identity, a proces web nie ma
  mountu KEK, GitHub App private key ani ciphertext DB do bezpośredniego odczytu;
- operacja o tym samym idempotency key i digest planu nie wykonuje mutacji drugi
  raz; ten sam klucz z innym digestem jest odrzucany;
- żaden test/API nie oferuje generycznej komendy, ścieżki hosta, URL-u ani
  nieallowlistowanego workflow/ref;
- skan obrazu i zależności, SBOM, podpis obrazu i przypięty digest;
- negatywny test uszkodzonego backupu i brakującego KEK;
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
- Real-Debrid, Rapideo, OpenSubtitles.com, alternatywę `.org` oraz YouTube z
  device-code OAuth i tokenem właściwym dla urządzenia;
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
- zabicie API i workera w każdej fazie operacji; po restarcie worker używa fencing
  token/outbox i remote inspection. Test obejmuje `REMOTE_ACCEPTED`, nieznany wynik,
  ręczną rekonsyliację i dowodzi braku ślepego ponowienia, a nie nierealnego
  exactly-once zewnętrznego API;
- bezpośrednia modyfikacja operacyjnej DB przez fixture skompromitowanego `web`
  nie wykonuje operacji bez ważnego grantu authz; drift preconditions daje
  `PLAN_STALE`;
- E2E przeglądarki: login WebAuthn, dashboard, filtrowanie urządzeń, podgląd
  harmonogramu, preflight, zatwierdzenie, SSE/postęp, wynik i audit; negatywnie
  CSRF, wygasła sesja, brak roli, zmieniony digest planu i wyścig pierwszego
  operatora; bootstrap kończy się dopiero po dwóch passkeys i trwałym `DISABLED`;
- fixture procesów cyklicznych rozróżniający: scheduler nie działa, run failed,
  run overdue, dane stale i poprawny no-op; alert powstaje raz i może zostać
  potwierdzony bez kasowania historii;
- wszystkie ekrany pozostają użyteczne przy niedostępnym GitHub/Profile Sync i
  pokazują ostatni poprawny snapshot jako `STALE/DEGRADED`, nie `OK`;
- backup online i restore całego `recovery_bundle_v1` do izolowanego projektu;
  mieszany backup epoch, brak wrapped KEK albo cofnięty audit anchor są odrzucane;
- awaria Profile Sync, GitHub i DNS bez utraty planu;
- odnowienie certyfikatu TLS, rotacja GitHub App i KEK;
- import shadow oraz rotacja fixture każdego typu sekretu, brak read-back i pełny
  canary-secret scan bazy, logów, audit, backupu, HTML oraz diagnostyki;
- test ARMv7 na rzeczywistym QNAP;
- kontrola widoczności aplikacji w Container Station;
- watchdog z dedykowanym mTLS na prywatnej sieci monitorujący cykliczny backup i
  observer endpoint Control Plane; loopback `/ready` pozostaje nieosiągalny z
  innego kontenera;
- writer API Profile Sync nie jest opublikowane do LAN i odrzuca certyfikat/scope
  niewłaściwe dla pairing, revoke, publish albo assignment;
- `mwodevelop-qnap-deployd` odrzuca nieallowlistowany projekt, digest, manifest,
  argument i cofniętą generation; przechodzi live inspect, self-upgrade, health i
  rollback bez montowania demona do kontenera aplikacyjnego;
- utrata całego QNAP i cold restore na pustym, zastępczym hoście z zachowaniem
  DNS/certyfikatu albo kontrolowaną rotacją zaufania.

## 8. Rollback i recovery

- rollout można zatrzymać przed następną falą;
- aktywna konfiguracja może wskazać poprzednią, nadal przechowywaną rewizję;
- klient przechowuje lokalny backup zmienianych ustawień i journal;
- kod dodatku nie jest automatycznie downgrade'owany bez jawnego, dostępnego
  artefaktu i osobnej zgody;
- control plane tworzy niemutowalny `recovery_bundle_v1` związany jednym
  `backup_epoch_id`, a nie zestaw niezależnych kopii o nieznanej zgodności;
- restore produkcyjny wymaga zatrzymania writerów, integralności, zgodności schematu
  i ponownego health checku;
- hostowe `tools/kodi_reinstall.py` oraz zaszyfrowany recovery kit pozostają
  ostatnią ścieżką break-glass, dopóki czysta instalacja nie zostanie wielokrotnie
  zakwalifikowana.

`recovery_bundle_v1` zawiera manifest digestów i zgodne epochy:

- Control Plane DB, operational blobs, kolejkę i audit;
- authz DB: publiczne credentiale WebAuthn, RBAC, zahashowane recovery codes oraz
  zaszyfrowane TOTP/session bootstrap secrets;
- Profile Sync DB, bloby, key registry i jego backup epoch;
- secret DB/ciphertext oraz KEK opakowany kluczem recovery przechowywanym poza
  QNAP — nie tylko metadata KEK;
- konfigurację Compose, policy/action/schedule manifests, certyfikaty możliwe do
  backupu oraz procedurę rotacji tych, których nie eksportujemy;
- lokalny DNS/RP ID, konfigurację QTS reverse proxy i minimalny runbook bootstrapu;
- audit checkpoint oraz odwołanie do najwyższego zewnętrznego anchora.

Backup coordinator wprowadza krótki writer barrier albo używa aplikacyjnych
snapshotów związanych nonce/epoch; mieszane epochy są odrzucane. Dwie zaszyfrowane
kopie trafiają do jawnie skonfigurowanych, niezależnych lokalizacji poza QNAP, z
retencją odporną na przypadkowe nadpisanie. Nazwy/owner tych lokalizacji są bramą
wdrożenia, nie opcjonalną notatką w runbooku. Restore drill odtwarza cały bundle do
izolowanego projektu i porównuje enrollment, bundle head, secret versions, RBAC,
audit anchor oraz możliwość wydania testowej koperty.

Docelowe parametry po cutover: RPO maksymalnie 24 godziny i RTO maksymalnie 4
godziny od dostępności zastępczego hosta Docker. Brak QNAP przełącza system w
degraded mode: Kodi zachowuje lokalne tokeny i odtwarzanie, nie usuwa konfiguracji
z powodu TTL, a nowe pairing, rotacje i rollouty są jawnie niedostępne.

## 9. Zmiany w repozytoriach

### `mwoDevelop/kodi`

- manifest desired-state i polityka rolloutów;
- `manifests/control-plane-schedules.json` z oczekiwanym czasem/freshness oraz
  `manifests/control-plane-actions.json` ze ścisłą allowlistą akcji/workflow;
- Compose i cykl życia obrazu control plane;
- rozszerzenie `tools/qnap_images.py` o nową usługę;
- host-side `mwodevelop-qnap-deployd` z allowlistą projektów/digestów, podpisanym
  deployment intent, self-upgrade state machine i break-glass CLI;
- atomowy, podpisany deployment receipt jako dowód ostatniego wdrożenia, bez
  nazywania go weryfikacją faktycznie działającego runtime;
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

### Istniejące `mwoDevelop/kodi-control-plane`

- LAN-only API/UI, RBAC i WebAuthn;
- magazyn sekretów;
- fleet/rollout controller;
- GitHub App integration;
- audit, backup i worker.

Control Plane pozostaje osobnym repozytorium, procesem i powierzchnią uprawnień.
Wspólne kontrakty są wersjonowanymi schematami/pakietami, nie współdzielonymi
tabelami ani kopiowanym kodem. Nie należy łączyć admin UI z consumer API Kodi.

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
  allowlistowane akcje, klasy ryzyka, plan/approval/operation oraz zredagowane
  przykłady GUI i CLI;
- `status-and-alerts.md` — semantyka `OK/DEGRADED/FAILED/UNKNOWN/STALE`, freshness,
  agregacja, reason codes, alerty, deduplikacja, acknowledgement oraz macierz
  owner/adapter/auth/trust/fallback dla każdego pola;
- `scheduled-jobs.md` — katalog GitHub/QNAP/device, oczekiwane terminy, lease,
  idempotency, retry oraz rozróżnienie scheduler/run/freshness;
- `operations.md` — state machine kolejki, safe points, cancel, retry,
  kompensacje, klasy skutków zewnętrznych, outbox/fencing, rekonsyliacja,
  idempotency i recovery po restarcie;
- `auth-bootstrap.md` — lokalne utworzenie jednorazowego tokenu, dwie passkeys,
  trwałe wyłączenie bootstrapu, recovery, proxy headers i utrata operatora;
- `qnap-deployd.md` — hostowa granica uprawnień, podpisany deployment intent,
  allowlista, self-upgrade, receipt/live inspect, rollback i break-glass;
- `github-app.md` — instalacja, minimalne uprawnienia, allowlista workflow,
  atestacje i rotacja klucza;
- `secrets.md` — klasyfikacja, shadow import, envelope, klucz urządzenia, rotacja,
  revocation, redaction i recovery, w tym globalne klucze API oraz per-device
  sesje OAuth YouTube;
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
13. dashboard rozróżnia brak schedulera, błąd runu i stale dane, a test zegara
    potwierdza alert po przekroczeniu każdego manifestowego deadline;
14. GUI i CLI wykonują tę samą operację przez ten sam kontrakt, a ponowienie z tym
    samym idempotency key nie tworzy drugiej lokalnej operacji; niejednoznaczny
    skutek zewnętrzny przechodzi przez rekonsyliację, nie ślepy retry;
15. proces web nie ma dostępu do KEK ani credentiali wykonawczych, secret store nie
    ma read-back, a canary secret scan całego pipeline jest czysty;
16. upgrade control plane nadal jest możliwy przy niedziałającym panelu przez
    przypięty digest i niezależny `mwodevelop-qnap-deployd`, a
    `tools/qnap_images.py` pozostaje zaudytowaną ścieżką break-glass.

## 12. Kolejność realizacji i przybliżony koszt

| Faza | Rezultat | Stan 2026-08-22 | Pozostały szacunek |
|---|---|---|---:|
| 0 | ADR, threat model i spiki go/no-go Kodi/crypto/WebAuthn | częściowo | 2–5 dni |
| 1 | Read-only API mTLS, audit, backup i QNAP Compose | wydane | 0 dni |
| 2 | Bundle, delegowany signer, lifecycle schematów i mixed-version | bundle wydany, delegacja offline | 3–7 dni |
| 3A1 | Read-only status API, katalog harmonogramów, freshness i UI mTLS | wydane i wdrożone | 0 dni |
| 3A2a | Tymczasowy browser auth password+TOTP, bootstrap/recovery i browser E2E | w realizacji | 0–1 dzień |
| 3A2b | Stabilny DNS/TLS, QTS proxy lub ingress i WebAuthn | odroczone po spike QTS 5.2 | 3–6 dni |
| 3B | Trwała kolejka akcji niskiego ryzyka, outbox/fencing i rekonsyliacja | do wykonania | 5–10 dni |
| 4 | Magazyn sekretów, import shadow, koperty i off-box recovery | do wykonania | 6–12 dni |
| 5A | Device Agent, GitHub App, kontroler fal, canary i exact-artifact proof | częściowo | 10–20 dni |
| 5B | Ograniczony QTS deployd, czysta instalacja, pełna flota, cold restore i release | do wykonania | 7–14 dni |

Pozostały bazowy szacunek to około 41–83 dni roboczych. Z buforem 30–40% na
WebAuthn na docelowym originie, kryptografię/ARMv7, realne rotacje credentiali,
integrację GitHub App, QTS deployd i cold restore należy planować około 55–117 dni.
Plan daje wartość wcześniej: read-only GUI ze statusami powinno być możliwe po
4–7 dniach, a pierwsze bezpieczne akcje niskiego ryzyka po kolejnych 9–18 dniach
obejmujących authz/WebAuthn i początek kolejki. Import produkcyjnych sekretów nie
jest skrótem MVP i nie może wyprzedzić recovery drill.

## 13. Następne przyrosty implementacyjne

### Przyrost 3A1 — status API i dashboard mTLS bez mutacji

1. Dodać manifest `scheduled-jobs` opisujący aktualne workflow GitHub, watchdog,
   zadania QNAP, backup i synchronizację urządzeń wraz z `next_expected` oraz
   `stale_after`.
2. Rozszerzyć agregator o statusy usług QNAP, Pages/release, backup/audit,
   bezpieczeństwo, urządzenia i niezależne freshness; dodać wersjonowane endpointy
   dashboardu.
3. Zbudować statyczne GUI bez CDN, dostępne wyłącznie w trybie read-only
   przez istniejące mTLS, aby zweryfikować model danych bez nowej autoryzacji.
4. Wdrożyć na QNAP przypięty digest, przejść test ARMv7, restart, degraded mode i
   potwierdzić, że żaden endpoint mutujący nie istnieje.

### Przyrost 3A2 — browser auth bez mutacji

1. W 3A2a opublikować osobny listener `:19444` bez certyfikatu klienta, ograniczony
   do LAN, dokładnego Host/Origin i ścieżki `/control-plane/`; obecne `:19443`
   pozostawić bez zmian za mTLS.
2. Uruchomić osobny authz z jednorazowym bootstrapem, hasłem scrypt, TOTP,
   recovery codes, limitem prób i sesjami. Web/BFF ma mieć wyłącznie certyfikat
   mTLS read-only do czterech endpointów core i nie ma dostępu do sekretów floty.
3. Wykonać browser E2E, negatywne Host/Origin/LAN/CSRF/session/scope tests,
   restart i recovery operatora. Potwierdzić, że browser TLS nie wysyła
   `CertificateRequest`, a stare API nadal go wymaga.
4. W 3A2b, po dostępności stabilnego lokalnego DNS i wspieranego ingressu,
   zastąpić ostrzeżenie certyfikatu zaufanym TLS i dodać WebAuthn. Nie blokuje to
   read-only 3A2a i nie otwiera mutacji.

### Przyrost 3B — kolejka i bezpieczne akcje

1. Dodać schema/migracje `action_plan`, `operation`, `operation_event`,
   `schedule_run`, `alert` i `approval` wraz z lifecycle N/N-1.
2. Uruchomić oddzielny `worker` bez portu LAN, z trwałym lease i wyłącznie
   adapterami `refresh`, `probe`, `enqueue-reconcile`, `verify-backup` oraz
   `export-diagnostics`.
3. Udostępnić preflight, digest planu, idempotency, status/postęp i cancel tylko w
   safe point; potwierdzić wspólny kontrakt GUI/CLI mTLS.
4. Przetestować restart API/workera/QNAP w każdej fazie, fencing/outbox,
   retry/no-op, równoległość, odmowę zmienionego planu, remote correlation oraz
   `UNKNOWN_REQUIRES_RECONCILIATION` bez ślepego retry.
5. Dopiero potem dołączać pairing, profile candidate/rollout i ścisłą allowlistę
   GitHub App; promocja stable pozostaje poza pierwszym zestawem akcji.

### Przyrost 4 — secret store shadow

1. Zatwierdzić ADR secret envelope/KEK i wykonać działający cold restore na
   fixture przed produkcyjnym importem.
2. Uruchomić osobny secret broker i typowany jednokierunkowy importer wszystkich
   rutynowych credentiali; GUI widzi tylko metadane.
3. Wykonać shadow compare obecność/wersja/użycie, rotację fixture oraz pełny
   canary-secret scan.
4. Przenieść kolejno adaptery OpenSubtitles/Rapideo, Umbrella/Real-Debrid, YouTube
   OAuth i VPN, zawsze BlueStacks -> X88 -> pozostała dostępna flota, z rollbackiem
   i drugim przebiegiem `NO_CHANGE`.
5. Po dwóch zweryfikowanych backupach i cold restore oznaczyć import jako
   `SHADOW_VERIFIED`; nie usuwać jeszcze lokalnego plaintextu ani nie unieważniać
   działających credentiali.

### Przyrost 5 — pełne sterowanie i cutover

1. Podłączyć constrained assignment key, release intent, kontroler fal i ocenę
   podpisanych raportów.
2. Włączyć akcje średniego/wysokiego ryzyka z re-auth i polityką approval.
3. Wdrożyć ograniczony `mwodevelop-qnap-deployd`, potwierdzić live runtime digest,
   self-upgrade i rollback bez przekazania Docker socketu kontenerom.
4. Przełączyć hostowe `kodi_ops` na wrapper API QNAP; ADB/SSH pozostawić wyłącznie
   dla bootstrap/reinstall/break-glass.
5. Przeprowadzić czysty bootstrap BlueStacks, canary BlueStacks/X88, pełny rollout
   dostępnej floty, restart QNAP/Kodi, outage GitHub/Profile Sync i finalny cold
   restore według dokumentacji.
6. Wykonać pełny przebieg bez localhost, zapisać `CUTOVER_COMMITTED`, następnie
   unieważnić stare credentiale i usunąć lokalny rutynowy plaintext, pozostawiając
   tylko zaszyfrowany break-glass recovery.
7. Po zielonych E2E, CI, security review i ARMv7 wydać tylko te obrazy/dodatki,
   których bajty faktycznie się zmieniły.

Pierwszą następną implementacją jest 3A2. Dodaje uwierzytelnienie przeglądarkowe i
recovery administratora bez rozszerzania powierzchni mutacji lub przedwczesnego
przenoszenia sekretów. Każdy kolejny przyrost ma osobny rollback do poprzedniego,
nadal działającego read-only obrazu.
