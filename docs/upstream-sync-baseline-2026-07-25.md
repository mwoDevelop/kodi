# Stan bazowy implementacji synchronizacji upstream

Schwytano: 25.07.2026

## Repozytoria

| Repozytorium | Oddział | Zobowiąż się |
|---|---|---|
| `mwoDevelop/kodi` | `main` | `8ec6410b901cb3c76043cc13b24b7463488ec70d` |
| `mwoDevelop/umbrellaplug.github.io` | `main` | `6fd1037b23590b99bd16c78fd204b17a96585c76` |
| `mwoDevelop/script.module.mwoscrapers` | `main` | `7c21ad6a634cc2eeb67fdc84747098aa4b97b030` |
| `mwoDevelop/ch.repo` | `master` | `da4350eb79d032730ca240c3b824e4f3fd2ca09d` |

Repozytorium root było czyste, z wyjątkiem nowo przygotowanego `UPSTREAM_SYNC_PLAN.md` i
jego niezależnej recenzji.

W momencie przechwytywania nie włączono żadnej ochrony gałęzi ani zestawu reguł
repozytorium w żadnym z czterech repozytoriów.

## Locki kanałów

stable i testing wskazywały na te same zatwierdzenia i bajty komponentu:

| Dodatek | Wersja | ZIP SHA-256 |
|---|---:|---|
| `plugin.video.umbrella` | `6.7.81.9` | `30da8ebe9b83d24c0c3e28708d94c4e95426de4bc254da236eaedb6e78b4b7dd` |
| `plugin.video.watchnixtoons2.mwodevelop` | `0.25.2` | `41666b66945565b6a8660028df0701240463437a078fe9e3e1f90668260d560d` |
| `script.module.mwoscrapers` | `0.1.3` | `afad0ba6bc0f0c51dd58765c5040247a90c2aebe87cebccd6d3a99f4b4efb6ab` |
| `script.mwoscrapers` | `0.1.1` | `f2610ec43aa41e1ff39fdd39c7e495c385fff16529957e834325e432ff678695` |

Indeksy publiczne:

- testing `addons.xml` SHA-256:
  `83fe0d9189ce854969c7682a7ba454348a6d0b1448e0c9f16a741351c79c0262`;
- stable `addons.xml` SHA-256:
  `7f0081dfa1f77cd30915417db2dbddac7b450c744aa8cb113d39536fc5cc6bd7`;
- pobrano publiczny plik `artifact-manifest.sha256` SHA-256:
  `2e5049c96a192bfb3041e99087b046c21ee72ec8338442a72a3241dc14d7b7df`.

Najnowszy test repozytorium głównego i publikacja testing dla
`8ec6410b901cb3c76043cc13b24b7463488ec70d` zakończyły się pomyślnie.

## BlueStacks1

- ADB: `/home/mwo/android-sdk/platform-tools/adb`
- Numer seryjny: `127.0.0.1:5556`
- Model: `SM-S901E`
- Kodi: `21.3`
- Proces Kodi był uruchomiony.

Zainstalowane dodatki mwoDevelop:

| Dodatek | Wersja | Kodi `installed.origin` |
|---|---:|---|
| `repository.mwodevelop` | `1.0.0` | `repository.mwodevelop` |
| `plugin.video.umbrella` | `6.7.81.9` | `repository.mwodevelop` |
| `plugin.video.watchnixtoons2.mwodevelop` | `0.25.2` | `repository.mwodevelop` |
| `script.module.mwoscrapers` | `0.1.3` | `repository.mwodevelop` |
| `script.mwoscrapers` | `0.1.1` | `repository.mwodevelop` |

`repository.mwodevelop.testing` nie został zainstalowany.

Jest to punkt odzyskiwania i porównania dla poimplementacyjnego BlueStacks E2E.
