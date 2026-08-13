# Plan domknięcia audytu cyklicznego i enrollmentów Profile Sync

Status: ukończony 13 sierpnia 2026 r.

## Cel

Uszczelnić dzienny audyt zaakceptowanych artefaktów providerów tak, aby dokładnie
pobrane i przypięte bajty oraz ich bezpiecznie zmaterializowana zawartość rzeczywiście
przechodziły ClamAV, Semgrep i Gitleaks; wyrównać dokumentację z aktywnymi źródłami;
oraz unieważnić stare tokeny Profile Sync bez naruszania aktualnych enrollmentów.

## Etap 1 — poprawny payload audytu providerów

1. Zmienić `check_upstreams.py`, aby po weryfikacji SHA-256 i struktury zapisywał:
   - dokładny ZIP pod deterministyczną nazwą;
   - bezpiecznie zmaterializowane pliki pod katalogiem danego źródła;
   - kompletną inwentaryzację w `summary.json`.
2. Zabronić niebezpiecznych nazw źródeł, dowiązań, plików specjalnych, kolizji
   nazw, traversal, zaszyfrowanych i zagnieżdżonych archiwów. Nie importować ani nie
   uruchamiać kodu upstream.
3. Dodać bramkę pokrycia, która po wspólnym skanerze porówna raport z oczekiwaną
   liczbą ZIP-ów, plików, członków archiwów i bajtów. Zielony workflow nie może być
   możliwy, gdy skan objął wyłącznie raport JSON.
4. Rozszerzyć testy jednostkowe i kontraktowe workflow o dokładną obecność oraz
   kolejność: pobranie → skan → weryfikacja pokrycia → publikacja artefaktu.

Kryterium wyjścia: raport skanera zawiera co najmniej dwa archiwa Coco/Viper oraz
ich zmaterializowane pliki, wszystkie cztery kontrole są `pass`, a próba z
niepełnym raportem kończy się błędem.

## Etap 2 — aktualna dokumentacja i monitoring

1. Usunąć Magneto z opisu aktywnego audytu w `docs/scheduled-processes.md`.
2. Opisać Coco i Viper jako aktywne źródła oraz Magneto jako zachowaną, wycofaną
   obserwację historyczną, która nie uczestniczy już w cyklu.
3. Uruchomić testy spójności dokumentu, cronów i manifestu watchdoga.

Kryterium wyjścia: dokument odpowiada lockowi mwoScrapers i nadal wymienia dokładnie
sześć monitorowanych workflow.

## Etap 3 — bezpieczne unieważnienie starych enrollmentów

1. Dodać do hostowego narzędzia QNAP wąskie, walidowane polecenie revocation
   wykorzystujące istniejący serwerowy interfejs administracyjny.
2. Przed zmianą wykonać spójną kopię online produkcyjnej bazy Profile Sync.
3. Dla BlueStacks i X88 wybrać najwyższą, nierevokowaną generację wyłącznie wtedy,
   gdy ma aktualny heartbeat i udany raport dla aktywnej rewizji.
4. Unieważnić wszystkie niższe, nadal aktywne generacje. Nie usuwać rekordów i nie
   zmieniać aktualnego enrollmentu, przypisania ani kanału.
5. Po operacji potwierdzić, że każde z tych urządzeń ma dokładnie jedną aktywną
   generację, aktualna generacja zachowała heartbeat i aktywną rewizję, backend oraz
   watchdog są zdrowe.

Rollback: revocation jest celowo nieodwracalna dla starego tokenu. Kopia bazy służy
wyłącznie do awaryjnego odtworzenia całego stanu; nie należy przywracać jej tylko po
to, aby ponownie aktywować stare tokeny. Gdyby aktualna generacja została błędnie
naruszona, urządzenie otrzyma nowy enrollment kontrolowanym mechanizmem parowania.

## Etap 4 — E2E, integracja i wydanie

1. Uruchomić pełne testy mwoScrapers oraz właściwe testy głównego repozytorium.
2. Zacommitować i wypchnąć najpierw mwoScrapers, następnie zaktualizować wskaźnik
   submodułu oraz dokumentację w `kodi`.
3. Uruchomić ręcznie `check-provider-upstreams.yml`, pobrać jego artefakt i
   potwierdzić rzeczywiste pokrycie skanu.
4. Sprawdzić CI obu repozytoriów i powrót watchdoga QNAP do `healthy` bez błędów.
5. Wydać nową wersję tylko wtedy, gdy zmienia się instalowany kod dodatku. Zmiana
   narzędzi audytowych i dokumentacji sama w sobie nie wymaga nowego ZIP-a Kodi.

Kryterium końcowe: kod, CI, ręczny przebieg cykliczny, artefakt skanera, QNAP oraz
stan enrollmentów dają zgodny, powtarzalny wynik bez aktywnych starych tokenów.

## Wynik realizacji

- mwoScrapers PR `#26` i korekta praw dostępu skanerów PR `#27` zostały scalone;
- kontrolowany workflow `31713645062` przeszedł na `main`: 2 archiwa, 174 członków,
  177 plików, 5 044 782 bajty, `skipped=0`, brak znalezisk, wszystkie cztery kontrole
  `pass`;
- główne repozytorium PR `#169` przeszło dwa niezależne E2E, a lokalnie uzyskano
  `492 passed` zarówno dla pełnego pytest, jak i `tests/e2e/run.sh`;
- przed zmianą produkcji utworzono i zaszyfrowano spójną kopię online
  `scheduled-hardening-20260813`; SQLite zwrócił `integrity_check=ok`;
- unieważniono 8 starszych enrollmentów: BlueStacks zachował wyłącznie generację 2,
  X88 wyłącznie generację 10. Obie aktywne generacje zachowały udany raport bieżącej
  rewizji `home-stable`;
- Profile Sync i provider relay na QNAP są zdrowe, a watchdog widzi dokładnie sześć
  workflow i pustą listę `workflow_failures`.

Nie utworzono nowej wersji dodatku Kodi: instalowany kod mwoScrapers 0.2.0 nie został
zmieniony; poprawka dotyczy wyłącznie narzędzi audytu, workflow i operacji hosta.
