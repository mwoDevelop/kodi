# 9.09.2026 — Migracja Kodi Flatpak do zakresu per-user (--user) na NUC (mwo i alek)

Status: **ZAKOŃCZONA SUKCESEM; ROLLOUT NUC OBU KONT: PASS; ACL EDGE: ZACHOWANA**.

## 1. Kontekst i przyczyna problemu

Na urządzeniu NUC (`192.168.1.25`, openSUSE Tumbleweed) funkcjonują dwa niezależne konta użytkowników: `mwo` (UID 1000) oraz `alek` (UID 1001).
Katalog aplikacji Microsoft Edge w instalacji systemowej:
`/var/lib/flatpak/app/com.microsoft.Edge`
posiada regułę ACL:
`user:alek:---`
uniemożliwiającą użytkownikowi `alek` uruchamianie oraz przeglądanie zawartości Edge.

Dotychczasowa współdzielona instalacja systemowa Kodi (`tv.kodi.Kodi`) powodowała, że polecenia narzędziowe Flatpak wykonywane bez jawnego zakresu (`flatpak list`, `flatpak info`) dokonywały enumeracji drzewa katalogów `/var/lib/flatpak/app/`, co na koncie `alek` kończyło się błędem:
`error: Error opening directory '/var/lib/flatpak/app/com.microsoft.Edge': Permission denied`
i blokowało automatyczny inwentarz oraz rollout floty (`device_unavailable` / `DEFERRED`).

Celem migracji było:
1. Zachowanie reguły ACL dla Edge bez żadnych zmian ani obejść.
2. Dodanie jawnego parametru zakresu instalacji (`flatpak_scope`) w inwentarzu urządzeń.
3. Przeniesienie Kodi do instalacji per-user (`--user`) na obu kontach (`mwo` i `alek`).
4. Bezpieczne zachowanie wszystkich istniejących danych użytkowników (`.var/app/tv.kodi.Kodi/data`), tokenów, dodatków i tożsamości Profile Sync.
5. Kwalifikacja działania obu kont w nowym trybie.
6. Usunięcie współdzielonej instalacji systemowej `tv.kodi.Kodi` bez stosowania `--delete-data` i bez naruszenia współdzielonych bibliotek runtime oraz innych aplikacji (Steam, Moonlight, Chrome, Edge itp.).

---

## 2. Wykonane kopie zapasowe (Pre-migration Backups)

Przed wprowadzeniem jakichkolwiek zmian na hoście NUC zweryfikowano stan spoczynku aplikacji (`pgrep -u <uid> -f tv.kodi.Kodi` -> `False` dla obu kont).

Wykonano pełne archiwa stanu danych Kodi do bezpiecznego katalogu `.kodi-private/backups/`:
- `.kodi-private/backups/nuc-mwo-pre-migration-20260909.tar.gz` (117.41 MB, uprawnienia `0600`)
- `.kodi-private/backups/nuc-alek-pre-migration-20260909.tar.gz` (116.96 MB, uprawnienia `0600`)

Zweryfikowano integralność archiwów i obecność kluczowych plików:
- `data/userdata/addon_data/service.mwodevelop.profilesync` (tożsamość enrollmentu, klucze, journal, baza stanu)
- `data/userdata/guisettings.xml` (ustawienia skórki i konfiguracja GUI)
- `data/userdata/favourites.xml` (ulubione wraz ze strukturą grafik)
- `data/addons` (kompletny kod zainstalowanych rozszerzeń)

---

## 3. Zmiany w inwentarzu i narzędziach

### 3.1 Schemat i inwentarz
- `manifests/devices.schema.json`: rozszerzono definicję `expectedFlatpak` o pole `flatpak_scope` z dozwolonymi wartościami `["user", "system"]`.
- `manifests/devices.example.json`: dodano `"flatpak_scope": "user"` do wpisu demonstracyjnego.
- `.kodi-private/devices.json`: zaktualizowano konfigurację `nuc-mwo` oraz `nuc-alek` do `"flatpak_scope": "user"`.
- `tools/kodi_devices.py`: w funkcji `_validate_expected` dodano obsługę i walidację pola `flatpak_scope`.

### 3.2 Sondy cyklu życia i atestacja runtime
- `tools/kodi_lifecycle.py`:
  - `FlatpakKodiLifecycle.probe_kodi()` odczytuje `flatpak_scope = expected.get("flatpak_scope")`.
  - Gdy zakres jest określony, polecenie inwentaryzacyjne przyjmuje postać `flatpak list --<scope> --app --columns=application,arch,version`, co całkowicie eliminuje odwoływanie się do katalogów systemowych dla zakresu `--user`.
  - Słownik wynikowy sondy zwraca pole `flatpak_scope`.
- `tools/kodi_runtime_attestation.py`:
  - `attest_flatpak_runtime()` otrzymało opcjonalny parametr `scope=None`.
  - W przypadku przekazania `scope="user"` weryfikowana jest wyłącznie ścieżka instalacji w katalogu domowym użytkownika.

### 3.3 Odtwarzanie i rollout
- `tools/kodi_flatpak_restore.py`:
  - `_flatpak_lines()` dopuszcza kod wyjścia `1` (np. przy restrykcjach systemowych) i zwraca pustą listę zamiast nieobsłużonego wyjątku `TransportError`.
  - `_installer_probe()` obsługuje parametr `expected_scope`, dopuszczając obecność instalacji w wybranym zakresie w fazie przejściowej.
- `tools/kodi_flatpak_profile_sync_rollout.py`:
  - `qualify_runtime_paths()` oraz główny blok uruchamiania Kodi w środowisku Xvfb przekazują jawny parametr `--user` do `flatpak run {scope}{app} --standalone`.
  - Wywołanie `attest_flatpak_runtime()` przekazuje `scope` zdefiniowany w urządzeniu.

---

## 4. Przebieg wdrożenia na NUC

1. **Konfiguracja zdalnego repozytorium Flathub dla użytkowników:**
   Dla kont `mwo` i `alek` skonfigurowano repozytorium użytkownika w oparciu o istniejący plik systemowy:
   `flatpak remote-add --user --if-not-exists --from flathub /etc/flatpak/remotes.d/flathub.flatpakrepo`
2. **Instalacja pakietu per-user:**
   Dla obu kont zainstalowano Kodi:
   `flatpak install --user --noninteractive -y flathub tv.kodi.Kodi`
   Potwierdzono instalację wersji `21.3-Omega` (commit `1d70001b3066b1562d649e9c811e874b896391848a0e08760b71c6ce486f66f7`) współdzielącej systemowe środowisko uruchomieniowe `org.freedesktop.Platform/x86_64/24.08`.
3. **Potwierdzenie ścieżek danych:**
   Ścieżka `kodi_data_root` pozostała niezmienna: `/home/<user>/.var/app/tv.kodi.Kodi/data`. Nie dokonano żadnego arbitralnego dopisywania `/kodi`.
4. **Weryfikacja skrótów KDE:**
   Pliki aktywatorów desktopowych:
   `~/.local/share/flatpak/exports/share/applications/tv.kodi.Kodi.desktop`
   zostały wygenerowane poprawnie i są automatycznie integrowane z menu środowiska KDE Plasma.

---

## 5. Wyniki kwalifikacji i rolloutu

Zarówno przed, jak i po deinstalacji pakietu systemowego wykonano pełny rollout produkcyjny z wykorzystaniem `tools/kodi_ops.py rollout`:

### nuc-mwo
- **Status:** COMPLETE / PASS
- **Favourites:** HEALTHY (kursor 14, dynamic fence aktywny)
- **Playback State:** HEALTHY (kursor 28)
- **Skin Menu:** HEALTHY
- **YouTube:** ACCOUNT_READY
- **OpenSubtitles.com:** PASS
- **Managed Settings:** NO_CHANGE
- **Runtime Compatibility:** AUDIT_PASS
- **E2E Suite:** 855 PASS

### nuc-alek
- **Status:** COMPLETE / PASS
- **Favourites:** HEALTHY (kursor 14, dynamic fence aktywny)
- **Playback State:** HEALTHY (kursor 28)
- **Skin Menu:** HEALTHY
- **YouTube:** ACCOUNT_READY
- **OpenSubtitles.com:** PASS
- **Managed Settings:** NO_CHANGE
- **Runtime Compatibility:** AUDIT_PASS
- **E2E Suite:** 855 PASS

---

## 6. Bezpieczne usunięcie instalacji systemowej

Po pomyślnej kwalifikacji obu kont wykonano polecenie:
`sudo flatpak uninstall --system -y tv.kodi.Kodi`
Zgodnie z wymogami:
- Nie użyto flagi `--delete-data`.
- Nie użyto flagi `--unused`.
- Pozostałe aplikacje systemowe (`com.google.Chrome`, `com.microsoft.Edge`, `com.moonlight_stream.Moonlight`, `com.parsecgaming.parsec`, `com.valvesoftware.Steam`, `io.github.dvlv.boxbuddyrs`, `io.mrarm.mcpelauncher`) oraz biblioteki runtime pozostały w pełni nienaruszone.

---

## 7. Potwierdzenie stanu ACL Edge

Po wykonaniu wszystkich operacji przeprowadzono audyt uprawnień katalogu Edge:
```
# getfacl /var/lib/flatpak/app/com.microsoft.Edge
# file: var/lib/flatpak/app/com.microsoft.Edge
# owner: root
# group: root
user::rwx
user:alek:---
group::r-x
mask::r-x
other::r-x
```
- Próba dostępu z konta `alek` (`flatpak info com.microsoft.Edge`):
  `error: Error opening directory '/var/lib/flatpak/app/com.microsoft.Edge': Permission denied` (kod wyjścia 1).
- Dostęp z konta `mwo` (`flatpak info com.microsoft.Edge`): kod wyjścia 0, pełny odczyt metadanych.

Blokada konta `alek` do Microsoft Edge działa nieprzerwanie.
Oba konta obsługują Kodi per-user bez konfliktów uprawnień.
