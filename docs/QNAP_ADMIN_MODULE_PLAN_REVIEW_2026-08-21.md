# Niezależna recenzja rozszerzenia QNAP Control Plane o panel administracyjny

Data: 2026-08-21

Recenzowany dokument:
[`QNAP_CONTROL_PLANE_DEVICE_CONVERGENCE_PLAN.md`](../QNAP_CONTROL_PLANE_DEVICE_CONVERGENCE_PLAN.md)

## Zakres i metoda

Oddzielny reviewer przeprowadził read-only challenge planu i porównał go z:

- aktualnym `mwoDevelop/kodi-control-plane`, w tym HTTP mTLS, SQLite WAL, audit,
  backup i `convergence_bundle_v1`;
- `mwoDevelop/kodi-profile-sync-server`, jego consumer, integration i loopback
  admin API;
- Compose QNAP dla Control Plane, Profile Sync i upstream watchdoga;
- `tools/qnap_images.py`, bieżącymi workflow cron i dokumentacją procesów
  cyklicznych;
- granicami Device Agenta, GitHub App, secret envelope, recovery i ARMv7.

Reviewer nie edytował plików. Niniejszy dokument zapisuje jego werdykt, ocenę
zasadności i decyzje zastosowane do planu.

## Werdykt

Kierunek jest poprawny: istniejący Control Plane należy rozszerzyć, zachowując
model pull urządzeń, brak Docker socketu w GUI, immutable bundle/CAS, constrained
assignment key i `testing canary -> stable global -> fleet verification`.

Read-only dashboard może wejść do implementacji. Produkcyjny import sekretów i
mutujące GUI byłyby jednak przed poprawkami niebezpieczne. Review wykrył cztery
blokujące uwagi P0, dziesięć P1 i trzy P2. Wszystkie P0 przyjęto. Uwagi P1/P2
również zastosowano, z dopasowaniem bootstrapa do wymagań stabilnego WebAuthn
originu i utrzymaniem pierwszego release bez self-deploy.

## Podsumowanie uwag i decyzji

| ID | Priorytet | Problem | Decyzja |
|---|---|---|---|
| A-P0-1 | P0 | współdzielony SQLite pozwalałby skompromitowanemu web fałszować approval | przyjęto: osobny authz i podpisane granty weryfikowane przez worker |
| A-P0-2 | P0 | etap shadow usuwał plaintext przed gotowymi konsumentami | przyjęto: `SHADOW_VERIFIED`, późny `CUTOVER_COMMITTED` po D/F |
| A-P0-3 | P0 | local idempotency błędnie obiecywało exactly-once remote | przyjęto: klasy adapterów, outbox/fencing, correlation i reconciliation |
| A-P0-4 | P0 | backupy baz/KEK nie były związane jednym epoch | przyjęto: `recovery_bundle_v1` i odrzucenie mixed epoch |
| A-P1-1 | P1 | approval występował przed i po utworzeniu operacji | przyjęto: oddzielny lifecycle planu i operacji |
| A-P1-2 | P1 | osobny kontener nie osiągnie loopback writer API Profile Sync | przyjęto: osobny prywatny writer mTLS z action scopes |
| A-P1-3 | P1 | watchdog nie osiągnie loopback `/ready` Control Plane | przyjęto: prywatny observer mTLS, loopback health bez zmian |
| A-P1-4 | P1 | WAL nie wystarcza bez kwalifikacji storage/locking | przyjęto: local POSIX FS, power-cut/full-disk/concurrency i fallback single owner |
| A-P1-5 | P1 | pierwszy operator mógł wygrać wyścig rejestracji | przyjęto: lokalnie mintowany token, krótki TTL, dwie passkeys i trwałe wyłączenie |
| A-P1-6 | P1 | nie wybrano przepływu GitHub App credentialu | przyjęto: broker JWT, krótki installation token tylko w pamięci workera |
| A-P1-7 | P1 | deployment receipt nie dowodzi runtime digestu | przyjęto: osobne statusy receipt/self-report/runtime-unverified |
| A-P1-8 | P1 | self-upgrade nadal wymagał workstation | przyjęto etapowo: MVP przez CLI, przed cutover ograniczony QTS deployd |
| A-P1-9 | P1 | lokalny HMAC nie chroni audytu przed root QTS | przyjęto: zewnętrzny append-only/WORM anchor najwyższego head |
| A-P1-10 | P1 | brakowało pochodzenia i trust level pól dashboardu | przyjęto: wersjonowana macierz status field -> owner/adapter/auth/trust/fallback |
| A-P2-1 | P2 | jeden próg 36 h i duplikacja cron/manifest/watchdog | przyjęto: progi per job i CI porównujące manifest z workflow YAML |
| A-P2-2 | P2 | 3A łączyło status API z WebAuthn i miało zbyt mały szacunek | przyjęto: 3A1 dashboard mTLS i 3A2 browser auth |
| A-P2-3 | P2 | brak limitów eventów/audytu/SSE | przyjęto: retencja, limity i rozdzielenie access log od audytu |

## Uwagi P0 i zastosowane poprawki

### A-P0-1 — approval nie może opierać się na zapisywalnej bazie web

Proces wystawiony do LAN nie może być współwłaścicielem danych uznawanych przez
worker za dowód autoryzacji. Sam brak KEK albo private key w web nie blokuje RCE
przed dopisaniem rekordu `APPROVED` do współdzielonej DB.

Plan dodaje `control-plane-authz`, osobną bazę operatorów i klucz grantu. Grant
wiąże plan digest, aktora, rolę, nonce, termin, policy version i preconditions.
Worker niezależnie go weryfikuje oraz odrzuca bezpośrednio dopisany rekord. Test
bezpieczeństwa modyfikuje DB jako skompromitowany web i oczekuje braku wykonania.

### A-P0-2 — shadow import nie jest cutoverem

Sam import i możliwość odszyfrowania fixture nie dowodzą, że Device Agent,
assignmenty, rollouty i wszystkie adaptery potrafią działać bez hosta. Usunięcie
plaintextu w etapie C przerwałoby bieżącą ścieżkę recovery.

Etap C kończy się wyłącznie `SHADOW_VERIFIED`. Obowiązuje dual-read bez dual-write.
`CUTOVER_COMMITTED` jest możliwy dopiero po działaniu adapterów, dostępnej floty,
`NO_CHANGE`, rollbacku, pełnym przebiegu bez localhost i restore całego recovery
bundle. Dopiero wtedy stare tokeny są unieważniane i lokalny plaintext usuwany.

### A-P0-3 — zewnętrzny skutek nie jest exactly-once

Crash po przyjęciu `workflow_dispatch`, ale przed lokalnym commitem, pozostawia
niejednoznaczny wynik. Ponowienie może uruchomić drugi workflow. Idempotency key w
SQLite nie rozwiązuje tego dla remote API.

Plan klasyfikuje adaptery jako `pure`, `idempotent`, `reconcilable` lub
`at_most_once`, używa transactional outbox i fencing tokenu. `operation_id` jest
correlation/concurrency key workflow. Po timeoutcie następuje remote inspection,
a brak korelacji kończy się `UNKNOWN_REQUIRES_RECONCILIATION`, nigdy ślepym retry.

### A-P0-4 — recovery wymaga jednego epoch

Osobno poprawne backupy mogą wskazywać różne wersje enrollmentu, bundle i kopert.
Metadata KEK nie wystarcza do odtworzenia ciphertextu.

Plan dodaje `recovery_bundle_v1` z `backup_epoch_id`: Control Plane, authz,
Profile Sync, secret DB, wrapped KEK, Compose, polityki, certyfikaty/rotację,
DNS/reverse proxy i audit anchor. Mixed epoch jest odrzucany, a dwie kopie muszą
trafić do jawnie nazwanych niezależnych lokalizacji poza QNAP.

## Najważniejsze poprawki P1

### Maszyna stanów i TOCTOU

Plan przechodzi teraz:

```text
DRAFT -> PREFLIGHTED -> AWAITING_APPROVAL -> APPROVED/EXPIRED
APPROVED -> QUEUED -> PREFLIGHT_RECHECK -> DISPATCHING -> RUNNING -> VERIFYING
```

Plan ma TTL i expected generations. Drift daje `PLAN_STALE`. Anulowanie jest
żądaniem `CANCEL_REQUESTED` i działa dopiero w safe point adaptera.

### Profile Sync writer

Wybrano osobny writer listener mTLS na prywatnej sieci Compose. Ma scope per
pairing/revoke/publish/assignment/report evaluation i nie jest publikowany do LAN.
Obecny loopback admin pozostaje break-glass, a read-only integration API nie jest
niepostrzeżenie rozszerzane o write.

### Watchdog i samomonitorowanie

Loopback `/ready` nadal służy healthcheckowi kontenera. Watchdog dostaje osobny
certyfikat read-only i prywatny observer endpoint na `mwodevelop-control`. Nadal
nie udajemy, że proces na tym samym NAS wykryje całkowitą utratę QNAP; do tego
potrzebny jest zewnętrzny dead-man.

### SQLite i retencja

Bazy mogą działać wyłącznie na lokalnym POSIX filesystem QNAP, nie SMB/NFS. Bramka
obejmuje concurrent writers, WAL checkpoint, fsync, full disk, power-cut, fencing
i pojedynczego migration leadera. Jeżeli test nie przejdzie, jeden proces jest
właścicielem DB i wystawia prywatne API. Polling GUI nie zapisuje każdego GET do
hash chain; access log i audit bezpieczeństwa są rozdzielone i mają retencję.

### Bootstrap operatora

Bootstrap token jest tworzony tylko przez lokalny CLI/mTLS, ma maksymalnie 10 minut
TTL i jest przypięty do stabilnego originu. Flow kończy się dopiero po dwóch
passkeys, jednorazowym wydaniu recovery codes i trwałym `DISABLED`. Reverse proxy
ma allowlistę Host/Origin/RP ID/forwarded headers, a QTS -> web jest jawnie wybranym
HTTP po loopback.

### GitHub App

Private key posiada secret broker. Worker dostaje tylko krótki installation token
w pamięci. Plan wymaga macierzy installation/repo/permissions/TTL/rate limit i
oddziela obserwację od dispatch, jeśli nie da się dowieść minimalnych wspólnych
uprawnień.

### Receipt, runtime i self-upgrade

Receipt oznacza ostatnie zatwierdzone wdrożenie, a self-report wersję procesu. Bez
`docker inspect` nie wolno pokazać `RUNTIME_VERIFIED`. Pierwszy release nadal używa
`tools/qnap_images.py`; przed pełnym cutover plan dodaje hostowy, ograniczony
`mwodevelop-qnap-deployd`. Nie przyjmuje on komend ani dowolnych parametrów, a
kontenery web/worker nigdy nie dostają Docker socketu.

### Audit anchor i pochodzenie statusu

Lokalny HMAC jest ochroną przed uszkodzeniem, nie root QTS. Najwyższy head trafia
do zewnętrznego append-only/WORM anchora. Każde pole dashboardu ma owner, adapter,
auth, freshness, trust level i fallback. Desired, self-report, receipt i runtime
nie są zamienne.

## Elementy pozostawione bez zmiany

Review potwierdził jako spójne:

- constrained online assignment key związany z offline release intent;
- `testing canary -> stable global -> fleet verification`;
- immutable `convergence_bundle_v1`, CAS i exact-artifact evidence;
- rozróżnienie `VERIFIED` od `ORIGIN_VERSION_ONLY`;
- N-1 bootstrap Device Agenta i restart procesu Kodi;
- koperty sekretów per enrollment oraz jawny brak ochrony przed root QTS;
- brak shell/SQL/URL/dowolnego workflow/Docker socketu w GUI;
- rozdzielenie scheduler health, run result i freshness;
- `UNKNOWN/STALE` zamiast fałszywego `OK`;
- shadow import i canary-secret scan jako bramy przed cutover.

## Bramka po review

Można rozpocząć przyrost 3A1: manifesty, status API, provenance/freshness i
read-only UI mTLS. Nie wolno jeszcze importować produkcyjnych sekretów ani włączać
mutacji GUI. Przed 3A2 wymagany jest spike QTS loopback reverse proxy/WebAuthn, a
przed 3B test authz grant i kwalifikacja SQLite na rzeczywistym QNAP ARMv7.
