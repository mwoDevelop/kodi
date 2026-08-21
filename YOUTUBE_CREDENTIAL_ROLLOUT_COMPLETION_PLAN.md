# Plan domknięcia YouTube OAuth i migracji sekretów na QNAP

Status: zatwierdzony do realizacji po niezależnym audycie

Data: 2026-08-21

## 1. Uporządkowanie obecnej implementacji

- Zweryfikować aktualną sesję hostową bez ujawniania sekretów i zebrać brakujące,
  zredagowane dowody E2E.
- Ujednolicić dokumentację: stosowany jest jeden wspólny zestaw trzech refresh
  tokenów dla całej floty.
- Rozdzielić raportowanie na wynik uzgadniania, stan kodu i API, stan konta oraz
  stan recovery.
- Potwierdzić na BlueStacks, a następnie X88: origin, wersję, konto/kanał,
  wyszukiwanie, subskrypcje, odtwarzanie, restart i drugi przebieg `NO_CHANGE`.

## 2. Kontrakt bezpieczeństwa

- Sprawdzić najmniejszy scope OAuth zgodny z wyszukiwaniem, subskrypcjami i
  odtwarzaniem. Pełny `auth/youtube` dopuścić tylko po udokumentowanym teście.
- Zaktualizować ADR-0005 i przyjąć RFC 9180 HPKE: DHKEM X25519/HKDF-SHA256,
  HKDF-SHA256 i ChaCha20-Poly1305 w trybie base. Autentyczność nadawcy zapewnia
  podpisany assignment.
- AAD wiąże logical device ID, enrollment ID i generation, secret-set ID i
  generation, adapter/addon schema, nonce oraz expiry.
- Brak interoperacyjności na ARMv7, ARM64 lub Flatpak zatrzymuje migrację; nie ma
  słabszego fallbacku.
- Enrollment dostaje odrębną parę X25519. Klucz Ed25519 raportów nie jest używany
  ponownie.

## 3. QNAP Secret Broker i transport

- Dodać osobny Secret Broker w prywatnej sieci Compose, bez portu LAN i Docker
  socketu.
- Profile Sync wydaje urządzeniu opaque envelope przez consumer API i istniejący
  bearer enrollmentu; urządzenie weryfikuje podpisany assignment.
- mTLS obowiązuje między Brokerem, Profile Sync i Control Plane. Urządzeniowe mTLS
  nie wchodzi do tego przyrostu.
- Device Agent dostaje capability `secret-envelope-v1`, odszyfrowuje dane tylko w
  pamięci i nie używa shared storage ani argumentów CLI.
- Mutacje `import`, `rotate`, `rewrap` i `revoke` są początkowo dostępne wyłącznie
  przez audytowany lokalny CLI QNAP. Mutujące GUI czeka na osobny authz i podpisane
  granty.
- Secret Broker wchodzi do `tools/qnap_images.py`, Compose, workflow build,
  healthchecku, backupu i `qnap-stable.json`.

## 4. Dane i lifecycle

- `youtube-session-v1` zawiera wspólny pakiet API i trzy refresh tokeny oraz
  `secret_set_id`, monotoniczną generation, kwalifikowaną wersję dodatku i schematu,
  lifecycle oraz czasy utworzenia i weryfikacji.
- Lifecycle: `PREPARED -> CANARY_VERIFIED -> ACTIVE -> RETIRING -> RETIRED`.
- Agent nigdy nie stosuje generation starszej niż lokalnie potwierdzona.
- Rotacja tworzy nowy immutable secret set i przechodzi pełne canary. Nie ma
  dual-write z urządzeń.
- Revocation enrollmentu blokuje kolejne koperty, ale kompromitacja urządzenia
  wymaga Google revoke i rotacji całej floty.
- Migracja porównuje dane krótkotrwałym keyed HMAC z migration nonce, a nie trwałym
  SHA-256 plaintextu.

## 5. Wdrożenie expand-first i cutover

1. Wydać Broker i Profile Sync obsługujące stare i nowe schematy.
2. Wydać Device Agenta z capability kopert, jeszcze bez wymuszania QNAP.
3. Potwierdzić capability heartbeat wymaganej floty.
4. Przetestować transport syntetycznym canary secretem.
5. Zaimportować produkcyjny pakiet jako `SHADOW_IMPORTED` i potwierdzić
   `SHADOW_VERIFIED`.
6. Wykonać fetch bez apply, następnie `CANARY_QNAP` na BlueStacks i X88.
7. Przejść w `FLEET_DUAL_READ`, preferując QNAP i zachowując host jako rollback.
8. Wykonać rollout i `NO_CHANGE` na całej dostępnej flocie.
9. Zasymulować powrót urządzenia offline ze starszym agentem; urządzenie ma samo
   zaktualizować agenta i pobrać kopertę bez localhost.
10. Wykonać cold restore `recovery_bundle_v1`.
11. Dopiero wtedy ustawić `CUTOVER_COMMITTED`.
12. Po obserwacji usunąć lokalne credentiale wykonawcze i `session.json`;
    `YOUTUBE_USER` zostaje prywatnym inventory.

## 6. Backup i recovery

- `recovery_bundle_v1` używa jednego `backup_epoch_id` i obejmuje bazy oraz bloby
  Control Plane/Profile Sync, Secret Broker DB, wrapped KEK, authz/enrollmenty,
  Compose, certyfikaty lub ich procedurę rotacji, manifest digestów i zewnętrzny
  audit anchor.
- Mieszane epoki są odrzucane.
- Utrzymywane są dwie niezależne, odporne na nadpisanie kopie poza QNAP.
- Cutover wymaga cold restore jednej kopii na pustym hoście zastępczym i odzyskania
  działającej sesji na testowym urządzeniu.

## 7. Testy, dokumentacja i release

- Testy obejmują schematy, lifecycle, redakcję, replay, expiry, cross-enrollment,
  corrupt envelope, downgrade generation, rotację, rollback i brak wycieków.
- E2E wykonujemy najpierw na BlueStacks, potem X88: logowanie, wyszukiwanie,
  subskrypcje, odtwarzanie, restart, VPN i `NO_CHANGE`.
- Regresja obejmuje Umbrella, mwoScrapers, Rapideo, oba dodatki napisów, favourites,
  thumbnails i Profile Sync.
- Rollout pozostałej floty następuje dopiero po canary; urządzenia offline dostają
  `DEFERRED` i muszą mieć przetestowany bootstrap po powrocie.
- Kolejność repozytoriów: server/broker -> Profile Sync -> Device Agent -> capability
  heartbeat -> shadow -> enforce -> usunięcie N-1. Każdy etap ma rollback.
- Uzupełnić runbook YouTube, threat model, ADR-0005, backup/restore, operacje,
  procesy cykliczne i datowany raport E2E.
- Wydać tylko zmienione komponenty infrastruktury. Oficjalny YouTube pozostaje w
  `repository.xbmc.org`.

## Kryteria zakończenia

- Cała dostępna flota raportuje `ACCOUNT_READY` i `NO_CHANGE`.
- Urządzenie offline po powrocie przechodzi na QNAP bez localhost.
- Cold restore spójnego recovery bundle przechodzi.
- Secret Broker i pozostałe usługi QNAP są healthy.
- Pełne CI/E2E są zielone i nie zawierają sekretów.
- Lokalne plaintext credentials są usuwane dopiero po `CUTOVER_COMMITTED`.
