# 9.09.2026 — mwoScrapers stable i pasywna obserwacja PR

Status: **W TRAKCIE**. Godziny workflow są w UTC (wieczór 8.09 odpowiada
nocy 9.09 w Polsce). Nie jest to deklaracja ukończenia P3/P4 Copilota.

## Release dodatków

- PR Kodi #350 aktualizuje lock mwoScrapers do 0.2.2 i referencję wrappera
  0.1.1 (niezmienione bajty wrappera). SHA ZIP-a:
  `774c51eec678d3304a8cd75cada0674042776a607c7b35d4e6b2dd786e145597`.
- CI exact-head `34284044739` PASS. Pierwotny run PR `34265240931` wymagał
  zgody na wykonanie workflow; zatwierdzono **uruchomienie testów**, nie bypass
  review. Po jego SUCCESS normalny merge #350 utworzył
  `a0853c74275a51aaaf99445e2da31ed7a442c4ab`.
- Osobny czysty checkout `kodi-release-20260909`, branch main. Niezwiązane
  lokalne zmiany QTS Gateway w pierwotnym checkout nie są objęte wydaniem.
- `kodi_ops.py release --dry-run` PASS. Rzeczywista operacja
  `941e86f246634f1c950c9e4048d55239`: pełna regresja **834 PASS**, dwa buildy
  deterministyczne. Raporty w prywatnym katalogu checkoutu wydania.
- Testing `34284683107` SUCCESS; snapshot
  `58162edc2ee03660c1f27fe2d39aa45747901c3014c3b46e3d51cde69daa6a25`.
  Pages `34285341670` SUCCESS. Następne fazy release pozostają w toku.
- Snapshot obejmuje wcześniejsze testing Umbrella 6.7.86.3 i Profile Sync
  1.5.1. Ich wspólna kwalifikacja urządzeń jest wymagana przed promocją.

## Copilot i niezależny review

- Live readback: jeden collaborator `mwoDevelop`, jeden wymagany approval,
  `MWOSCRAPERS_COPILOT_MODE=observe`, brak aktywnej flagi policy-bot approvals.
- Review planu agy-yolo `gemini-3.8-flash-high`: SUCCESS, sesja
  `2003dafc-2314-42f1-9372-54c8148a3d73`, minimum puli 0.9264124631881714.
  P3 nie wolno włączyć bez kwalifikowanej ścieżki maintenance. App i rollback
  to zadania implementacyjne, nie zastępują tej decyzji.
- P5a przygotowano w Control Plane **0.12.4**, PR **#28**. Tylko GET; bez
  importu kodu kandydata, żądań AI, approval, merge i odczytu lokalnego rejestru.
- Review kodu: ten sam model, SUCCESS, sesja
  `1f2b5b84-acf1-4d9f-95fb-b518d337ed18`, minimum puli 0.9241979122161865.
  Poprawiono zachowanie formalnego werdyktu po komentarzu, pomijanie autora,
  kadencję bez cronów i wspólny próg świeżości. Wyłączenie źródła ukrywa stary
  cache jako `disabled`.
- Zaostrzenie walidacji ujawniło podwójne ID w fixture: pierwszy CI #28
  `34285886150` failure. Fixture poprawiono bez osłabienia walidacji.
  Ponowne testy: **115 PASS**, składnia JS i diff whitespace PASS.
- Read-only live GET odczytał PR mwoScrapers #29. Osobny GET wewnątrz
  kontenera QNAP z istniejącym tokenem: **HTTP 200**, dokument listowy.
  Nie zmieniano ani nie ujawniano tokenów.
- Chrome CDP fixture: render karty, refresh i błąd API z zachowaniem starych
  wierszy oraz widocznym ostrzeżeniem — **PASS**.

Odtworzenie testu UI z checkoutem Control Plane 0.12.4:

```bash
.venv/bin/python tests/e2e/control_plane_dashboard_cdp.py \
  --control-plane-source /home/mwo/projects/kodi-control-plane \
  --expect-pr-observer
```

## Odbiór końcowy — do uzupełnienia

- [ ] Certyfikacja snapshotu na BlueStacks i X88.
- [ ] Promocja stable, publiczny smoke i pełny rollout.
- [ ] CI/merge CP #28, kwalifikowany obraz, deploy katalogu/obrazu i no-op.
- [ ] Odczyt produkcyjnego API i GUI, zgodność źródeł, jawne blokady.
- [ ] Commit/push dokumentacji, katalogu i testu E2E bez zmian Gateway/sekretów.

P3 (natywne approvals/required App check) i P4 (zlecenia napraw z limitem tur)
nie są ukończone. P5a nie oznacza pełnej obserwacji kontrolera ani jego kosztów.
