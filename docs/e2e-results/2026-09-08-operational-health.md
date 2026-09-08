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
