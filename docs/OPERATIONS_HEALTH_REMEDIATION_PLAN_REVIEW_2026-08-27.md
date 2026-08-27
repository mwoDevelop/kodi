# Niezależny audyt korekt planu zdrowia operacyjnego

Data: 27 sierpnia 2026 r.

Zakres: sekcje 13-21
[`OPERATIONS_HEALTH_REMEDIATION_PLAN.md`](../OPERATIONS_HEALTH_REMEDIATION_PLAN.md),
dodane po live audycie Kodi Control Plane na QNAP.

Reviewer przeprowadził analizę tylko do odczytu względem aktualnych źródeł
`kodi`, `kodi-control-plane` i `kodi-profile-sync-server`. Nie edytował plików.

## Wynik

Nie wykryto problemów P0. Dziesięć uwag P1 i cztery uwagi P2 uznano za zasadne i
zastosowano w planie. Wcześniejsze decyzje dotyczące zgodności N/N+1 watchdoga,
expected inventory, trybów urządzeń, klasyfikacji Profile Sync, polityki missed
windows oraz standardowego pipeline QNAP zostały ocenione jako spójne.

## Zastosowane uwagi P1

| Ustalenie | Korekta planu |
|---|---|
| `ONLINE/OFFLINE` nie ma niezależnego źródła i miesza obserwację z `monitoring_mode` | Zachowano policy jako osobną oś; reachability jest opcjonalna, wymaga provenance/TTL i bez collectora pozostaje `UNKNOWN`. Świeży heartbeat nie jest już nazywany online. |
| Nie określono persistence dla „atomowości per job” | Wybrano failure isolation per job i per observation, merge z poprzednim `jobs[]` oraz jeden atomowy zapis istniejącego snapshotu. Bez migracji SQLite. |
| Reader i writer GitHub schedules są w tym samym obrazie | Dodano release A z tolerant readerem i writerem wyłączonym flagą, następnie zreviewowane włączenie writera w release/config B. Top-level pozostaje addytywnym schema 1. |
| Jeden `observation_state` miesza scheduled i manual | Dodano oddzielne stany, czasy sukcesu/próby i błędy dla scheduled oraz remediation. Timeout manualny nie unieważnia świeżego scheduled runu. |
| Brama „jeden timeout daje PARTIAL” przeczy retry | Udany retry daje `READY` i licznik retry; `PARTIAL` powstaje dopiero po wyczerpaniu wszystkich prób danej obserwacji. |
| `expected_window` zmieniał fingerprint przy każdym cron | Alerty pozostają stateless; klucz bazuje na repo, workflow i rodzinie warunku, a okna/run ID są dowodami. Usunięto obietnicę nieistniejącego lifecycle incydentów. |
| Watchdog nie publikuje expected window | Control Plane wyprowadza outage windows z autorytatywnego schedule catalogu, `checked_at` i timestampów runu. Watchdog nie duplikuje cronów. |
| Revocation jest bezwarunkowy i podatny na wyścig | Rozszerzono scope backendu o content-addressed plan/apply z CAS, transakcją, audytem i prywatnym użyciem enrollment ID. Dodano build/promocję/deploy obrazu Profile Sync. |
| Brakowało jawnej macierzy severity | Zaplanowano wersjonowany katalog condition/reason → severity/overall/condition family, w tym critical dla `missed_windows_failure` niezależnie od legacy `OVERDUE`. |
| Starsza sekcja mówiła o „najwyższej aktywnej generacji” | Ujednolicono regułę: autorytatywna jest najwyższa generacja niezależnie od revocation; starszy heartbeat jej nie maskuje. |

## Zastosowane uwagi P2

| Ustalenie | Korekta planu |
|---|---|
| Secondary rate limit mógł utrzymywać równoległe żądania | Po secondary rate limit collector nie uruchamia nowych żądań i respektuje `Retry-After` wyłącznie do globalnego deadline. |
| Fault injection mógł dotknąć produkcyjny collector | Test ma działać w izolowanym candidate containerze albo testowym proxy na osobnej sieci Compose QNAP. |
| Sekcje bazowe i korekcyjne dublowały release | Sekcję 19.2 oznaczono jako deltę po zrealizowanym etapie bazowym 10.2. |
| Opis certyfikatu sugerował brak zależności od TLS QTS | Doprecyzowano, że gateway dziedziczy certyfikat QTS; nie wymaga CA Control Plane w przeglądarce, ale wygasły certyfikat QTS nadal wymaga osobnej rotacji. |

## Ważne decyzje zachowane

- Brak automatycznego revocation bez dry-run, CAS i ręcznego zatwierdzenia hasha
  planu.
- Brak automatycznego masowego dispatchu brakujących workflow.
- Błąd transportu collectora nie zmienia wyniku workflow na `FAILED`.
- Watchdog i collector są dwoma źródłami jednego bieżącego incydentu, nie dwoma
  niezależnymi alertami.
- Nowa tabela incydentów i trwały lifecycle `OPEN/RESOLVED/REOPEN` pozostają poza
  tym zakresem. Dashboard prezentuje deterministyczny bieżący widok.
- Rollout dodatków Kodi nie jest wymagany dla zmiany samego Control Plane. Profile
  Sync jest wydawany tylko dlatego, że bezpieczne plan/apply revocation wymaga
  zmiany backendu.

## Konkluzja

Po korektach plan jest spójny z aktualnym modelem danych i pipeline QNAP. Dwie
najważniejsze bramy implementacyjne to:

1. release A musi potwierdzić tolerant reader przy nadal wyłączonym nowym writerze;
2. żadne starsze enrollmenty nie mogą zostać odwołane bez atomowego CAS
   potwierdzającego niezmieniony aktywny zbiór i świeżą najwyższą generację.
