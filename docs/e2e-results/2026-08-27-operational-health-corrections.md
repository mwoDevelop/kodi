# Korekty semantyki kondycji operacyjnej — E2E 2026-08-27

## Zakres

Wdrożono rozdzielenie kondycji heartbeat, enrollmentu, łączności i konfiguracji
urządzeń, częściowe zbieranie GitHub Actions z ograniczonym retry, korelację
incydentów Watchdog/collector oraz wersjonowaną politykę severity. Operacje
usuwania starych enrollmentów otrzymały prywatny plan content-addressed i
atomowy apply z kontrolą CAS.

Wydano `kodi-control-plane` 0.8.1 oraz `kodi-profile-sync-server` 0.7.0. Stable
lock QNAP wskazuje immutable digesty tych wydań. Dodatki i stable lock Kodi nie
zmieniły się, dlatego nie wykonano rolloutu dodatków na urządzenia, w tym na
Bedroom TV.

## Testy automatyczne

- Control Plane: 72 testy zakończone sukcesem; CI obrazu wieloplatformowego i
  approval zakończone sukcesem.
- Profile Sync Server: 41 testów zakończonych sukcesem; CI obrazu
  wieloplatformowego i approval zakończone sukcesem.
- Repozytorium Kodi: 648 testów zakończonych sukcesem lokalnie; pełne E2E
  dokładnych headów PR 264, 265, 266 i 267 zakończone sukcesem w GitHub Actions.
- Powtórny deploy usług QNAP zwrócił `NO_CHANGE`.

Podczas testu wykryto i naprawiono dwie dodatkowe regresje:

1. browser facade nie wystawiał spakowanego `favicon.svg`; wersja 0.8.1 dodaje
   trasę oraz test regresyjny;
2. promocja locka zmieniała commit głównego repo i wymuszała ponowny build
   niezmienionych obrazów. Re-use approval dopuszcza teraz wyłącznie commit
   będący przodkiem bieżącego HEAD oraz identyczny hash deklarowanych inputów w
   zatwierdzonym i bieżącym commicie.

## Test live QNAP i przeglądarki

- `control-plane`, `control-plane-authz`, `control-plane-web`, `profile-sync`,
  `secret-broker` i `upstream-watchdog` działają z digestów stable locka;
- Watchdog raportuje kompletną kolekcję `READY`; wykryte błędy workflow nie są
  przedstawiane jako awaria obserwatora;
- panel przeszedł pięć przeładowań i pięć użyć przycisku „Odśwież stan”;
- HTML, CSS, JavaScript, API, status sesji i `favicon.svg` zwróciły HTTP 200;
- konsola przeglądarki nie zawierała błędów;
- BlueStacks i X88 mają `enrollment=OK`; plan CAS unieważnił odpowiednio dwie i
  trzy starsze generacje, bez ujawniania identyfikatorów enrollmentów.

Provider Relay podczas jednego odczytu przeszedł przejściowo do `unhealthy` z
powodu timeoutu lokalnego healthchecku po obciążeniu wdrożeniowym. Kolejna próba
healthchecku oraz bezpośrednie `/health` zakończyły się sukcesem bez restartu i
bez zmiany obrazu.

## Pozostałe ostrzeżenia

Panel pozostaje `DEGRADED`, ponieważ GitHub nie uruchomił części zaplanowanych
okien cron. Collector ma stan `READY`, ostatnie wykonania zakończyły się
sukcesem, a korelacja tworzy po jednym incydencie na workflow mimo dowodu z
collectora i Watchdoga. Jest to rzeczywisty stan zewnętrznego schedulera, nie
błąd panelu; ręczny catch-up nie może maskować pominiętego okna.
