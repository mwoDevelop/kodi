# Naprawa statusów operacyjnych — 8 września 2026

## Zweryfikowany stan początkowy

- QNAP: siedem kontenerów `running/healthy`, osiem źródeł Control Plane `OK`.
- Trzy workflow mwoScrapers: rzeczywisty błąd publikacji artefaktów, nie providerów.
  Przebiegi 34106189104, 34107195645 i 34109740675 przeszły właściwe testy,
  lecz upload został odrzucony przez limit magazynu GitHub Actions.
  Nowsze próby są odrzucane przed startem przez budżet Actions.
- Watchdog pomija nieudane ręczne próby przy wyborze skutecznej remediacji.
  Błędnie używa wieku starego przebiegu także do cooldownu, więc wysyła
  następne próby co około 90 sekund zamiast co najmniej 15 minut.
- Pięć urządzeń ma `ACTIVE_ASSIGNMENT_MISSING`; należy porównać to z backendem,
  stanem kanału i podpisanymi przypisaniami, zanim zmieni się konfigurację.
- `DELAYED` procesów dziennych oznacza rzeczywisty brak dzisiejszego crona,
  nie błąd wyświetlania. `STALE` urządzenia nie dowodzi awarii sieci.

## Kolejność realizacji

1. Naprawić cooldown watchdoga: uwzględniać także nieudane/anulowane próby,
   niezależnie od skutecznego przebiegu używanego do oceny zdrowia. Zachować
   alarm i nie uznawać odrzuconego/aktywnego ponowienia za sukces. Dodać regresje.
2. Sprawdzić zużycie artefaktów i dostępne bezkosztowe działania. Nie zwiększać
   budżetów, nie zmieniać prywatności repozytoriów ani nie usuwać dowodów
   release bez osobnej decyzji. Jeżeli blokada rozliczeniowa pozostanie,
   jawnie oznaczyć ją jako zależność zewnętrzną zamiast ukrywać alarm.
3. Wykonać backup backendu i sprawdzić podpisy/generacje przypisań. Uzupełniać
   wyłącznie brakujące przypisania już zatwierdzonej aktywnej rewizji istniejącym
   skryptem bootstrap. Nie promować przy okazji nieprzetestowanego kandydata.
   Potwierdzona przyczyna: `publish_candidate` usuwał wszystkie przypisania
   kanału. Poprawka backendu 0.10.1 ogranicza usuwanie do `candidate`;
   regresja sprawdza zachowanie active i wycofanie zastąpionego candidate.
4. Uruchomić regresje oraz E2E watchdoga i panelu, zbudować niezmienny obraz
   standardowym skryptem i wdrożyć tylko zmienioną usługę. Pozostawić cudze,
   niezwiązane zmiany bramy QTS bez zmian.
5. Odświeżyć Control Plane i porównać statusy z GitHub/QNAP. Udokumentować
   wyniki `PASS`, `PARTIAL` i zewnętrzne blokady; nie ogłaszać pełnego sukcesu,
   jeśli GitHub nadal odrzuca zadania albo urządzenia nie potwierdziły stanu.

## Kryteria odbioru

- Nieudany dispatch nie może generować następnej próby przed cooldownem.
- Po wdrożeniu watchdog nadal publikuje kompletny i świeży katalog 12 procesów.
- Panel pokazuje aktualne obserwacje i zachowuje prawdziwe alarmy.
- Każda zmiana przypisania ma backup, poprawny podpis i odczyt zwrotny;
  samo przypisanie nie jest dowodem jego zastosowania na wyłączonym Kodi.
