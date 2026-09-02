# Plan deklaratywnej synchronizacji menu skórki Kodi

Status: `IMPLEMENTED_PENDING_RELEASE_E2E`

## 1. Problem i wynik docelowy

X88 ma osierocone pozycje `Movies` i `TV Shows` w menu Aeon Nox Silvo. Ich
akcje nadal wskazują na usunięty `plugin.video.fenlight`. Bieżący Profile Sync
zarządza wybranymi ustawieniami Kodi/Umbrella, Favourites z grafikami oraz
stanem odtwarzania, ale nie plikiem
`userdata/addon_data/script.skinshortcuts/mainmenu.DATA.xml`.

Docelowo wszystkie urządzenia używające `skin.aeon.nox.silvo` mają otrzymywać
jedną podpisaną, deklaratywną definicję menu bez urządzenia nadrzędnego. Pierwsza
wersja zawiera kolejno `Programs`, `Settings`, `Cartoons` i warunkowe
`PlayDisc`. Zastosowanie ma usuwać wszystkie inne pozycje, w tym odwołania do
niezainstalowanych dodatków.

## 2. Granice

W zakresie:

- nowy adapter rewizji `kodi.skin_menu` / `skin_shortcuts_v1` o własności
  `whole_document`;
- jawny kontrakt wyłącznie dla `skin.aeon.nox.silvo` i `mainmenu.DATA.xml`;
- crash-recoverable zastosowanie, journal, rollback, weryfikacja i powtarzalny
  `NO_CHANGE`;
- odbudowanie menu przez skórkę bez kopiowania plików generowanych;
- widoczny, zredagowany status adaptera w E2E i dokumentacji operacyjnej.

Poza zakresem:

- synchronizacja całego `addon_data`, ustawień wyglądu, widgetów, cache lub
  plików `*.hash`/`*.properties` generowanych przez `script.skinshortcuts`;
- synchronizacja zmian menu wprowadzanych lokalnie przez użytkownika;
- CRDT, merge pozycji lub urządzenie-publisher. Konfiguracja repo/QNAP jest
  autorytatywna i zawsze zastępuje cały dokument.

## 3. Kontrakt i bezpieczeństwo

1. Dodać publiczny, niesekretny manifest kanonicznego menu w `manifests/`.
2. Rozszerzyć schemat rewizji Profile Sync o `skin_shortcuts_v1` z polami:
   `skin_id`, `menu_id`, `ownership`, `apply_mode` i uporządkowanym `items`.
3. Ograniczyć liczbę oraz długość pól, odrzucać znaki sterujące, duplikaty ID,
   ścieżki spoza `special://skin/` i akcje poza zamkniętą listą czterech pozycji
   V1. `visible` jest symbolem kontraktu, nie dowolnym warunkiem Kodi.
4. Wymagać capability `skin-shortcuts-menu-v1` i minimalnej wersji klienta przed
   promocją rewizji. Starszy klient ma odrzucić assignment przed mutacją.
5. Nie przenosić absolutnych ścieżek, poświadczeń ani danych urządzenia.
6. W V1 dołączyć adapter do podpisanej rewizji bazowej dopiero po potwierdzeniu
   capability przez najnowszy aktywny enrollment każdego urządzenia z inventory.
   Runtime stosuje go tylko dla bieżącego profilu z aktywnym Aeon Nox Silvo,
   włączonym Skin Shortcuts 2.x i `shared_menu=true`. Brak precondition oznacza
   pominięcie adaptera, nie quarantine całej rewizji. Selektywne warstwy/tagi
   pozostają możliwym rozszerzeniem, ale nie są wymagane w V1.

## 4. Implementacja

1. W `profile-sync-addon` dodać izolowany moduł `skin_menu.py`, który:
   - waliduje i kanonizuje kontrakt;
   - czyta semantycznie bieżący `mainmenu.DATA.xml`;
   - planuje jedną operację journalowaną tylko przy różnicy;
   - zapisuje XML przez plik tymczasowy, `fsync`, `os.replace` i `fsync`
     katalogu nadrzędnego, odrzucając symlinki;
   - zapisuje przed mutacją pełną operację i jej poprzednie bajty w journalu,
     a publicznie raportuje fazy `SOURCE_WRITTEN`, `BUILD_REQUESTED`,
     `GENERATED_VERIFIED`;
   - wywołuje wspierany builder `RunScript(script.skinshortcuts,type=buildxml&`
     `mainmenuID=9000&levels=2&group=mainmenu|buttonmenu)`, czeka na zakończenie
     `skinshortcuts-isrunning` i sprawdza wygenerowany include;
   - przy błędzie przywraca dokładne poprzednie bajty, ponownie buduje poprzednie
     menu i je weryfikuje; nieudana odbudowa daje `ROLLBACK_PENDING`;
   - nie uruchamia buildera/reloadu podczas odtwarzania; pozostawia jawny
     `DEFERRED_PLAYBACK` i ponawia przy następnym bezpiecznym cyklu.
2. Uogólnić `TransactionalApplier` przez rejestr wersjonowanych handlerów
   operacji z preflight/apply/verify/rollback/post-apply, zachowując recovery
   istniejącego journala schema 1 oraz kontrakt Favourites. Jeden lock blokuje
   równoległe zastosowanie adapterów podpisanej rewizji (w tym historycznego
   adaptera Favourites) i menu. Dynamiczny strumień Favourites ma własny journal,
   a wspólny `StateStore` serializuje osobno wszystkie operacje read-modify-write.
3. W kompozytorze produkcyjnej rewizji wczytać kanoniczny manifest menu z repo,
   nie z urządzenia-publishera, i dołączyć go do podpisanej rewizji.
4. Rozszerzyć walidację JSON Schema, compose/no-op i raporty rolloutowe o nowy
   adapter. Favourites i playback pozostają osobnymi strumieniami.
5. Podnieść wersję Profile Sync, zbudować repo testing i najpierw rozprowadzić
   klienta obsługującego capability. Capability musi zostać potwierdzone w
   heartbeat aktywnych enrollmentów przed przypisaniem rewizji menu. Offline
   klient zachowuje poprzedni assignment do aktualizacji lub jawnego retired.
6. Nie łączyć pierwszego włączenia/skonfigurowania skórki i zastosowania menu w
   jednej rewizji. Adapter wykonuje semantic drift check przy każdym cyklu z
   ważnym podpisanym assignmentem. Wygasły assignment zachowuje dotychczasową
   zasadę bezpieczeństwa i nie powoduje nowej mutacji; okresowość zapewnia
   odnawianie assignmentu przez istniejące procesy operacyjne.

## 5. Testy i bramy

### Testy automatyczne

- walidacja kanonicznego manifestu i schematu;
- eksport/compose deterministyczny oraz zachowanie adaptera podczas aktualizacji
  Favourites;
- brak zmiany dla zgodnego menu;
- fazowy apply, build/reload tylko po zmianie, rollback po wstrzykniętym
  błędzie i recovery po przerwaniu procesu;
- kompatybilne recovery starego journala schema 1 i blokada równoległego apply;
- odroczenie podczas odtwarzania i ukończenie po przejściu do Home;
- odrzucenie nieznanej skórki, menu, akcji, ścieżki, nadmiarowych pól,
  duplikatu i klienta bez capability;
- regresja pełnych testów głównego repo, add-onu, serwera i Control Plane.

### E2E i rollout

1. Zarchiwizować zredagowane dowody przed zmianą i wykonać dry-run.
2. Opublikować nowy Profile Sync w testing; wdrożyć na BlueStacks i X88.
3. Opublikować menu jako candidate i potwierdzić na obu canary:
   - X88 traci `Movies`/`TV Shows` i nie zawiera `plugin.video.fenlight`;
   - oba urządzenia mają dokładnie cztery rekordy źródłowe w tej samej
     kolejności; bez napędu DVD widoczne są trzy, bo `PlayDisc` ma warunek
     `System.HasMediaDVD`;
   - restart Kodi zachowuje menu, Favourites i playback są `HEALTHY`;
   - powtórzenie zwraca `NO_CHANGE` i nie przeładowuje skórki.
4. Po sukcesie promować stable i wykonać pełny rollout na wszystkie dostępne
   urządzenia Android oraz oba profile Flatpak. Niedostępny cel raportować jako
   istniejący stan `DEFERRED`, bez cofania poprawnych urządzeń.
5. Sprawdzić Kodi Admin/QNAP: aktywna rewizja, aktualne heartbeat, brak
   `QUARANTINED` i brak regresji procesów cyklicznych.

## 6. Dokumentacja i zakończenie

- uaktualnić `docs/architecture.md`, `docs/kodi-private-profile.md`,
  `docs/kodi-operations.md` oraz indeks `docs/README.md`;
- opisać, że disaster-recovery przechowuje szeroki stan skórki, natomiast
  rutynowy Profile Sync zarządza wyłącznie semantycznym menu głównym;
- zapisać odtwarzalny raport E2E bez sekretów;
- po zielonych testach zakomitować zmiany w repo komponentu i głównym repo,
  wypchnąć gałęzie, przejść CI/PR i wydać nową wersję tylko komponentów, których
  artefakty faktycznie się zmieniły.

## 7. Kryteria akceptacji

- X88, BlueStacks i wszystkie osiągalne cele mają identyczne semantyczne menu;
- nie istnieje żadna aktywna akcja menu wskazująca na Fen Light;
- zmiana jest podpisana, default-deny i odwracalna;
- istniejące Favourites, grafiki oraz playback nie zmieniają semantyki;
- drugi przebieg jest bezpiecznym `NO_CHANGE`;
- repozytoria są czyste, zsynchronizowane z origin i przechodzą CI.
