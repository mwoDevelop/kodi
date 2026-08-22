# QNAP Control Plane 3A2a — dostęp przeglądarkowy bez certyfikatu klienta

Data: 2026-08-22

## Wynik

Przyrost 3A2a został wydany i wdrożony. `kodi-control-plane` 0.6.0 zachowuje
dotychczasowe read-only API mTLS na porcie `19443` i dodaje osobny panel HTTPS
na porcie `19444`. Przeglądarka nie wymaga certyfikatu klienta; operator
uwierzytelnia się hasłem i TOTP. Połączenia web do authz i core nadal używają
oddzielnych tożsamości mTLS, a warstwa przeglądarkowa pozostaje read-only.

## Dowody

- `kodi-control-plane`: 35 testów jednostkowych oraz zielone CI obejmujące skan
  dokładnego źródła i build wieloarchitekturowy AMD64/ARMv7;
- repo `kodi`: pełna regresja przed scaleniem `627 passed`, dwa odtwarzalne E2E
  Control Plane oraz 42 testy integracji wdrożeniowej;
- przed promocją stable: walidacja locka, dry-run i 51 testów narzędzi QNAP;
- QNAP: trzy kontenery core/authz/web działają z tym samym immutable digestem i
  raportują `healthy` po restarcie;
- jednorazowy bootstrap utworzył operatora, zaszyfrowany seed TOTP i 10 kodów
  odzyskiwania; świeże logowanie po restarcie potwierdziło trwałość sesji i bazy;
- mutacja przez BFF została odrzucona kodem `405`, a dashboard zwrócił `OK`;
- Chrome przez CDP 9222 zalogował operatora i wyrenderował dashboard bez
  certyfikatu klienta;
- X88 Pro 20: Chrome otworzył panel po zaakceptowaniu lokalnego ostrzeżenia TLS,
  zalogował operatora hasłem+TOTP i wyrenderował dashboard `OK`; nie instalowano
  CA ani certyfikatu klienta;
- BlueStacks1 potwierdził dostęp TCP z Androida do portów `19443` i `19444`;
- kandydat QNAP
  `1d8d3103b1fb438e90401842d57f8c5662b232951545004d75abb8138c0dc1b8`
  przeniósł bez zmian cztery pozostałe obrazy stable; powtórny deploy dokładnego
  digestu Control Plane zakończył się `NO_CHANGE`.

## Własności bezpieczeństwa

- dokładny Host i Origin, ograniczenie do podsieci LAN, token CSRF oraz ciasteczka
  `Secure`/`HttpOnly` chronią powierzchnię przeglądarkową;
- authz nie publikuje portu LAN i ma oddzielną bazę oraz klucz AEAD;
- BFF ma wyłącznie tożsamość read-only do czterech endpointów core;
- stare API na `19443` nadal wymaga certyfikatu klienta;
- lokalne ostrzeżenie urzędu certyfikacji jest świadomym ograniczeniem 3A2a;
  zaufany DNS/TLS i WebAuthn pozostają zakresem 3A2b.
