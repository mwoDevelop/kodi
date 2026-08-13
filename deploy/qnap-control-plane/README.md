# Read-only Kodi Control Plane na QNAP

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
