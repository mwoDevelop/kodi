# Niezależny review planu katalogu możliwości Kodi

Data: 2026-09-01

Przedmiot: `KODI_RUNTIME_CAPABILITY_CATALOG_PLAN.md`

Reviewer nie edytował repozytorium. Sprawdził plan z aktualnym evaluatorem,
restore Android/Flatpak, build matrix, workflow GitHub oraz implementacją
`CAddonInfo::MeetsVersion` Kodi 21.3. Pierwotny werdykt: `REVISE`.

## P0 — uwagi blokujące

1. **Migracja schematu nie była jedną transakcją.** Wydzielenie katalogu wymaga
   jednego bootstrap merge obejmującego katalog 21.2/21.3, policy schema v2 bez
   `runtimes`, catalog schema, evaluator, report schema, wszystkich konsumentów
   i testy. Stary klucz `runtimes` ma być odrzucany, a rollback wskazuje jeden
   commit całego bootstrapu.
2. **Restore miał sprzeczną kolejność bram.** Rzeczywisty reprobe jest możliwy
   dopiero po destrukcyjnej reinstalacji. Przyjęto dwie fazy: preflight na
   podstawie przypiętego instalatora przed destrukcją oraz obowiązkowy live
   reprobe przed kopiowaniem profilu/dodatków. Mismatch uruchamia recovery albo
   kończy się `RECOVERY_REQUIRED`.
3. **Istniejący wpis mógł zostać nadpisany przez przesunięty tag.** Katalog jest
   append-only. Ten sam klucz wydania z innym tagiem, commitem albo hashami
   źródeł daje `TAG_DRIFT`. Canonical identity opiera się na repo, commicie i
   kanonicznych hashach wybranych plików; SHA archiwum jest tylko dowodem
   transportowym, ponieważ rekompresja może zmienić jego bajty.

## P1 — uwagi istotne

- Build musi sprawdzać iloczyn platform/ABI i wszystkich wspieranych wydań
  21.2/21.3, a nie pojedynczą wersję na profil.
- Dispatch CI odbywa się po unikalnej gałęzi, a następnie sprawdza exact
  `run.headSha`, zgodnie z istniejącym działającym wzorcem. Writer i dispatcher
  mają osobne minimalne uprawnienia, `force-with-lease` i concurrency bez
  anulowania aktywnego przebiegu.
- Generator odkrywa wszystkie bezpośrednie systemowe providery z
  `backwards-compatibility`; nie kopiuje listy ID ze starej polityki i nie może
  po cichu pominąć nowej klasy API. Materializacja `.in` ma pełną allowlistę i
  fixtures 21.2/21.3.
- Parser zależności musi czytać `minversion` oraz `version`. Pusta
  `CAddonVersion` odpowiada `0.0.0`, a comparator pozostaje zgodny z Kodi dla
  epoch, tyldy i rewizji.
- Attestation porównuje wpis upstream z systemowymi `addon.xml` co najmniej na
  BlueStacks, X88 i jednym NUC/Flatpak. Downstream patch nie może automatycznie
  zmienić katalogu.
- Fetch ma allowlistę hostów, timeouty, limity, uwierzytelnienie bez logowania,
  walidację repo/release/draft/prerelease/tag/commit oraz szybki metadata no-op
  przed pobraniem archiwum. Writer ponownie sprawdza hash artefaktu i base SHA.

## P2 — ograniczenie scope

- Symulowany Kodi 22 istnieje wyłącznie jako fixture testowa.
- V1 obsługuje stable-only i nie zastępuje istniejących wpisów. Prerelease jest
  odłożony; może zostać dodany później bez zmiany evaluatorów.
- Pełny rollout dotyczy bootstrap migration. Przyszły `NO_CHANGE` nie powoduje
  rolloutu ani wydania dodatków.

## Werdykt po przyjęciu uwag

Po zastosowaniu powyższych zmian plan zachowuje OCP, rozdziela kod od danych,
ma jednoznaczną granicę recovery i wykonalny model GitHub Actions. Nie pozostał
znany blocker P0 przed implementacją.
