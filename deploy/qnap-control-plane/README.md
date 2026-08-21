# Read-only Kodi Control Plane i dashboard na QNAP

Projekt Compose uruchamia czwartą aplikację Kodi w Container Station. API na
porcie `19443` wymaga mTLS. Połączenie do Profile Sync używa prywatnej zewnętrznej
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
montuje je read-only. Pod `https://<QNAP>:19443/` działa statyczny dashboard bez
CDN; tak samo jak API wymaga certyfikatu klienta mTLS. Endpointy
`/api/v1/{dashboard,schedules,services,alerts}` są wyłącznie odczytowe.

Powtarzalny test kontraktu i renderowania:

```bash
.venv/bin/python tests/e2e/control_plane_readonly.py
.venv/bin/python tests/e2e/control_plane_dashboard_cdp.py \
  --cdp http://127.0.0.1:9222
```
