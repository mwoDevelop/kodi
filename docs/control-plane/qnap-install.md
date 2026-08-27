# Instalacja Control Plane na QNAP

Pierwszy przyrost jest czwartą aplikacją Container Station zarządzaną przez
`tools/qnap_images.py`. Obraz musi zawierać `linux/amd64` i `linux/arm/v7`, a
wdrożenie korzysta z immutable digestu.

Dokładny kontrakt Compose i niskopoziomowy punkt wejścia opisuje
[README wdrożenia](../../deploy/qnap-control-plane/README.md).

## Wymagane pliki prywatne

W ignorowanym katalogu `.kodi-private/control-plane/` znajdują się:

- certyfikat i klucz serwera API;
- dedykowany CA certyfikatów operatorskich, odrębny od CA Profile Sync;
- certyfikat i klucz klienta do Profile Sync integration API;
- dedykowane certyfikaty BFF do core i authz oraz certyfikat serwera authz;
- 32-bajtowy klucz AEAD authz, przechowywany poza bazą;
- losowy klucz checkpointu audytu, minimum 32 bajty;
- opcjonalnie plik tokenu GitHub read-only; publiczne repo działa bez niego.

Klucze mają tryb `0400` lub `0600`. Certyfikaty publiczne mogą mieć `0644`.
Wartości nie są zapisywane w `.env`, locku obrazu ani logach.

## Cykl życia

```bash
python tools/qnap_images.py build control-plane --dry-run
python tools/qnap_images.py deploy control-plane --dry-run
python tools/qnap_images.py status
python tools/qnap_images.py browser-bootstrap
```

Po promocji immutable digestu wdrożenie produkcyjne wykonuje się przez zwykły
`tools/kodi_ops.py rollout` albo diagnostycznie przez `qnap_images.py deploy`.

Po wdrożeniu należy potwierdzić:

1. trzy kontenery projektu są widoczne w Container Station i mają stan
   healthy/degraded;
2. integracyjny port Profile Sync nie jest publikowany do hosta;
3. wywołanie API bez certyfikatu klienta kończy się błędem TLS;
4. `GET /v1/fleet` z certyfikatem nie zawiera tokenów ani kluczy;
5. backup i restore do izolowanej bazy zachowują checkpoint audytu;
6. drugi refresh identycznych źródeł nie zmienia ich digestu payloadu.
7. `https://<QNAP>/cgi-bin/qpkg/KodiCPGateway/gateway.cgi/control-plane/login`
   działa bez certyfikatu klienta przez HTTPS QTS, port backendu
   `127.0.0.1:19445` nie jest osiągalny z LAN, a bezusługowy QPKG nie korzysta
   z `app_proxy.conf`;
8. bootstrap, login, logout, restart i odzyskanie TOTP zachowują kontrakt sesji.

Po aktualizacji z wydania `0.1.x` baza jest migrowana expand-only ze schematu 1
do 2. Przed wdrożeniem należy zachować podpisany backup. Restore backupu schematu
1 pozostaje obsługiwany i migruje dopiero kopię w katalogu docelowym.

Lifecycle bundle testuje główny E2E `tests/e2e/control_plane_readonly.py`:
uruchamia Profile Sync i Control Plane, wykonuje lokalnym CLI `prepare`, `ready`
oraz `publish`, po czym odczytuje generację 1 przez operator API mTLS. Żądanie bez
certyfikatu i każda mutacja HTTP nadal muszą zostać odrzucone.
