# Copilot PR — odbiór operatorskiego pilota P1/P2

8 września 2026. Wynik: **PASS dla pilota; PARTIAL dla całego planu**.

Implementacja [PR #34](https://github.com/mwoDevelop/script.module.mwoscrapers/pull/34),
commit `e9ead353bb53d5bd1f3fcaa994f638af562723fb`, bazuje na oczekującym #33.
[Plan](../COPILOT_PR_AUTOMATION_PLAN.md) i
[niezależny review](../COPILOT_PR_AUTOMATION_PLAN_REVIEW.md).

## Potwierdzone próby

| Próba | Wynik |
|---|---|
| Preflight CDP | Aktywny Copilot Pro, początkowo 0/1500 kredytów; płatne nadwyżki AI $0/stop usage; approvals w repo wyłączone |
| Lokalna pełna regresja pilota | 177 PASS; ruff PASS; importy jawnie z lib bieżącego worktree |
| Lokalna pełna regresja głównego repo Kodi | 828 PASS w 130,62 s; jedno oczekiwane ostrzeżenie testu celowo zdublowanej ścieżki ZIP |
| Dokumentacja i konfigurator GitHub | 9 PASS |
| Stan PR #32 przed requestem | Dokładny head 028d6d695922f61237022b7549990cbbab27d736 i base 357c1e6df7d8414768a69ba8108fe84b44ef5804, test/malware-scan SUCCESS, auto-merge nieuzbrojony |
| Pierwszy operatorski request | REQUESTED, jedna trwała rezerwacja, bez approval/merge |
| Natywny Copilot | Run 34250532103 SUCCESS, review 5144331082 COMMENTED dla tego head |
| Asynchroniczna obserwacja | Początkowo wykryto błąd pustego requested_reviewers; poprawiono przez timeline i rejestr, dodano regresje |
| Powtórzenia live E2E | PASS, post_count=0, stale ten sam review, attempts=1, merge_authorized=false |
| Scope negatywny #33 | BLOCKED/FILE_CHANGE_SCOPE; brak requestu i merge |
| Weryfikacja uwag Copilota | Zasadna niespójność runtime 0.2.1 / pakiet 0.2.2 poprawiona w #32; druga uwaga dotyczy tylko redundantnego warunku sentinela — logiki providera nie zmieniano |
| Regresja korekty wersji #32 | 84 PASS; ruff i validate_addon PASS |

[Natywny run Copilot](https://github.com/mwoDevelop/script.module.mwoscrapers/actions/runs/34250532103)
wykonał analizę w około cztery minuty. Odczyt licznika kredytów może być opóźniony;
nie interpretowano nieodświeżonego salda jako bezpłatności review.

Odtwarzalny test to `tools/test_copilot_advisory.py` w worktree pilota. Po korekcie
wersji head #32 zmienił się na `386261b` i poprzednie review nie jest dowodem
nowej rewizji. Polityka blokuje poszerzony zakres plików zamiast go automatycznie
zaakceptować. Nie zmieniono przypiętych przepisów AST pod wpływem opinii AI.

## Granice i pozostałe wdrożenie

- CI nowych commitów uruchomiono; końcowy wynik jest odnotowywany poniżej.
- Kod opublikowany w gałęziach/PR, ale bootstrap #31/#33/#34 nadal wymaga
  niezależnego review lub osobnej decyzji właściciela o konkretnej procedurze.
- Nie ma nowego checka App, liczonego approval Copilota, automatycznego merge,
  automatu napraw ani nowego widoku PR w Kodi Admin. Tych faz nie kwalifikowano.
- Nie zmieniono obrazów usług ani stable; deploy QNAP i rollout urządzeń nie
  były potrzebne dla samego pilota. Kandydat dodatku nadal wymaga osobnego
  release i testów BlueStacks/X88 po zakończeniu kwalifikacji/review.
- Żadne sekrety, pliki SQLite ani zastane zmiany QTS Gateway nie są częścią PR.

## Uwaga o środowisku testowym

Pierwsza próba regresji #32 użyła współdzielonego virtualenv z editable importem
starszego drzewa, co dało cztery błędy, w tym nowy test wersji. Ponowiono przez
`PYTHONPATH=lib:. .../python -m pytest -q`, uzyskując 84 PASS na faktycznym kodzie
kandydata. Nie wyłączono testów ani nie uznano wcześniejszego uruchomienia za PASS.

## CI i transport artefaktów

- #32, nowy head `386261b53eb8e3d0a0b9dc8bdd3f4edf2feb8978`: runy test
  34251933717 (push) i 34251936763 (PR) oraz build 34251936765 — SUCCESS.
- #34, head `e9ead353bb53d5bd1f3fcaa994f638af562723fb`: push test
  34251931339 — SUCCESS, w tym malware-scan i test.
- Pierwsze przebiegi PR 34252010991 i build 34252010946: skany wykonano, ale
  upload-artifact zakończył się `FinalizeArtifact 403 Forbidden`. Zapis raportu
  jest obowiązkową częścią dowodu, więc nie pominięto błędu i nie oznaczono tego
  przebiegu jako PASS. Uruchomiono po jednym ponowieniu nieudanych jobów.
