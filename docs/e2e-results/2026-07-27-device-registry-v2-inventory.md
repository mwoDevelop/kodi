# Rejestr urządzeń v2 i inwentaryzacja cyklu życia

Data: 27.07.2026

Zakres: kwalifikacja tylko do odczytu schematu rejestru v2, neutralny transport ADB i
cykl życia Android. Żadne ustawienie, dodatek, rejestracja ani plik profilu Kodi nie
zostały zmutowane.

## Powtarzalne polecenia

```bash
python3 tools/kodi_devices.py validate

python3 tools/kodi_inventory.py bluestacks1 \
  --adb /home/mwo/android-sdk/platform-tools/adb \
  --adb-server-port 5038

python3 tools/kodi_inventory.py sony-tv \
  --adb /home/mwo/android-sdk/platform-tools/adb \
  --adb-server-port 5038

python3 tools/kodi_inventory.py bedroom-tv \
  --adb /home/mwo/android-sdk/platform-tools/adb \
  --adb-server-port 5037
```

## Wyniki

| urządzenie logiczne | platforma | Kodi | zauważył ABI | bieganie | ścieżki wykonawcze |
|---|---|---:|---|---:|---|
| `bluestacks1` | Emulator Android | 21,3 | x86_64, x86, arm64-v8a, armeabi-v7a, armeabi | tak | wykwalifikowany |
| `sony-tv` | Android TV | 21,3 | armeabi-v7a, armeabi | tak | wykwalifikowany |
| `bedroom-tv` | Android TV | 21,2 | armeabi-v7a, armeabi | tak | wykwalifikowany |

Dane wyjściowe inwentaryzacji nie zawierają punktu końcowego, nazwy użytkownika, ścieżki
domowej, odcisku palca hosta ani prywatnej wartości referencyjnej.

## Brama Linux/Flatpak

Podczas tego przebiegu punkt końcowy NUC zwrócił `No route to host`. Lokalne testy
fałszywego SSH obejmują przypięte `known_hosts`, uprawnienia klucza prywatnego, UID
konta/stronę główną, odcisk palca maszyny, wersję/architekturę Flatpak, kontrole
właściciela, ucieczkę dowiązania symbolicznego i stan `REQUIRES_IN_PROCESS_KODI_PROBE`.
Prawdziwy wynik NUC nie jest deklarowany i pozostaje bramą do wydania dla cyklu życia
Flatpak.

## Testy automatyczne

```text
27 focused registry/transport/lifecycle/reinstall tests passed
110 full repository tests passed
devices.schema.json passed Draft 2020-12 validation for:
- the public schema v2 example;
- the migrated private schema v2 registry;
- the preserved private schema v1 backup.
```
