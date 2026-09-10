# Domknięcie operacji po handoverze agy/Grok — 10.09.2026

Status: implementacja i dostępne testy wykonane; odbiór floty PARTIAL,
publikacja kodu w toku. Szczegóły odroczeń w raporcie wykonania.
Review: [raport](OPS_SYNC_RECOVERY_REVIEW_2026-09-10.md).
Wyniki: [raport wykonania](e2e-results/2026-09-10-ops-sync-recovery.md).
Poprzednie wyniki: [9.09](e2e-results/2026-09-09-remaining-ops.md),
[migracja NUC](e2e-results/2026-09-09-nuc-flatpak-user-migration.md).

## Stan odniesienia i granice

- Main `a388116`: PR #366–#369 scalone. Migracja obu NUC do `--user`
  zakończona; nie reinstalować ponownie i nie zmieniać ACL Edge.
- Pozostałości lokalnego checkoutu są bajtowo zgodne z main. Zachować je
  w nazwanym stashu; pracować na osobnej gałęzi od main. Sekrety pozostają
  w ignorowanych `.env`, `.kodi-private` i `~/.ssh`.
- Dzisiejsza regresja: 858 PASS. Dwie symulacje wykazały jednak fail-open
  w kontroli odtwarzania Androida i sondzie instalatora Flatpak.
- QNAP: active `63a8026e…`, candidate `3c3391bf…`, generation 7.
  Nie promować/kasować zastanego kandydata ani nadpisywać favourites bez
  rozstrzygnięcia właściciela. Scoped rollout dodatków może działać niezależnie.
- X88: aktywny enrollment generation 20 ma wyłączony playback state.
  Sony/X88: Kodi działa, heartbeat starszy niż dobę. Sam PID nie dowodzi
  działania pętli synchronizacji. NUC Kodi zatrzymane; Bedroom/BlueStacks
  aktualnie nieosiągalne. Ponownie sprawdzić przed każdym apply.
- Copilot pozostaje `observe`; nowa tożsamość App/approval, zakup VIP i zmiana
  budżetów są osobnymi decyzjami, nie częścią naprawy. Nie usuwać ograniczeń
  bezpieczeństwa ani podnosić progów monitoringu, żeby uzyskać zielony wynik.
- Nie dotykać projektu ZeroTier/Download Station. NordVPN na Androidzie nadal
  tuneluje Kodi; wykluczenie Netflix zachowane. Zmiana serwera Bedroom w celu
  potwierdzenia blokady WAF jest dozwolona, nie zakup nowej usługi VPN.

## Kolejność i kryteria odbioru

### A. Bezpieczeństwo mutacji (przed rolloutem)

1. Android: rozróżnić aktywne odtwarzanie, potwierdzony brak i nieznany stan.
   Gdy działające Kodi nie odpowie lub zwróci zły kontrakt, mutacja otrzymuje
   `DEFERRED/playback_unknown`. Gdy potwierdzono `running == False`, wolno je
   uruchomić w normalnym rolloucie. Dry-run pokazuje nieznany stan jawnie.
   Wspólna brama obowiązuje też przed niszczącymi fazami restore Androida.
   Testy: aktywny/idle, timeout, błędny typ JSON, Kodi zatrzymane; żadna
   funkcja zmieniająca urządzenie nie wywołana przy active/unknown.
2. Flatpak: `flatpak list` z kodem niezerowym to błąd inwentaryzacji, nie
   brak aplikacji. Fallback snapshotu wyłącznie po poprawnym pustym wyniku.
   Jawny scope wyklucza enumerację drugiego zakresu. Testy: permission denied,
   pusty wynik, snapshot/no snapshot, uszkodzone wiersze, dwa scope oraz
   niezgodna tożsamość. Bez live destrukcyjnego restore dla już sprawnych NUC.
3. Rapideo: usunąć bezwarunkowy ADB export tokenu wydawcy z każdego scoped
   rolloutu. Wykorzystać prywatny token i/lub logowanie przez `.env` w już
   istniejącym adapterze; eksport wydawcy tylko jawnie w workflow, które
   tego wymaga. Nie retry logowania ani całego adaptera przy
   `ACCESS_RESTRICTED`/WAF; raport odroczenia ma wskazywać tę przyczynę.
   Test: wyłączony publisher nie blokuje innego celu; prywatne tokeny nie
   trafiają do logów; dotychczasowe logowanie i retry zachowane.

### B. Profile Sync — odtworzenie polityki, nie tożsamości

1. Brakuje wspólnego manifestu polityki enrollmentu: dodać
   `manifests/profile-sync-state-policy.json` (kanał, feature enabled, scope),
   użyć istniejących serwerowych setterów, bez nowego serwisu.
   Zapewnić idempotentne uzgodnienie jej z właściwym enrollmentem
   po bootstrapie/ponownym parowaniu. Nie kopiować enrollmentów między celami.
   Walidować logical id, kanał, aktualną generację i scope przed mutacją.
2. Użyć tej ścieżki do naprawy X88 **bez parowania i bez rotacji generacji 20**.
   Nie zmieniać obcego scope ani kwarantanny; odczyt przed i po, tożsamość
   przypięta do klienta, błąd przy konkurencyjnej zmianie generacji.
   Test: ten sam enrollment, playback enabled,
   właściwy scope, drugi przebieg NO_CHANGE. Ponowne parowanie pokryć testem
   regresji bez niepotrzebnej rotacji tokenu produkcyjnego.
3. Zdiagnozować brak heartbeat Sony/X88 przez logi, lokalny publiczny stan,
   działanie usługi, czas urządzenia, VPN/LAN i backend. Najpierw dowód
   przyczyny; nie restartować w pętli i nie odtwarzać danych profilu w ciemno.
   Przed restartem zabezpieczyć prywatnie log i stan, sprawdzić również
   `terminal_configuration_fingerprint`. Restart Kodi tylko przy potwierdzonym
   braku odtwarzania; najpierw graceful quit (15 s), co najwyżej jeden restart
   diagnostyczny na cel. Brak poprawy → diagnoza, nie kolejny restart.
   Zachować stan użytkownika. Jeśli błąd klienta/serwera — poprawka + regresje.
4. Testy: świeża próba i zakończony cykl, heartbeat widoczny w API/panelu,
   playback i favourites zdrowe, brak nieoczekiwanych kolejek, powtórny no-op.
   Test konfliktu odtwarzania na kontrolowanym wpisie, z backupem i cleanupem
   tego wpisu, bez oznaczania rzeczywistej biblioteki użytkownika.

### Uzupełnienie po live diagnozie X88 (10.09, 14:35 UTC)

- In-Kodi probe: brak payloadu dodatku i `settings.xml`, lokalny stan
  `UNPAIRED`; baza dodatków nadal deklaruje 1.5.1. Log potwierdza UNPAIRED
  od 9.09 18:44 UTC. Źródło usunięcia plików pozostaje nieustalone.
- Samo włączenie flag generacji 20 nie odtworzy utraconych kluczy klienta.
  Najpierw zabezpieczyć log i backend, odbudować dokładnie stabilny dodatek.
  Jeżeli potwierdzi się brak lokalnej tożsamości po odbudowie i nie ma zgodnej
  kopii kluczy generacji 20, dopuścić nowe parowanie istniejącym adapterem.
  Jest to wyjątek od B2 wynikający z dowodu utraty stanu, nie sposób leczenia
  zwykłego błędu synchronizacji. Po sukcesie sprawdzić wycofanie starej
  generacji i powtórzyć przebieg bez następnej rotacji.
- NO_CHANGE stable musi sprawdzać też pliki ZIP wspólnym istniejącym
  `installed_archive_matches`, nie tylko wersję w DB Kodi. Testy: poprawna
  wersja + brak/zmienione pliki wymaga odbudowy, pełna zgodność daje no-op.
- Hostowy probe raportuje obecność plików oraz czasy cyklu/heartbeatu
  i blokadę terminalną bez ujawniania kluczy ani fingerprintu konfiguracji.
- Udana ręczna naprawa może zostawić zapamiętaną blokadę terminalną usługi.
  Wycofać ją dopiero po potwierdzonym APPLIED/NO_CHANGE tej samej przypisanej
  rewizji, bez kwarantanny, pending report i journalu. Zabezpieczyć prywatny
  stan, wznowić tylko usługę Profile Sync i sprawdzić rzeczywisty świeży cykl.
  Testy negatywne nie mogą kasować kwarantanny ani zmieniać kluczy. Drugi
  przebieg nie powinien ponownie przeładowywać usługi.

### C. Bedroom / Rapideo i rollout dostępnej floty

1. Odtworzyć dostęp z `.env`, potwierdzić tożsamość i player. Offline →
   `DEFERRED`, nie fałszywy PASS. BlueStacks przed X88 dla nowych pakietów,
   jeżeli oba dostępne; brak canary blokuje promocję nowego pakietu stable,
   nie testy hostowych zabezpieczeń ani naprawę konfiguracji X88.
2. Bedroom: zapisać stary serwer/politykę NordVPN (bez sekretów); porównać
   odpowiedź Rapideo z Kodi z Sony. Przy WAF zmienić serwer i wykonać ten sam
   test; nie wyłączać VPN dla Kodi i nie obchodzić blokady zmianą parsera.
   Brak poprawy → uczciwy wynik ograniczenia zewnętrznego, rollback ustawień.
3. Wdrożyć wyłącznie potrzebne zmiany przez istniejące skrypty. Scoped
   `kodi_ops.py rollout --device ID --dry-run`, potem apply po bramie A.
   Domknąć stabilne dodatki, konta, menu/favourites, playback i heartbeat.
   `.org VIP_REQUIRED` pozostaje opisanym ograniczeniem, `.com` ma działać.
4. NUC: inwentaryzacja i synchronizacja, bez reinstall. QNAP: deploy obrazów
   przez `qnap_images.py`/locki tylko jeśli kod usługi faktycznie się zmienił.

### D. Procesy cykliczne i kandydat konfiguracji

1. Porównać panel z rzeczywistym wynikiem/eventem/czasem GitHub oraz watchdog.
   Oddzielić awarię workflow, opóźnienie schedulera i stan kontenera.
   Respektować cooldown/budżet istniejącej remediacji; bez dispatch storm.
   Nie wymagać oczekiwania na cron jako bramy innych napraw. Błąd naszego
   kolektora naprawić i przetestować; nieregularność GitHub jawnie opisać.
2. Kandydat `3c3391bf…`: ponownie potwierdzić diff i właściciela stanu, zapisać
   rekomendację. Bez jednoznacznego wyboru nie zmieniać active/candidate.
   To jawna pozycja odroczona, nie przyczyna blokowania scoped rolloutu.
3. Copilot P3/P4: wskazać konkretną brakującą decyzję/uprawnienie w raporcie;
   nie włączać approvals przy okazji naprawy urządzeń. VIP analogicznie.

### E. Review, dokumentacja, publikacja i odbiór

- Przed A: osobny niezależny review planu; zapisać uwagi przyjęte/odrzucone.
- Testy regresji hostowych i klienta/serwera odpowiednio do zmian, pełny pytest,
  deterministyczny build repo (bez nadpisywania istniejących dowodów), security
  i exact-head CI przed merge. Testy scenariuszy błędnych nie dotykają urządzeń.
- Raport E2E rozróżnia fixture, live GET, zastosowanie konfiguracji i rzeczywiste
   odtwarzanie. Każdy cel: PASS/DEFERRED/ERROR + przyczyna i data.
  Niedostępność/WAF → PARTIAL całej floty, nigdy COMPLETE. Druga weryfikacja
  naprawionej polityki i konfiguracji musi dać NO_CHANGE; odświeżenie raportu
  lub podpisanego assignmentu nie jest nieidempotentną zmianą ustawień.
- Uaktualnić runbook operacji i indeks dokumentacji; nie ogłaszać pełnego
  sukcesu przy odroczonym Bedroom, nieznanym playerze lub starej telemetrii.
- Commit/push/PR wyłącznie naszego zakresu bez sekretów; nie obchodzić CI/review.
  Wersja repo Kodi bez zmian. Nowe wersje dodatków/obrazów tylko gdy potrzebne.
- Końcowy odczyt API + GUI panelu przez CDP, kontrola usługi i idempotencji.
  Nie promować nieprzetestowanego pakietu ani ponownie wdrażać identycznego obrazu.

## Postęp

- [x] Audyt 10.09: 858 PASS, potwierdzone luki i odrębny stan runtime.
- [x] P0: zabezpieczenie starego worktree i nowa gałąź od main.
- [x] Niezależny review planu i zastosowanie zasadnych uwag.
- [x] A: zabezpieczenia rollout/restore/Rapideo + testy.
- [x] B: X88 naprawiony; polityka wszystkich 6 enrollmentów NO_CHANGE,
  świeży rzeczywisty cykl X88 i zdrowe stany; konflikt LWW sprawdzony fixture.
- [ ] C: Bedroom osiągalny ADB, ale RPC odtwarzania UNKNOWN — bezpiecznie
  odroczony; test konfliktu między fizycznymi klientami nadal niekwalifikowany.
- [x] D: monitoring sprawdzony; decyzje Copilot/candidate/VIP jawnie odroczone.
- [ ] E: dokumentacja, CI, publikacja i końcowy odbiór.
