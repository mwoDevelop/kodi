# QTS gateway panelu Kodi Control Plane

Minimalny, bezusługowy pakiet QPKG rejestruje panel w QTS i instaluje
bramę CGI. Nie zarządza kontenerami i nie modyfikuje `app_proxy.conf`. CGI
przekazuje wyłącznie własny prefiks
`/cgi-bin/qpkg/KodiCPGateway/gateway.cgi/control-plane/` do backendu HTTP
wystawionego wyłącznie na `127.0.0.1:19445`.

Pakiet wyłącza wejście HTTP (`Web_Port=-2`) i używa systemowego HTTPS QTS
(`Web_SSL_Port=-1`). `package_routines` tworzy standardowe dowiązanie QPKG pod
`/home/httpd/cgi-bin/qpkg/`; aktualizacja z 0.1.x usuwa stare metadane proxy.
CGI przepuszcza tylko GET, HEAD i POST, ogranicza ciało żądania i forwarduje
zamkniętą listę nagłówków potrzebnych do sesji i CSRF.

Kliknięcie skrótu z aktywnej sesji administratora QTS dodatkowo waliduje
`NAS_SID` lokalnym API QTS i wykonuje logowanie serwer-serwer przez istniejący
endpoint Control Plane. Zwykłe wejście bez sesji QTS nadal wyświetla ręczny
ekran logowania. Nazwa operatora, hasło i sekret TOTP są dołączane z ignorowanego
pliku `.kodi-private/control-plane-operator.json` wyłącznie do generowanego QPKG,
instalowane jako pliki `0600` poza katalogiem WWW i nigdy nie trafiają do DOM,
adresu URL ani logów.

Pakiet jest budowany i instalowany przez `tools/qnap_control_plane_gateway.py`.
Źródło QDK 2.5.3 jest pobierane z przypiętym SHA-256; wygenerowany plik QPKG
nie jest wersjonowany.
