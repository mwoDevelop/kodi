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
montuje je read-only. Dotychczasowy dashboard mTLS pozostaje pod
`https://<QNAP>:19443/`. Dla zwykłej przeglądarki działa dodatkowo
`https://<QNAP>:19444/control-plane/`: nie wymaga certyfikatu klienta, lecz wymaga
hasła i TOTP oraz akceptacji ostrzeżenia lokalnego certyfikatu. Listener akceptuje
wyłącznie skonfigurowaną podsieć LAN i dokładny Host/Origin. Web/BFF używa
dedykowanego certyfikatu mTLS, którego core ogranicza do odczytu endpointów
dashboardu. Authz nie publikuje żadnego portu do LAN.

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
.venv/bin/python tests/e2e/control_plane_dashboard_cdp.py \
  --cdp http://127.0.0.1:9222
```
