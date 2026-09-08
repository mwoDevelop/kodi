# Naprawa statusów operacyjnych — 8 września 2026

Aktualny wynik opisuje sekcja F i [raport po aktywacji Pro](e2e-results/2026-09-08-pro-recovery.md).
Pozostałe sekcje zachowują historię wcześniejszego etapu i jego ówczesnych blokad.

## F. Odblokowanie po aktywacji GitHub Pro — plan bieżącej kontynuacji

Użytkownik aktywował Pro samodzielnie. Odczyt Billing potwierdza Pro $4/mies.;
nie zmieniamy żadnych budżetów nadwyżek ani innych subskrypcji. Stan początkowy
panelu: 8 źródeł działa, 3 historyczne błędy mwoScrapers, opóźniony cron
promocji Umbrelli i 1 oczekujące przypisanie Bedroom TV (pozostałe 5 zastosowane).

1. Wykonać po jednym kontrolowanym ponowieniu trzech audytów mwoScrapers
   oraz zablokowanych CI PR backendu #20 i mwoScrapers #31. Odróżnić przyjęcie
   zadania od sukcesu testu, uploadu dowodu i publikacji obrazu. Przy dalszej
   blokadzie magazynu nie ponawiać w pętli ani nie wyłączać skanów/artefaktów.
2. Zweryfikować faktyczne opóźnienie promocji Umbrelli i istniejące aktywne
   próby. Jeżeli żadna nie działa, wykonać jedno ponowienie, bez resetowania
   trwałych limitów automatycznych retry watchdoga.
3. Po zielonym CI scalić PR backendu #20 (zachowanie aktywnych przypisań),
   opublikować przeskanowany obraz 0.10.1 i wdrożyć tylko Profile Sync przez
   `qnap_images.py`, z backupem bazy i zachowaniem starego digestu. Sprawdzić
   wersję, health, przypisania i idempotentne drugie wdrożenie.
4. Po zielonym CI scalić PR mwoScrapers #31 i w tej samej operacji wdrożeniowej
   skoordynować oba katalogi monitoringu z tygodniowymi audytami. Dzienny test
   providerów pozostaje. Dodać regresje limitu wieku tygodniowych obserwacji;
   nie releasować dodatku na urządzenia wyłącznie z powodu zmiany cronów.
   Audyt implementacji wykazał dodatkową zależność: Control Plane 0.12.1
   odrzuca dzień tygodnia w parserze cron. Najpierw wdrożyć kompatybilny
   parser 0.12.2 z regresją niedziela=0, UTC, granic tygodnia i pominiętego
   poniedziałku; dopiero następnie nowe katalogi i rzeczywiste crony.
5. Ponownie sprawdzić Bedroom TV bez nadpisywania tożsamości. Jeżeli jest
   niedostępny, jawnie zachować DEFERRED; nie usuwać prawdziwego ostrzeżenia.
6. Uruchomić regresje i E2E API/mTLS oraz CDP panelu, publiczne repo, health
   QNAP. Po odświeżeniu porównać job ID/statusy z GitHub. Aktualizować stable
   locki tylko dla przetestowanych digestów; zapisać dowody oraz odstępstwa.

Kryterium sukcesu: nowe audyty z rzeczywistym SUCCESS (łącznie z uploadem),
brak historycznego BILLING_BLOCKED po odczycie nowych wyników, zgodna kadencja
GitHub/watchdoga/panelu, backend zachowuje aktywne przypisania, a panel nie
ukrywa niedostępnego klienta. Zastane zmiany bramy QTS pozostają poza zakresem.

Nowy test po odblokowaniu potwierdził osobny problem PirateBay: filmy testowe
zwracają pusty sentinel API (odcinki działają), a diagnostyka nazywa go
FILTERED_EMPTY. Sprawdzić zapytanie zawierające rok wobec samego tytułu i
zachować ścisłą walidację tytułu/roku/IMDb. Nie zmieniać próbek ani progów tylko
w celu zazielenienia monitoringu; poprawka adaptera wymaga osobnej kwalifikacji.

### Wynik F — 8 września, 12:34 UTC

- Audyt bezpieczeństwa, discovery i ponowienie promocji Umbrelli: SUCCESS.
  Blokada uruchamiania/uploadu nie powtórzyła się po aktywacji Pro.
- Backend **0.10.1** i Control Plane **0.12.3** wdrożone na QNAP; drugi deploy
  `NO_CHANGE`, siedem kontenerów zdrowych, pięć przypisań nadal `APPLIED`.
- Dodatkowa naprawa panelu: ręczny sukces na gałęzi testowej nie jest już
  traktowany jako naprawa produkcyjnego crona. Regresje, API i produkcyjny
  CDP PASS; audyt providerów prawidłowo pokazuje `FAILED`, nie fałszywe `OK`.
- PirateBay: ograniczony fallback bez roku przechodzi 83 testy i rzeczywisty
  health probe na gałęzi **mwoScrapers #32**. Wdrożenie pozostaje zablokowane
  przez `REVIEW_REQUIRED`, podobnie jak optymalizacja harmonogramów **#31**.
  Nie ominięto review. Zależny **kodi #360** pozostaje draftem; nowe katalogi
  tygodniowe nie są aktywne w produkcji. Parser tygodniowy jest już gotowy.
- Bedroom TV: ponowna próba ADB kończy się timeoutem, nadal DEFERRED.
- Kod serwerów, stable lock i raport: scalone, wypchnięte, testy zakończone
  sukcesem. Szczegółowe run ID, digests i dalsze kroki są w podlinkowanym raporcie.

## Zweryfikowany stan początkowy

- QNAP: siedem kontenerów `running/healthy`, osiem źródeł Control Plane `OK`.
- Trzy workflow mwoScrapers: rzeczywisty błąd publikacji artefaktów, nie providerów.
  Przebiegi 34106189104, 34107195645 i 34109740675 przeszły właściwe testy,
  lecz upload został odrzucony przez limit magazynu GitHub Actions.
  Nowsze próby są odrzucane przed startem przez budżet Actions.
- Watchdog pomija nieudane ręczne próby przy wyborze skutecznej remediacji.
  Błędnie używa wieku starego przebiegu także do cooldownu, więc wysyła
  następne próby co około 90 sekund zamiast co najmniej 15 minut.
- Pięć urządzeń ma `ACTIVE_ASSIGNMENT_MISSING`; należy porównać to z backendem,
  stanem kanału i podpisanymi przypisaniami, zanim zmieni się konfigurację.
- `DELAYED` procesów dziennych oznacza rzeczywisty brak dzisiejszego crona,
  nie błąd wyświetlania. `STALE` urządzenia nie dowodzi awarii sieci.

## Kolejność realizacji

1. Naprawić cooldown watchdoga: uwzględniać także nieudane/anulowane próby,
   niezależnie od skutecznego przebiegu używanego do oceny zdrowia. Zachować
   alarm i nie uznawać odrzuconego/aktywnego ponowienia za sukces. Dodać regresje.
2. Sprawdzić zużycie artefaktów i dostępne bezkosztowe działania. Nie zwiększać
   budżetów, nie zmieniać prywatności repozytoriów ani nie usuwać dowodów
   release bez osobnej decyzji. Jeżeli blokada rozliczeniowa pozostanie,
   jawnie oznaczyć ją jako zależność zewnętrzną zamiast ukrywać alarm.
3. Wykonać backup backendu i sprawdzić podpisy/generacje przypisań. Uzupełniać
   wyłącznie brakujące przypisania już zatwierdzonej aktywnej rewizji istniejącym
   skryptem bootstrap. Nie promować przy okazji nieprzetestowanego kandydata.
   Potwierdzona przyczyna: `publish_candidate` usuwał wszystkie przypisania
   kanału. Poprawka backendu 0.10.1 ogranicza usuwanie do `candidate`;
   regresja sprawdza zachowanie active i wycofanie zastąpionego candidate.
4. Uruchomić regresje oraz E2E watchdoga i panelu, zbudować niezmienny obraz
   standardowym skryptem i wdrożyć tylko zmienioną usługę. Pozostawić cudze,
   niezwiązane zmiany bramy QTS bez zmian.
5. Odświeżyć Control Plane i porównać statusy z GitHub/QNAP. Udokumentować
   wyniki `PASS`, `PARTIAL` i zewnętrzne blokady; nie ogłaszać pełnego sukcesu,
   jeśli GitHub nadal odrzuca zadania albo urządzenia nie potwierdziły stanu.

## Kryteria odbioru

- Nieudany dispatch nie może generować następnej próby przed cooldownem.
- Po wdrożeniu watchdog nadal publikuje kompletny i świeży katalog 12 procesów.
- Panel pokazuje aktualne obserwacje i zachowuje prawdziwe alarmy.
- Każda zmiana przypisania ma backup, poprawny podpis i odczyt zwrotny;
  samo przypisanie nie jest dowodem jego zastosowania na wyłączonym Kodi.

## Wynik realizacji

- Watchdog: poprawka przeszła CI i wspólną bramę malware; obraz
  `sha256:0857e6b183387e4613e72abf9378844669de9c7ab101eed8d6c771359e3f568c`
  wdrożono i przypięto w stable locku (PR #354). Ponowny deploy zwraca `NO_CHANGE`.
- Profile Sync: pięć brakujących przypisań odtworzono. BlueStacks potwierdził
  `NO_CHANGE`, Sony zachował swój zastosowany kandydat. X88 wymagał dodatkowej
  naprawy instalacji; po niej również potwierdził `NO_CHANGE` i zdrowe menu.
- Backend 0.10.1: poprawka zachowania przypisań jest w
  [PR #20](https://github.com/mwoDevelop/kodi-profile-sync-server/pull/20),
  54 testy lokalne i wspólne E2E przeszły. **Wdrożenie pozostaje zablokowane**:
  Actions prywatnego repo odrzuca zadanie przed startem z powodu budżetu,
  a lokalny publisher nie ma scope umożliwiającego push do GHCR.
- Brama WWW: odtworzono brakujące dowiązanie CGI przez zainstalowany lifecycle
  QPKG. Poprawiono fałszywie dodatni test `cgi-ready`; przeglądarka CDP potwierdziła
  działający panel oraz przejście przycisku odświeżania `true` → `false`.
- X88: skrypt stable odtworzył brakujące dodatki i zależności, usunął wpisy
  dodatków wycofanych przez politykę projektu. Pięć skrótów do starego
  WatchNixtoons2 blokowało walidację listy; istniejący migrator poprawił adresy
  i zmaterializował grafiki. Po ponownym enrollment i włączeniu synchronizacji
  dynamicznej BlueStacks i X88 mają po **7 ulubionych i 7 lokalnych miniatur**.
- Bedroom TV pozostaje niedostępny przez ADB. NUC odpowiada przez SSH, ale Kodi
  nie działa w obu profilach. Przypisania oczekują na potwierdzenie po starcie;
  nie przedstawiamy tego jako awarii systemu ani zakończonego rolloutu.
- Nie zwiększono budżetów, nie zmieniono widoczności repozytoriów, nie usunięto
  artefaktów ani dowodów wydań. Aktywny magazyn samego repo Kodi to około 5,8 GiB,
  z czego większość stanowią kopie `testing-snapshot` przechowywane 90 dni.
  Wymaga to osobnej polityki retencji z weryfikacją kopii w immutable releases.

Szczegółowe dowody: [raport testów operacyjnych](e2e-results/2026-09-08-operational-health.md).

## Etap domknięcia — plan po niezależnym review

### A. Retencja i blokada Actions

1. Ponownie sprawdzić najnowsze adnotacje GitHub. Oddzielić limit magazynu
   artefaktów, blokadę budżetową uruchamiania oraz brak `write:packages`.
   Nie zmieniać płatnych limitów ani widoczności repozytoriów.
2. Dodać narzędzie z domyślnym trybem bez zmian do porządkowania wyłącznie
   tymczasowych artefaktów `testing-snapshot` w `mwoDevelop/kodi`.
   Pozostawić co najmniej 30 dni historii oraz wszystkie aktywne/nieudane
   przebiegi. Zweryfikować konsumentów (również certyfikację przez run ID).
   Usunięcie dopuszczać tylko po potwierdzeniu kopii obu plików w release
   `testing-snapshot-<id>`: identycznych bajtów snapshotu i raportu bezpieczeństwa.
   Nie usuwać release, tagów, certyfikatów ani jedynego dowodu skanu.
   Pierwsza partia wymaga również prawidłowej historycznej attestacji dla
   konkretnego snapshotu. Nie odświeża to jej ważności do nowej promocji.
3. Przed wykonaniem zapisać plan z dokładnymi ID, sumami i rozmiarem odzysku;
   wykonanie wymaga skrótu zatwierdzanego planu i ponownej walidacji warunków.
   Zacząć od małej partii. Dokumentować usunięcie i dostępność zachowanych kopii.
   Przed usunięciem zapisać i sprawdzić dodatkowy trwały backup poza Actions
   (ZIP i mapowanie run/attempt → snapshot/release/asset ID/SHA).
   GitHub Releases mają `immutable=false`; nie zakładać niezmienności i nie
   włączać jej automatycznie — certyfikacja dopisuje pliki do release.
   **Pozostawić TTL 90 dni.** Sam TTL 7 dni usunąłby także jedyne kopie przy
   awarii writer. Cleanup blokować przy aktywnych konsumentach, a dla
   historycznego rerun rozróżnić prawdziwy no-op od utraty artefaktu po
   udanym writer; drugi przypadek ma jawnie wymagać workflow_dispatch z ID.
4. Nie ponawiać ręcznie odrzuconych jobów w pętli. Po usunięciu blokady wykonać
   po jednej próbie trzech audytów i potwierdzić prawdziwy wynik w panelu.
   Przeliczenie magazynu może wymagać 6–12 godzin; nie czekać bezczynnie i nie
   obiecywać, że naprawi także budżet minut lub płatny limit.

### B. Backend Profile Sync 0.10.1

1. Ponownie wykonać regresje PR #20 oraz E2E publikacji kolejnego kandydata:
   aktywne przypisania muszą pozostać, zastąpione kandydackie zostać wycofane.
2. Zweryfikować istniejące, prywatnie przechowywane możliwości publikacji.
   Bez działającego CI/GHCR nie omijać skanów ani wymaganego review; nie
   przenosić prywatnego kodu do publicznego workflow jako obejścia budżetu.
3. Po przejściu bram zbudować i wdrożyć niezmienny obraz istniejącym
   `tools/qnap_images.py`; wcześniej backup bazy i zapis starego digestu.
   Zaktualizować stable lock dopiero dla obrazu z prawidłowym dowodem skanu.
   Odczytać health, wersję oraz przypisania; drugi deploy powinien być `NO_CHANGE`.
   W razie regresji przywrócić poprzedni obraz; backup bazy przywracać tylko
   jeżeli jest to konieczne i bez nadpisania nowszego stanu klientów.

### C. Pozostałe urządzenia i regresje

1. Sprawdzić rzeczywisty model/endpoint Bedroom TV oraz sesje obu kont NUC.
   Nie mylić dostępnego hosta z działającym Kodi. Zachować per-device identity.
2. Użyć istniejących skryptów stabilnego rolloutu/synchronizacji. Na NUC
   preferować start istniejącej instalacji w prawidłowej sesji użytkownika
   i sprawdzenie automatycznego zastosowania przypisania; nie robić reinstalacji
   ani nowego enrollment, jeżeli działająca tożsamość tego nie wymaga.
   Jeżeli nie ma sesji graficznej, wolno użyć istniejącego kontrolowanego
   testu Xvfb/Flatpak, z wyłącznym zajęciem instancji i przywróceniem początkowego
   stanu stopped po teście. Świeży heartbeat po takim teście nie oznacza
   pozostawienia Kodi stale uruchomionego.
3. Potwierdzić na każdym dostępnym kliencie zastosowaną rewizję, heartbeat,
   wygenerowane menu, wspólny cursor ulubionych i historii oraz miniatury.
   Nie promować kandydata Sony i nie nadpisywać dynamicznego stanu statycznym
   backupem. Niedostępne lub pozbawione sesji urządzenie raportować `DEFERRED`.
4. Uruchomić testy regresyjne narzędzi, backendu i E2E mTLS; ponownie odświeżyć
   panel przez API i CDP, porównać z rzeczywistymi zadaniami GitHub i urządzeniami.
   Sprawdzić publiczne repo dodatków. Nie zmieniać wersji repo Kodi z powodu
   zmian administracyjnych i nie wdrażać niezmienionych dodatków.

### Review, dokumentacja i zakończenie

- Przed implementacją osobny agent oceni zakres, bezpieczeństwo usuwania,
  zależności certyfikacji, kryteria sukcesu i realność odblokowania publikacji.
- Zasadne uwagi i odstępstwa zapisać tutaj; instrukcje retencji i wywołań
  narzędzia dodać do dokumentacji procesów cyklicznych, a dowody do raportu E2E.
- Zachować zastane, niezwiązane modyfikacje bramy QTS. Przed ewentualnym
  commitem skontrolować zakres i brak sekretów; status końcowy ma oddzielać
  kod przetestowany, kod wdrożony i działania zależne od zewnętrznej blokady.

### Uwagi niezależnego review zastosowane

- Retencja 7 dni była sprzeczna z ochroną jedynego dowodu po awarii writer;
  pozostaje 90 dni, a cleanup ma osobne warunki i próg ponad 30 dni.
- Konsument `certify-umbrella-hermetic` używa źródłowego run ID, nie wyłącznie
  release. Nie wolno utożsamić zniknięcia pliku z prawidłowym no-op.
- Release jest obecnie mutowalny; dodatkowy backup i ponowne porównanie
  przed DELETE są obowiązkowe. Usuniętego ID Actions nie da się odtworzyć;
  odtwarzalne są bajty, a powtórzenie certyfikacji używa snapshot ID.
- Backend pozostaje na zatwierdzonym obrazie aż do przejścia rzeczywistych
  bram publikacji. Poprawna kwalifikacja lokalna nie zastępuje tego dowodu.

## D. Dodatkowe zadanie: utrzymanie kosztu GitHub na poziomie $0

### Pomiar potwierdzony 8 września przez zalogowaną przeglądarkę

- Plan konta: **GitHub Free**. Zakładka Actions w Billing Overview pokazuje
  **2000/2000 minut** i **0,5/0,5 GB** wliczonego magazynu, reset za 23 dni.
  Gross usage $40,92 jest w całości skompensowane discounts $40,92; billable $0.
  Nie jest to rachunek do zapłaty. Budżet $0 z `Stop usage` chroni przed
  przekroczeniem; nie należy go usuwać ani przełączać na unlimited.
- Audyt API 28 repozytoriów (21 prywatnych): prywatne artefakty bieżące to
  około 97 MiB, ale naliczony magazyn w okresie rozliczeniowym jest inną miarą.
  Największe kopie bieżące leżą w publicznych repo; nie wolno utożsamiać ich
  sumy z płatnym wykorzystaniem. Publiczne standardowe joby mają rabat.
- Jeden prywatny projekt spoza Kodi ma około 10,07 GiB cache. To oddzielny
  limit per repo, wymagający audytu właściciela; w tym zadaniu nic tam nie kasowano.
- mwoScrapers: API wykazało ponad 2600 przebiegów od 1 września. W próbce
  1000 ostatnich: 997 `workflow_dispatch`, 3 `schedule`, wszystkie failure.
  Nie jest to liczba zużytych minut: odrzucone przed startem próby nie wykonały
  testów. Dokumentowana wcześniej pętla retry jest istotnym ryzykiem kosztowym.
- REST billing jest niedostępne dla obecnego CLI (brak scope `user`); liczby
  limitów odczytano z GUI. Endpoint run timing zwracał zera, więc nie używamy go
  do pozornego wyliczenia rzeczywistego rachunku.

### Rekomendacja — najpierw oszczędny wariant hosted, bez zmiany budżetów

1. Zachować $0/Stop usage dla wszystkich produktów. Ustalić wewnętrzny cel
   maksymalnie **1400 minut/miesiąc na całe konto** i 600 minut rezerwy;
   to cel planistyczny, nie zmiana limitu GitHub. Wszystkie projekty dzielą pulę.
   Cel dotyczy zużycia wliczonej puli prywatnych jobów, nie sumy czasów publicznego
   CI. Przed zmianami zebrać koszt/częstotliwość per workflow, a po zmianach
   potwierdzić prognozę pełnego miesiąca z retry, macierzą i rezerwą.
2. Rozszerzyć obecny poprawiony cooldown o rozpoznawanie blokady billing/quota:
   przy takim potwierdzonym błędzie brak kolejnych prób co 15 minut; najwyżej
   jedna kontrolowana próba na dobę lub po ręcznym potwierdzeniu odblokowania.
   Zwykłe awarie sieci zachowują ograniczone ponowienia, a alarm nie znika.
   Projektować klasyfikację na podstawie adnotacji, nie długości joba ani
   samego słowa failure. Zapis ma przetrwać restart obserwatora.
3. Zostawić codzienny tani test działania providerów. Odkrywanie nowych wersji
   przenieść na cotygodniowe; pełny audyt malware uruchamiać dla nowego digestu
   i okresowo co tydzień. Każdy nowy import/release nadal obowiązkowo skanować
   świeżym skanerem zgodnie z istniejącą polityką. Nie zastępować bramy bezpieczeństwa
   samym trafieniem w cache i nie obniżać pokrycia testów.
   W tym samym PR zmienić oczekiwaną kadencję w obu manifestach monitoringu
   i dokumentacji. Test: między poprawnymi tygodniowymi przebiegami brak
   fałszywego DELAYED i dodatkowych dispatchów. Zachować ważność raportu
   24 h i świeżość sygnatur 48 h; zmiana reguł/skanera/polityki wymaga rewalidacji.
   Tygodniowy audyt historyczny nie jest aktualnym pozwoleniem na release.
4. Usunąć podwójne wykonania identycznych testów na push + PR + container;
   jeden wynik dla dokładnego SHA, z poprawnymi wymaganymi checkami. Buildy
   tylko przy zmianach wejść obrazu lub jawnym release, limity czasu i
   `concurrency` dla zastąpionych kandydatów. Nie przerywać rozpoczętego writer.
   Reuse tylko przy równoważnych wejściach, środowisku i macierzy. Testować
   required check dla PR/merge SHA, pominiętego builda i anulowanego kandydata;
   nie uznawać skipped ani pustego checka za przejście właściwych testów.
5. Artefakty transportowe usuwać wyłącznie po zatwierdzonej archiwizacji,
   a małe raporty/dowody zachowywać. Limit roboczy prywatnego magazynu: 300 MiB,
   pozostawiając rezerwę w puli 500 MiB. Cache utrzymywać poniżej 8 GiB/repo,
   bez usuwania aktywnie używanych kluczy ani cudzych projektów bez uzgodnienia.
   Cel 300 MiB nie gwarantuje limitu naliczonych GB-godzin; uwzględnić pozostałe
   współdzielone płatne Packages. Budżet konta nadal jest nadrzędnym zabezpieczeniem.
6. Do Kodi Admin zaprojektować osobną obserwację: pozostałe minuty, naliczony
   magazyn, bieżące artefakty i cache, czas resetu oraz `BILLING_BLOCKED`.
   Progi 70/85/95%; brak dostępu do billing ma oznaczać `NOT_OBSERVED`, a nie zero.
   Nie dodawać kolejnego częstego workflow GitHub tylko do odczytu zużycia.

### Jeżeli limit nadal nie wystarczy

- Dedykowany, efemeryczny self-hosted runner dla prywatnych buildów/testów
  jest wariantem bez opłaty GitHub za minuty według aktualnych zasad. To nie
  znosi limitu upload-artifact. Raporty i zatwierdzenia trzeba nadal trwale
  archiwizować i weryfikować, a prawa GHCR nadać minimalnie publisherowi.
- Preferować odizolowaną maszynę/VM, nie runner z dostępem do produkcyjnego
  socketu Dockera QNAP, katalogów sekretów czy LAN urządzeń. Runner skanujący
  nieufny upstream nie może otrzymać sekretów wdrożeniowych. QNAP może trzymać
  kontroler/kolejkę i archiwum; kontener sam w sobie nie stanowi tej izolacji.
- Instalacja runnera, zmiana harmonogramów i nowy monitoring są **propozycją
  kolejnego etapu**, nie wykonanym wdrożeniem w tej sesji. Nie publikować
  prywatnego kodu jako obejścia limitu. Nie zwiększać budżetu bez osobnej decyzji.
- Obecnych 2000 zużytych minut nie odzyska cleanup. Domknięcie backendu przed
  resetem wymaga uzgodnionej ścieżki własnego runnera/publikacji albo osobnej
  decyzji budżetowej; nie oznaczać tego jako naprawione po usunięciu ZIP-ów.

Sekcję D również poddano niezależnemu review. Powyższe kryteria mierzalności,
spójnej kadencji monitoringu, ważności skanów i wymaganych checków wynikają
z zastosowanych uwag. Wariant własnego runnera eliminuje opłatę za minuty
GitHub według obecnych zasad, nie koszty energii i utrzymania hosta.

Źródła zasad (sprawdzone 8 września):
[GitHub Actions billing](https://docs.github.com/en/billing/concepts/product-billing/github-actions),
[GitHub Packages billing](https://docs.github.com/en/billing/concepts/product-billing/github-packages).
GHCR storage i transfer są obecnie darmowe; odrzucony push w tym zadaniu
dotyczył zakresu tokenu, nie dowiedzionego przekroczenia budżetu Packages.

## E. Realizacja zaakceptowanego wariantu $0 — kolejność i bramy

Status początkowy: retencja i rozróżnienie publikacji no-op są scalone w PR #356;
oba profile NUC przeszły kontrolowany rollout synchronizacji (bez reinstalacji).
Backend PR #20 nadal nie ma wykonanego CI. Zastane zmiany bramy QTS nie należą
do tego etapu i pozostają poza zakresem commitów.

1. **Ochrona przed powtarzaniem błędów budżetu.** Rozpoznawać wyłącznie
   potwierdzone adnotacje GitHub o blokadzie Actions/budżetu/magazynu, a nie
   sam status failure. Odczyt ograniczony do API danego repo, bez zapisywania
   treści adnotacji. Udostępnić kod `BILLING_BLOCKED` i stan obserwacji klasyfikacji.
   Dla takich awarii dopuścić najwyżej jeden automatyczny dispatch na workflow
   w ciągu 24 h; normalne awarie zachowują istniejący cooldown.
2. **Trwały dziennik prób.** Zapisywać identyfikator workflow/ref, czas próby
   i potwierdzoną blokadę w prywatnym wolumenie watchdoga. Zapis atomowy i fsync
   musi zakończyć się przed POST. Restart nie zeruje ochrony. Uszkodzony lub
   niezapisywalny dziennik blokuje remediację, ale nie odczyt zdrowia. Nowszy
   sukces jest dowodem odblokowania. Niedostępne API adnotacji nie może
   wymazać wcześniej potwierdzonej blokady. Nie zmieniać failed na healthy.
3. **Test i wdrożenie samego watchdoga.** Regresje: restart, utrata odpowiedzi
   POST, błąd zapisu, uszkodzony JSON, błąd/ograniczenie uprawnień API,
   nowy sukces, próba przed/po 24 h, zwykła awaria. Kontener testowy z trwałym
   wolumenem; potem pełne testy repo, skan, niezmienny obraz, zatwierdzenie
   standardową ścieżką qnap_images i odczyt statusu QNAP/API/GUI. Nie restartować
   innych usług. Zachować poprzedni digest do rollbacku; nie usuwać dziennika.
4. **Kadencja i duplikacja CI.** Przygotować razem tygodniowy audit/discovery
   mwoScrapers, odpowiadające im oczekiwania w obu katalogach monitoringu,
   regresje i dokumentację. Codzienny health pozostaje. Koordynować wdrożenie
   między repozytoriami: oczekiwania monitoringu aktywować dopiero po scaleniu
   rzeczywistego crona. Wyliczyć konserwatywną prognozę minut; uwzględnić retry
   i pozostałe prywatne projekty bez zmieniania ich konfiguracji. Usuwać
   podwójne testy tylko przy zachowaniu wymaganych checków PR/merge i skanów.
5. **Prywatne CI i publikacja backendu.** Najpierw audyt dostępnej infrastruktury
   runnerów. Runner urządzeniowy `mwo-kodi-release-runner` nie jest automatycznie
   kwalifikowany do tego zadania. Brak bezpiecznej izolowanej maszyny, uprawnień
   publikacji lub skanu jest jawną blokadą, nie uzasadnieniem obejścia bram.
   Po uzyskaniu prawdziwych wyników CI/scanu wrócić do części B: backup,
   wdrożenie backendu 0.10.1, readback i powtórny deploy `NO_CHANGE`.
6. **Monitoring zużycia.** Najpierw publikować potwierdzoną przyczynę blokady
   z adnotacji; liczniki billing wdrażać dopiero z działającym uprawnionym
   źródłem. Brak źródła = `NOT_OBSERVED`, nie licznik 0. Nie odczytywać
   prywatnych danych rozliczeniowych przez publiczne Actions ani nie dodawać
   częstego workflow do monitorowania samego limitu.
7. **Domknięcie.** Ponowić ograniczony test dostępności Bedroom TV i wykonać
   istniejący rollout tylko dla prawidłowo zidentyfikowanego dostępnego urządzenia.
   Zweryfikować panel względem niezależnego API, publiczne repo i regresje.
   Udokumentować osobno wykonane, wdrożone i zablokowane etapy; commit/push
   wyłącznie własnych zmian po kontroli sekretów. Bez zmiany wersji repo Kodi
   ani ponownej instalacji niezmienionych dodatków.

Przed implementacją tej sekcji osobny reviewer ocenia trwałość cooldownu,
bezpieczeństwo runnera, kolejność wdrożeń dwóch repozytoriów i kryteria sukcesu.

### Review E — przyjęte uściślenia

- Rollback do obrazu bez trwałego cooldownu musi uruchamiać wyłącznie obserwację
  (bez `--remediate`), również po automatycznym błędzie deployu. Zachować dziennik.
- Klasyfikacja uwzględnia najnowszą zakończoną próbę, także nieudaną ręczną,
  którą wybór skutecznej remediacji pomija. Sukces innej gałęzi lub wcześniejszy
  od potwierdzonego błędu nie zwalnia blokady.
- Tygodniowy cron wymaga rozszerzenia walidatora progów i tolerancji większej
  niż 7 dni. Zmiana samego crona i manifestu byłaby niewystarczająca.
- Dziennik: prywatny RW bind poza tmpfs, provisioning UID 10001 i zmiana
  walidatora qnap_images, pojedynczy writer, fsync pliku i katalogu, jawne
  pierwsze utworzenie. Brak/uszkodzenie wcześniej utworzonego pliku blokuje POST.
- Brak adnotacji/uprawnień oznacza nieznaną przyczynę i zachowawcze 24 h,
  bez przesuwania terminu przy każdym pollu. Dla zwykłych błędów dodać również
  twardy limit trzech automatycznych prób w ruchomych 24 h na workflow;
  samo minimum 15 minut nie chroni miesięcznej puli. Licznik nie jest kasowany
  przez restart ani udany dispatch, a nowszy sukces usuwa klasyfikację billing.

### Stan wykonania E (8 września, 11:07 UTC)

- E1–E3: implementacja scalona w **PR #357**, końcowe regresje **817 PASS**;
  obraz przeszedł skan i wieloarchitekturowy build `34218298136`.
  Kontrolowany deploy watchdoga i restart na QNAP przeszły: 12/12 obserwowanych
  workflow, trzy potwierdzone blokady billing, brak dodatkowego dispatchu po
  restarcie, identyczny dziennik przed/po. Promocja tego digestu do stable jest
  ostatnią bramą tego etapu; nie oznacza odblokowania prywatnych Actions.
- E4: **PR #31 mwoScrapers** zawiera tygodniowy audit/discovery, codzienny health,
  deduplikację push/PR i filtrowanie builda relay po wejściach. Lokalnie **81 PASS**
  i ruff PASS. CI prywatnego repo odrzuciło start, więc PR nie został scalony,
  a aktywne katalogi monitoringu nadal zgodnie opisują codzienny cron.
  Przy cutover ustawić progi watchdoga: remediacja `608400` s (tydzień + 1 h),
  maksymalny wiek `610200` s (tydzień + 1,5 h); najpierw rozszerzyć limit
  walidatora ponad `604800`. Zmienić oba katalogi, submodule ref i testy kadencji
  dopiero dla scalonego commitu. Pełny tydzień i granice tolerancji muszą przejść
  regresję przed włączeniem oczekiwań tygodniowych.
- Prognoza wyłącznie harmonogramów mwoScrapers: ostatnie udane próbki
  `34022666523` / `34023008514` / `34024256992` dają zaokrąglone czasy jobów
  odpowiednio 3/3/1 min. Dla 31 dni i 5 poniedziałków: **217 → 61 min/miesiąc**
  bez retry i wydań. To oszacowanie z czasów jobów, nie odczyt rachunku.
  Maksymalnie trzy retry dziennie przy tych przykładowych czasach dodałyby
  651 min; timeouts i koszt wydań mogą zwiększyć wynik. Cel 1400 dla całego
  konta nie jest gwarancją — pozostają inne projekty, release i rezerwa.
- E5–E6: backend PR #20 i publikacja nowego widoku liczników billing nadal
  wymagają odblokowanego prywatnego CI/kwalifikowanego runnera. Istnieje runner
  urządzeniowy oraz `/dev/kvm` na hoście, ale nie ma jeszcze zakwalifikowanego
  odizolowanego runnera buildów. Nie użyto dostępu do produkcyjnego LAN/sekretów
  jako obejścia izolacji; nie podnoszono budżetów ani zakresów tokenów.
- E7: Bedroom TV nadal niedostępny. Publiczny smoke **57/57**, E2E Control Plane
  mTLS **PASS**, panel pokazuje osiem źródeł `OK`, 5/6 applied i rzeczywiste
  błędy budżetu. Pola `BILLING_BLOCKED`/cooldown są obecnie w API watchdoga
  i narzędziu statusu; GUI zachowuje `FAILED`/`LAST_RUN_FAILED`, a nie licznik
  wolnych minut, którego API nadal nie udostępnia obecnemu tokenowi.

## Historyczny stan etapu domknięcia — przed aktywacją Pro

- A: narzędzie zaimplementowano i przetestowano, usunięto tylko dwa zweryfikowane
  duplikaty (113 MiB), zachowano trwały backup i release. Poprawka braku snapshotu
  rozróżnia rzeczywisty no-op od utraconego transportu. Minuty pozostają wyczerpane.
- B: 54 testy backendu i ponowne E2E mTLS PASS; publikacja/deploy nadal BLOCKED
  przez wyczerpaną pulę Actions. Nie omijano bram wydania.
- C: NUC-mwo i NUC-alek PASS synchronizacji istniejących tożsamości, menu,
  ulubionych i historii. Powrót do stopped po kontrolowanym teście. Panel
  potwierdza 5/6 zastosowanych klientów; Bedroom nadal DEFERRED.
- D: audyt budżetu wykonany, plan optymalizacji zapisany. Harmonogramy,
  monitoring billing i izolowany runner pozostają propozycją dalszego etapu.
