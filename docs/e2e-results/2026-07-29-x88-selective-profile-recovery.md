# Selektywne odzyskiwanie profilu X88

Data: 29.07.2026

## Zdarzenie i główna przyczyna

Usunięcie `repository.mwodevelop.testing` do Kodi spowodowało również usunięcie
zarządzanych dodatków i `addon_data`, mimo że ich zainstalowane źródło zostało już
przypisane do `repository.mwodevelop`. Przywrócono dokładne pakiety dodatków stable, ale
Umbrella mógł przeszukiwać metadane bez rozwiązywania problemu z odtwarzaniem.

Zredagowana sonda ustawień w Kodi ustaliła, że:

- Real-Debrid został włączony, ale nie było żadnych wartości autoryzacyjnych;
- dostawca zewnętrzny został wyłączony i nie jest już wybrany;
- pamięć podręczna dostawcy powróciła do 48 godzin.

Kod dodatku, kandydat na repozytorium, wykres zależności i stan włączenia były
prawidłowe. WatchNixtoons2 nadal został rozwiązany i odtwarzany, izolując awarię
ustawień użytkownika Umbrella, a nie transportu odtwarzania Kodi.

## Powrót do zdrowia

Przywrócono tylko `tools/kodi_profile.py restore-path`:

```text
userdata/addon_data/plugin.video.umbrella/settings.xml
```

ze zweryfikowanej prywatnej migawki Sony. Polecenie akceptuje tylko dokładne ścieżki
zadeklarowane przez tę migawkę, weryfikuje pełną migawkę przed zbudowaniem minimalnego
archiwum, sprawdza liczbę przywróconych plików po stronie urządzenia, restartuje Kodi i
usuwa pliki pomostowe.

Pierwsze uruchomienie na prawdziwym urządzeniu pokazało również, że Kodi może utracić
datagram serwera zdarzeń natychmiast po uruchomieniu. Transport przywracania jest teraz
ponawiany z nowym klientem i ograniczonym limitem czasu na próbę. Kolejne uruchomienie
na rzeczywistym urządzeniu zakończyło się bez ręcznej interwencji i zgłosiło dokładnie
jeden przywrócony plik.

## Po odzyskaniu E2E

| Testuj | Wynik |
|---|---|
| Wyszukiwanie filmów Umbrella, `Sintel` | zwrócony wynik pasujący |
| Odtwarzanie filmów Umbrella, `Sintel` | rozwiązany w 20,834 s; grał przez 12,354 s |
| Wyszukiwanie odcinków Umbrella, `Breaking Bad` | zwrócone pasujące wyniki |
| Odtwarzanie odcinka Umbrella, `Breaking Bad S01E01` | rozwiązany w 16,873 s; grał przez 15,046 s |
| Katalog na żywo WatchNixtoons2 | Zwrócono 16 aktualnych wpisów |
| Odtwarzanie WatchNixtoons2, `Mao Episode 17` | rozwiązany w 3,047 s; grał przez 12 s |
| Przenośna ulubiona grafika WatchNixtoons2 | 5 dopasowanych, 5 zmaterializowanych, 0 nieudanych |
| Pakiet repozytoriów lokalnych | 192 minęło |

Zainstalowane wersje to Umbrella `6.7.81.18`, MwoScrapers `0.1.6`, MwoScrapers Manager
`0.1.1`, WatchNixtoons2 `0.26.1` i `repository.mwodevelop` `1.0.0`.

## Niezależne utwardzanie recenzji

W wyniku późniejszego niezależnego przeglądu stwierdzono, że implementacja zamknęła
następujące dodatkowe tryby awarii:

- utracone potwierdzenie EventServer może rozpocząć równoczesne pełne przywracanie;
- stałe znaczniki postoju mogą być mylone w różnych operacjach;
- zgłoszono sukces bez udowodnienia, że ​​usługa dodatkowa nie przywróciła ustawień po
  ponownym uruchomieniu;
- selektywne odzyskiwanie dopuszczonego kodu dodatku oraz danych profilu;
- przekroczenie limitu czasu zakończenia lub przerwanie hosta może spowodować
  niebezpieczną lub przestarzałą blokadę urządzenia;
- wersje dodatków zawierające przyrostek `+` nie były porównywalne.

Utwardzony protokół wykorzystuje potwierdzenie rozpoczęcia atomowego, losowy
identyfikator operacji, skrót wyboru i blokadę pojedynczego urządzenia. Ponawia próbę
tylko przed potwierdzeniem, zatrzymuje Kodi przed zwolnieniem blokady, gdy moduł
zapisujący może być nadal aktywny, i dostarcza jawną komendę `recover-lock` dla
przerwanego hosta. Ścieżki selektywne są ograniczone do `userdata`; `addon_data` wymaga
zainstalowanej kompatybilnej wersji dodatku zarówno przed, jak i po ponownym
uruchomieniu. Zwykłe pliki otrzymują weryfikację rozmiaru i SHA-256. Ustawienia dodatków
są stosowane poprzez interfejs API ustawień Kodi i weryfikowane semantycznie po ponownym
uruchomieniu.

Na X88 przywrócono bieżące sterowanie i po ponownym uruchomieniu zweryfikowano jeden
neutralny plik profilu. Celowa ponowna próba wykonania starszej migawki Umbrella została
odrzucona: Umbrella wyczyścił nieaktualną autoryzację Trakt podczas uruchamiania, więc
narzędzie nie zgłosiło fałszywego sukcesu. Urządzenie pozostało sprawne:

| Przegląd testu regresji | Wynik |
|---|---|
| Selektywne przywracanie profilu neutralnego | 1 przywrócony, 1 zweryfikowany po ponownym uruchomieniu |
| Stary stan OAuth Umbrella | odrzucony po tym, jak dodatek unieważnił go |
| Odtwarzanie Umbrella `Sintel` | rozwiązany w 20,603 s; grał przez 12,362 s |
| WatchNixtoons2 `Mao Episode 17` | rozwiązany w 3,065 s; grał przez 12 s |
| Powtarzalny pakiet lokalny | 209 minęło |
| Blokada inscenizacji i przywracania urządzenia | sprzątać zarówno po sukcesie, jak i porażce |

## Zasady czyszczenia

Zastąpione dodatki do repozytoriów należy raczej wyłączyć niż odinstalować, dopóki
oddzielny test migracji nie wykaże, że Kodi zachowuje zarówno zarządzane dodatki, jak i
ich `addon_data`. Samo ponowne przypisanie źródła repozytorium nie jest wystarczającym
dowodem na to, że dezinstalacja jest bezpieczna.
