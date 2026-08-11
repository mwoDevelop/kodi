# Niezależny review planu Kodi Operations

Data: 2026-08-11

Przedmiot: `KODI_OPS_PLAN.md`

Zakres review: spójność i logiczność, rzeczywiste workflow repo, granice
release/rollout/restore, rollback, idempotencja, resume, bezpieczeństwo
sekretów, wykonalność E2E i ziarnistość publicznego CLI.

Reviewer nie edytował plików. Werdykt pierwotnej wersji: warunkowo
zaakceptować po usunięciu luk P0 i P1. Trzy publiczne operacje faktycznie
upraszczają interfejs, lecz pierwsza wersja planu ukrywała ręczny approval
stable, przeceniała rollback i nie definiowała dokładnie scoped rollout.

## P0 — uwagi blokujące

### 1. Rzeczywisty proces stable ma ręczny punkt approval

`promote-stable.yml` tworzy PR locka stable i nie scala go. Plan musi mieć
stan `WAITING_APPROVAL`, przypinać PR/snapshot/atestację i pozwalać wznowić
dokładny run dopiero po niezależnym review oraz merge. Orchestrator nie może
sam zatwierdzać ani scalać własnego PR. Zmieniona treść PR lub wygasła
siedmiodniowa atestacja wymagają ponownej certyfikacji.

Decyzja: przyjęto w sekcjach release, modelu stanów, etapie 4, przykładach i
kryteriach release.

### 2. Rollback i atomowość były obiecane zbyt szeroko

Aktualny deploy QNAP nie daje bezwarunkowego rollbacku po zmianie danych, a
rollout urządzenia składa się z wielu niezależnych transakcji. Każdy adapter
musi deklarować transaction boundaries, safe points, capabilities i dostępne
kompensacje. QNAP wymaga backupu aplikacyjnego, zweryfikowanej kopii off-NAS,
poprzedniego Compose/env/digesta i bramy kompatybilności schema. Brak
bezpiecznej kompensacji daje `RECOVERY_REQUIRED`.

Decyzja: przyjęto; usunięto obietnicę globalnej i per-device atomowości.

### 3. Restore wymaga mocniejszej bramy destrukcyjnej

W v1 restore powinien przyjmować jeden cel i jawny tryb `repair|reinstall`.
Uninstall istniejącej instalacji jest fail-closed bez zweryfikowanego backupu,
ponownej identyfikacji urządzenia i target binding snapshotu. `--yes`
autoryzuje tylko wyświetlony content-addressed plan. `restore --all` nie
powinien istnieć. Flatpak restore jest nowym zakresem, nie funkcją obecnego
Androidowego `kodi_reinstall.py`.

Decyzja: przyjęto wraz z feasibility gate dla Flatpak.

## P1 — uwagi istotne

1. Run przypina stable lock, snapshot i SHA-256; zmiana między falami daje
   `DRIFTED`, bez przełączania wersji w locie.
2. Lokalny lock nie wystarcza. Plan wykorzystuje GitHub concurrency/exact SHA,
   QNAP generation/CAS i operation ID urządzeń.
3. `rollout --device` jest scoped: QNAP read-only, brak ukrytych canary i brak
   nowych selektorów podczas resume.
4. QNAP build jest wybierany przez content hash inputów, a deploy przez różnicę
   zatwierdzonego i uruchomionego digesta. Sam commit repo nie wystarcza.
5. Sekrety wymagają allowlistowego raportu, praw `0700/0600`, atomowych zapisów,
   odmowy symlinków, bezpiecznego przekazywania i testów sentinel-secret.
6. Deterministyczne bramy są oddzielone od ponawianej diagnostyki zewnętrznego
   providera, VPN, resolvera i playbacku.
7. Wyniki etapów są oddzielone od stanów runu. Dodano `WAITING_APPROVAL`,
   `DRIFTED`, `RECOVERY_REQUIRED`, `SKIPPED` i mapowanie kodów wyjścia.
8. Wyjątek dla watchdoga wymaga ograniczonego czasowo waivera dla dokładnego
   workflow; brak świeżego statusu nie podlega waiverowi.
9. Dry-run wykonuje wyłącznie plan i read-only probes w run-private; nie
   uruchamia mutujących workflow ani testów zapisujących kanoniczne `.e2e/`.

Decyzja: wszystkie przyjęto.

## P2 — dopracowanie

- przykłady konsekwentnie używają `.venv/bin/python`;
- kontrakt adaptera jest capability-based zamiast wymagać rollbacku wszędzie;
- czyste worktree jest precondition, a nie obietnicą cleanupu całego świata;
- szacunek rozdziela pracę implementacyjną od oczekiwania na urządzenia,
  review, atestację i CI.

Decyzja: przyjęto.

## Dokumentacja przykładów rollout

Plan wymaga osobnej strony `docs/kodi-operations.md` i przykładów:

- pełny `rollout --dry-run`;
- pełny rollout z QNAP i canary;
- scoped rollout jednego i wielu urządzeń;
- resume dokładnego runu;
- release zatrzymujący się na approval;
- restore jednego celu;
- kody wyjścia, raport, drift stable i niedostępny cel.

Każdy przykład opisuje zakres mutacji, canary, oczekiwane wyniki i lokalizację
raportu. Uzupełnienie zostało dodane bezpośrednio do planu jako wymaganie etapu
dokumentacyjnego i wzorzec treści przyszłej strony operacyjnej.

## Ocena po poprawkach

Plan jest spójny jako projekt mniej ziarnistego interfejsu. Zachowuje review i
content-addressed release, nie utożsamia wielu transakcji z atomowością,
rozdziela build od deployu QNAP, precyzuje full/scoped rollout oraz nie ukrywa
nowego zakresu Flatpak restore. Może przejść do akceptacji decyzji z sekcji 11
planu przed implementacją.

## Re-review po pierwszej korekcie

Druga runda porównała poprawiony plan ponownie z bieżącymi workflow i znalazła
jedną lukę P0 oraz trzy doprecyzowania P1.

### P0 — odnawialna certyfikacja nie może nadpisywać dowodu

Obecny `certify-testing.yml` operuje pojedynczym
`device-attestation.json`. Samo sprawdzanie ważności nie wystarcza, ponieważ
ponowna certyfikacja tego samego snapshotu po wygaśnięciu nie może bezpiecznie
nadpisać dowodu używanego przez istniejący promotion lock. Plan wymaga teraz
immutable `device-attestation-<attestation_id>.json`; lock promocji zapisuje
dokładne attestation ID i SHA-256, a Etap 4 obejmuje migrację obu workflow.

Decyzja: przyjęto wraz z testem wygaśnięcia, ponownej certyfikacji i promocji
wyłącznie dokładnie wskazanego assetu.

### P1 — autoryzacja QNAP, diagnostyka i tryb repair

1. Prywatny `.kodi-private/qnap-images.json` nie może autoryzować produkcyjnego
   deployu. Dodano wersjonowany `manifests/locks/qnap-stable.json`, zmieniany
   przez PR i exact-head CI, zawierający input hash, security report, digest i
   approval record.
2. Po wyczerpaniu retry zewnętrzna awaria daje `DIAGNOSTIC_FAILED`, run
   `PARTIAL` i kod 2. Zatrzymuje dalsze fale, gdy dotyczy canary, ale nie
   uruchamia nieuzasadnionego rollbacku. Dowiedziona regresja lokalna pozostaje
   `ERROR`/`FAILED` i może uruchomić bezpieczną kompensację adaptera.
3. `repair` nie reinstaluje binariów Kodi. Uninstall i instalacja należą
   wyłącznie do `reinstall`; oba tryby korzystają później ze wspólnego
   uzgodnienia dodatków, ustawień i E2E.

Decyzja: wszystkie przyjęto w kontraktach, etapach, testach, kryteriach i
przykładach kodów wyjścia.

## Ocena po drugiej korekcie

Po obu rundach plan nie ma znanej luki blokującej rozpoczęcie implementacji.
Zachowuje ręczny approval, wiąże release i QNAP z niezmiennymi artefaktami,
nie obiecuje nieosiągalnej atomowości, rozdziela deterministyczne bramy od
zewnętrznej diagnostyki i ogranicza destrukcyjny restore do jednego celu.
Przykłady rollout są obowiązkowym, testowalnym elementem dokumentacji, a nie
dodatkiem odkładanym po implementacji.

## Końcowa weryfikacja

Trzecia kontrola nie znalazła P0. Wskazała jedną pozostałą lukę P1: plan
zmieniał `qnap-stable.json` przez PR, ale nie wiązał go jednoznacznie z jednym
punktem `WAITING_APPROVAL`. Przyjęto jeden PR promocji, który atomowo obejmuje
publiczny lock stable oraz zmienione locki QNAP. Wznowienie wymaga merge i
exact-head CI całego zestawu; dopiero wtedy może rozpocząć się rollout.

Doprecyzowano również, że heartbeat jest mutacją telemetryczną, ale nie zmianą
zarządzanej konfiguracji ani deploymentu, dlatego nie odbiera wyniku
`NO_CHANGE`. Przykłady full i scoped rollout opisują teraz jawnie wynik
`DIAGNOSTIC_FAILED`, stan `PARTIAL`, kod 2 oraz zatrzymanie fal po błędzie
diagnostycznym canary.

## Werdykt końcowy

Po zastosowaniu uwag z trzech rund niezależnego review nie pozostała znana
luka P0 ani P1. Plan jest logicznie spójny, ma jednoznaczne granice mutacji,
approval i resume oraz zawiera wymagany plan dokumentacji z przykładami
wywołań rollout.
