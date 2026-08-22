# QTS gateway panelu Kodi Control Plane

Minimalny pakiet QPKG rejestruje panel w QTS i włącza wspierany mechanizm
`QPKG_USE_PROXY`. Nie zawiera aplikacji, danych ani sekretów i nie zarządza
kontenerami. QTS przekazuje `/control-plane/` do backendu HTTP wystawionego
wyłącznie na `127.0.0.1:19445`.

Pakiet jest budowany i instalowany przez `tools/qnap_control_plane_gateway.py`.
Źródło QDK 2.5.3 jest pobierane z przypiętym SHA-256; wygenerowany plik QPKG
nie jest wersjonowany.
