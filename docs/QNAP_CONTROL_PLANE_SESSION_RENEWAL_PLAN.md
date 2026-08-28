# Plan odnowienia sesji Kodi admin przez QTS

## Diagnoza

Sesja przeglądarkowa Control Plane wygasa po 30 minutach bezczynności albo po
8 godzinach bezwzględnie. Cookie `mwo_cp_session` nie ma jednak własnego czasu
wygaśnięcia i pozostaje w profilu Chrome do końca sesji przeglądarki. Gateway
QPKG sprawdzał wyłącznie obecność cookie. Wygasła wartość blokowała więc
automatyczne logowanie z ważnej sesji administratora QTS, a backend przekierowywał
użytkownika na `/login`.

Otwarta karta mogła dodatkowo nadal wyświetlać poprzednio wyrenderowany dashboard.
Kolejne odświeżenie API zwracało `401`, lecz frontend jedynie pokazywał błąd i
nie przechodził ponownie przez gateway.

## Zakres poprawki

1. Gateway dla wejścia na główną ścieżkę sprawdza cookie sesyjne lokalnym,
   loopback-only backendem. Samo istnienie cookie nie jest dowodem ważnej sesji.
2. Gdy sesja jest nieważna, ale `NAS_SID` potwierdza administratora QTS, gateway
   wykonuje dotychczasowe logowanie serwer-serwer i zastępuje cookie sesji oraz CSRF.
3. Dashboard po odpowiedzi `401` wraca na główną ścieżkę. Dzięki temu również
   karta pozostawiona otwarta przechodzi przez mechanizm odnowienia.
4. Weryfikacja sesji usuwa wszystkie rekordy przekraczające limit idle lub limit
   bezwzględny, aby baza nie gromadziła nieosiągalnych generacji sesji.

## Bezpieczeństwo i granice

- odnowienie nadal wymaga lokalnie zweryfikowanej sesji administratora QTS;
- credentiale i sekret TOTP pozostają w plikach QPKG `0600`, poza WWW;
- przeglądarka nie otrzymuje credentiali, TOTP ani wartości `NAS_SID`;
- walidacja cookie trafia wyłącznie do backendu `127.0.0.1:19445`;
- brak ważnego `NAS_SID` zachowuje ręczny ekran logowania;
- gateway nie podąża za przekierowaniem podczas sprawdzania sesji.

## Testy i wdrożenie

1. Testy gateway: brak cookie, ważne cookie oraz wygasłe cookie z ważnym
   `NAS_SID`.
2. Testy authz: jedno wywołanie usuwa wszystkie przeterminowane sesje, ale zachowuje
   bieżącą ważną sesję.
3. Test statyczny frontendu potwierdza przekierowanie po `401`.
4. Pełne testy `kodi-control-plane` oraz testy gateway w repozytorium `kodi`.
5. Publikacja nowego immutable obrazu Control Plane, aktualizacja locka i wdrożenie
   przez wspólny mechanizm QNAP.
6. Ponowna instalacja QPKG `KodiCPGateway` i weryfikacja przez CDP: wygasła sesja,
   kliknięcie skrótu, automatyczne odnowienie, dashboard oraz odświeżenie bez
   `401`.

