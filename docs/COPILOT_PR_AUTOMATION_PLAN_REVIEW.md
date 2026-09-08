# Niezależny review planu Copilot PR

8 września 2026. Wykonawca: `agy-yolo`, model `gemini-3.8-flash-high`,
sesja `ae260c9f-88f5-4d58-b5e1-6a428a29f9e5`, wynik SUCCESS.
Przed delegacją minimum puli Gemini wynosiło 0.8384807109832764.
Audyt wyłącznie do odczytu: plan, wcześniejszy odbiór i kod kontrolera PR #33.

| Uwaga | Ocena i decyzja |
|---|---|
| P1: PASS_MANUAL przy jednym maintainerze blokuje późniejsze zmiany polityki | Zasadna. P3 zablokowany do kwalifikacji rzeczywistej ścieżki utrzymania. Nie tworzymy pozornego drugiego review ani nie zakładamy zgody na bypass |
| P1: workflow z kandydata nie może testować sam siebie jako zaufane main | Zasadna. Rozdzielono operatorski pilot API, testy CI kandydata i dopiero późniejsze uruchomienie kontrolera na main |
| P1: nowe poprawki AI nie pasują do ścisłych hashy AST | Zasadna. Poprawiono diagram i odbiór P4: propozycja nowego kodu wymaga ręcznej kwalifikacji |
| P2: brak wybudzenia po review | Częściowo zasadna. Dodano konkretny operatorski reconcile i wymóg kwalifikacji eventu w P3. Nie przyjęto twierdzenia, że wszystkie zdarzenia wszystkich App nie uruchamiają Actions |
| P2: wyścig natywnego auto-merge i walidacji | Zasadna. Końcowy check i uzbrojenie dopiero po rewalidacji; uczciwie opisano brak transakcji klient–GitHub |
| P2: zmiany bazy mogą wyczerpać 3 review | Ryzyko zasadne, proponowany reset limitu odrzucony. Baza nadal zużywa limit; osobny powód i możliwość jawnego zwiększenia przez operatora |
| P2: brak trwałego nośnika rezerwacji przed POST | Zasadna. P1/P2: prywatny SQLite i transakcja; P3: check-runy dedykowanej App. Nie edytujemy review Copilota |
| P3: required check zbyt wcześnie blokuje tryb advisory | Zasadna. P1/P2 nie zmieniają wymaganych checków ani liczonych approvals |
| P3: backup nie jest narzędziowym rollbackiem | Zasadna. Wpisano obowiązek implementacji i testu rollbacku w P3, z zachowaniem review/skanów |

Odrzucono ogólny wniosek „cała integracja z GitHub zablokowana”: preflight
potwierdził już aktywną licencję Copilot Pro, a bezpieczny operatorski request
natywnego review nie wymaga scalenia nowego kontrolera. Nadal zablokowane jest
uruchomienie nowej polityki jako zaufanej automatyzacji main bez bootstrapu.

Plan po korektach: [Copilot PR](COPILOT_PR_AUTOMATION_PLAN.md).

## Review implementacji P1/P2

Drugi audyt, ten sam model: sesja `55d38bbe-8d59-4aed-89fc-7e7d0155014f`,
SUCCESS, minimum puli 0.9320245981216431. Reviewer potwierdził 162 testy w stanie
przed końcowymi korektami. Ostatnia regresja po korektach: 177 PASS.

| Uwaga | Decyzja |
|---|---|
| COMMIT w finally przy błędzie rezerwacji | Dodano jawny rollback i test odblokowania. Nie potwierdzono opisanego maskowania błędu BEGIN: BEGIN już był poza try/finally |
| REQUEST_UNCERTAIN nie ma automatycznej ścieżki do NOT_SENT | Świadomie odrzucono automatyczne kasowanie niepewności na podstawie pustej listy pending. Live test wykazał, że lista bywa pusta podczas pracy Copilota. Potrzebny dowód review lub decyzja operatora |
| Znany NOT_SENT niepotrzebnie zużywa limit i blokuje retry | Poprawiono: bezpieczne ponowienie przed-POST bez nowego kosztu. REQUEST_UNCERTAIN nadal zużywa limit |
| Zależność od zegara hosta, brak review ID w rejestrze | Poprawiono: powiązanie po dokładnym SHA i natywnej tożsamości, zapis ID rozstrzygnięcia. Brak tolerancji zegarowej udającej pewny dowód |
| observe/reconcile raportują WOULD_REQUEST | Poprawiono jawny tryb i spójną akcję, bez sugestii wysyłania z pasywnej obserwacji |
| Odczyt ignorował istniejący state-db | Dodano SQLite mode=ro, test niezmienności pliku i jawny LEDGER_NOT_FOUND dla reconcile |
| Zmiana kontrolera/bazy tworzy nowy slot dla tego samego head | Deduplikacja requestu także po head; pełna tożsamość nadal pozostaje dowodem audytowym |
| Znana blokada polityki robi czerwony job obserwacji | Znane stany blokad są poprawną obserwacją; błędy API/formatu/integralności nadal kończą się błędem |

Dodatkowo test na GitHub ujawnił alias aktora w timeline (`Copilot`) i znikanie
`requested_reviewers` podczas dynamicznego runu. Dodano odczyt timeline, kontrolę
stałego ID bota i regresje. Dane operatorskie oraz klucze nie trafiły do agenta.
