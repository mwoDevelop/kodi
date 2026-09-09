# 9.09.2026 — mwoScrapers stable i pasywna obserwacja PR

Status: **W TRAKCIE**. Godziny workflow są w UTC (wieczór 8.09 odpowiada
nocy 9.09 w Polsce). Nie jest to deklaracja ukończenia P3/P4 Copilota.

## Release dodatków

- PR Kodi #350 aktualizuje lock mwoScrapers do 0.2.2 i referencję wrappera
  0.1.1 (niezmienione bajty wrappera). SHA ZIP-a:
  `774c51eec678d3304a8cd75cada0674042776a607c7b35d4e6b2dd786e145597`.
- CI exact-head `34284044739` PASS. Pierwotny run PR `34265240931` wymagał
  zgody na wykonanie workflow; zatwierdzono **uruchomienie testów**, nie bypass
  review. Po jego SUCCESS normalny merge #350 utworzył
  `a0853c74275a51aaaf99445e2da31ed7a442c4ab`.
- Osobny czysty checkout `kodi-release-20260909`, branch main. Niezwiązane
  lokalne zmiany QTS Gateway w pierwotnym checkout nie są objęte wydaniem.
- `kodi_ops.py release --dry-run` PASS. Rzeczywista operacja
  `941e86f246634f1c950c9e4048d55239`: pełna regresja **834 PASS**, dwa buildy
  deterministyczne. Raporty w prywatnym katalogu checkoutu wydania.
- Testing `34284683107` SUCCESS; snapshot
  `58162edc2ee03660c1f27fe2d39aa45747901c3014c3b46e3d51cde69daa6a25`.
  Pages `34285341670` SUCCESS. Ta pierwsza operacja została zatrzymana przed
  promocją: security run `34286062056` ujawnił wyścig zegara w teście TOTP
  (kod wyliczany po przeciwnych stronach 30-sekundowego okna). Nie był to
  wynik skanera malware ani błąd logowania produkcyjnego Gateway.
- Fixture TOTP otrzymał kontrolowany zegar i dwa przypadki brzegowe 59/60 s;
  produkcyjny CGI pozostał niezmieniony. Dodatkowo test katalogu statusów
  sprawdza teraz dziewięć konkretnych identyfikatorów, zamiast stałej liczby
  ośmiu. Lokalna pełna regresja: **837 PASS** (w tym jeden niezależny, lokalny
  test Gateway; nie wchodzi do naszego commitu). Czysty zakres CI obejmuje
  **836 testów**. PR Kodi **#363** scalono normalnie po SUCCESS obu dokładnych
  przebiegów `34287450762` i `34287459495`; merge
  `b191252bdd4e664a33027ad78dea0e173caee280`.
- Nowy release `d43fb4a53ce645eb8b549ad965182f91` rozpoczęto z czystego main
  powyżej, bez zmiany zapisów nieudanej operacji. Lokalny pełny E2E **836 PASS**,
  dwa buildy identyczne. CI main `34287764076`, automatyczny testing ze skanem
  `34287764134` i Pages `34288330760`: **SUCCESS**.
- Właściwa brama security tej operacji: `34288932583` **SUCCESS**. Przed
  wymuszonym snapshotem skrypt czeka na zakończenie pojedynczej kolejki Pages.
- Wymuszony snapshot `34290045255` **SUCCESS**, ID
  `510d6f130153f38742aa174b171aaa3b356d437430a2ea522bf9724f31b62b4b`.
- Control Plane 0.12.4: build/test/scan/weryfikacja `34290634581` **SUCCESS**,
  digest `sha256:9786179d6fe9873abf98ed4332f9dd994fccb7fcd1a28681a540d195e80abd4d`.
  Cztery pozostałe obrazy użyto ponownie bez zmian. Kandydat QNAP:
  `c00b7033b11b873371fe496a290e71809701b6855e4d3a9e920d056716b2434d`,
  SHA dokumentu `13aaccf981e57afc9a5fb8b1d62efc6c489dd47193be19e720089ff4603a228c`.
- Certyfikacja urządzeń `34290958091`: **FAIL** na X88 — dwa
  `resolve_timeout` dla Big Buck Bunny. BlueStacks przeszedł wcześniejszą
  część macierzy. Operacja poprawnie zatrzymała się przed promocją.

### Naprawa stanu X88 przed ponowieniem tej samej certyfikacji

- Potwierdzono wyłączony `provider.external.enabled` i puste powiązanie
  providera, przy aktywnym mwoScrapers na BlueStacks. `rd_cloud.enabled=false`
  oraz timeout 60 s były zgodne na obu urządzeniach. Błąd nie dowodzi awarii RD/VPN.
- `kodi_mwoscrapers_configure.py` przywrócił kanonicznych sześciu providerów,
  publiczne endpointy i pełne powiązanie Umbrella; readback po restarcie PASS.
- Profile Sync raportował `UNPAIRED`. `kodi_android_profile_sync.py --device
  x88pro20` odtworzył parowanie i zastosował aktywną rewizję; `APPLIED`,
  `skin_menu_status=HEALTHY`.
- Osobny błąd importu YouTube wynikał z brakujących plików, nie z wersji
  `addon.xml`: brak 16 z 220 plików przypiętego pakietu 7.4.4, pozostałe zgodne.
  Pakiet o SHA `d744e5ba2d2b50924a9fa5624f4d209c2be95b97ef1ad1682cafbed160fb428f`
  ponownie wdrożono przez transakcyjny `kodi_addon_candidate_rollout.py`,
  zachowując userdata. Transakcja `a2009612cc9548b980a08516ee5c8aa3` COMMITTED;
  readback wszystkich **220/220** plików zgodny, bez braków i różnic.
- `kodi_youtube_configure.py`: `ACCOUNT_READY`, API 200, zweryfikowane konto.
  `kodi_youtube_playback.py --observe-seconds 100`: **PASS**, start 6,147 s,
  postęp materiału 110,838 s, zero zatrzymań/HTTP 403/błędów segmentów, bufor
  wzrósł z 1,16% do 18,83%. Prywatny raport
  `.kodi-private/youtube/x88-repair-playback-20260909.json`.
- Nie zmieniano snapshotu, polityki VPN ani kryteriów testu. Ponowienie release
  ma ponownie sprawdzić dotychczasowe dowody i wykonać certyfikację obu urządzeń.
- Ponowienie `34293451303`: **SUCCESS**. BlueStacks i X88 zaliczyły po pięć
  bram: inventory, wersje/originy, wyszukiwanie Umbrella, resolver/odtwarzanie
  Umbrella i odtwarzanie WatchNixtoons2. Atestacja
  `a6ef7b5161a183c6a77a476ca8d289abdbdff22946e2f2554f7e8e461abf019f`,
  SHA `63ee40e9ce3c2a800de3ac3540a3aa73785fd25400a76e5e35804df047eb571b`.
- Release utworzył PR **#364**, head `f4cda40a91fe962fd887865bfa80dcb3cc2e5119`,
  wyłącznie dwa locki. Stan `WAITING_APPROVAL`. Uruchomiono CI pull_request
  `34294027280` po wymaganej zgodzie na wykonanie workflow; nie użyto bypassu.
- Niezależny audyt promocji agy-yolo `gemini-3.8-flash-high`: **PASS**, sesja
  `3896570b-80b7-48e3-b698-dde75217d04e`. Świeży odczyt natywny przed audytem:
  minimum puli 0.9183964133262634. Reviewer zweryfikował snapshot, atestację,
  jej ważność 9–16.09, sumy locków, raport bezpieczeństwa obrazu i brak zmian
  pozostałych składników. CI exact-head `34294025755` SUCCESS; standardowy
  przebieg PR w chwili audytu jeszcze trwał.
- Standardowy CI `34294027280` również SUCCESS. PR #364 scalono normalnie
  do `b81fd01a81807f9742dd23accecc20690fbbe18e` o 00:18:53 UTC.
  Wznowiono ten sam release w celu publikacji i pełnego rolloutu.
- Deploy stable `34294476975` oraz Pages `34294502146`: **SUCCESS**.
  Publiczny smoke: **57/57** plików zgodnych. Uruchomiono pełny rollout
  `26a5672e59e0461fac86b22f1432557c`.
- Dodatkowy read-only audyt YouTube na BlueStacks i Sony: **220/220** plików
  zgodnych z tym samym przypiętym ZIP-em, bez braków i różnic.
- Snapshot obejmuje wcześniejsze testing Umbrella 6.7.86.3 i Profile Sync
  1.5.1. Ich wspólna kwalifikacja urządzeń jest wymagana przed promocją.

## Copilot i niezależny review

- Live readback: jeden collaborator `mwoDevelop`, jeden wymagany approval,
  `MWOSCRAPERS_COPILOT_MODE=observe`, brak aktywnej flagi policy-bot approvals.
- Review planu agy-yolo `gemini-3.8-flash-high`: SUCCESS, sesja
  `2003dafc-2314-42f1-9372-54c8148a3d73`, minimum puli 0.9264124631881714.
  P3 nie wolno włączyć bez kwalifikowanej ścieżki maintenance. App i rollback
  to zadania implementacyjne, nie zastępują tej decyzji.
- P5a scalono normalnie w Control Plane **0.12.4**, PR **#28**, merge
  `852ec07e154bc549b9d5ecfe25ea38aed7e49689`. CI dokładnego head
  `34285996489` oraz main `34286655532`: **SUCCESS**. Obraz produkcyjny
  został zakwalifikowany i wdrożony na QNAP (digest i run powyżej). Tylko GET; bez
  importu kodu kandydata, żądań AI, approval, merge i odczytu lokalnego rejestru.
- Review kodu: ten sam model, SUCCESS, sesja
  `1f2b5b84-acf1-4d9f-95fb-b518d337ed18`, minimum puli 0.9241979122161865.
  Poprawiono zachowanie formalnego werdyktu po komentarzu, pomijanie autora,
  kadencję bez cronów i wspólny próg świeżości. Wyłączenie źródła ukrywa stary
  cache jako `disabled`.
- Zaostrzenie walidacji ujawniło podwójne ID w fixture: pierwszy CI #28
  `34285886150` failure. Fixture poprawiono bez osłabienia walidacji.
  Ponowne testy: **115 PASS**, składnia JS i diff whitespace PASS.
- Read-only live GET odczytał PR mwoScrapers #29. Osobny GET wewnątrz
  kontenera QNAP z istniejącym tokenem: **HTTP 200**, dokument listowy.
  Nie zmieniano ani nie ujawniano tokenów.
- Chrome CDP fixture: render karty, refresh i błąd API z zachowaniem starych
  wierszy oraz widocznym ostrzeżeniem — **PASS**; powtórzone również z czystego
  checkoutu scalonego main i backendu 0.12.4.
- Produkcyjny API + CDP po deployu: **PASS**, 9/9 źródeł OK, 14 procesów,
  PR #29 z poprawnym head i `NOT_OBSERVED` dla review/kwalifikacji. Przycisk
  odświeżania: `aria-busy=true` → `false`, aktualizacja daty obserwacji.

## Rollout i dodatkowe zabezpieczenie gotowości Compose

- Pierwszy pełny rollout `26a5672e59e0461fac86b22f1432557c` wdrożył CP 0.12.4,
  ale odczytał WWW w fazie startu. Wszystkie 7 kontenerów osiągnęło `healthy`.
  Przyczyną przedwczesnego zakończenia oczekiwania był brak kontenerów authz/web
  w bramie `qnap_lock.py`; dodano weryfikację obu, ich digestów i limitu 120 s.
  Regresje: **24 PASS**, w tym start, trwałe unhealthy, brak i niezgodny digest
  każdego kontenera towarzyszącego. Produkcyjny test helpera, również po poprawce
  review: **NO_CHANGE**. Review agy-yolo `fad5f7fb-a175-4cba-8bcf-d42b8351d9b7`
  wskazał rozróżnienie rzeczywistego `{status: missing}` od braku klucza; dodano
  realistyczne fixture, ograniczone oczekiwanie i osobny błąd nieważnej obserwacji.
  Minimum puli przed audytem: 0.9127495884895325; model `gemini-3.8-flash-high`.
- Eksport Rapideo i później odczyt YouTube zostały prawidłowo odrzucone, gdy
  symlinki w tymczasowym checkout prowadziły poza jego prywatny katalog.
  Utworzono w nim rzeczywiste prywatne katalogi (700) i pliki (600);
  nie osłabiono walidacji ścieżek ani nie ujawniono sekretów.
- Pełna promocja konfiguracji zatrzymana na wcześniejszym kandydacie
  `sha256:3c3391bf5a67880e732ce0d8489589c1b8407ac70adaddb43c71857bcf744430`.
  Backup diagnostyczny `ps-1788914278-diagnostic-candidate-5dfcf4` potwierdza
  różnicę w `umbrella.preferences` i hash polityki, nie w wydawanych dodatkach.
  Kandydat był już obserwowany na Sony w raporcie z 8.09. Nie zastąpiono go
  ani nie zmieniono aktywnej generacji 7. Obecny eksport favourites ma 7 pozycji,
  starsza aktywna rewizja 8; nie potraktowano tego jako zgody na publikację.
- Rozpoczęto rollout tych samych locków na wszystkie sześć wskazanych celów,
  bez kroku promocji nowej konfiguracji: `f34a550cb73046afac2a6dafbb4b78c2`.
- Unieważnienie starego enrollmentu X88 wykonano osobno przez istniejący
  plan/apply CAS: generacja **19** unieważniona, **20** pozostaje aktywna.
  SHA planu `6d28d73df4708e0b22f1c7ed63bac0107e13cb8bd23888c66e3df3500162b271`.
  Odczyt API `audit_sequence=103806`: enrollment X88 **OK**, alert
  `MULTIPLE_ACTIVE_GENERATIONS` usunięty. Bieżące dane/token zachowano.
- Ponowne E2E Profile Sync → Control Plane → mTLS: **PASS**, 9 źródeł,
  14 procesów, odrzucenie klienta bez certyfikatu i niedozwolonej mutacji.
  Pełna regresja przed ostatnią uwagą review: **845 PASS** (jeden test jest
  niezależną lokalną zmianą Gateway, niewłączoną do naszego commitu).

## Dodatkowa diagnostyka operacyjna

- Sony TV i X88: ADB osiągalne, Kodi uruchomione. BlueStacks Rvc64 uruchomiono;
  instancja ADB osiągalna, Kodi należy uruchomić przed certyfikacją.
- Bedroom TV: timeout ADB; rollout wymaga dostępności urządzenia.
- NUC `mwo`: SSH, kwalifikacja ścieżek i Kodi 21.3 Flatpak poprawne, aplikacja
  była wyłączona podczas audytu.
- NUC `alek`: SSH działa, ale polecenia Flatpak (również `info tv.kodi.Kodi`)
  kończą się odmową odczytu `/var/lib/flatpak/app/com.microsoft.Edge`.
  Potwierdzono jawną ACL `user:alek:---` na katalogu Edge. Nie usuwano tej
  niezwiązanej z Kodi polityki dostępu. To blokada Flatpak, a nie brak sieci.
- Watchdog zgłaszał zbyt stary przebieg Umbrella przy ostatnim wyniku SUCCESS:
  wiek 6649 s > 4500 s, `RETRY_BUDGET_EXHAUSTED`. Ręczny dispatch
  `34287582363` zakończył się SUCCESS. Panel potwierdził `OK / REMEDIATED`,
  a watchdog w próbie 22:55:25 UTC wrócił do `HEALTHY`, bez awarii workflow
  i blokad billing. Następny natywny cron `34289635006` (23:13:18 UTC) również
  zakończył się SUCCESS. Nie zwiększano limitów ponowień ani budżetów.

Odtworzenie testu UI z checkoutem Control Plane 0.12.4:

```bash
.venv/bin/python tests/e2e/control_plane_dashboard_cdp.py \
  --control-plane-source /home/mwo/projects/kodi-control-plane \
  --expect-pr-observer
```

## Odbiór końcowy — do uzupełnienia

- [ ] Certyfikacja snapshotu na BlueStacks i X88.
- [ ] Promocja stable, publiczny smoke i pełny rollout.
- [ ] CI/merge CP #28, kwalifikowany obraz, deploy katalogu/obrazu i no-op.
- [ ] Odczyt produkcyjnego API i GUI, zgodność źródeł, jawne blokady.
- [ ] Commit/push dokumentacji, katalogu i testu E2E bez zmian Gateway/sekretów.

P3 (natywne approvals/required App check) i P4 (zlecenia napraw z limitem tur)
nie są ukończone. P5a nie oznacza pełnej obserwacji kontrolera ani jego kosztów.
