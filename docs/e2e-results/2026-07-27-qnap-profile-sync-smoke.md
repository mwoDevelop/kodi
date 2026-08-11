# QNAP Profile Sync dym syntetyczny

Data: 27.07.2026

Zakres: tylko etap 6A. W przebiegu wykorzystano syntetyczne dane klucza publicznego,
jednorazowy katalog poza `/share/ProfileSync`, port obsługujący tylko pętlę zwrotną i
zasady ponownego uruchamiania `no`. Nie zawierał profili Kodi, danych
uwierzytelniających użytkowników, tokenów ani kluczy produkcyjnych.

## Niezmienny obraz

- wersja serwera: 0.1.0;
- zatwierdzenie kompilacji: `b5ece3776f877634f9574def249a4612f49dacc8`;
- manifest:
  `ghcr.io/mwodevelop/kodi-profile-sync-server@sha256:9df7716d8b6606a1657f9dce77752105a8ce6036a974f975b3adc993d44c6671`;
- sprawdzone platformy: `linux/amd64`, `linux/arm/v7`;
- zwolnij workflow:
  <https://github.com/mwoDevelop/kodi-profile-sync-server/actions/runs/30300480694>.

## Dowody na żywo QNAP

- architektura hosta: `armv7l`;
- Docker: `26.1.4-qnap2`;
- Utwórz: `2.27.1-qnap1`;
- sterownik pamięci masowej: `overlay2`;
- główny układ pozostał uszkodzony i odbudowywał się (`[U_]`, około 30,2% podczas
  pomyślnego przebiegu), więc nie podjęto próby produkcji;
- Utwórz projekt: `qnap-profile-sync-smoke`;
- opublikowany punkt końcowy: tylko port pętli zwrotnej QNAP 28765;
- `/ready`: `ready`, API `v1`, schemat bazy danych 2, tryb rejestracji zweryfikowanej;
- ręczny restart procesu powrócił do `ready`;
- kontrolowane zatrzymanie spowodowało, że punkt końcowy stał się niedostępny;
- uruchomienie tego samego niezmiennego wdrożenia spowodowało zwrócenie go do `ready`.

## Dowody oczyszczenia

Po weryfikacji, Utwórz i zakończono strzeżone czyszczenie:

```json
{
  "containers": 0,
  "networks": 0,
  "volumes": 0,
  "smoke_parent_present": false
}
```

Nie pozostał żaden autostart, tunel, anonimowy wolumin, sieć Compose ani katalog dymu.
Ścieżki produkcyjne `/share/ProfileSync` nigdy nie były używane.

## Powtarzalny przepływ hosta

```bash
cd /home/mwo/projects/kodi

.venv/bin/python tools/qnap_profile_sync.py preflight

.venv/bin/python tools/qnap_profile_sync.py smoke-deploy \
  --image \
  ghcr.io/mwodevelop/kodi-profile-sync-server@sha256:9df7716d8b6606a1657f9dce77752105a8ce6036a974f975b3adc993d44c6671 \
  --run-id profile-sync-YYYYMMDDa

.venv/bin/python tools/qnap_profile_sync.py verify

.venv/bin/python tools/qnap_profile_sync.py destroy-smoke \
  --run-id profile-sync-YYYYMMDDa

.venv/bin/python tools/qnap_profile_sync.py status
```

Narzędzie wymaga trybu prywatnego 0600 `.env` i przypiętego klucza hosta QNAP. Nigdy nie
drukuje hosta, nazwy użytkownika ani hasła.
