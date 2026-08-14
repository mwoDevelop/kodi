# QNAP Control Plane — faza 2 i release stable (2026-08-14)

## Zakres

- `kodi-control-plane` 0.2.0: `convergence_bundle_v1`, przygotowanie
  `PREPARING -> READY`, exact-artifact evidence, CAS desired-state head i
  kompatybilny restore schematu 1;
- `kodi-profile-sync-server` 0.5.0: ścisłe kontrakty podpisanego release intent,
  delegowanego assignmentu i raportu konwergencji urządzenia;
- certyfikacja i publikacja jednego niezmiennego snapshotu Kodi oraz odpowiadających
  mu obrazów QNAP.

## Odtwarzalna weryfikacja

```bash
tests/e2e/run.sh
.venv/bin/python tools/qnap_images.py status
.venv/bin/python tools/smoke_public.py
```

Wyniki:

- lokalny i końcowy E2E: 507/507 przed poprawką raportowania oraz 509/509 po
  dodaniu regresji `DEFERRED`/`DIAGNOSTIC_FAILED`;
- dwa niezależne CI dla poprawki: 509/509;
- snapshot: `8928681246dca2d76eed7b3483f6e5d9c0bb760f847d923c94d9a9156ef225ce`;
- attestacja urządzeń: `268785a5b32b8250644dfe34028aa285a863dc70abe1429b32ab16c785066fcc`;
- QNAP candidate: `8b2992293a15ea8d6aa7e6e511d0c0a688aeaefa5ba858234754fde5051bfa22`;
- workflow certyfikacji urządzeń `31758860815`: BlueStacks i X88 — sukces;
- workflow deploy stable `31759364395`: sukces, 56 publicznych plików;
- QNAP: `control-plane`, `profile-sync`, `provider-relay` i
  `upstream-watchdog` — `healthy`; watchdog: 6 workflow, 0 awarii.

## Rollout floty

BlueStacks, X88 i Sony TV osiągnęły stable oraz `CONVERGED`; provider,
Real-Debrid, Rapideo i OpenSubtitles.com przeszły diagnostykę. Drugi przebieg
BlueStacks i X88 zakończył się `NO_CHANGE`. Bedroom TV oraz profile NUC były
niedostępne i otrzymały `DEFERRED`, dlatego raport całej floty pozostał
`PARTIAL` bez lokalnej regresji.

Orkiestrator został poprawiony tak, aby `release:rollout` zachowywał tę przyczynę:
same cele `DEFERRED` nie są już błędnie nazywane `DIAGNOSTIC_FAILED`.
