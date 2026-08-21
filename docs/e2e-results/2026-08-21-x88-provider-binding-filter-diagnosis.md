# X88: binding mwoScrapers i filtr nazw źródeł

## Zakres

Kontrolowany test na X88 Pro 20 rozdzielił stan sieci providerów, konto
Real-Debrid, konfigurację Umbrella i zależności od QNAP. Raporty surowe pozostały
w ignorowanym `.kodi-private/tmp/`; nie zawierają tokenów, URL-i magnet ani nazw
plików źródeł.

## Wynik diagnozy

- konto Real-Debrid jest premium; konto i `torrents/activeCount` zwracają HTTP
  200, a wyłączony przez RD `instantAvailability` jest prawidłowo klasyfikowany
  jako `disabled_endpoint`;
- Comet, Torz, MediaFusion, EZTV i PirateBay zwróciły poprawne wyniki. Torrentio
  za aktywnym VPN zwraca HTTP 403 dla wszystkich trzech profili nagłówków, ale
  nie jest jedynym źródłem i nie blokuje pozostałych providerów;
- po starcie pozostawało `provider.external.enabled=true`, lecz nazwa i moduł
  providera były puste. Ponowne związanie z `script.module.mwoscrapers`
  przywróciło pobieranie źródeł;
- z 60 surowych wyników dla Big Buck Bunny usunięto 30 duplikatów, po czym
  `realdebrid.filter.filename=true` odrzucił pozostałe typowymi oznaczeniami
  wydania. Nie był to błąd VPN ani autoryzacji RD;
- stare sekcje MySQL w `advancedsettings.xml` wskazywały niedostępną bazę QNAP.
  Usunięto tylko te sekcje; lokalne bazy Kodi zostały otwarte prawidłowo.

## Zabezpieczenia regresji

Polityka Profile Sync zarządza kompletnym bindingiem mwoScrapers, a wspólny
profil wyłącza nadmiernie szeroki filtr nazw. Stable rollout usuwa stare bindingi
baz QNAP i jawnie wycofane dodatki wraz z osieroconym `addon_data`. Sonda RD
sprawdza teraz również pomocniczy endpoint aktywnych torrentów, bez ujawniania
identyfikatorów ani tokenu.
