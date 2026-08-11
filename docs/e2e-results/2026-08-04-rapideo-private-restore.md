# Certyfikat przywracania prywatnego Rapideo — 2026-08-04

## Zakres

workflow do czystego przywracania uzyskał rejestr dozwolonych prywatnych adapterów
dodatków. Pierwszy adapter odczytuje `RAPIDEO_USER` i `RAPIDEO_PASS` z ignorowanego
pliku referencyjnego trybu `0600`, konfiguruje oficjalny dodatek Rapideo, wymusza nowe
logowanie, weryfikuje punkt końcowy konta i usuwa wszystkie tymczasowe materiały
uwierzytelniające Android. Raporty zawierają wyłącznie dowody dotyczące transportu i
stanu logicznego.

## Automatyczna certyfikacja

- pełny pakiet Python: `317 passed`;
- Odpowiednik CI `tests/e2e/run.sh`: `317 passed` po dwóch deterministycznych
  kompilacjach repozytoriów;
- `git diff --check`: pass;
- prywatna jednostka adaptera i przywracanie testów integracyjnych: pass.

## Dowód urządzenia

| Urządzenie | Wynik przywracania/konfiguracji | Wynik Rapideo |
|---|---|---|
| BlueStacks1 (`SM-S901E`) | Przepustka `restore-only`; 4287 plików; Kodi 21,3; Aeon Nox Silvo; wymagane dodatki zweryfikowane | Rapideo 1.5.0; Logowanie i konto HTTP 200 JSON; obecny świeży token |
| Sony TV | istniejący profil zachowany; samodzielna idempotentna przepustka adaptera | Rapideo 1.5.0; Logowanie i konto HTTP 200 JSON; obecny świeży token |
| X88 Pro 20 | zaliczone fazy profilu/domyślnego dodatku; zablokowana ostatnia faza prywatna | aktywne wyjście OpenVPN zwróciło HTTP 200 `text/html` z punktu końcowego logowania Rapideo |
| Bedroom TV | Transport Kodi przywrócony po ponownym uruchomieniu; ustawienia zastosowane | aktywna ścieżka NordVPN zwróciła HTTP 200 JSON z błędem API 4 i brakiem tokena |

W tym raporcie nie wydrukowano ani nie zapisano żadnych danych uwierzytelniających,
tokenów, tożsamości konta, treści odpowiedzi API ani rozpoznanego adresu URL
multimediów. Dwie awarie specyficzne dla VPN nadal stanowią wyraźne blokady wdrożeniowe,
a nie są osłabiane do ostrzeżeń.
