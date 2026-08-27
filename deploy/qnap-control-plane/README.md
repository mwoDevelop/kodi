# Read-only Kodi Control Plane i dashboard na QNAP

Projekt Compose uruchamia trzy procesy jednego obrazu w Container Station:
`control-plane`, `control-plane-authz` i `control-plane-web`. API na porcie
`19443` nadal wymaga mTLS. Połączenie do Profile Sync używa prywatnej zewnętrznej
sieci `mwodevelop-control`; port integracyjny `8767` nie jest publikowany na QNAP.

Wdrożenie jest obsługiwane przez wspólny interfejs:

```bash
python tools/qnap_images.py build control-plane --dry-run
python tools/qnap_images.py deploy control-plane --dry-run
python tools/qnap_images.py status
```

Pliki certyfikatów i kluczy są pobierane wyłącznie z ignorowanego katalogu
`.kodi-private/control-plane/`. Compose nie montuje Docker socketu, bazy Profile
Sync ani żadnego pliku `.env` z credentialami urządzeń.

Wdrożenie kopiuje z repo kanoniczne manifesty
`control-plane-schedules.json` i `control-plane-status-sources.json`, a następnie
montuje je read-only. Z prywatnego rejestru urządzeń generuje także zredagowany
`device-inventory.json`, zawierający wyłącznie logiczny identyfikator, kanał, tryb
monitorowania i progi świeżości. Adresy, tokeny i credentiale nie trafiają do
Control Plane. Dotychczasowy dashboard mTLS pozostaje pod
`https://<QNAP>:19443/`. Dla zwykłej przeglądarki działa dodatkowo kanoniczne
`https://<QNAP>/cgi-bin/qpkg/KodiCPGateway/gateway.cgi/control-plane/`: nie
wymaga certyfikatu klienta, lecz wymaga hasła i TOTP. QPKG `KodiCPGateway`
rejestruje skrót QTS, a bezstanowe CGI przekazuje ten prefiks z HTTPS QTS do
backendu dostępnego wyłącznie na `127.0.0.1:19445`. Web/BFF używa
dedykowanego certyfikatu mTLS, którego core ogranicza do odczytu endpointów
dashboardu. Authz nie publikuje żadnego portu do LAN.

Wdrożenie QPKG weryfikuje wersję, systemowy port HTTPS, brak usługi i proxy oraz
standardowe dowiązanie CGI. Nie edytuje konfiguracji Apache i nie restartuje
Qthttpd, więc skrót pozostaje niezależny od regeneracji `app_proxy.conf`.

Pierwszy bootstrap albo jawny reset break-glass:

```bash
python tools/qnap_images.py browser-bootstrap
python tools/qnap_images.py browser-bootstrap --reset
```

Kod jest jednorazowy i wygasa po 10 minutach. `--reset` usuwa istniejącego
operatora, sesje i kody odzyskiwania, dlatego używa się go wyłącznie świadomie.

Powtarzalny test kontraktu i renderowania:

```bash
.venv/bin/python tests/e2e/control_plane_readonly.py
.venv/bin/python tests/e2e/control_plane_browser.py
.venv/bin/python tests/e2e/control_plane_dashboard_cdp.py \
  --cdp http://127.0.0.1:9222
```

Budowa, instalacja i kontrola samego gatewaya:

```bash
python tools/qnap_control_plane_gateway.py build --output /tmp/qnap-gateway
python tools/qnap_control_plane_gateway.py deploy
python tools/qnap_control_plane_gateway.py status
```

Format pakietu i jego granice opisuje
[README QPKG gatewaya](../qnap-control-plane-gateway/README.md).
