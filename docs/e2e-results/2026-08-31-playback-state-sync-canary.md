# E2E synchronizacji stanu odtwarzania — BlueStacks i X88

Data: 2026-08-31  
Zakres: `watchnixtoons2.playback.v1`, Profile Sync, backend QNAP  
Prywatność: raport nie zawiera tytułów, URL-i, tokenów ani identyfikatorów enrollmentu.

## Dokładne artefakty kandydujące

- `service.mwodevelop.profilesync` 1.3.3 — ZIP SHA-256
  `0587c1a05e65b57f76ff99b8b5470836b3da92fbd27d52ce0f041d0d9ee47e22`;
- `plugin.video.watchnixtoons2.mwodevelop` 0.30.3 — ZIP SHA-256
  `34299a47155e2b2f54e104788d502f27cc52adc209daa7b3ba602daf1c69703e`;
- badana ścieżka treści ma wyłącznie zredagowany SHA-256
  `bff3e35426b6d5549b5b3717c20272ab162a54d126e0c858be7a8a7b12376527`.

## Wyniki

1. Powtórny cleanup Fen Light i YouTube2KodiLibrary zwrócił `NO_CHANGE` na obu
   urządzeniach.
2. BlueStacks odczytał rekord rewizji 1 jako `playcount=0`, resume `11/1327` i
   raportował `HEALTHY`, cursor 1, bez pending/error.
3. X88, bez wcześniejszego natywnego wpisu Kodi, odczytał ten sam rekord na liście.
   Profile Sync raportował `HEALTHY`, a jeden natywny zapis pozostał jawnie odłożony.
4. Odtworzenie na X88 utworzyło rewizję 2. BlueStacks po kolejnym odświeżeniu
   zastosował cały rekord X88 (`17/1327`) i przesunął cursor do 2.
5. Konflikt utworzono przy obu klientach na rewizji bazowej 2. BlueStacks wysłał
   lokalny rekord `9/1327` jako pierwszy i utworzył rewizję 3. Późniejszy rekord X88
   `19/1327` został rozstrzygnięty jako `SUPERSEDED_BY_REMOTE`; X88 przyjął dokładnie
   `9/1327`.
6. Stan końcowy QNAP: jeden rekord w scope, rewizja 3, dwa eventy per canary i licznik
   `remote_won=1` dla X88. Oba urządzenia mają feature flag włączoną, brak pending
   eventów i status `HEALTHY`.
7. Zewnętrzne źródła historii zostały wyrównane bez tworzenia rekordów LWW: na obu
   canary Umbrella używa backendu Trakt i spełnia politykę ustawień, a YouTube ma
   aktywną sesję oraz włączoną historię lokalną i zdalną. Autoryzacja Trakt pozostaje
   wyłączona, dlatego test historii konta Umbrella wymaga późniejszej jawnej
   autoryzacji użytkownika; nie blokuje to wydania adaptera WatchNixtoons2.
8. Publiczny kanał testing wystawił dokładnie Profile Sync 1.3.3 i WatchNixtoons2
   0.30.3; pobrane ZIP-y miały sumy identyczne z `manifests/locks/testing.json`.
9. Pierwsza automatyczna certyfikacja release została bezpiecznie zatrzymana przez
   brak metadanych `origin` czterech niezmienionych dodatków na X88. Rollout został
   uogólniony do pełnej polityki: artefakty identyczne ze stable należą do stable,
   a różniące się do testing. BlueStacks zwrócił `NO_CHANGE`, X88 wykonał naprawę,
   a powtórzenie na X88 również zwróciło `NO_CHANGE`; oba urządzenia mają 6/6
   dozwolonych originów.
10. Kolejna próba ujawniła brak prywatnych ustawień Real-Debrid na X88. Istniejący
    adapter przywrócił autorytatywny zestaw bez ujawniania wartości, po czym ten sam
    canary Big Buck Bunny przeszedł z `resolve_timeout` do poprawnego playbacku.
    Workflow certyfikacji przed macierzą przywraca teraz dokładny autorytatywny stan
    Umbrella na obu urządzeniach i akceptuje `NO_CHANGE` dopiero po porównaniu
    wartości, nie samej obecności pól.
11. Końcowa lokalna macierz na niemutowalnym snapshocie przeszła 5/5 kontroli na
    każdym canary: inventory, wersje/originy, Umbrella search, Umbrella
    resolver/playback i WatchNixtoons2 playback.
12. Release `ed22e86823794da39bf463f3e3e18a67` zakończył się `COMPLETE`. Snapshot
    `6e8ca80bc5a19529b133ccec77cc36f25eed2c3fcd0be546433728400aba9414`
    został promowany przez PR #299 i opublikowany w stable. Publiczny lock ma SHA-256
    `d27052a65ad22a0716f9258bc1640f59831ce95fb3cf99489002f34c59ab3b11`.
13. Rollout stable najpierw na BlueStacks, potem X88 potwierdził oczekiwane wersje
    siedmiu dodatków i 6/6 pochodzeń stable. Drugi przebieg obu urządzeń zwrócił
    `NO_CHANGE`; produkcyjny sync przez TLS także zwrócił `NO_CHANGE` bez
    oczekującego raportu.
14. Po wdrożeniu locka QNAP Control Plane działa na obrazie
    `sha256:98dff2ec8a676b571591ca6058ba4fce3255ffb92b6a0533d56d4de684928404`,
    a Profile Sync na
    `sha256:042ba838d1ab06274d276751bde67776d5fbae10081908e294731f185bbb8d20`;
    oba oraz pozostałe usługi raportują `healthy`.
15. Końcowa sonda z wdrożonym backendem raportuje na obu urządzeniach
    `playback_status=HEALTHY`, cursor 9, zero pending eventów i brak błędu.
    BlueStacks ma zero odłożonych aplikacji. X88 zachowuje jeden rekord jako
    `pending_application`, ponieważ odpowiadająca mu ścieżka nie ma jeszcze natywnego
    wiersza w bazie Kodi; rekord pozostaje widoczny przez cache WatchNixtoons2 i nie
    obniża zdrowia synchronizacji.

## Testy regresji

- Profile Sync: 61 testów;
- WatchNixtoons2: 25 testów, w tym odtwarzalny import drzewa downstream;
- wspólne narzędzia repozytorium: po poprawce originów i przywracania prywatnych
  ustawień pełny hermetyczny przebieg zakończył się wynikiem 691 testów;
- jawny tryb naprawy kwarantanny jest dozwolony tylko dla pierwszego nieudanego
  assignmentu bez wcześniej zastosowanej rewizji;
- stare generacje enrollmentu X88 zostały unieważnione dopiero po pomyślnej
  konwergencji nowej generacji.

## Świadome granice

- Rapideo nie ma jeszcze stabilnej tożsamości `file.id`, więc adapter pozostaje
  wyłączony zamiast hashować nazwę lub zmienny URL;
- Umbrella/Trakt i YouTube używają własnych usług kontowych, a QNAP obserwuje jedynie
  zredagowane booleany zdrowia; ich historia nie jest kopiowana przez playback LWW.
