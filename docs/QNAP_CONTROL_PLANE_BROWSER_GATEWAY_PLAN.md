# Plan naprawy dostępu przeglądarkowego do Kodi Control Plane

## Problem i cel

Panel na `https://192.168.1.39:19444/control-plane/` używa prywatnego
certyfikatu serwera. Port i kontenery działają, ale przeglądarki bez prywatnego
CA pokazują interstitial TLS, a część klientów/VPN blokuje niestandardowy port.
Poprzedni test CDP ukrywał ten problem przez wyłączenie walidacji certyfikatu.

Celem jest jeden kanoniczny adres:

`https://192.168.1.39/control-plane/`

Panel ma używać istniejącego wejścia HTTPS QTS na porcie 443. Nie wolno
udostępnić hasła, TOTP ani sesji przez jawny HTTP w sieci LAN.

## Docelowa architektura

1. QTS kończy TLS na porcie 443 i przez wspierany mechanizm QPKG HTTP Proxy
   przekazuje wyłącznie prefiks `/control-plane/`.
2. `control-plane-web` udostępnia backend HTTP tylko na `127.0.0.1` QNAP, na
   osobnym porcie technicznym. Port nie jest osiągalny z LAN.
3. BFF nadal wymaga hasła, TOTP, sesji, CSRF, dokładnego `Host`/`Origin` i
   pozostaje wyłącznie do odczytu. Połączenia BFF do core i authz nadal używają
   prywatnego mTLS.
4. API operatorskie `:19443` pozostaje bez zmian i nadal wymaga certyfikatu
   klienta.
5. Integracja QTS jest zarządzana jako mały QPKG-gateway, niezależny od obrazu
   aplikacji i danych Control Plane.

## Implementacja

1. Dodać do web/BFF jawny tryb backendu proxy bez TLS. Tryb musi być
   fail-closed: dozwolony wyłącznie przez osobną flagę, przy adresie loopback
   albo w kompozycji publikującej port tylko na loopback hosta.
2. Zmienić Compose QNAP: usunąć publiczny listener web `:19444`, opublikować
   backend techniczny tylko na `127.0.0.1` i ustawić kanoniczny Host/Origin na
   `https://192.168.1.39`.
3. Dodać odtwarzalny projekt QPKG z `QPKG_USE_PROXY=1` i
   `QPKG_PROXY_PATH=/control-plane`, wskazujący lokalny port backendu.
4. Rozszerzyć skrypt wdrożeniowy o instalację/aktualizację gatewaya,
   weryfikację jego własności oraz rollback konfiguracji i Compose przy
   nieudanym teście.
5. Uaktualnić skrót pulpitu QTS i dokumentację do kanonicznego adresu bez
   portu 19444.

## Bramki bezpieczeństwa i testy

1. Testy jednostkowe muszą odrzucać publiczny/plaintext listener oraz zmianę
   Host/Origin, mutacje HTTP, brak CSRF i brak sesji.
2. Test Compose ma potwierdzić: core tylko na prywatnym `:19443`, backend web
   tylko na loopback, authz bez portu publicznego.
3. Test QPKG ma walidować stałą nazwę, proxy path, port backendu, widoczność
   tylko dla administratorów i brak sekretów w pakiecie.
4. E2E QNAP: logowanie, dashboard, ręczne odświeżenie i wylogowanie przez
   `https://192.168.1.39/control-plane/`; bez użycia portu 19444.
5. E2E Android: Chrome ma otworzyć kanoniczny adres bez
   `Security.setIgnoreCertificateErrors`; test rozróżnia stronę logowania od
   interstitiala prywatności.
6. Negatywnie: port backendu nie może być osiągalny z BlueStacks/X88/Sony, a
   API `:19443` bez certyfikatu nadal ma odrzucać połączenie.
7. Po sukcesie przeprowadzić PR/CI, wdrożyć zatwierdzone artefakty, ponownie
   wykonać E2E i zaktualizować dokumentację architektury.

## Rollback

W razie błędu gateway QPKG zostaje wyłączony/usunięty, a poprzedni Compose i
środowisko są przywracane atomowo. Stary listener `:19444` można przywrócić
wyłącznie jako awaryjny, nadal z jego wcześniejszym ograniczeniem prywatnego CA.

## Ograniczenie pozostające poza zmianą

Certyfikat QTS jest obecnie samopodpisany i wygasł 9 marca 2026. Urządzenia,
które już otwierają `https://192.168.1.39/`, korzystają z zaakceptowanego
wyjątku. Gateway usuwa drugi certyfikat i niestandardowy port, ale pełne
usunięcie ostrzeżeń na nowych urządzeniach wymaga odnowienia certyfikatu QTS
albo publicznej nazwy DNS z certyfikatem zaufanego CA.
