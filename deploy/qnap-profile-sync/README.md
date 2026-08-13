# Kontener Profile Sync na QNAP

W przypadku rutynowych kompilacji i wdrożeń współdzielonych z innymi usługami Kodi QNAP,
użyj [`tools/qnap_images.py`](../../docs/qnap-images.md). Poniższe polecenia pozostają
interfejsem cyklu życia i odzyskiwania Profile Sync niższego poziomu.

Jest to jedyny obsługiwany kształt wdrożenia zaplecza. Jest przeznaczony dla aplikacji
Container Station 3 wspieranej przez Docker Compose.

Cykl życia hosta dotyczy `/var/run/docker.sock`, silnika Docker zarządzanego i
wyświetlanego przez GUI Container Station 3. Nie wdrażaj tego projektu w oddzielnym
silniku `/var/run/system-docker.sock`.

Ograniczenia bezpieczeństwa:

- ustaw `PROFILE_SYNC_IMAGE` na niezmienny skrót wielu architektur;
- powiąż opublikowany port z jednym jawnym adresem LAN i obsługuj zweryfikowany TLS
  bezpośrednio z kontenera;
- zamontuj dane SQLite/blob i rejestr kluczy publicznych z dedykowanych ścieżek;
- zamontuj certyfikat TLS i klucz prywatny w trybie tylko do odczytu; klienci muszą ufać
  dedykowanemu prywatnemu CA zamiast wyłączać weryfikację certyfikatu;
- renderuj z wyraźną nazwą projektu Compose; nie dodawaj `container_name`;
- utrzymuj główny system plików w trybie tylko do odczytu i ograniczaj możliwości;
- nigdy nie używaj `--unsafe-accept-signatures` w tym wdrożeniu;
- read-only API integracyjne `8767` podłącz wyłącznie do zewnętrznej sieci Compose
  `mwodevelop-control`, bez publikowania portu na QNAP; wymagaj certyfikatu klienta;
- wykonaj kopię zapasową bazy danych poprzez operację tworzenia kopii zapasowej
  aplikacji, a nie poprzez kopiowanie aktywnego pliku bazy danych WAL.

Cykl życia hosta odmawia wdrożenia produkcyjnego, chyba że wszyscy członkowie RAID są
online, nie jest uruchomiona żadna przebudowa, obraz jest przypięty przez podsumowanie,
klucz hosta SSH jest przypięty, a wszystkie prywatne pliki mają restrykcyjne
uprawnienia.

Wdrażaj i sprawdzaj produkcję w ramach ograniczonego cyklu życia hosta:

```bash
python tools/qnap_profile_sync.py --references .env deploy-production \
  --image ghcr.io/mwodevelop/kodi-profile-sync-server@sha256:<digest> \
  --host-ip 192.0.2.39 \
  --key-registry /private/key-registry.json \
  --tls-certificate /private/server.crt \
  --tls-key /private/server.key \
  --ca-certificate /private/ca.crt
python tools/qnap_profile_sync.py --references .env verify-production \
  --host-ip 192.0.2.39 --ca-certificate /private/ca.crt
```

Utwórz kopię zapasową SQLite online i skopiuj ją z serwera NAS. Przerwane pobieranie
można wznowić bez odtwarzania lub nadpisywania kopii zapasowej po stronie serwera:

```bash
python tools/qnap_profile_sync.py --references .env backup-production \
  --backup-id production-20260731 --output /private/production.sqlite
python tools/qnap_profile_sync.py --references .env \
  download-production-backup \
  --backup-id production-20260731 --output /private/production.sqlite
```

Rotacja urządzenia może pozostawić starszy enrollment z nadal ważnym tokenem. Po
potwierdzeniu, że najwyższa generacja ma świeży heartbeat i udany raport aktywnej
rewizji, unieważnij dokładny starszy identyfikator przez hostowy interfejs CLI:

```bash
.venv/bin/python tools/qnap_profile_sync.py --references .env \
  revoke-production-enrollment --enrollment-id 'enr:<dokładny-id>'
```

Najpierw wykonaj kopię online. Polecenie nie przyjmuje logicznej nazwy urządzenia ani
zakresu generacji, aby przypadkowo nie objąć bieżącego enrollmentu. Revocation jest
nieodwracalna dla danego tokenu; w razie utraty aktualnego enrollmentu utwórz nową
generację kontrolowanym parowaniem zamiast reaktywować stary token.

Zaszyfruj kopię poza serwerem NAS za pomocą osobnego trybu `0600`, 32-bajtowego klucza i
wykonaj odszyfrowanie oraz sprawdzenie integralności SQLite przed uznaniem, że kopia
zapasowa została ukończona:

```bash
python tools/profile_sync_backup.py encrypt \
  --input /private/production.sqlite \
  --output /private/production.sqlite.mwobak \
  --key-file ~/.config/mwodevelop/profile-sync-backup.key
python tools/profile_sync_backup.py decrypt \
  --input /private/production.sqlite.mwobak \
  --output /tmp/profile-sync-restore.sqlite \
  --key-file ~/.config/mwodevelop/profile-sync-backup.key
sqlite3 /tmp/profile-sync-restore.sqlite 'PRAGMA integrity_check;'
```

Zweryfikuj politykę produkcyjną bez uruchamiania kontenera:

```bash
python tools/qnap_compose_policy.py \
  --mode production \
  --allow-placeholder \
  --env-file deploy/qnap-profile-sync/env.example
```

Sprawdź izolowaną nakładkę dymu:

```bash
python tools/qnap_compose_policy.py \
  --mode smoke \
  --allow-placeholder \
  --env-file deploy/qnap-profile-sync/smoke.env.example
```

Środowisko dymu jest jedynie szablonem. Uruchomienie musi zastąpić obraz niezmiennym
skrótem 64-szesnastkowym i użyć nowego jednorazowego katalogu poza `/share/ProfileSync`.
Dane dymu, rejestr kluczy, projekt, port i tunele muszą zostać usunięte po teście.
