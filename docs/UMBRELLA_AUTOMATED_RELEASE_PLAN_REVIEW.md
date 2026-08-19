# Niezależny review planu automatycznego release Umbrelli

Data: 2026-08-19

## Wynik

Plan został przyjęty po korektach bezpieczeństwa i spójności. Review wykrył
problemy P0 dotyczące lokalizacji klucza GitHub App, semantyki rollbacku oraz
atestacji. Zgodnie z późniejszą, jawną decyzją właściciela projektu fizyczne
BlueStacks i X88 nie są obowiązkową bramą pre-release; pozostają smoke testem po
wydaniu. W tym punkcie decyzja właściciela zastępuje pierwotną rekomendację
reviewera.

## Zastosowane uwagi

- GitHub App działa tylko w chronionym GitHub Environment, nie na QNAP, i nie
  ma bypassu rulesetów.
- Kandydat testing jest komponentowo izolowany do Umbrelli.
- Stable używa niezmiennego snapshotu, atestacji oraz ponownie zweryfikowanego,
  niezmienionego locka QNAP.
- Rollback został zastąpiony wydaniem naprawczym o ściśle wyższej wersji;
  rzeczywista baza upstream jest osobnym polem.
- Status ma niezależne osie procesu i zdrowia wydania, ścisły schemat i termin
  ważności.
- GitHub Pages ma jednego serializowanego writera.
- Kod kandydata jest testowany bez sieci, sekretów i zapisu do hosta.
- Parser i polityka powiadomień są odizolowane od upstreamowego kodu Umbrelli.

## Kontrole aktywacyjne

Auto-merge pozostaje domyślnie wyłączony. Włączenie wymaga udanego przebiegu
obserwacyjnego, testów negatywnych allowlisty, zielonego CI i potwierdzonego
no-op. Approval App jest kontrolą polityki, a nie ludzkim review.
