# Audyt operacyjny i naprawy — 8.09.2026

## Wyniki potwierdzone

| Obszar | Wynik | Dowód |
| --- | --- | --- |
| Regresja projektu po watchdogzie i bramie | PASS | `764 passed`; wcześniejszy test ujawnił brak linku do planu, poprawiono indeks dokumentacji |
| Backend Profile Sync | PASS lokalnie / deployment BLOCKED | 54 testy, PR #20; limit budżetu prywatnych Actions, brak scope GHCR dla alternatywnego publishera |
| API/mTLS E2E | PASS | `tests/e2e/control_plane_readonly.py`: 8 źródeł, 14 procesów, mutacje i brak certyfikatu odrzucone |
| Watchdog — historia rzeczywistej awarii | PASS | replay runów 34206752636 i 34106189104: 60 s po nieudanej próbie `NOT_DUE`, alarm nadal `FAILED` |
| Watchdog — build i skan | PASS | [run 34207689177](https://github.com/mwoDevelop/kodi/actions/runs/34207689177), dokładny commit `bce4ffe435912fec4a1dcd9d653982948d160c2b` |
| Watchdog — deploy | PASS | nowy immutable digest w stable locku, ponowne `qnap_images.py deploy upstream-watchdog` daje `NO_CHANGE` |
| Kodi Admin przez CDP 9222 | PASS | naprawa 404, panel za bramą QTS, odświeżenie z widocznym `aria-busy=true` i powrotem do `false`, aktualne dane |
| BlueStacks | PASS | aktywne przypisanie `63a8026e…`, `NO_CHANGE`, poprawne menu, 7 ulubionych i 7 miniatur |
| X88 | PASS synchronizacji | odtworzone stable dodatki, enrollment 19, aktywne przypisanie `63a8026e…`, `NO_CHANGE`, zdrowe menu i Favourites, 7/7 miniatur |
| Sony | PASS obserwacji | świeży heartbeat, zastosowany wcześniej kandydat `3c3391bf…`; brak nowego rolloutu na Sony |
| Bedroom / oba profile NUC | DEFERRED | Bedroom nieosiągalny przez ADB; NUC osiągalny, Kodi zatrzymane; przypisania istnieją, oczekują na zastosowanie |

## Rzeczywiste błędy i granice wniosków

Trzy workflow mwoScrapers nie oznaczają dziś awarii providerów. W próbach
34106189104, 34107195645 i 34109740675 właściwe kroki testowe były zielone;
odrzucono dopiero upload raportu (`Artifact storage quota has been hit`).
Nowszy dispatch 34206752636 jest blokowany jeszcze przed uruchomieniem joba
(`Actions budget is preventing further use`). Nie wyłączono obowiązkowego raportu
ani nie ustawiono fałszywego sukcesu. Watchdog powinien nadal pokazywać ten alarm.

Podczas deployu obserwowano przejściowe `WATCHDOG_HTTP_503`; po załadowaniu
kompletnego raportu wszystkie osiem źródeł panelu wróciło do `OK`.
Dzienne crony GitHub ruszyły z opóźnieniem i po sukcesie/odświeżeniu panel usuwał
`DELAYED`; nie było potrzeby dodatkowych dispatchów tych procesów.

X88 miał brakujące pliki dodatków, niezarejestrowany Profile Sync i pięć starych
adresów `plugin.video.watchnixtoons2`. Normalny skrypt stable naprawił zależności
`idna` i `urllib3` oraz instalację naszych dodatków. Zgodnie z polityką usunął
wycofane Fen Light, CocoScrapers, oryginalny WatchNixtoons2 i repo CocoScrapers
wraz z ich pozostałościami. Próba bezpośredniego backupu starego XML ulubionych
przez ADB została odrzucona przez Android; migrator zachował pięć pozycji,
zmieniając ich adresy i grafiki. Ostateczną listę pobrał mechanizm QNAP Sync.
Nie wykonano w tym audycie testów odtwarzania filmów — dowody X88 dotyczą
instalacji, konfiguracji, menu i synchronizacji.

Nowa diagnostyka skryptu enrollmentu zapisuje wyłącznie nazwę pliku, linię
i funkcję wyjątku; nie zapisuje komunikatu wyjątku, pełnych ścieżek, zmiennych
lokalnych ani sekretów. Umożliwiło to wskazanie blokującej walidacji
`portable.py:_plugin_url` bez ujawniania konfiguracji użytkownika.

## Etap domknięcia po niezależnym review planu

Powyższa tabela opisuje wcześniejszy etap tego samego dnia. W kolejnym przebiegu:

| Obszar | Wynik | Dowód |
| --- | --- | --- |
| Regresja | PASS | 787 testów w 133,52 s; następnie 23 testy retencji (w tym dodatkowy readback) i 6 testów dokumentacji |
| Backend PR #20 | PASS lokalnie / BLOCKED publikacji | ponownie 54 testy i E2E mTLS; produkcyjny obraz nie został zmieniony |
| NUC mwo i alek | PASS synchronizacji | istniejący `kodi_flatpak_stable_rollout.py`, `rollout_mode=sync`, `NO_CHANGE`, active `63a8026e…`, 7 favourites/cursor 12, playback cursor 26, menu HEALTHY |
| Konfiguracja NUC | PASS | Profile Sync 1.5.0, Umbrella 6.7.86.1, WatchNixtoons2 0.30.3, mwoScrapers 0.2.1; YouTube ACCOUNT_READY, OpenSubtitles.com login pass/search 25; managed settings NO_CHANGE |
| Zakończenie testów NUC | PASS | oba procesy Kodi ponownie stopped, ścieżki Flatpak qualified; bez reinstalacji ani wymiany enrollmentu |
| Bedroom TV | DEFERRED | ponownie brak dostępu ADB; nie nadpisano konfiguracji |
| Repo publiczne | PASS | `smoke_public.py`: 57 zweryfikowanych plików |
| Panel QNAP | PASS | 8/8 źródeł OK, 5/6 świeżych i zastosowanych klientów; tylko Bedroom oczekuje przypisania. CDP login=false, refresh true→false |
| Approval promocji Umbrelli | PASS po ponowieniu | opóźniony cron; pojedynczy dispatch zakończył się sukcesem i po refresh API zmieniło DELAYED na OK/SUCCESS |
| Porządkowanie Actions | PASS dla małej partii | dwa exact ID usunięte po backupie; DELETE + 404 + ponowne hashe release i kopii lokalnych |

### Dowody retencji

- Usunięte ID: `8898388629`, `8856032923`; łącznie **118301137 bajtów**
  (około 113 MiB). Release/tagi i ich pliki nie zostały usunięte.
- Snapshoty: `847ba98e1664368ec2f1cb5fdb0fc27c622c87e093618f0cadfba80a9ae5a1c5`
  i `75e31558b47d0d73501c0fe23f086e09b7bb5c955bb5b3e025b647871fcf2903`.
- Trwałe kopie oraz `evidence.json`/`deleted.json` znajdują się pod
  `.kodi-private/actions-artifact-backups/<ID>/`. Da się odzyskać bajty, nie
  oryginalne ID Actions. Plan drugiej partii zatwierdzono skrótem
  `171490ff7ee3bd17775b5ff152905784659f43832418f0543d7af5d17d86323c`.
- Dodatkowy przegląd 38 nieudanych późniejszych certyfikacji: logi dostępne,
  brak odniesienia do obu snapshotów. Kontrola aktywnych konsumentów ponowiona
  bezpośrednio przed DELETE. Nie deklarujemy pełnego indeksu zależności po head SHA.
- Trzy inne kandydatury zachowano z powodu nieudanych zależnych procesów.
- Realne E2E `check-missing`: źródło `30923793057` po usunięciu artefaktu daje
  błąd z instrukcją workflow_dispatch; aktualny no-op `34209810797` jest poprawnie
  rozpoznawany jako `confirmed publication no-op`. Początkowy HTTP 415 downloadu
  usunięto przez właściwy Accept dla endpointu Actions; release używa octet-stream.
- TTL pozostał 90 dni. Cleanup nie stał się nowym zadaniem cyklicznym.

### Budżet — potwierdzona blokada zewnętrzna

Zalogowana przeglądarka Billing Overview potwierdziła GitHub Free,
2000/2000 minut i 0,5/0,5 GB. Kwota billable wynosi $0, reset za 23 dni.
Nie zmieniono żadnego budżetu. Usunięcie duplikatów nie cofa zużytych minut
ani naliczonego historycznie GB-hour; nie odblokowano w ten sposób backendu.
Trzy audyty prywatnego mwoScrapers pozostają FAILED, watchdog propaguje ten
rzeczywisty błąd. Nowa strategia oszczędzania jest opisana jako propozycja w
[planie napraw](../OPERATIONS_HEALTH_REMEDIATION_PLAN_2026-09-08.md#d-dodatkowe-zadanie-utrzymanie-kosztu-github-na-poziomie-0),
nie jako zrealizowana migracja runnerów czy zmiana harmonogramów.
