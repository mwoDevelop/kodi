# ADR-0005: koperty sekretów per enrollment

Status: zaakceptowany; wdrożenie etapowe

## Decyzja

Sekrety użytkownika są przechowywane przez osobny Secret Broker na QNAP i
dostarczane jako koperty RFC 9180 HPKE w trybie base. Pakiet używa dokładnie:

- DHKEM X25519/HKDF-SHA256;
- HKDF-SHA256;
- ChaCha20-Poly1305;
- informacji kontekstowej `mwo-kodi/secret-envelope-v1`.

Każdy enrollment ma odrębną parę X25519. Klucz Ed25519 raportów nie jest używany
do szyfrowania. Android korzysta z BoringSSL, a Linux/Flatpak z publicznego API
EVP OpenSSL. Brak bezpiecznego backendu wyłącza capability
`secret-envelope-v1`; nie istnieje fallback do wspólnego klucza AEAD.

AAD wiąże typ i generację secret setu, lifecycle, logical device ID, enrollment
i jego generation, klucz odbiorcy, adapter, ID i wersję dodatku, nonce oraz czas
ważności. Profile Sync uwierzytelnia urządzenie istniejącym bearerem enrollmentu,
ale widzi wyłącznie opaque envelope. Z Brokerem komunikuje się przez prywatne
mTLS. Control Plane ma osobny certyfikat wyłącznie do sondy `/ready`.

## Etapy i lifecycle

Dozwolone przejścia są liniowe i wykonywane przez compare-and-swap:

`PREPARED -> CANARY_VERIFIED -> ACTIVE -> RETIRING -> RETIRED`.

Agent ma jawny tryb dostawy:

- `shadow` — może odszyfrować najnowszy przygotowany zestaw, ale go nie stosuje;
- `canary` — stosuje wyłącznie `CANARY_VERIFIED` albo `ACTIVE`;
- `active` — stosuje wyłącznie `ACTIVE`.

Migracja starszego enrollmentu rejestruje klucz X25519 jednorazowym,
uwierzytelnionym i idempotentnym endpointem. Klucz prywatny jest zapisywany
atomowo przed żądaniem, dzięki czemu przerwanie nie wymaga ponownego parowania.

## Konsekwencje

Przejęty root urządzenia nadal może odczytać działającą sesję oficjalnego dodatku.
Ponieważ flota używa jednego wspólnego zestawu tokenów YouTube, kompromitacja
jednego urządzenia wymaga unieważnienia zgody Google i rotacji całej generacji.
QNAP root również pozostaje w granicy zaufania. Lokalne plaintext credentials
hosta można usunąć dopiero po pełnym canary, rollout, powrocie urządzenia offline
i sprawdzonym cold restore.
