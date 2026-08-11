# Niezależna recenzja planu pełnego wydania synchronizacji upstream

Data: 2026-07-29

Przedmiot: `UPSTREAM_SYNC_PLAN.md`

Tryb: niezależny reviewer read-only oraz dwa osobne tory kontrolne:

- GitHub Actions, tokeny, workflow dispatch i rulesety;
- bezpieczeństwo, release, snapshoty, atestacja i rollback.

Reviewerzy nie edytowali plików. Kontrolny zestaw
`tests/upstream_sync` i `tests/test_snapshot_bundle.py` zakończył się wynikiem
`30 passed`.

## 1. Werdykt

Werdykt przed korektami: **coherent-with-fixes**.

Kierunek architektury był prawidłowy, ale plan przeceniał gotowość stable,
mieszał różne typy akcji PR i nie opisywał wystarczająco granic zaufania
atestacji urządzeniowej. Wszystkie ustalenia critical/high oraz wykonalne
medium poniżej zostały zaakceptowane i zastosowane w planie.

## 2. Ustalenia blokujące i decyzje

| ID | Severity | Ustalenie | Decyzja zastosowana w planie |
|---|---|---|---|
| FR1 | critical | Generyczne `open_or_update_pr` miesza PR komponentu, provenance i testing lock; nowe bajty providera również mogły dostać PR. | Dodano typowane akcje z właścicielem, profile policy adapterów, osobny release-lock reconciler i per-provider wyniki. |
| FR2 | critical | Stable nie promuje immutable snapshotu: `promote-stable.yml` pobiera Pages, a `deploy-stable.yml` przebudowuje repo. | Dodano osobny pakiet snapshot schema 2, stable lock schema 2, promocję po `snapshot_id` i composer Pages bez builda komponentów. |
| FR3 | high | `resources/upstream-observations.lock.json` trafia do ZIP-a przez `resources/**`, więc provenance-only zmienia bajty. | Observation state zostaje przeniesiony do `.upstream/`, wyłączony z paczki i objęty testem niezmienności ZIP SHA. |
| FR4 | high | `atomic_commit:true` nie zgadza się z różnymi pinami modułu i wrappera (`6c4b795...` i `7c21ad6...`). | Dodano bootstrap do wspólnego osiągalnego commita bez bumpa wersji i bez zmiany ZIP-ów. |
| FR5 | high | Kolejka `certifying` była zwalniana dopiero przez stable promotion lub reject. | Rozdzielono `published_testing → certifying → certified/rejected` od niezależnego `stable_promoted`; kolejkę zwalnia certyfikacja albo odrzucenie. |
| FR6 | high | Plan wymaga review, ale wszystkie cztery rulesety mają zero wymaganych approvals. | V1 wymaga jednego approval dla kodu, testing locka i stable; auto-merge wyłączono z zakresu v1. |
| FR7 | high | Root, Umbrella i mwoScrapers nie mają `workflow_dispatch` w test workflowach, a PR utworzony tokenem nie może polegać na kaskadowym triggerze. | Dispatch testu jest prerequisite writera; `ensure-required-check` sprawdza exact PR head SHA także przy retry. |
| FR8 | high | Watch writer ufał głównie trailerowi `Candidate-ID` i dispatchował test tylko po pushu. | Dodano osobny pakiet hardeningu: exact tree/base/autor/trailery, re-read target, disposition i naprawę brakującego PR/checka. |
| FR9 | high | Granica writerów nadal zawierała pozostałość GitHub App i kod z root `kodi`. | Writer v1 uruchamia zaufany kod z base SHA własnego repo i używa repo-local `GITHUB_TOKEN`; App nie uczestniczy w v1. |
| FR10 | high | Digest JSON atestacji nie dowodził pochodzenia i nie chronił przed replay. | Wybrano chroniony self-hosted runner z nonce, snapshot/head/test SHA, tożsamością urządzenia/runnera, TTL i oddzielnym weryfikatorem. |

## 3. Ustalenia medium i decyzje

| ID | Ustalenie | Decyzja zastosowana w planie |
|---|---|---|
| FR11 | Nazwy `git_fork`, branch Watch i bazowe wersje były nieaktualne. | Ujednolicono `git_patch_stack`, rzeczywiste branche oraz baseline Umbrella `6.7.81.18` i Watch `0.26.1`. |
| FR12 | Redeploy starszego Pages nie cofa już zainstalowanych dodatków Kodi. | Nazwano go containmentem i zawsze połączono z forward-revert o wyższej wersji. |
| FR13 | Cron nie może wykryć własnego niewykonania przez 36 godzin. | Wymagany jest zewnętrzny watchdog, preferencyjnie kontener QNAP odpytujący GitHub API. |
| FR14 | Oczekiwanie naturalnej zmiany każdego upstreamu może blokować release. | Obowiązkowy jest staging drill z kontrolowanym źródłem; naturalna zmiana produkcyjna staje się post-release canary. |
| FR15 | `pip install pytest` bez wersji/hasha osłabia odtwarzalność release. | Release workflow używa wersjonowanego dependency locka z hashami. |
| FR16 | Automatyczne mapowanie `~alpha/~beta` nie ma jednoznacznej polityki. | V1 wykrywa prerelease, ale kieruje je do quarantine i ręcznej decyzji. |
| FR17 | Jeden globalny managed issue nie realizuje issue per komponent/klasa ani recovery. | Pakiet obserwowalności wprowadza klucz `(component, problem_class)`, deduplikację i zamknięcie po recovery. |
| FR18 | Status rulesetów był nieaktualny. | Plan odnotowuje aktywne rulesety wszystkich czterech default branchy oraz brak approval jako lukę do utwardzenia. |

## 4. Sugestie odroczone poza v1

Poniższe propozycje są wartościowe, lecz nie blokują poprawnego release v1:

- GitHub artifact attestations i SBOM dla snapshotów oraz ZIP-ów;
- platformowa immutability Releases albo druga kopia CAS;
- obraz buildowy przypięty digestem zamiast `ubuntu-latest`;
- automerge provenance-only/testing-lock po osobnym review, burn-in i
  path-scoped rulesetach.

Plan zachowuje allowlistę pól i secret scan raportów urządzeniowych już w v1,
ponieważ surowe logi Kodi mogą zawierać tokeny lub wrażliwe URL-e.

## 5. Wynik po zastosowaniu korekt

Po zastosowaniu FR1–FR18 plan rozdziela:

- source discovery od release-lock reconcile;
- kod, provenance-only, quarantine i testing-lock;
- certyfikację od promocji stable;
- containment Pages od forward-revert klientów;
- read-only prepare/test od repo-local writerów;
- staging drill od nieprzewidywalnej naturalnej zmiany upstream.

Końcowy werdykt dokumentu po korektach: **coherent** jako plan pełnego release
v1. Werdykt nie oznacza ukończenia implementacji; bramy Definition of Done
muszą zostać potwierdzone dowodami podczas realizacji.
