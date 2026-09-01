# Plan ujednolicenia kompatybilności dodatków z runtime Kodi

Data: 2026-09-01

Status: zrealizowany i zakwalifikowany na BlueStacks, X88 oraz NUC Flatpak

## 1. Cel

Każda zarządzana instalacja lub naprawa dodatku ma przed pierwszą mutacją wykazać,
że dokładny artefakt jest zgodny z docelowym runtime Kodi. Ta sama, czysta biblioteka
oceny ma być używana przez Android, Linux Flatpak, restore oraz narzędzia
kwalifikujące kandydatów.

Rozwiązanie ma pozostać otwarte na nowe dodatki i runtime przez dane oraz adaptery,
bez dopisywania warunków do każdego instalatora. Nie zastępuje natywnego mechanizmu
zależności Kodi, lecz dodaje fail-closed bramę tam, gdzie projekt instaluje ZIP przez
bezpośrednią podmianę plików.

## 2. Stan obecny i luka

- `kodi_ops rollout` kwalifikuje urządzenie względem prywatnego rejestru: model,
  platformę, ABI, główną wersję Kodi i ścieżki Flatpak;
- restore sprawdza zgodność wersji Kodi, ABI snapshotu i ABI APK;
- oficjalne dodatki mają częściową politykę minimalnych wersji zależności oraz ABI
  `inputstream.adaptive`;
- publikacja repo sprawdza domknięcie nazw zależności i kontrakt provider API;
- bezpośredni instalator kandydata sprawdza strukturę ZIP, ID i wersję, ale nie
  ocenia całego `<requires>` i metadanych `<platform>` przed podmianą;
- backup poprzedniego dodatku jest usuwany przed porestartowym sprawdzeniem, więc
  błąd aktywacji nie ma pełnej kompensacji;
- bezpośrednie wywołanie adaptera może ominąć preflight nadrzędnego `kodi_ops`.

## 3. Granice i źródła prawdy

### 3.1. Źródła kompatybilności

1. Dokładny `addon.xml` z kwalifikowanego ZIP-a albo katalogu snapshotu:
   - `id` i `version`;
   - wymagane i opcjonalne `<requires><import ...>`;
   - minimalna wersja zależności;
   - platformy z `xbmc.addon.metadata/platform`, z brakiem pola traktowanym jak
     `all` zgodnie z zachowaniem Kodi.
2. Wersjonowana polityka `manifests/kodi-addon-runtime-compatibility.json`:
   - obsługiwane główne wersje Kodi;
   - minimalne gwarantowane wersje wirtualnych zależności runtime, początkowo
     `xbmc.python=3.0.0` dla Kodi 21;
   - mapowanie platform projektu i ABI na zbiór nazw Kodi, np.
     `android + android-aarch64` albo `linux + linux-x86_64`;
   - jawne wyjątki dla artefaktów z kodem natywnym wraz z dozwolonymi ABI;
   - brak wpisu dla wykrytego kodu natywnego oznacza odmowę.
3. Fakty live przed mutacją:
   - dokładna wersja Kodi i jej major;
   - platforma;
   - ABI procesu/pakietu Kodi, nie tylko ogólne ABI urządzenia;
   - wersje i stan włączenia zainstalowanych zależności oraz systemowych capability
     Kodi (`xbmc.python`, `xbmc.gui`, `xbmc.addon` i pozostałe jawnie skatalogowane);
   - planowane wersje zależności z tego samego, przypiętego zestawu artefaktów.

Polityka nie może osłabiać wymagań `addon.xml`. Może tylko doprecyzować platformę,
ABI i znane wirtualne capability runtime.

### 3.2. Natywna instalacja Kodi

Instalacja użytkownika z repo mwoDevelop i `kodi-native-official` nadal korzysta z
natywnego `CAddonInstaller`, który rozwiązuje zależności i wersje. Nasza brama:

- ocenia runtime, platformę i wirtualne zależności przed wywołaniem instalacji;
- po instalacji potwierdza dokładną wersję, origin, włączenie oraz zależności;
- nie replikuje całego algorytmu wyszukiwania wersji z repo Kodi.

### 3.3. Bezpośrednie artefakty projektu

ZIP-y stable/testing i artefakty przenoszone do Flatpak muszą przejść pełną ocenę
`addon.xml` względem zależności zainstalowanych lub planowanych w tym samym,
content-addressed zestawie. Nieznana główna wersja Kodi, nieznany format wersji,
brak wymaganej zależności, niewłaściwa platforma albo niezakwalifikowany kod natywny
kończą przebieg przed zmianą plików.

## 4. Projekt modułów

### 4.1. `tools/kodi_addon_runtime_compatibility.py`

Czysta, niezależna od transportu biblioteka:

- bezpiecznie czyta `addon.xml` z ZIP-a lub katalogu;
- zwraca kanoniczny deskryptor artefaktu i listę wymaganych zależności;
- wykrywa pliki natywne bez rozpakowywania poza kontrolowany katalog;
- porównuje wersje zgodnie z semantyką `AddonVersion` Kodi, w tym prerelease
  `~alpha/~beta` i sufiksy dystrybucyjne; nieznany format odrzuca fail-closed;
- ocenia jeden artefakt lub zestaw artefaktów względem `RuntimeFacts`;
- rozróżnia zależności `installed`, `planned`, `virtual`; planowana wersja
  deterministycznie przesłania zainstalowaną, graf wymaga unikalnych ID, braku cykli
  i kolejności topologicznej;
- nieobecna zależność opcjonalna nie blokuje, ale obecna lub planowana musi spełnić
  deklarowane wymaganie wersji;
- zwraca ustrukturyzowany raport `PASS|INCOMPATIBLE` z kodami przyczyn, bez URL-i i
  sekretów;
- publiczne API nie wykonuje I/O urządzenia ani mutacji.

Centralny parser dodatkowo odrzuca duplicate names i kolizje wielkości liter,
backslash/NUL, zaszyfrowane wpisy, nie-regularne tryby Unix, DTD/entity w XML,
nadmierny compression ratio oraz przekroczenie limitu liczby plików, rozmiaru
`addon.xml` i sumarycznej dekompresji.

Polityka ma osobny JSON Schema, odrzuca nieznane pola i jest identyfikowana
kanonicznym SHA-256 używanym przez każdy adapter.

### 4.2. Adaptery faktów runtime

- Android: wersja Kodi przez JSON-RPC, ABI pakietu przez `dumpsys package`, zbiór
  tokenów platformy, wersje zależności przez `Addons.GetAddons`;
- Flatpak: istniejący `KodiPlatformLifecycle.probe_kodi()` oraz przypięty zestaw
  artefaktów; rollout nadal wymaga zatrzymanego i path-qualified Kodi;
- restore: fakty docelowe wynikają ze zweryfikowanego APK/Flatpaka i target binding,
  nie z wersji instalacji, która ma zostać usunięta.

Adapter Androida będzie dostępny także dla samodzielnego
`kodi_addon_candidate_rollout.py`, dzięki czemu bezpośrednie wywołanie nie ominie
bramy.

### 4.3. Jeden raport na transakcję

Każdy adapter zapisuje w wyniku:

- wersję schematu raportu;
- ID i wersję dodatku;
- platformę, wersję Kodi i ABI;
- skrót polityki oraz skróty ocenianych ZIP-ów;
- wynik i kody przyczyn;
- informację, czy zależność pochodziła z runtime, instalacji czy planu.

Nie zapisuje ścieżek prywatnych, endpointów ADB/SSH ani danych uwierzytelniających.

## 5. Dwufazowa instalacja bezpośredniego ZIP-a

Produkcyjny helper zostaje przeniesiony z `tests/e2e` do
`tools/device/kodi_addon_transaction.py` i otrzyma jawne operacje:

1. `prepare-activate`:
   - po zaliczeniu hostowej bramy rozpakowuje ZIP do bezpiecznego stagingu;
   - ponownie sprawdza ID i wersję wewnątrz runtime;
   - tworzy trwały journal i backup pod `special://home/.mwodevelop-transactions`,
     po sprawdzeniu `st_dev` targetu, stagingu i backupu;
   - journal zapisuje atomowo i synchronizuje plik oraz katalog przez `fsync` przed
     i po każdym rename;
   - przenosi poprzedni katalog do unikalnego backupu;
   - aktywuje kandydata, ale nie usuwa backupu;
   - zwraca losowy identyfikator transakcji i stan kompensacji.
2. Host restartuje Kodi, wykonuje `UpdateLocalAddons` i wymaga dokładnej wersji,
   włączenia dodatku oraz ponownej oceny wymaganych zależności.
3. `commit` usuwa backup i staging wyłącznie po sukcesie.
4. Przy dowolnym błędzie po aktywacji `rollback` usuwa kandydata, przywraca backup,
   restartuje Kodi i potwierdza poprzednią wersję/stany. Nieudana kompensacja daje
   `RECOVERY_REQUIRED`, nie fałszywy sukces.

Naprawa osieroconego, nieindeksowanego katalogu nie ma poprzedniego działającego
stanu. Raport oznacza wtedy `compensation=REMOVE_CANDIDATE_ONLY`; rollback usuwa
kandydata, lecz nie odtwarza nieczytelnego osieroconego katalogu.

Przerwana transakcja pozostaje rozpoznawalna po addon ID bez znajomości UUID.
Obowiązuje jeden aktywny transaction per addon oraz idempotentne
`status/commit/rollback`. Journal zachowuje poprzednią wersję, enabled i origin.
Następny proces najpierw bezpiecznie kończy rollback oraz potwierdza odtworzenie albo
odmawia działania; nie usuwa w ciemno nieznanych katalogów. Brak gwarancji wspólnego
filesystemu zatrzymuje przebieg przed mutacją.

## 6. Integracje

### 6.1. Android stable/testing

- przed pętlą instalacji oceniany jest cały przypięty lock i fakty runtime, a kolejność
  wynika z topologicznego grafu zamiast ręcznego `ADDON_ORDER`;
- `kodi_addon_candidate_rollout.rollout()` wykonuje ponowną ocenę jednego ZIP-a jako
  defense in depth i używa dwufazowej transakcji;
- nawet dodatki już zgodne wersją są oceniane, aby zmiana runtime nie pozostała
  niezauważona;
- wynik `kodi_android_stable_rollout.py` zawiera zbiorczy raport kompatybilności.

### 6.2. Dodatki domyślne i oficjalne

- dokładne ZIP-y są oceniane przed instalacją;
- zależności krytyczne z manifestu zachowują dotychczasowe minimalne wersje i ABI;
- zastąpienie istniejącej wersji `kodi-native-official` używa ocenionego exact ZIP-a
  i dwufazowej transakcji zamiast `remove -> InstallAddon(id)`;
- dla nieobecnego dodatku `InstallAddon(id)` jest dozwolone, lecz przed akceptacją
  całe zainstalowane drzewo musi odpowiadać przypiętemu ZIP-owi; różnica usuwa nowy
  stan i daje błąd;
- zależności, które ma rozwiązać oficjalne repo Kodi, są sprawdzane ponownie po
  instalacji;
- direct repair dokładnego oficjalnego ZIP-a korzysta z tej samej transakcji i
  rollbacku.

### 6.3. Linux Flatpak

- po pobraniu i weryfikacji SHA-256, ale przed wysłaniem payloadu, wspólna biblioteka
  ocenia wymagane, dependency i official artifacts jako jeden planowany zestaw;
- źródłem runtime jest już zakwalifikowany probe Flatpak;
- urządzeniowy adapter nadal wykonuje porestartową weryfikację wersji, originów i
  otwieralności;
- destrukcyjny reinstall wykonuje po instalacji Flatpaka nowy probe faktycznej wersji,
  architektury, systemowych capability i ścieżek, a następnie ponawia ocenę snapshotu
  przed skopiowaniem profilu; wersja deklarowana w snapshot nie jest faktem live;
- błąd bramy nie wysyła payloadu i nie zmienia profilu.

### 6.4. Restore/reinstall

- przed destrukcyjną fazą oceniany jest każdy katalog `payload/addons/<id>` kopiowany
  przez restore, względem docelowej wersji Kodi, platformy, ABI oraz całego
  projektowanego grafu;
- nieparsowalny lub niezgodny dodatek jest fail-closed albo jawnie wyłączony z
  payloadu przed autoryzacją; nie może zostać skopiowany i ponownie włączony bez
  oceny;
- niezgodność zatrzymuje proces przed uninstall i nie wymaga rollbacku.

### 6.5. Build, release i natywne repo

- `build_repo.py` używa parsera do sprawdzenia wszystkich publikowanych dodatków;
- build wymaga obsługiwanego runtime, kompletnego planowanego domknięcia zależności
  oraz kwalifikacji kodu natywnego;
- zewnętrzne zależności oficjalne pochodzą z przypiętego katalogu kwalifikacyjnego;
  build nie pobiera live metadanych;
- atestacja canary pozostaje końcowym dowodem funkcjonalnym, a nie zamiennikiem bramy;
- wersji dodatków ani repozytorium nie zwiększamy, jeśli zmieniają się wyłącznie
  narzędzia hosta, manifest polityki i dokumentacja.

## 7. Testy

### 7.1. Jednostkowe

- poprawne wymagania Python 3 i zależności planowane/zainstalowane;
- odrzucenie nieznanego Kodi major, za wysokiego `xbmc.python`, brakującej lub za
  starej wymaganej zależności;
- opcjonalna zależność nie blokuje;
- `platform=all`, `android`, `linux` oraz niezgodna platforma;
- dowolny kod natywny w zarządzanym ZIP-ie jest w pierwszym release odrzucany;
  `inputstream.adaptive` pozostaje w osobnej, przypiętej ścieżce natywnego Kodi;
- złośliwe ścieżki ZIP, symlink, zły ID/wersja i nieobsługiwany format wersji;
- stabilny, redacted raport i deterministyczny hash polityki.

### 7.2. Integracyjne

- Android stable i default wywołują bramę również przy `NO_CHANGE`;
- bezpośredni candidate nie mutuje przy błędzie bramy;
- sukces wykonuje `prepare-activate -> restart/verify -> commit`;
- wymuszony błąd aktywacji przywraca poprzednią wersję;
- przerwany przebieg po `activate` jest odzyskiwany przez nowy proces bez markera i
  bez znajomości transaction ID;
- Flatpak nie wysyła payloadu po niezgodności, a reinstall wykonuje post-install
  reprobe przed profile copy;
- restore odmawia przed uninstall także dla niezgodnego dodatku spoza
  `required_addons`;
- build repo odrzuca niezgodny publikowany dodatek.

### 7.3. E2E i wdrożenie

1. Dry-run i test negatywny na syntetycznym, niezgodnym ZIP-ie bez mutacji.
2. BlueStacks jako pierwszy canary:
   - audyt wszystkich stable/default dodatków;
   - kontrolowana reinstalacja tej samej wersji jednego bezpiecznego dodatku;
   - test wymuszonego błędu i potwierdzenie rollbacku;
   - standardowy scoped rollout oraz drugi przebieg `NO_CHANGE`;
   - regresja Umbrella/mwoScrapers, YouTube, WatchNixtoons2, Rapideo, napisy i
     Profile Sync.
3. X88 po sukcesie BlueStacks: audyt, zwykły scoped rollout i regresja bez testu
   destrukcyjnego rollbacku.
4. NUC Flatpak: read-only audit, rollout tylko jeśli bieżący plan wymaga mutacji;
   drugi przebieg `NO_CHANGE`.
5. Pozostała flota dopiero po sukcesie canary; niedostępne urządzenie daje
   `DEFERRED`, nie osłabia bramy.
6. Deterministyczne `tests/e2e/run.sh`, testy dokumentacji i dwie zielone bramki
   PR/`main`. Nie nazywamy tego live E2E; dowody live pochodzą z jawnych prób
   BlueStacks/X88/NUC opisanych wyżej.

Artefakt testowy niezgodnego dodatku powstaje wyłącznie w katalogu tymczasowym i nie
jest publikowany w repo Kodi.

## 8. Dokumentacja

- uaktualnić `docs/kodi-operations.md` o automatyczną bramę, kody błędów,
  `RECOVERY_REQUIRED` i przykłady audytu;
- uaktualnić `docs/architecture.md` o przepływ runtime facts -> compatibility gate
  -> transaction -> post-verify;
- dodać datowany raport do `docs/e2e-results/`;
- opisać rozszerzanie polityki dla nowego Kodi major, platformy lub dodatku natywnego;
- zaznaczyć, że ręczna instalacja z interfejsu Kodi używa natywnej kontroli Kodi i
  nie generuje raportu hostowego.

## 9. Kolejność realizacji i punkty stop

1. Dodać politykę, parser/evaluator oraz testy bez integracji z urządzeniami.
2. Wpiąć fail-closed preflight do build i Android candidate; testy rollbacku.
3. Wpiąć Android stable/default oraz restore; pełna regresja lokalna.
4. Wpiąć Flatpak i testy izolacji payloadu.
5. BlueStacks canary; przy błędzie lokalnym poprawa i ponowny pełny test.
6. X88 oraz NUC, potem pozostała dostępna flota.
7. Dokumentacja, raport E2E, PR, CI, merge i sprawdzenie procesów po merge.

Nie wykonujemy mutacji urządzenia, jeżeli nie ma raportu `PASS` dla dokładnego ZIP-a,
runtime i polityki. Nie wykonujemy full rollout, jeżeli rollback canary, E2E lub
bramka bezpieczeństwa nie przejdą.

## 10. Kryteria ukończenia

- wszystkie zarządzane bezpośrednie ZIP-y przechodzą wspólny preflight przed
  mutacją;
- bezpośrednie wywołanie candidate nie omija bramy;
- brak znanego Kodi major, platformy, ABI lub wymaganej zależności jest fail-closed;
- nieudana porestartowa aktywacja przywraca poprzedni działający dodatek albo daje
  jawne `RECOVERY_REQUIRED`;
- Android, Flatpak i restore korzystają z tej samej semantyki raportu:
  `AUDIT_PASS|NO_CHANGE|INCOMPATIBLE|RECOVERY_REQUIRED`, z digestem projektowanego
  grafu i opcjonalnym transaction ID;
- BlueStacks, X88 i NUC mają aktualny dowód E2E, a drugi rollout jest idempotentny;
- dokumentacja odpowiada implementacji;
- worktree jest czysty, zmiany są w PR, wymagane CI przeszło, PR jest scalony i
  proces po merge zakończył się sukcesem.

Każdy dodatek jest osobną sagą. Plan nie obiecuje atomowości całego locka; częściowy
rollout zachowuje raport wykonanych transakcji i kończy się jawnym statusem zamiast
udawać globalny rollback.

## 11. Wynik realizacji

Plan wdrożono 2026-09-01. Wspólny evaluator jest używany przez build repo,
Android stable/testing, dodatki domyślne, bezpośrednią transakcję ZIP, Android
restore, Flatpak rollout i Flatpak restore. Produkcyjny helper przeniesiono z
`tests/e2e` do `tools/device`, a ręczna kolejność `ADDON_ORDER` została zastąpiona
porządkiem grafu.

BlueStacks potwierdził rzeczywisty commit oraz kontrolowany rollback z odtworzeniem
dokładnych bajtów, X88 potwierdził ARM i pełną regresję, a NUC — ścieżkę Flatpak.
Nie zmieniono wersji repo ani dodatków, ponieważ publiczne ZIP-y pozostały bez zmian.
Szczegóły i identyfikatory przebiegów znajdują się w
[raporcie E2E](e2e-results/2026-09-01-addon-runtime-compatibility.md).
