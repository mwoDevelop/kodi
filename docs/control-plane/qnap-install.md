# Instalacja read-only Control Plane na QNAP

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
- losowy klucz checkpointu audytu, minimum 32 bajty;
- opcjonalnie plik tokenu GitHub read-only; publiczne repo działa bez niego.

Klucze mają tryb `0400` lub `0600`. Certyfikaty publiczne mogą mieć `0644`.
Wartości nie są zapisywane w `.env`, locku obrazu ani logach.

## Cykl życia

```bash
python tools/qnap_images.py build control-plane --dry-run
python tools/qnap_images.py deploy control-plane --dry-run
python tools/qnap_images.py status
```

Po promocji immutable digestu wdrożenie produkcyjne wykonuje się przez zwykły
`tools/kodi_ops.py rollout` albo diagnostycznie przez `qnap_images.py deploy`.

Po wdrożeniu należy potwierdzić:

1. kontener jest widoczny w Container Station i ma stan healthy/degraded;
2. integracyjny port Profile Sync nie jest publikowany do hosta;
3. wywołanie API bez certyfikatu klienta kończy się błędem TLS;
4. `GET /v1/fleet` z certyfikatem nie zawiera tokenów ani kluczy;
5. backup i restore do izolowanej bazy zachowują checkpoint audytu;
6. drugi refresh identycznych źródeł nie zmienia ich digestu payloadu.
