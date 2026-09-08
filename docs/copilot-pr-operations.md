# Operatorski pilot Copilot PR

Stan z 8.09.2026: działa lokalny pilot review. Nowy kontroler nie jest jeszcze
wdrożony na chronionym `main`; [PR #34](https://github.com/mwoDevelop/script.module.mwoscrapers/pull/34)
zależy od bootstrapu #33. Nie zmieniono wymaganych approvals, stable ani QNAP.

[Plan](COPILOT_PR_AUTOMATION_PLAN.md),
[review](COPILOT_PR_AUTOMATION_PLAN_REVIEW.md) i
[dowody E2E](e2e-results/2026-09-08-copilot-advisory.md).

## Wywołania z hosta

Do czasu scalenia używaj istniejącego worktree implementacji:

```bash
cd /home/mwo/projects/kodi/.kodi-private/worktrees/mwoscrapers-copilot-20260908
python3 tools/copilot_pr_review.py observe --pr 32 \
  --state-db /home/mwo/projects/kodi/.kodi-private/copilot-pr/reviews.sqlite3
```

`observe` czyta API i istniejący rejestr bez zapisu. `request` bez apply jest
próbą bez zmian. Mutujący request wymaga sprawdzenia, że dostępny jest Copilot
w abonamencie, nadwyżki są zatrzymane, approvals nie są liczone i PR nie ma
uzbrojonego auto-merge:

```bash
python3 tools/copilot_pr_review.py request --pr 32 \
  --state-db /home/mwo/projects/kodi/.kodi-private/copilot-pr/reviews.sqlite3 \
  --apply --confirm-included-budget --confirm-approvals-disabled
```

Nie używaj potwierdzeń bez preflight. Skrypt nie kupuje licencji ani nie zmienia
ustawień. Żądania z Actions są blokowane do wdrożenia odpowiedniej zaufanej fazy.
Przykładowy PR #32 po korekcie wersji ma szerszy zakres niż obecny przepis, więc
nowa rewizja zasadnie raportuje MANUAL_REQUIRED, zamiast korzystać ze starej zgody.

Odczyt wyniku asynchronicznego i uzgodnienie lokalnego rejestru:

```bash
python3 tools/copilot_pr_review.py reconcile --pr 32 \
  --state-db /home/mwo/projects/kodi/.kodi-private/copilot-pr/reviews.sqlite3
python3 tools/test_copilot_advisory.py --pr 32 --timeout-seconds 300
```

E2E domyślnie jest tylko do odczytu. Opcjonalne flagi apply/potwierdzenia oraz
state-db pozwalają przetestować najwyżej jeden POST i deduplikację. PASS dotyczy
review, nie merge ani braku uwag do kodu; nowy head wymaga nowej kwalifikacji.

## Statusy i ograniczenia

- REVIEW_PENDING: Copilot pracuje; pusta lista requested_reviewers nie dowodzi
  zakończenia. Adapter sprawdza również timeline i trwałe rezerwacje.
- REVIEWED_ADVISORY: komentarz, nie approval. Uwagi należy ocenić w PR.
- APPROVAL_NOT_QUALIFIED: natywny approval nie został zakwalifikowany do merge.
- MANUAL_REQUIRED / FILE_CHANGE_SCOPE: zmiana poza polityką, nie awaria usługi.
- REQUEST_UNCERTAIN: nie ponawiaj POST ani nie usuwaj rejestru; brak w API
  może być przejściowy. Reconcile nie oznacza niepewnej próby jako niewysłanej.
- REVIEW_LIMIT_REACHED: trzy wysłane/niepewne próby; rebase nie resetuje limitu.
- NOT_SENT: wiadomo, że nie wykonano POST; ponowienie jest bezpieczne.
- LEDGER_NOT_FOUND: użyto niewłaściwej ścieżki istniejącego rejestru.

Rejestr ma katalog 0700 i plik 0600, jest niewersjonowany, bez tokenów/promptów.
Nie ma automatycznej pętli napraw ani nowego crona. Profil agenta jest szablonem
propozycji zmian; nie nadaje uprawnień do merge/deploy. Instrukcje w repo nie są
technicznym zabezpieczeniem i nie zastępują testów/skanerów.

W razie wycofania pilota nie wysyłać kolejnych requestów. Pozostawione reviews
są doradcze; pilot nie uzbraja auto-merge ani nie zmienia rulesetu. Rollback
produkcyjnej fazy approvals będzie osobnym elementem P3 po jej kwalifikacji.
