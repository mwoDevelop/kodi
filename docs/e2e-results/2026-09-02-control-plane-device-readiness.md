# Control Plane 0.12 — gotowość klienta i aktywnego assignmentu

Data kwalifikacji: 2026-09-02.

## Wynik

Control Plane 0.12 został wydany jako niezmienny obraz, promowany w stable locku
i wdrożony na QNAP. Wszystkie siedem procesów kontenerowych jest uruchomionych i
zdrowych. Panel zachowuje dotychczasowy monitoring harmonogramów, a dodatkowo
pokazuje dla każdego urządzenia:

- zgodność wersji klienta z deklarowanym minimum;
- obecność wymaganych capabilities;
- wynik aktywnego assignmentu dla bieżącej generacji enrollmentu;
- zbiorczy stan konfiguracji niezależny od heartbeat i łączności.

Pierwsze wymuszone odświeżenie produkcyjne pokazało jeden rzeczywisty alert
`FLEET_CAPABILITY_PENDING`. BlueStacks, X88 i Sony TV raportują klienta 1.5.0,
capability `skin-shortcuts-menu-v1` i assignment `APPLIED`. Bedroom TV oraz oba
profile NUC nadal raportują klienta 1.4.2 bez tego capability i assignment
`PENDING`. To oczekiwany, prawdziwy drift po odroczonym wdrożeniu, a nie błąd
panelu ani transportu: wszystkie sześć zapisanych heartbeatów było świeżych.

## Release i wdrożenie

- komponent `mwoDevelop/kodi-control-plane`: commit
  `2aa0a412982ecd660e3dfdada88023ad762fe2be`, wersja 0.12.0;
- build, skan i approval obrazu: GitHub Actions `33676970203`;
- obraz stable:
  `ghcr.io/mwodevelop/kodi-control-plane@sha256:75983d45ae680cb73755fbd6bf219b418ceaddc9cc51fcb4a16f8587dbbdc5e5`;
- kandydat QNAP:
  `06a53436949e473bd645b3c362eb2be5c937456555c6800cc0db9859d54cf558`;
- automatyczny deploy stable: GitHub Actions `33677837440`, sukces;
- ręczny reconcile przez `tools/qnap_images.py`: `DEPLOYED`;
- `control-plane`, `control-plane-authz` i `control-plane-web` używają tego
  samego digestu i mają health `healthy`; pozostałe cztery usługi QNAP również
  są zdrowe.

## Testy

- `kodi-control-plane`: 77 testów jednostkowych;
- główne repozytorium: 742 testy;
- testy narzędzi inventory/QNAP/watchdog: 66 testów;
- `tests/e2e/control_plane_readonly.py`: `PASS`, mTLS bez certyfikatu odrzucone,
  API mutujące odrzucone, 14 procesów i Profile Sync database schema 8;
- `tests/e2e/control_plane_dashboard_cdp.py`: `PASS`, render `3/4` capabilities,
  `3/4` assignmentów i ręczne odświeżenie bez błędu;
- produkcyjny HTML i JavaScript zawierają nowe karty oraz kolumny
  `Capabilities` i `Assignment`;
- workflow CI PR-ów komponentu i repozytorium głównego zakończyły się sukcesem.

Pełny rollout `71adb6f665544588ae7e9c7a20cf8a9f` zakończył się `PARTIAL`: BlueStacks,
X88 i Sony TV przeszły bez zmian z zielonymi próbami providerów i Real-Debrid,
a końcowe `tests/e2e/run.sh` zakończyło się `PASS`. Bedroom TV, `nuc-mwo` oraz
`nuc-alek` były niedostępne i zostały sklasyfikowane jako `DEFERRED`. Pierwsza
próba BlueStacks trafiła na przejściowy błąd kopiowania adaptera
OpenSubtitles.com przez ADB; bezpośrednia próba potwierdziła 25 wyników, a
wznowienie tego samego planu zakończyło urządzenie wynikiem `NO_CHANGE`.

## Oczekiwane domknięcie

Po uruchomieniu trzech odroczonych klientów należy wznowić rollout. Panel ma
wtedy samoczynnie przejść z `FLEET_CAPABILITY_PENDING` do stanu bez alertu, gdy
każdy heartbeat pokaże klienta co najmniej 1.5.0 i raport aktywnego assignmentu
zmieni się na `APPLIED`.
