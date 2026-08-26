# Niezależny audyt planu zdrowia usług i procesów cyklicznych

Data: 26 sierpnia 2026 r.

Zakres: [`OPERATIONS_HEALTH_REMEDIATION_PLAN.md`](../OPERATIONS_HEALTH_REMEDIATION_PLAN.md)

Reviewer przeprowadził analizę tylko do odczytu względem aktualnych źródeł
`kodi`, `script.module.mwoscrapers`, `service.mwodevelop.profilesync`,
`kodi-profile-sync-server` i `kodi-control-plane`. Nie edytował plików.

## Wynik

Nie wykryto problemów P0. Wszystkie osiem uwag P1 i pięć uwag P2 uznano za
zasadne i zastosowano w planie.

| Priorytet | Ustalenie | Zastosowana korekta |
|---|---|---|
| P1 | Brak zgodności N/N+1 payloadu watchdoga | Zachowano schema 2 i alias `healthy`, dodano consumer-first oraz kryterium usunięcia aliasu |
| P1 | Dwa booleany mieszały liveness, kolekcję i wynik workflow | Wprowadzono liveness, `collection_state`, `monitored_state` i `observer_ready`; błąd API daje `UNKNOWN` |
| P1 | Bezpośredni collector i watchdog tworzyły dwa alerty jednego runu | Dodano korelację po repozytorium, workflow i scheduled run ID oraz listę źródeł dowodu |
| P1 | Sztywne progi nie uwzględniały urządzeń on-demand | Dodano zredagowane expected inventory oraz tryby always-on, on-demand, maintenance i retired |
| P1 | „Najnowsza aktywna generacja” mogła reaktywować starszą tożsamość | Najwyższa generacja pozostaje autorytatywna także po revocation; wiele aktywnych generacji ostrzega |
| P1 | Retry Profile Sync obejmował także błędy terminalne | Rozdzielono retryable/terminal/normal oraz heartbeat success od całego cycle success |
| P1 | Scheduler miał konkurencyjne progi i pojedynczy reason code | Zastąpiono je missed-window policy oraz trzema niezależnymi conditions i listą reason codes |
| P1 | Plan błędnie mówił o dwóch lockach QNAP i pomijał pipeline kandydatów | Wprowadzono approval/re-use, `qnap_candidate.py`, candidate asset i jeden stable lock |
| P2 | Brak deterministycznej agregacji providerów | Dodano tabelę sample → capability → provider → workflow i priorytet reason codes |
| P2 | Identyczny wynik dwóch live probe był nierealistyczny | Determinizm dotyczy fixture; live probe ma spełniać quorum i budżet |
| P2 | Brak jawnego budżetu wielopróbkowej sondy | Dodano globalny/per-provider deadline, limit wywołań i częściowy artifact |
| P2 | API per-device nie gwarantowało widoku GUI | Dodano tabelę urządzeń, browser E2E i kontrolę redakcji DOM/BFF |
| P2 | Dowody i test awarii sieci były zbyt ogólne | Dodano prywatną retencję/tryby plików oraz fault injection bez zmiany VPN/routingu |

## Elementy ocenione pozytywnie

- rozdzielenie obserwatora od obserwowanego stanu;
- zakaz automatycznego wyłączania providera po pojedynczym incydencie;
- redakcja telemetrii oraz brak magnetów, hashy, URL-i i sekretów;
- OCP przez katalog przypadków i opcjonalny wspólny sink;
- brak wielodniowej bramy release;
- immutable artefakty i locki;
- diagnostyka przed re-enrollmentem;
- BlueStacks, następnie X88, potem flota oraz `DEFERRED` dla niedostępnych;
- końcowy rollout `NO_CHANGE`, backup i pełne stare oraz nowe E2E.

## Konkluzja

Po korektach plan jest logicznie spójny i wykonalny. Najważniejszą bramą
implementacyjną jest zachowanie kolejności: tolerancyjny Control Plane, następnie
rozszerzony watchdog, a dopiero później usunięcie aliasów kompatybilności. Drugą
bramą jest expected inventory, bez którego nie można poprawnie interpretować
braku heartbeatów urządzeń uruchamianych na żądanie.
