# Rezerwowy punkt końcowy dostawcy MwoScrapers

Data: 2026-07-30

## Wynik

Diagnoza potwierdziła rzeczywistą lukę w czasie wykonywania w MwoScrapers 0.1.6: po
skonfigurowaniu punktu końcowego prywatnego dostawcy, awaria transportu lub protokołu
zwróciła pustą listę źródeł bez sprawdzania publicznego punktu końcowego dostawcy.
Domyślny punkt końcowy w ustawieniach był prawidłowy, ale nie był to powrót do
środowiska wykonawczego.

Kandydat 0.1.7 naprawia lukę we współdzielonym adapterze Stremio:

- skonfigurowany punkt końcowy pozostaje pierwszy;
- publiczny punkt końcowy będący własnością kodu jest unikalnym drugim kandydatem;
- awarie transportu, HTTP, JSON i kontraktu strumieniowego przechodzą na następnego
  kandydata;
- ważna pusta odpowiedź jest wiarygodna i nie jest powielana;
- kondycja dostawcy kończy się niepowodzeniem dopiero po niepowodzeniu każdego kandydata
  na punkt końcowy.

Przekaźnik QNAP pozostawał sprawny przez cały test: jeden sprawny kontener, jedna sieć
Compose i brak woluminów. Jest to nadal bezstanowa optymalizacja metadanych wolna od
poświadczeń. Nie przechodzi przez nią żadna operacja Real-Debrid.

## Inwentarz dostawcy

MwoScrapers zawiera dwa oryginalne adaptery kontraktowe Stremio:

- Torrentio jest domyślnie włączone i zwraca 5 źródeł dla `Sintel` plus 49 dla `Breaking
  Bad S01E01`;
- Comet jest opcjonalny i jego bieżący nieskonfigurowany publiczny punkt końcowy zwrócił
  HTTP 403 na hoście i w każdym testowanym środowisku wykonawczym Kodi.

Dlatego prawidłowe jest pozostawienie wyłączonego Comet. [bieżący projekt
Comet](https://github.com/g0ldyy/comet) oczekuje skonfigurowanej instancji i sam może
integrować usługi debridowania, co nie jest pasywną granicą dostawcy używaną przez
MwoScrapers. Nie można jej włączać tylko po to, aby liczba dostawców wyglądała na
większą.

## Dokładny kandydat

- repozytorium: `mwoDevelop/script.module.mwoscrapers`;
- zatwierdzenie: `47b4135b5b7401059ce805256c13881699f189a3`;
- wersja: `0.1.7`;
- kandydat ZIP SHA-256:
  `f12494ee9fde346fc0f80effdc0030af42fb70ae6ff098f63c3dcc6dd87f7b39`;
- PR: `mwoDevelop/script.module.mwoscrapers#11`.

Minęły lokalne bramy:

- 45 testów MwoScrapers;
- Batalion;
- weryfikacja dodatku;
- dwa atomowe testy kandydatów do wdrożenia;
- deterministyczna kompilacja repozytorium.

GitHub sprawdza w seriach `30577640978`, `30577659268` i `30577659233`, w tym dokładne
skanowanie pod kątem złośliwego oprogramowania, testy i kompilację obrazu
przekaźnikowego.

## Matryca urządzenia

| Urządzenie | Skonfigurowana ścieżka | Skonfigurowane wyniki | Niedostępne zachowanie przekaźnika | Odtwarzanie |
| --- | --- | --- | --- | --- |
| BlueStacks1 | publiczne | 5 / 49 | błąd przekaźnika, sukces publiczny, 5 | film 12,141 s; odcinek 12.146 s |
| Sony TV | Przekaźnik LAN | 5 / 49 | błąd przekaźnika, próba publiczna, ale HTTP 403 | film 12,276 s; odcinek 12,485 s |
| X88 Pro 20 | Przekaźnik LAN | 5 / 49 | błąd przekaźnika, sukces publiczny, 5 | film 12,161 s; odcinek 12.430 s |
| Bedroom TV | niedostępne | nie biegać | nie biegać | nie biegać |

Wszystkie sześć ukończonych przypadków odtwarzania korzystało z Umbrella 6.7.81.18.
Raporty BlueStacks i Sony bezpośrednio zarejestrowały `realdebrid.add_magnet` i `Played
file as resolve`. Pamięć masowa X88 Android odmówiła dostępu powłoki do `umbrella.log`,
więc sonda logiczna w Kodi odczytała ten sam dziennik i potwierdziła oba znaczniki bez
eksportowania linii dziennika, adresów URL, skrótów lub poświadczeń.

Odciski źródłowe pozostały spójne tam, gdzie istniejąca matryca mogła odczytać dziennik
Umbrella:

- `Sintel`: `5a6b52180d6a015e`;
- `Breaking Bad S01E01`: `6f39c1e78d9c75c4`.

## Ograniczenie VPN

Wyjście Sony NordVPN nadal odbiera HTTP 403 z publicznego Torrentio. Wersja 0.1.7 usuwa
zależność oprogramowania od QNAP, zawsze próbując publicznego rozwiązania awaryjnego,
ale nie może zastąpić decyzji upstream o zablokowaniu adresu VPN. Na tej konkretnej
trasie sieciowej pomyślne wyszukiwanie nadal wymaga sprawnego przekaźnika, innego
wyjścia VPN lub wykluczenia wszystkich Kodi z VPN. Android TV NordVPN oferuje dzielone
tunelowanie na poziomie aplikacji, a nie na domenę, więc wykluczenie Kodi spowodowałoby
również przeniesienie ruchu Real-Debrid poza VPN i nie zostało zastosowane.

Rozwiązywanie pozostaje niezależne od QNAP w każdym przypadku: MwoScrapers zwraca
metadane magnesu, następnie Umbrella samodzielnie przesyła wybrany magnes do Real-Debrid
i otrzymuje odtwarzalny adres URL.

## Powtarzalne polecenia

Zbuduj dokładnego kandydata, używając obejścia blokady testing, a następnie zastosuj go
za pomocą:

```bash
.venv/bin/python tools/kodi_addon_candidate_rollout.py \
  path/to/script.module.mwoscrapers-0.1.7.zip \
  --addon-id script.module.mwoscrapers \
  --version 0.1.7 \
  --serial DEVICE
```

Uruchom oczyszczoną macierz skonfigurowanego/publicznego/niedostępnego przekaźnika za
pomocą:

```bash
.venv/bin/python tools/kodi_mwoscrapers_endpoint_probe.py \
  --serial DEVICE
```

Uruchom odtwarzanie filmów i odcinków za pomocą `tests/e2e/sony_kodi_matrix.py`.

## Stan publikacji

Dokładny kandydat jest zainstalowany na BlueStacks1, Sony TV i X88 Pro 20. Publikacja
celowo oczekuje na oczekiwanie, ponieważ ochrona oddziału odrzuciła połączenie
administracyjne bez zatwierdzania recenzji z innego konta z dostępem do zapisu. Nie
zmieniono blokady testing/stable, wersji dodatku do repozytorium ani artefaktu
publicznego. Po prawnym zatwierdzeniu PR 11, to samo zatwierdzenie musi zostać
opublikowane w testing, zweryfikowane bajt po bajcie, ponownie wypuszczone z publicznego
repozytorium, a dopiero potem awansowane do stable.
