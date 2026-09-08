# Kontrolowana akceptacja PR mwoScrapers — plan i odbiór

Data: 8 września 2026. Status: PO NIEZALEŻNYM REVIEW; IMPLEMENTACJA.

## Cel i zakres zgody

Automatyzować kwalifikację, review polityki, scalenie i potwierdzenie stanu po
scaleniu, bez globalnego usuwania wymaganych reviews. Akceptacja bota oznacza
spełnienie opisanych reguł i testów, nie niezależne ludzkie review ani gwarancję
braku wszystkich wad. Nie powstaje dodatkowa płatna usługa ani nowy częsty cron.

Użytkownik zlecił zaplanowanie, niezależne review, implementację, wdrożenie i testy.
Zmiany zabezpieczeń poza opisaną polityką, zakup usług i obejście rulesetów nie
są częścią automatyzacji. Zastane lokalne zmiany QTS Gateway pozostają nietknięte.

## Stan początkowy (sprawdzony przez API)

- `mwoDevelop/script.module.mwoscrapers`: auto-merge wyłączony, jeden wymagany
  approval, usuwanie nieaktualnych approvals, aktualna baza i check `test`.
  GitHub Actions może tworzyć reviews; domyślny token ma uprawnienia odczytu.
- PR #31: tygodniowy audit/discovery i odchudzenie wyzwalania CI/buildów;
  zmienia `.github/workflows`, dlatego nie jest zwykłym PR providera.
- PR #32: ograniczony fallback PirateBay i diagnostyka sentinel; testy i
  ręczny health probe gałęzi PASS, wymagane review jeszcze niespełnione.
- Kodi #360 jest draftem z tygodniowymi oczekiwaniami monitoringu; Control Plane
  0.12.3 już potrafi interpretować tygodniowe crony i izoluje wyniki gałęzi.
- Panel ma osiem źródeł OK; rzeczywiste problemy to health PirateBay na `main`
  oraz oczekujące przypisanie niedostępnego Bedroom TV.

## Projekt

### 1. Jawne klasy dopuszczanych zmian

- `provider-runtime`: wyłącznie jawnie wymienione adaptery publicznych torrentów,
  towarzyszące testy i dokumentacja; zmiana wersji dodatku tylko spójna i rosnąca.
  Bez zależności, nowych endpointów spoza polityki, plików wykonywalnych, symlinków,
  workflow, relay, credentiali, resolverów RD ani kodu bootstrap/sync.
- `provider-provenance`: zmiana odnośnika/commitu obserwacji przy niezmienionym
  źródle, wersji oraz SHA-256 artefaktu. Nie pobierać ani importować kodu w jobie
  mającym prawo zatwierdzania. Pełny audyt źródła jest osobną bramą.
- Zmiany workflow/uprawnień/polityki/validatora zawsze `MANUAL_REQUIRED`.
  #31 i wdrożenie samej automatyzacji są jednorazowym bootstrapem po zleconym
  niezależnym review, nie precedensem pozwalającym botowi zatwierdzać własną politykę.
- Pozostałe zmiany, fork obcego repo, nieznany autor, draft, brak dowodów lub
  niejednoznaczność: brak approval, stan z powodem wymagającym działania.

### 2. Rozdzielenie zaufania i dowodów

- Validator i workflow zatwierdzający pochodzą z chronionego `main`, nie z PR.
  Klasyfikacja analizuje pełny diff i bazowe pliki, nie etykietę ani tytuł PR.
- Testowana tożsamość zawiera repo, PR, `head_sha`, `base_sha` i rewizję polityki.
  Zmiana któregokolwiek elementu wymaga nowej kwalifikacji.
- Skan dokładnego drzewa przed wykonaniem kodu. Obowiązkowe `malware-scan`
  i `test` muszą mieć SUCCESS (nie skipped/neutral), właściwą aplikację i workflow.
- Dla runtime dodatkowo regresje z zaufanej bazy oraz live health probe uruchomione
  z zaufanego narzędzia/progów/próbek. Testy zmienione w PR są dodatkiem, nie mogą
  zastąpić testów bazowych. Kod PR działa wyłącznie na efemerycznym runnerze bez
  sekretów produkcyjnych i bez tokenu pozwalającego pisać do repo.
- Job zatwierdzający wykonuje tylko validator i API GitHub. Nie odpala skryptów,
  hooków, instalatorów ani kodu pobranego z PR. Token PR-write jest ograniczony do
  tego repo. Autor i reviewer muszą być różnymi tożsamościami; bot nie zatwierdza
  własnych PR-ów. Brak odpowiedniej tożsamości oznacza blokadę, nie owner bypass.
- Po review implementacji pierwsza wersja runtime dopuszcza tylko dokładnie
  przejrzany wariant PirateBay z #32, przypięty parą hashy pełnych AST modułu
  **i testów**. Sama nazwa metody/wywołania nie wystarcza (rebindings/dekoratory
  mogły ominąć pierwszą allowlistę). Inny kod wymaga ręcznie zatwierdzonej zmiany
  przepisu w polityce. Nie jest to automatyczny reviewer dowolnego Pythona.
  Metadane poza wersją są identyczne; podbicie wersji wyłącznie patch +1.
- Review jest związane z dokładnym commitem; przed approval i merge ponowny odczyt
  head/base. Wymagana aktualna baza i obowiązkowe checki pozostają w GitHub.
- Dopiero zatwierdzony PR dostaje native auto-merge. Brak flagi włączenia lub
  brak/utrata dostępu do dowodów oznacza tryb bez mutacji.

### 3. Uruchamianie i ponowienia

- Zdarzenia zakończenia kwalifikacji/CI oraz ręczny `workflow_dispatch` jako
  naprawa; nie dodawać pętli pytań co 15 minut do prywatnego repo.
- Konkretne wyzwalacze w mwoScrapers: `workflow_run` po `test` (completed)
  oraz `workflow_dispatch(pr_number, apply=false)`. Weryfikacja i testy mają
  tylko odczyt; osobny job mutujący dopiero po kwalifikacji, z globalną
  serializacją operacji merge/reconcile dla repozytorium.
- Kwalifikacja i wydanie są idempotentne dla repo/PR/head/base/policy. Tożsamość
  raportu i znacznik review pozwalają rozpoznać ponowne wywołanie (`NO_CHANGE`).
- Rozdzielić test kandydata od codziennego health produkcji; kandydat nie może
  zmienić produkcyjnego statusu w watchdogu/panelu.
- Merge przez `GITHUB_TOKEN` nie gwarantuje uruchomienia następnego workflow:
  jawny dispatch na `main` po odczytanym sukcesie scalenia, z deduplikacją.
  Bez bezwarunkowego release dodatków przy zmianach dokumentacji/cronów.
- Merge musi zakończyć się podczas ograniczonego oczekiwania 120 s; inaczej
  wyłączyć auto-merge i zażądać ponownej kwalifikacji. Nie pozostawiać uzbrojonej
  akceptacji po zwolnieniu globalnej kolejki. Ręczny dispatch scalonego PR ma
  osobną ścieżkę `reconcile`, a nie blokadę `PR_NOT_OPEN`.
- Po nieudanej próbie merge wycofać własny review bota dla dokładnego
  head/znacznika; zachować pozostałe reviews. Cleanup obejmuje również błędy
  publikacji review i uruchomienia komendy merge. Faktyczne scalenie pomiędzy
  odczytami API kieruje do followup zamiast fałszywego STALE_BASE.
- Zachować zapis próby przed wysłaniem dispatchu. Niepewna odpowiedź sieciowa
  daje `DISPATCH_UNCERTAIN`, nie automatyczną pętlę; operator może jawnie użyć
  `retry_uncertain=true`. `MAIN_ADVANCED` jest brakiem dowodu starego SHA, nie
  błędem samego merge ani fałszywym sukcesem testu produkcyjnego.

### 4. Bootstrap i konfiguracja GitHub

- Zachować istniejący ruleset oraz jeden approval; włączyć native auto-merge.
  Dodać `malware-scan` do formalnie wymaganych checków obok `test`.
- Przed zmianą ustawień zapisać prywatny backup i wykonać odczyt porównawczy.
  Narzędzie konfiguracji ma dry-run, scope jednego repo i nie usuwa pozostałych reguł.
- Sprawdzić działającą tożsamość bota i ścieżkę pierwszego review. Nowa polityka
  nie może sama zalegalizować swojego wdrożenia. Jeżeli nie ma istniejącego
  uprawnionego reviewera, raportować konkretną blokadę bootstrap zamiast
  tymczasowo zdejmować protection albo wykonać administracyjny merge.
- Review wykazał, że jedynym kolaboratorem jest autor obu PR-ów. Reviewer
  zaproponował jednorazowy operatorski bypass, już dozwolony technicznie przez
  istniejący ruleset, dla #31 i PR wprowadzającego automat. **Ta opcja wymaga
  osobnej wyraźnej zgody użytkownika**; zadano pytanie. Bez odpowiedzi wolno
  przygotować kod, CI i tryb obserwacyjny, lecz bootstrap pozostaje BLOCKED.
  Nie tworzyć dodatkowych kont/aplikacji wyłącznie dla upozorowania review.
- Niezależnie zakwalifikować #31 jako zmianę operatora; #32 jako runtime.
  Nowy commit po scaleniu innego PR wymaga ponownej kwalifikacji aktualnej pary.

### 5. Wdrożenie pozostałych poprawek

1. Po review/bootstrap scalić automatyzację i skonfigurować repo; najpierw dry-run.
2. #31: sprawdzić CI i review, scalić; następnie skoordynować kodi #360, nowy
   obraz watchdoga i katalog Control Plane. Przez krótkie okno przejściowe
   monitoring może pozostać stary; nie przedstawiać cutover jako atomowej
   transakcji dwóch repozytoriów. Po wdrożeniu sprawdzić zgodność i `NO_CHANGE`.
   Cutover wykonać w tej samej sesji, przed kolejnym porannym oknem dziennego
   monitoringu; w razie braku możliwości nie scalać #31 przed przygotowaniem
   przetestowanego obrazu i planu rollbacku.
3. #32: automatyczna kwalifikacja, review i merge; jawny health na `main`, odczyt
   watchdoga i refresh panelu, bez ręcznego kasowania jego rejestru remediacji.
   Po #31 i bootstrapie zaktualizować #32 względem `main` i ponowić całą
   kwalifikację. Dotychczasowy zielony run starego head nie jest już dowodem.
4. Nowy dodatek: kwalifikacja pakietu na BlueStacks, następnie X88; używać
   istniejących narzędzi build/release/rollout. Niedostępne urządzenie = DEFERRED,
   bez fałszywej kwalifikacji i bez publikacji nieprzetestowanego pakietu stable.
   Brama PR kończy się na merge i próbie produkcyjnej; ZIP/lock/rollout to osobny
   istniejący proces Kodi, nie nowe uprawnienia bota zatwierdzającego.
5. Serwisy QNAP: wyłącznie zmienione, przez `qnap_images.py`, niezmienne digests,
   backup i powtórny deploy. Nie przeinstalowywać niezmienionych dodatków.
6. Bedroom TV: jedna ponowna próba łączności; po dostępności istniejący rollout
   i potwierdzenie przypisania/heartbeatu, bez zmiany tożsamości.

## Testy odbiorowe

- Unit: poprawny provider/provenance; zakazana ścieżka, symlink, nowy endpoint,
  zmienione wymagania, nieznany autor/fork, usunięte testy bazowe, fałszywy check,
  brak/paginacja API, skipped/failure/running, stary SHA/base, podszyty raport,
  własny PR bota, duplicate invocation, dry-run bez żadnego zapisu.
- Negatywne E2E: PR zmieniający workflow nie dostaje auto-approval; failed/skipped
  skan lub zdrowie blokuje akcję; zmiana head/base po kwalifikacji blokuje merge.
- Pozytywne E2E: dokładny #32 przechodzi kwalifikację, bot review, auto-merge,
  próbę na `main`; ponowienie daje no-op bez kolejnej publikacji.
- Cutover cronów: GitHub, oba manifesty i runtime QNAP zgodne; tydzień + tolerancja
  poprawnie oceniane, nie dodano fałszywych dziennych DELAYED.
- Zachowane regresje projektu, bezpieczeństwa, API/mTLS/CDP i 57 plików Pages;
  wyniki urządzeń raportowane oddzielnie od testów repo i kontenerów.

## Monitoring i dokumentacja

- Zachować 12 źródeł cyklicznych; automatyzacja PR jest procesem zdarzeniowym.
  Wyniki i powody `ELIGIBLE`, `WAITING_CHECKS`, `MANUAL_REQUIRED`, `APPROVED`,
  `MERGED`, `NO_CHANGE`, `FAILED` udostępnić jako podsumowania Actions i raporty.
- Nie maskować `REVIEW_REQUIRED` jako awarii usługi. Panel nadal obserwuje
  produkcyjne testy na właściwej gałęzi; ewentualna karta kolejki PR jest
  rozszerzeniem obserwacji, nie nowym cyklicznym workflow.
- Dodać instrukcję włączenia/wyłączenia, przykłady dry-run/dispatch/ponowienia,
  granice akceptacji bota, bootstrap, źródła statusu i rollback. Podlinkować
  plan, review i raport E2E przez główne README/indeks dokumentacji.
- Rollback: wyłączyć flagę autoakceptacji, zachować PR/review/checki i dowody;
  cofnąć tylko zmienione ustawienia repo do zweryfikowanego backupu. Rollback
  kadencji przywraca spójnie crony i oba katalogi, nie sam próg watchdoga.

## Niezależny review i wykonanie

Review: agy-yolo, `gemini-3.8-flash-high`, sesja
`49e66111-6f9e-40ec-91c6-5518eb646ce9`, wynik SUCCESS. Minimum dostępnej puli
przed delegacją 0.9569956660270691. Odczyt planu i repo bez edycji.
Przyjęto uwagi o deadlocku bootstrap, zdarzeniu `workflow_run`, aktualizacji bazy,
pochodzeniu checków, ścisłej allowliście i rozdzieleniu merge od release.
Nie przyjęto jako automatycznej zgody postulatu owner bypass — oczekuje decyzji
użytkownika. Nie przyjęto ogólnego globu `tests/test_*.py`; v1 ma listę konkretnych
plików i zachowanie istniejących testów. Szczegóły: [review](CONTROLLED_PR_AUTOMATION_PLAN_REVIEW.md).

Nie uznawać przygotowanego kodu, przyjętego dispatchu ani zielonego testu innej
gałęzi za wdrożenie. [Odbiór częściowy z 8 września](e2e-results/2026-09-08-controlled-pr-automation.md)
zawiera wyniki testów, wdrożoną konfigurację GitHub i gotowy obraz watchdoga.
Bootstrap #31/#33, pozytywny merge #32 oraz jego pakiet/rollout nadal wymagają
dokończenia; flaga automatycznej akceptacji pozostaje wyłączona.
