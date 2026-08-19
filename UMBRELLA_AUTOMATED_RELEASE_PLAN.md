# Plan automatycznego wydawania i monitorowania Umbrelli

Status: zaimplementowany lokalnie; aktywacja automatycznego merge pozostaje
obserwacyjna do przejścia CI i no-op na GitHub

Data bazowa: 2026-08-19

## 1. Cel i decyzje

Automatyzacja ma wykryc nowy upstream Umbrelli, przeskanowac i odtworzyc
downstreamowy stos poprawek, zakwalifikowac izolowany artefakt, opublikowac go
w kanale stable oraz udostepnic w Kodi czytelny stan procesu. Realne urzadzenia
nie sa brama release; aktualizuja sie z `repository.mwodevelop` po uruchomieniu.

Plan dotyczy tylko Umbrelli. Pozostale dodatki zachowuja dotychczasowe wymagania
review i certyfikacji. Historyczny `UPSTREAM_SYNC_PLAN.md` pozostaje zapisem v1.

## 2. Bezpieczny automatyczny release

- Najpierw naprawic obecne awarie `propose-upstream-update.yml` i wymagac
  zielonego przebiegu oraz kolejnego `no-op` przed aktywacja automatyki.
- Discovery przypina dokladny commit Omega. Nowszy commit uniewaznia starszy
  Candidate-ID, PR i jego atestacje.
- Kandydat przechodzi skanowanie, replay patchy, deterministyczny build oraz
  testy hermetyczne bez sekretow, OIDC, cache i sieci. Checkout nie utrwala
  credentiali, a wykonanie ma read-only input i limity zasobow.
- Lock testing otrzymuje tryb komponentowy dla `plugin.video.umbrella`.
  Pozostale piny musza pozostac bajtowo identyczne, a kazdy etap wymaga
  `changed_components == ["plugin.video.umbrella"]`.
- Testing publikuje immutable snapshot oraz `qualification-v2` typu
  `hermetic_ci`. Istniejaca device-attestation pozostaje dla innych i recznych
  procesow.
- Stable kopiuje dokladnie ZIP z testing i ponownie wykorzystuje zweryfikowany,
  niezmieniony `qnap-stable.json`; obrazy QNAP nie sa przebudowywane bez zmiany
  ich deklarowanych wejsc.

## 3. Autoryzacja GitHub

- QNAP pozostaje obserwatorem i nie otrzymuje klucza GitHub App ani bypassu.
- Klucz dedykowanej App znajduje sie w chronionym GitHub Environment. App ma
  minimalne uprawnienia do review, auto-merge i workflow dispatch, bez zapisu
  bezposrednio do chronionych branchy.
- Zaufany workflow z default branch weryfikuje repo, autora, branch, exact head
  SHA, Candidate-ID, dozwolone pliki, checki i atestacje. Dopiero wtedy osobna
  tozsamosc App wystawia approval i wlacza native auto-merge.
- App nie omija rulesetu. PR spoza scislej allowlisty pozostaje reczny.

## 4. Status i powiadomienia Kodi

Publiczny status ma niezalezne osie:

- `pipeline.state`: `in_sync`, `detected`, `qualifying`, `blocked`;
- `release.health`: `healthy`, `incident`, `unknown`;
- `versions`: `upstream`, `stable`, `stable_upstream_base`.

Manifest zawiera schema version, Candidate-ID, upstream SHA, `generated_at`,
`expires_at` i bezpieczny kod bledu. Nie zawiera logow, tokenow ani danych
uzytkownika. Jeden serializowany kompozytor Pages sklada stable, testing i
status, aby niezalezni writerzy nie nadpisywali witryny.

Downstreamowy modul Umbrelli uzywa indeksu Omega, parsera XML, ograniczonych
timeoutow i watku respektujacego `abortRequested`. Respektuje
`general.checkAddonUpdates`, waliduje manifest oraz deduplikuje tlumaczone
powiadomienia. `blocked` i `incident` sa widoczne w Kodi, ale nie czesciej niz
raz na 72 godziny. Status nie steruje instalacja i jego niedostepnosc nie
blokuje dodatku.

## 5. Incydenty i forward rollback

Profile Sync przekazuje wersjonowany, znormalizowany heartbeat dodatku: ID,
wersje, klase urzadzenia, stan startu, kod awarii i czas. Nie przesyla tytulow,
URL-i, magnetow, hashy tresci ani credentiali.

Lokalny blad daje alarm na urzadzeniu. Globalny `incident` wymaga tego samego
kodu i wersji na co najmniej dwoch aktualnych, podpisanych enrollmentach roznych
klas w oknie szesciu godzin. Incydent blokuje zwykle promocje, ale nie kandydata
naprawczego.

Rollback nie publikuje nizszej wersji, ktorej Kodi nie zainstaluje. Ostatnie
znane dobre zrodla sa ponownie skanowane i wydawane jako scisle wyzszy forward
rollback. Rzeczywista baza kodu jest zapisana osobno jako
`upstream_base_version`. Merge forward rollbacku pozostaje reczny.

## 6. Konwergencja, testy i rollout

Profile Sync zapewnia aktywne `repository.mwodevelop`, poprawny origin Umbrelli,
`general.addonupdates=0` i brak testing repo na urzadzeniach stable. Urzadzenie
offline nadrabia aktualizacje po uruchomieniu.

Wymagane testy obejmuja wersjonowanie, status i deduplikacje, awarie transportu,
malware, konflikty patchy, chronione sciezki, izolacje credentiali i sieci,
exact digest, allowliste PR, komponentowy lock, identycznosc ZIP testing/stable,
publiczny indeks, natywna aktualizacje na co najmniej jednym dostepnym
urzadzeniu, drill incydentu i forward rollback oraz koncowy `in_sync` i drugi
idempotentny `no-op`.

Auto-approver najpierw dziala obserwacyjnie. Auto-merge wolno wlaczyc dopiero po
pelnej probie bez zmian i negatywnych testach allowlisty. Dokumentacja musi
jawnie zaznaczac, ze approval App jest kontrola polityki, a nie niezaleznym
ludzkim review.

## 7. Stan realizacji

Zaimplementowano izolowany lock Umbrelli, hermetyczna atestacje, dwa
auto-approvery w trybie obserwacyjnym, pojedynczy writer Pages, publiczny status,
powiadomienia Kodi, trwale raportowanie `blocked` powiazane z Candidate-ID,
forward rollback oraz natywne auto-update Kodi. Przygotowana wersja Umbrelli to
`6.7.81.21`.

Profile Sync `1.0.6` stosuje `general.addonupdates=0` przez JSON-RPC i emituje
minimalny heartbeat zdrowia Umbrelli. Automatyczna korelacja `release.health`
nie jest jeszcze aktywna: wymaga wdrozenia zgodnego magazynu w backendzie i
read-only widoku Control Plane. Do tego czasu wersjonowany manifest zdrowia
pozostaje kontrola reczna i fail-closed.

Dowody testow oraz odtwarzalne polecenia zapisano w
`docs/e2e-results/2026-08-19-umbrella-auto-release.md`.
