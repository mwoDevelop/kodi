# Przywrócenie zdrowia usług i procesów cyklicznych — 2026-08-26

## Zakres

Wydanie obejmuje wielopróbkowy audyt providerów MwoScrapers, rozdzielenie
gotowości watchdoga od zdrowia obserwowanych workflow, per-device inventory w
Control Plane, tolerancję opóźnień harmonogramu GitHub oraz ograniczony retry
Profile Sync. Dodatkowo naprawiono walidację prywatnej konfiguracji YouTube schema
2 podczas rolloutu Kodi Flatpak.

## Wydane wersje i wdrożenia

- `script.module.mwoscrapers` 0.2.1, commit `357c1e6`;
- `service.mwodevelop.profilesync` 1.1.2, commit `a266d12`;
- `kodi-control-plane` 0.7.0, commit `a7a9e59`;
- stabilna rewizja repo Kodi `44fb6d2`;
- release Kodi `6a795bb4a85640a8bdc9441b38a3a2f7` zakończony sukcesem;
- QNAP wdrożony z immutable stable lock; wszystkie siedem usług raportuje
  `running/healthy`, a watchdog `observer_ready=true`,
  `collection_state=READY`, `monitored_state=HEALTHY`.

## Dowody automatyczne

- pełny zestaw głównego repo: `640 passed`;
- testy adaptera Flatpak po poprawce schema 2: `33 passed`;
- ręczny provider probe
  [`32963871652`](https://github.com/mwoDevelop/script.module.mwoscrapers/actions/runs/32963871652):
  `success`;
- scheduled approval Umbrella
  [`32972824544`](https://github.com/mwoDevelop/kodi/actions/runs/32972824544):
  `success`;
- publikacja Pages
  [`32971492235`](https://github.com/mwoDevelop/kodi/actions/runs/32971492235):
  `success`;
- stable deploy
  [`32971467261`](https://github.com/mwoDevelop/kodi/actions/runs/32971467261):
  `success`;
- read-only Control Plane E2E: `PASS`, 13 zadań cyklicznych, mTLS bez klienta i
  mutacje poprawnie odrzucone;
- render dashboardu przez Chrome CDP: `PASS`.

## Rollout urządzeń

Orkiestrator `tools/kodi_ops.py` zakończył scoped rollout
`b5f173a074e84e0b9d4bcb46620cc5ec` ze statusem `COMPLETE`:

- BlueStacks1: stable, providery, Real-Debrid, Rapideo, OpenSubtitles.com i
  YouTube — pass; stan przenośny `CONVERGED`;
- Sony TV: stable, providery, Real-Debrid, Rapideo, OpenSubtitles.com i YouTube —
  pass; stan przenośny `CONVERGED`;
- `nuc-mwo`: Kodi Flatpak 21.3, Profile Sync 1.1.2, YouTube schema 2
  `ACCOUNT_READY`, OpenSubtitles.com — pass; powtórzenie `NO_CHANGE`;
- `nuc-alek`: analogiczny rollout zakończony sukcesem; osobne powtórzenie dało
  `sync_status=NO_CHANGE`.

OpenSubtitles.org nadal zwraca `VIP_REQUIRED`; jest to stan konta/usługi, a nie
regresja dodatku. OpenSubtitles.com pozostaje działającą usługą domyślną.

## Odroczenia

- Bedroom TV pominięto po jawnej decyzji operatora; nie wykonywano po niej
  dalszych operacji na urządzeniu.
- X88 oznaczono `DEFERRED`, ponieważ host był osiągalny, ale port ADB odrzucał
  połączenia. Nie przypisano mu pozornego sukcesu i nie zmieniano enrollmentu.
