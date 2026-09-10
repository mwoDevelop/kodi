# Niezależny review planu naprawczego — 10.09.2026

Plan: [OPS_SYNC_RECOVERY_PLAN_2026-09-10.md](OPS_SYNC_RECOVERY_PLAN_2026-09-10.md).
Wykonawca: agy-yolo `gemini-3.8-flash-high`, sesja
`eb1a3b72-7796-478c-a1b6-6ce87d286211`, wynik SUCCESS, tylko odczyt kodu/planu.
Przed delegacją natywne `/model` i `/usage`: SUCCESS, minimum właściwej puli
0.7753555774688721 (> 0.10). Bez sekretów, sieci i mutacji repo przez reviewera.

## Zastosowane doprecyzowania

1. Jawny IDLE/ACTIVE/UNKNOWN i wspólna brama dla niszczących etapów restore
   Androida, nie wyłącznie zwykłego rolloutu.
2. Usunięcie bezwarunkowego eksportu tokenu publishera z pętli per-device;
   również retry całego adaptera ma respektować WAF (nie tylko retry loginu).
3. Konkretny manifest polityki stanów enrollmentu, idempotencja, scope i
   generacja przypięte do klienta. X88 naprawiane bez tworzenia generacji 21.
4. Log/stan zabezpieczone przed restartem, analiza błędów terminalnych,
   graceful shutdown i limit jednego restartu diagnostycznego na cel.
5. PARTIAL zamiast COMPLETE przy niedostępności/WAF; drugi odczyt i NO_CHANGE.
6. Jednoznaczne rozróżnienie `running == False` od nieznanego stanu.

## Korekty interpretacji review

- Reviewer nazwał cztery istniejące błędy implementacji „lukami planu”, choć
  A.1–A.3 już nakazywały ich naprawę. Zachowujemy te wymagania i wzmacniamy
  kryteria testów; nie traktujemy obecnego wadliwego kodu jako zamierzonego celu.
- Nie przyjmujemy bezwzględnego zakazu deployu obrazów, jeśli diagnostyka
  wykaże błąd serwera. Plan nadal wymaga deployu wyłącznie zmienionych usług.
- Brak nowego parowania dotyczy naprawy istniejącego X88, nie zakazu
  obsługi przyszłych nowych urządzeń. Ta ścieżka ma mieć regresję polityki.
- Nie obiecujemy 100% NO_CHANGE całego workflow: odnowienie raportów,
  heartbeat i wygasających assignmentów jest prawidłową pracą okresową.
- Nie wyłączamy ochrony TLS, kwarantanny, CI, ACL Edge ani ograniczeń budżetu.

Werdykt właściciela implementacji: zasadne uwagi zastosowane; można rozpocząć A.

Późniejsza obserwacja produkcyjna skorygowała założenie punktu 3: na X88 nie
było już kluczy ani payloadu dodatku (lokalnie UNPAIRED od poprzedniego dnia).
Wyjątek odbudowy/parowania opisuje uzupełnienie planu. Review nie obejmował
tej niedostępnej wówczas informacji; nie przypisujemy reviewerowi jej akceptacji.
