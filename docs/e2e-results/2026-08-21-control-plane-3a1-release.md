# QNAP Control Plane 3A1 — dashboard, release i live deploy

Data: 2026-08-21

## Wynik

Przyrost 3A1 został wydany i wdrożony. `kodi-control-plane` 0.3.0 udostępnia
read-only dashboard i wersjonowane API mTLS z katalogiem 13 harmonogramów,
czterema źródłami statusu, freshness, provenance oraz alertami. Obraz działa na
QNAP z immutable digestem z `manifests/locks/qnap-stable.json`.

## Dowody

- lokalny pełny zestaw regresyjny po poprawkach: `590 passed`;
- PR #218: dwa zielone E2E; trwały fixture resolvera Big Buck Bunny;
- certyfikacja urządzeń `32484098144`: BlueStacks1 i X88, wyszukiwanie Umbrella,
  rzeczywiste odtwarzanie resolvera i WatchNixtoons2;
- snapshot `9792618200510e973ed173343e5f4f3c3a46d4fd02b279d385b275d81efe14e8`
  oraz device-attestation `a1eb882d987e6f239c52d2fbe3f574df4bbbb13bfe99108d228e204a92feb6cc`;
- `kodi-control-plane` 0.3.0: test, skan, multiarch AMD64/ARMv7 i release;
- QNAP candidate `96b16d252d4ff44fde838551d79e2e3bf2557cb585b2694d26ea9ccb6fdda896`;
- live deploy: control-plane, Profile Sync i provider relay `NO_CHANGE`, watchdog
  zaktualizowany; ponowny dry-run wskazał dokładnie cztery digesty stable;
- cross-repo E2E: brak certyfikatu mTLS odrzucony, mutacja odrzucona, lifecycle
  bundle `PREPARING_READY_PUBLISHED`, 13 zadań i cztery źródła statusu;
- Chrome CDP 9222: dokument `complete`, bez błędu JavaScript, dashboard wyrenderował
  cztery urządzenia, usługi i harmonogramy.

## Poprawki znalezione podczas E2E

1. Certyfikacja resolvera używa stabilnego, otwartego materiału Big Buck Bunny
   zamiast niestabilnych źródeł Sintela.
2. Orchestrator przekazuje wymagane `attestation_kind=device` do promocji stable.
3. Czysta promocja obu locków stable nie uruchamia ponownego testing-build.
4. Watchdog przy błędzie lub limicie GitHub API publikuje kompletny raport
   `api_error` i pozostaje uruchomiony w stanie niezdrowym.
5. Umbrella auto-approval traktuje device-qualified i QNAP-only promocje jako
   kontrolowany no-op; ścisła autoaprobata pozostaje tylko dla `hermetic_ci`.

## Stan ostrzeżeń

Po odnowieniu publicznego limitu GitHub watchdog odczytał wszystkie 11 wpisów.
Raport zawiera historyczną porażkę approvera Umbrella wywołaną legalną promocją
device/QNAP; wdrożony prefilter zamieni następny taki przebieg w no-op. Drugie,
rzeczywiste ostrzeżenie dotyczy WatchNixtoons2: upstream 0.29 nie przechodzi bramy
bezpieczeństwa z powodu globalnego wyłączenia weryfikacji TLS. Stable pozostaje na
zakwalifikowanej wersji 0.27.1; wyjątek bezpieczeństwa nie został dodany.
