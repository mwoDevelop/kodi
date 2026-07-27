# Device registry v2 and lifecycle inventory

Date: 2026-07-27

Scope: read-only qualification of registry schema v2, neutral ADB transport and
Android lifecycle. No Kodi setting, add-on, enrollment or profile file was
mutated.

## Reproducible commands

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

## Results

| logical device | platform | Kodi | observed ABI | running | runtime paths |
|---|---|---:|---|---:|---|
| `bluestacks1` | Android emulator | 21.3 | x86_64, x86, arm64-v8a, armeabi-v7a, armeabi | yes | qualified |
| `sony-tv` | Android TV | 21.3 | armeabi-v7a, armeabi | yes | qualified |
| `bedroom-tv` | Android TV | 21.2 | armeabi-v7a, armeabi | yes | qualified |

The inventory output contains no endpoint, username, home path, host
fingerprint or private reference value.

## Linux/Flatpak gate

The NUC endpoint returned `No route to host` during this run. Local fake-SSH
tests cover pinned `known_hosts`, private key permissions, account UID/home,
machine fingerprint, Flatpak version/architecture, owner checks, symlink
escape and the `REQUIRES_IN_PROCESS_KODI_PROBE` state. A real NUC result is not
claimed and remains a release gate for the Flatpak lifecycle.

## Automated tests

```text
27 focused registry/transport/lifecycle/reinstall tests passed
110 full repository tests passed
devices.schema.json passed Draft 2020-12 validation for:
- the public schema v2 example;
- the migrated private schema v2 registry;
- the preserved private schema v1 backup.
```
