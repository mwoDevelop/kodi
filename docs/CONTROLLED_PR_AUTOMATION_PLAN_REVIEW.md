# Niezależny review kontrolowanej akceptacji PR

8 września 2026; agy-yolo `gemini-3.8-flash-high`, sesja
`49e66111-6f9e-40ec-91c6-5518eb646ce9`; zadanie wyłącznie do odczytu, SUCCESS.

| Priorytet | Uwaga reviewera | Decyzja |
|---|---|---|
| P0 | Jeden kolaborator będący autorem nie może zaakceptować swojego PR; bootstrap bez bypassu lub drugiego reviewera jest zablokowany | Potwierdzono. Wyraźne pytanie do właściciela o jednorazowy bypass dwóch PR; bez zgody brak merge |
| P0 | Brak konkretnego wyzwalacza bez nowego częstego crona | `workflow_run` po `test` + ręczny dispatch; auto-merge włączany osobnym skryptem |
| P0 | #32 ma nieaktualną bazę po scaleniu #31/automatu | Update branch, nowe CI i kwalifikacja head/base; nie używać starych wyników |
| P1 | Sama nazwa checka i skipped nie dowodzą sukcesu | GitHub Actions, właściwy workflow/run/head, wymagane success i pełna paginacja |
| P1 | Zbyt ogólne dozwolone pliki runtime | V1 tylko PirateBay, konkretna metoda AST, zachowane istniejące testy, identyczne metadane poza patch version |
| P1 | Oczekiwania tygodniowe muszą zmienić się przed kolejnym dziennym oknem | Przygotować obraz przed #31; cutover w tej samej sesji i gotowy rollback |
| P2 | Merge PR nie jest release dodatku | Rozdzielono bramę PR/health od ZIP, kwalifikacji BlueStacks/X88 i promocji Kodi |

Reviewer proponował wykorzystanie istniejącego owner bypassu jako najkrótszy
bootstrap. Jest to wykonalna opcja, lecz sam review techniczny nie stanowi zgody
użytkownika na jej wykonanie. Reguła jednego approval pozostaje w rulesecie.

Wdrożenie musi przejść negatywne testy workflow edits, skipped/failure, podszycia
checków, zmienionego head/base, nieznanych plików i autora, niespójnych wersji
oraz dry-run bez mutacji. Przy teście pozytywnym wymagane osobno: approval bota,
merge bez bypassu, health `main`, readback panelu oraz idempotentne ponowienie.

Plan po korektach: [kontrolowana akceptacja PR](CONTROLLED_PR_AUTOMATION_PLAN.md).

## Review implementacji i zastosowane korekty

Drugi niezależny audyt: sesja `c6d3ca3a-35a8-4eb3-81e9-e1077fa3b81e`,
`gemini-3.8-flash-high`, SUCCESS; minimum puli przed delegacją 0.9541776180267334.

| Uwaga | Rozstrzygnięcie |
|---|---|
| P0: nazwy dozwolonych wywołań można przesłonić; ciało/dekoratory testów były dowolne | Zastąpiono heurystykę parami hashy pełnych AST przejrzanej poprawki i testów. Dodano negatywne testy eval/rebinding/importów/dekoratorów/defaults/dynamicznych URL/encoding |
| P1: `allow_auto_merge=false` | Wdrożono konfigurację skryptem z backupem 0600; readback APPLIED, drugie wywołanie NO_CHANGE. Pozostaje jeden approval, dodatkowo wymagany malware-scan |
| P1: asynchroniczne merge i concurrency per PR | Globalna serializacja, 120 s obserwacji, rozbrojenie oczekującego auto-merge i ponowna kwalifikacja po timeout/zmianie bazy |
| P1: nieosiągalny reconcile po merge | Osobna ścieżka ręcznego dispatchu już scalonego PR, bez kolejnego review/publikacji |
| P1: MAIN_ADVANCED nie jest awarią merge | Jawny POST_MERGE_PENDING; nie przypisuje nowego runu do starego SHA |
| P1: niepewny dispatch blokuje ponowienie | Dodano jawny operatorski retry-uncertain. Odrzucono odwrócenie markera i POST: grozi zdublowaniem wywołań przy utracie odpowiedzi sieciowej |
| P1: bezwarunkowe sudo i brak diagnostyki | sudo dotyczy wyłącznie hosted GitHub (namespaces/AppArmor); lokalnie nie jest potrzebne. Dodano ograniczony log błędu jako JSON, nie surowe komendy Actions |
| P2: różne runy checków, mutowalny checkout | Wymagany ten sam run test/malware-scan; checkout SHA oraz odczyt aktualnego main i czystości validatora |

Zakres celowo nie automatyzuje akceptacji nowej, dowolnej implementacji providera.
To bezpieczna automatyzacja kwalifikacji i scalenia wcześniej przejrzanego przepisu
oraz zmian provenance, nie zastąpienie niezależnego review kontrolą nazw plików.

### Ponowny review po uszczelnieniu AST

Sesja `a4cbfbf2-f689-4026-94f8-de82d65ba067`, SUCCESS, ten sam model;
minimum puli 0.9096102714538574. Reviewer potwierdził zgodność hashy z kodem #32,
izolację oraz 121 testów PASS. Znalazł trzy uwagi P1 dotyczące cyklu życia review:

- Wyłączenie auto-merge nie cofało pozostawionego approval — dodano dismissal
  wyłącznie własnego review bota, dla dokładnego commitu i znacznika decyzji.
- Błąd przed rozpoczęciem pętli omijał cleanup — rozszerzono try/finally także
  na publikację review i komendę merge; utrata odpowiedzi POST też jest obsłużona.
- Merge między odczytami mógł dać fałszywy STALE_BASE/STALE_HEAD — usunięto
  podwójny GET w pętli i po cleanup ponownie rozpoznaje się faktyczny merge,
  wykonując jego followup. Dodano testy wyścigu i poszanowania ludzkich reviews.
