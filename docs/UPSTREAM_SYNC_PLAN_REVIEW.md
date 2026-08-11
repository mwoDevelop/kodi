# Niezależna recenzja planu synchronizacji upstream

Data review: 2026-07-25

Przedmiot: `UPSTREAM_SYNC_PLAN.md`

Tryb: niezależny reviewer, bez prawa edycji plików

## 1. Zakres recenzji

Reviewer sprawdził plan względem:

- aktualnych workflow repo nadrzędnego i komponentów;
- faktycznej historii Git oraz branchy upstream/downstream;
- istniejących locków, submodułów i procesu publikacji Kodi;
- `PLAN.md`, `umbrella/downstream-patches.yml` oraz provenance providerów;
- ograniczeń GitHub Actions i modelu GitHub App;
- OCP, idempotencji, wersjonowania, rollbacku i wykonalności E2E.

Nie znaleziono błędu klasy critical. Znaleziono dziesięć luk high i dziewięć
uwag medium. Wszystkie poniższe uwagi zostały uznane za zasadne i włączone do
planu; żadna nie została odrzucona wyłącznie jako kosmetyczna.

## 2. Ustalenia high i decyzje

| ID | Ustalenie | Decyzja |
|---|---|---|
| H1 | `repository_dispatch` między repo nie miał wykonalnego modelu tokenu. | MVP używa wyłącznie centralnego crona i `workflow_dispatch`; klucz App pozostaje tylko w `kodi`. |
| H2 | Ochrona `main` koliduje z bezpośrednim pushem obecnego `promote-stable.yml`. | Ochrona `kodi/main` jest włączana dopiero po migracji promocji do modelu zgodnego z rulesetem. |
| H3 | Lock-only PR nie był lokalnie odtwarzalny przy starych gitlinkach submodułów. | Lock jest release source of truth; test lokalny zawsze materializuje exact lock do izolowanego katalogu. |
| H4 | Idempotencja pomijała downstream base, wersję adaptera i odrzucone kandydaty. | Wprowadzono kanoniczny `candidate_id` oraz disposition kandydata. |
| H5 | Pojedynczy enum wyniku nie opisywał jednoczesnego driftu provenance i dostępności Magneto. | Wynik ma niezależne osie content/provenance/availability/history oraz osobne statusy prepare/validation. |
| H6 | Plan mylił obserwowane Coco/Viper/Magneto z zaakceptowanym kodem Torrentio/Comet. | Rozdzielono observed state, accepted import state i release state; import wymaga licencji i kwalifikacji. |
| H7 | Plan dublował `downstream-patches.yml` i kolidował z patch-stackiem z `PLAN.md`. | Umbrella zachowuje jeden rozszerzony manifest patchy; mechaniczne pola `addon.xml` obsługuje transformacja, funkcjonalne zmiany replay patch stacku. |
| H8 | Polityka wersji nie określała zachowania per komponent ani semantyki Kodi. | Dodano konkretne strategie wersji i testy zgodne z porządkiem wersji Kodi. |
| H9 | Stable promuje cały snapshot, lecz plan certyfikował komponenty osobno. | Kandydat testing ma niezmienny snapshot ID i atestację całego delta stable→testing; certyfikacja jest serializowana. |
| H10 | Etapy uruchamiały writer przed App, a skrócona kolejność mówiła odwrotnie. | Ustalono jedną kolejność: baseline → read-only → App/writer/rules compatibility → cutover adapterów → testing reconcile. |

## 3. Ustalenia medium i decyzje

| ID | Ustalenie | Decyzja |
|---|---|---|
| M1 | Cron GitHub nie powstaje dynamicznie z manifestu. | MVP ma jeden statyczny dzienny cron dla wszystkich tanich discovery. |
| M2 | Nie było formatu granicy discovery → writer. | Dodano kanoniczny candidate manifest z SHA plików i content-addressed bundle. |
| M3 | Mirror Umbrelli wymagał dwóch baz rewrite i prawa do workflow. | W MVP mirror jest lokalnym refem; serwerowy mirror nie jest aktualizowany przez App. |
| M4 | Atomowość modułu i wrappera nie miała deklaracji w manifeście. | Dodano release groups z oddzielnymi wersjami i digestami artefaktów. |
| M5 | Rollback Pages nie miał magazynu ani retencji. | Dodano adresowalne snapshoty, retencję i ręczny redeploy snapshotu. |
| M6 | Bramy MVP i rozwiązania docelowego były pomieszane. | Rozdzielono kryteria MVP od rozszerzeń Rapideo/cache. |
| M7 | „Wszystkie zmiany trafiają do PR” przeczyło quarantine/issue. | PR dotyczy tylko zmiany proponowanej do akceptacji; anomalie nie mutują branchy. |
| M8 | „Identyczny raport” przeczył volatile timestampom. | Kanoniczny raport nie zawiera czasu/run URL; job summary może je zawierać. |
| M9 | Brakowało polityki aktualizacji otwartego PR przy nowym upstream. | Nowszy kandydat superseduje stary, zmienia `candidate_id` i unieważnia approvals. |

## 4. Dodatkowe luki potwierdzone podczas lokalnej weryfikacji

Lokalna weryfikacja repo potwierdziła ponadto:

- żadne z czterech repo nie ma obecnie branch protection ani rulesetu;
- `publish-testing.yml` uruchamia publikację po każdym pushu do `main`, nawet
  gdy wynikowy snapshot jest bajtowo identyczny;
- provider lock jest parsowany regexem zależnym od kolejności pól YAML;
- BlueStacks E2E nie może być zwykłym jobem GitHub-hosted i powinien być bramą
  przed stable albo kontrolowanym jobem na dedykowanym runnerze;
- stały branch bota wymaga `force-with-lease`, kontroli autora i ochrony przed
  nadpisaniem ręcznie zmodyfikowanego brancha;
- discovery musi rozróżniać deterministyczne `404/410` od przejściowych
  timeoutów i odpowiedzi `5xx`.

Te punkty również zostały dodane do planu.

## 5. Elementy zachowane bez osłabienia

- brak automatycznej promocji do stable;
- brak sekretów w CI kandydata;
- zakaz `pull_request_target` dla kodu kandydata;
- centralny manifest i adaptery zgodne z OCP;
- dokładne commity, SHA-256 i deterministyczne buildy;
- osobny adapter vendoringu WatchNixtoons2;
- zatrzymanie na rewrite, konflikcie, zmianie workflow i braku licencji;
- forward-revert zamiast podmiany opublikowanego ZIP-a;
- dry-run, rzeczywisty PR, publiczny smoke i BlueStacks E2E jako kolejne bramy.

## 6. Wynik recenzji

Plan po korektach jest logicznie wykonalny pod warunkiem zachowania kolejności
wdrożenia. Nie wolno włączać writera ani rulesetów przed:

1. ukończeniem read-only dry-run;
2. przebudową mechanizmu promocji stable;
3. materializowaniem locków niezależnie od gitlinków;
4. skonfigurowaniem GitHub App i kontroli branchy botowych.

Największym ryzykiem pozostaje certyfikowanie ruchomego kanału testing.
Pierwsze wdrożenie musi zatem serializować kandydatów i certyfikować cały,
adresowalny snapshot, a nie pojedynczy dodatek w oderwaniu od pozostałych.

## 7. Ponowna recenzja po pierwszej korekcie

Reviewer ponownie sprawdził zaktualizowany plan. Potwierdził zamknięcie
H1–H10 oraz M1–M9, po czym znalazł dwie nowe luki high i trzy medium:

| ID | Ustalenie follow-up | Zastosowana korekta |
|---|---|---|
| H11 | Rekonstrukcja Umbrelli od czystego upstreamu replayowałaby commity `.github/workflows`, których App bez `Workflows` nie może pushować. | Rekonstrukcja pozostaje lokalna i bez tokenu; finalny zdalny commit ma parent aktualnego `main`, chronione pliki identyczne z base, a repository-policy patche są wyłączone z replay. |
| H12 | Upload Release asset wymaga `contents: write`, co nie może trafić do joba wykonującego testy komponentu. | Rozdzielono `build-and-test`, `snapshot-writer` i `pages-deploy` na joby o rozłącznych tokenach. |
| M10 | Ręcznie zamykane issue nie może być autorytatywną blokadą certyfikacji. | Stan maszyny przechowuje GitHub Deployment; issue jest tylko widokiem. |
| M11 | Atestacja E2E nie miała miejsca zapisu ani modelu zaufania. | Dodano JSON Schema, digest, Actions artifact z joba bez zapisu i oddzielny chroniony writer atestacji do snapshot asset. |
| M12 | Testing i stable mają różne ścieżki/indeksy, więc „bez rebuilda” było nieprecyzyjne. | Snapshot zawiera channel-neutral ZIP-y i przygotowany `promotion/stable` payload; promocja publikuje ten payload, nie przebudowując ZIP-ów. |

Po zastosowaniu korekt App synchronizacyjna nie potrzebuje uprawnienia
`Workflows`, kod komponentów nigdy nie jest wykonywany z tokenem zapisu, a
promocja jest powiązana z maszynowym stanem i zaufaną atestacją całego
snapshotu.

Finalny follow-up review potwierdził zamknięcie H11, H12 oraz M10–M12.
Końcowy verdict niezależnego reviewera: **coherent**, bez pozostawionej
sprzeczności high ani medium w kontrolowanych obszarach.
