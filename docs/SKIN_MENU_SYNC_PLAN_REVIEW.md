# Niezależny audyt planu synchronizacji menu skórki

Werdykt: kierunek jest poprawny, ale pierwotny plan utożsamiał atomowy zapis
źródłowego XML z potwierdzoną zmianą menu widocznego przez skórkę.

Zastosowane uwagi:

- jawne uruchomienie buildera Skin Shortcuts, oczekiwanie i sprawdzenie
  wygenerowanego include zamiast samego `ReloadSkin()`;
- fazowy journal i rollback obejmujący ponowny build poprzedniego menu;
- target tag oraz preconditions skórki, dodatku, profilu i `shared_menu`;
- kompatybilność recovery starego journala oraz wspólny lock handlerów;
- dwufazowy release: najpierw klient/capability, potem podpisana rewizja menu;
- odroczenie build podczas odtwarzania i okresowy semantic drift check;
- zamknięty kontrakt czterech pozycji, semantyczna kontrola źródła, include i GUI;
- użycie istniejącego stanu rolloutowego `DEFERRED`.

Powtórny audyt gotowej implementacji wykrył i zamknął przed release dwie luki:

- wszystkie wejścia `service`, `--sync-once` i rollout są serializowane jednym
  blokującym lockiem plikowym zwalnianym przez system także po awarii procesu;
- gdy przed zmianą nie istniał źródłowy XML, journal zachowuje semantykę
  poprzedniego wygenerowanego menu, a rollback czeka na jej ponowną odbudowę.
  Brak jakiegokolwiek weryfikowalnego stanu rollback zatrzymuje mutację.

Nie przyjęto rozszerzania V1 o inne skórki, kopiowania hash/properties/include,
forka Skin Shortcuts, lokalnego multi-writer ani przeładowania skórki przy no-op.
