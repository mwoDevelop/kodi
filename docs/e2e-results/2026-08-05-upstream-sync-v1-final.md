# Certyfikat wersji ostatecznej upstream Sync v1

Data: 2026-08-05

Migawka testing `b88a0d70c1def535adbebbac9ae160b8ace656241c5011cf31315200612b77b7` z
adresowaną zawartością została certyfikowana i awansowana do wersji stable bez
konieczności przebudowywania archiwów komponentów. Dodatek repozytorium celowo pozostaje
w wersji `1.0.0`; w tej wersji wersjonuje się mechanizm synchronizacji, a nie bootstrap
repozytorium Kodi.

## Niezmienny dowód wydania

- certyfikacja urządzenia chronionego [run
  31028742156](https://github.com/mwoDevelop/kodi/actions/runs/31028742156) przekazana
  na BlueStacks1 i X88 Pro 20;
- przejrzano promocję stable PR [#125](https://github.com/mwoDevelop/kodi/pull/125)
  połączono dokładną migawkę `b88a0d70c1de…`;
- Wdrożenie stable [uruchom
  31029695984](https://github.com/mwoDevelop/kodi/actions/runs/31029695984) zakończone
  sukcesem;
- publiczne archiwum stable Profile Sync 1.0.2 ma SHA-256
  `2c644202e185d9f5e80ca6bbdec7cea5181f66b67e84e45bdddf6aad67d5bdea`, identyczne z
  certyfikowanym archiwum testing;
- stable rejestruje indeks źródła SHA-256
  `231f627410fb6fddf6ab51d2237cf3e225457597eaa236f57e6f4b97d574222a` i manifest
  artefaktu SHA-256 `1c35ca95055bee58f95a84a9b4aa5b4c2c8fdfb4113b84deedf19b1e78b1ac14`;
- lokalne wykrywanie zakończyło się deterministycznym niepowodzeniem, blokada stable
  pozostała niezmieniona, a pełny przebieg regresji przeszedł pomyślnie: testy Umbrella
  50, WatchNixtoons2 17, mwoScrapers 47 i repozytorium głównego 325.
- końcowy operacyjny PR [#126](https://github.com/mwoDevelop/kodi/pull/126) przeszedł
  zarówno dokładne [push
  CI](https://github.com/mwoDevelop/kodi/actions/runs/31034041248), jak i [pull-request
  CI](https://github.com/mwoDevelop/kodi/actions/runs/31034102176) przed połączeniem.

Profile Sync 1.0.2 naprawia przypadek, w którym przypisanie wygasło po zastosowaniu
dokładnie tej podpisanej wersji. Takie urządzenie pozostaje teraz zdrowe, zamiast
błędnie odrzucać swój aktualny stan. Jego komponent CI i trzy komponenty upstream
workflow wykorzystują przypięte akcje kompatybilne ze środowiskiem wykonawczym Node 24.
Przeglądany wskaźnik komponentu głównego PR
[#124](https://github.com/mwoDevelop/kodi/pull/124) zachował dokładne bajty wydania.

## Matryca urządzenia stable

| Urządzenie | Dodatki stable | Umbrella | WatchNixtoons2 | Profile Sync / stan przenośny |
| --- | --- | --- | --- | --- |
| BlueStacks1 | dokładne wersje i pochodzenie stable | wyszukiwanie + rozwiązanie + przepustka odtwarzania | przepustka odtwarzania | 1.0.2, `NO_CHANGE`, pass |
| X88 Pro 20 | dokładne wersje i pochodzenie stable | wyszukiwanie + rozwiązanie + przepustka odtwarzania | przepustka odtwarzania | 1.0.2, `NO_CHANGE`, pass |
| Sony TV | stable Profile Sync | wcześniej certyfikowane odtwarzanie; audyt przenośny powtórzony | audyt przenośny powtórzony | 1.0.2, `NO_CHANGE`, pass |
| Bedroom TV | stable Profile Sync | wcześniej certyfikowane odtwarzanie; audyt przenośny powtórzony | audyt przenośny powtórzony | 1.0.2, `NO_CHANGE`, pass |

Wszystkie cztery urządzenia Android wykorzystują różne rejestracje produkcyjne na kanale
`home-stable` i są zbieżne w aktywnej wersji
`sha256:4c7d728d214a6d31d1d277d2fd6b30957bc2d07d873648df5e0ffda69a1c905e`. Każdy ma te
same osiem ulubionych, siedem przenośnych akcji WatchNixtoons2 i nie brakuje żadnych
grafik. Prywatne dowody nadające się do odczytu maszynowego są przechowywane poza Gitem
pod `.kodi-private/e2e/`.

X88 wymagał przywrócenia sprawności po dryfie lokalnym urządzeniu, zanim został
zaliczony. Repozytorium i niestandardowe katalogi dodatków zostały odbudowane z
dokładnych plików ZIP stable; niekompletny oficjalny `script.module.urllib3` został
zastąpiony zweryfikowanym ZIPem 2.2.3 Kodi; Profile Sync otrzymał nową, unikalną
rejestrację; a brakujące ustawienia Umbrella/Real-Debrid i mwoScrapers zostały
przywrócone transakcyjnie ze stanu hosta prywatnego. Wdrożenie ustawień wielokrotnego
użytku wykorzystuje teraz blokadę przywracania Kodi, rollback, weryfikację semantyczną
po ponownym uruchomieniu i oczyszczone dowody. Druga synchronizacja zwróciła
`NO_CHANGE`, po którym nastąpiła pełna macierz odtwarzania X88.

Repozytorium testing pozostaje dostępne wyłącznie jako jawny kanał certyfikacji na
wybranych urządzeniach obsługujących technologię Canary. Każdy wydany dodatek mwoDevelop
używany przez matrix jest własnością pochodzenia stable. Bedroom TV pozostaje wyłącznie
stable. Repozytorium testing nie jest usuwane automatycznie, ponieważ dezinstalacja
repozytorium może spowodować usunięcie zależnych dodatków lub `addon_data`; wyłączenie
lub wycofanie go wymaga osobno zweryfikowanej migracji.

## Zaplanowane działanie i bezpieczeństwo

Centralne uzgadnianie workflow, aktualizatora Umbrella, aktualizatora WatchNixtoons2 i
wykrywania dostawców mwoScrapers mają aktualnie pomyślne zaplanowane uruchomienia/brak
operacji. Centralna weryfikacja ręczna [run
31027430984](https://github.com/mwoDevelop/kodi/actions/runs/31027430984) również
przeszła pomyślnie. Niezależny watchdog QNAP działa i jest zdrowy z niezmiennego obrazu
z systemem plików tylko do odczytu i polityką restartu `unless-stopped`.

Zagraniczni kandydaci przechodzą przez fail-closed ClamAV i bramkę polityki
semantycznej, zanim będą mogli dotrzeć do pisarza. Test dotyczący
pozytywnego/negatywnego złośliwego oprogramowania, w tym ścieżka odrzucenia EICAR,
został przekazany w [uruchom
30822178765](https://github.com/mwoDevelop/kodi/actions/runs/30822178765). Żaden
komponent upstream nie jest automatycznie łączony w gałąź produktu, a promocja stable
pozostaje sprawdzoną, ręczną decyzją na podstawie dokładnych certyfikowanych bajtów.

Obydwa skonfigurowane podmioty główne NUC/Flatpak zostały ponowione w dniu wydania, ale
host był nieosiągalny zarówno przez ICMP, jak i SSH (`No route to host`). Stanowią zatem
wyraźny wyjątek dotyczący dostępności i nie są zgłaszane jako przemijające ani błędnie
klasyfikowane jako regresja oprogramowania. Ich kwalifikacja tylko do odczytu pozostaje
następną akcją po powrocie gospodarza; żadna praca związana z wydaniem Android nie jest
zablokowana.
