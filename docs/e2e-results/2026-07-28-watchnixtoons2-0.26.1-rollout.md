# Wdrożenie WatchNixtoons2 0.26.1

Data: 28.07.2026

## Artefakt i publikacja

- zatwierdzenie wideł: `83560a2a5ccf7ab56724183959688a42b63b9615`;
- Wersja upstream: `0.26` i `6b3183f56aef4e90ba1f0eb067c88ad2bc69e593`;
- Wersja downstream: `0.26.1`;
- deterministyczny/publiczny ZIP SHA-256:
  `01a84245391da1beef7bc65982b4d47dd517595c533296473b65763e6a1e2312`;
- Publikacja testing: <https://github.com/mwoDevelop/kodi/actions/runs/30373242032>;
- artefakt publiczny:
  <https://mwodevelop.github.io/kodi/testing/omega/plugin.video.watchnixtoons2.mwodevelop/plugin.video.watchnixtoons2.mwodevelop-0.26.1.zip>.

Pobrano publiczny plik ZIP i przed każdym wdrożeniem sprawdzano jego streszczenie. Kodi
przeprowadzał każdą aktualizację poprzez swój graficzny interfejs użytkownika `Install
from zip file`. Kodi pozostawia puste pole `installed.origin` dla tej ścieżki; źródło
jest potwierdzane poprzez publiczny adres URL i pasujący skrót, a nie przez twierdzenie
o pochodzeniu menedżera repozytorium.

## Matryca urządzenia

Wszystkie trzy urządzenia rozwiązały tę samą ścieżkę treści,
`mao-episode-17-english-subbed`, wybrały źródło `480 (SD)` i zgłosiły ten sam łączny
czas trwania wynoszący 25:19.

| Urządzenie | Kodi | Dodatek | Rozwiąż | Dowody odtwarzania |
|---|---:|---:|---:|---|
| BlueStacks1 (`127.0.0.1:5715`) | 21,3 | 0.26.1 | 2,009 s | strumień wejściowy, demux, dekoder AAC, progresja 12 s |
| Sony TV (`192.168.1.12:5555`) | 21,3 | 0.26.1 | 5,056 s | strumień wejściowy, demux, dekoder AAC, progresja 12 s |
| Bedroom TV (`192.168.1.18:5555`) | 21,3 | 0.26.1 | 2,021 s | strumień wejściowy, demux, dekoder AAC, progresja 12 s |

Oczyszczone raporty do odczytu maszynowego:

- [BlueStacks1](2026-07-28-bluestacks1-watchnixtoons2-0.26.1.json)
- [Sony TV](2026-07-28-sony-watchnixtoons2-0.26.1.json)
- [Bedroom TV](2026-07-28-bedroom-tv-watchnixtoons2-0.26.1.json)

## Wdrożenie profilu Bedroom TV

To samo urządzenie otrzymało również Profile Sync `0.1.6` od
`repository.mwodevelop.testing`. Dodatek E2E sparował urządzenie z tymczasowym lokalnym
backendem, wykonał uwierzytelniony puls, zweryfikował podpisanego kandydata i
potwierdził, że kandydat nie ma zastosowania w trybie tylko do odczytu. Zainstalowanym
źródłem w bazie danych dodatku Kodi był `repository.mwodevelop.testing`.

Oczyszczony raport do odczytu maszynowego: [Bedroom TV Profile
Sync](2026-07-28-bedroom-tv-profile-sync-0.1.6.json).

## Dowód cyklicznej aktualizacji

Pierwszy cykl zdalny przygotował merytorycznie zaadresowanego kandydata na stanowisko
tylko do odczytu, zweryfikował go na stanowisku piszącego i otworzył recenzowane PR
<https://github.com/mwoDevelop/ch.repo/pull/5>. Cykl po połączeniu początkowo wykazał,
że nowa kasa nie zawierała zaakceptowanego, niezmiennego obiektu upstream. PR
<https://github.com/mwoDevelop/ch.repo/pull/7> naprawił to, pobierając dokładnie
zaakceptowane zatwierdzenie, gdy jest nieobecne.

Ostatni drugi cykl zakończył się pomyślnie i pominął przygotowanie kandydatów,
przesłanie artefaktów i tworzenie PR, co okazało się prawdziwym niepowodzeniem:
<https://github.com/mwoDevelop/ch.repo/actions/runs/30374992303>.

`mwonuc` był nieosiągalny w momencie `192.168.1.25` podczas tego wdrożenia (`No route to
host`), więc nie podjęto próby mutacji NUC. Jego dwa klucze SSH specyficzne dla konta
pozostają zainstalowane i przeszły wcześniej testy odrzucania dla wielu kont.
