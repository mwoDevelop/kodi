# Filtry możliwości Umbrella per urządzenie — 7.09.2026

## Zakres

Zweryfikowano wszystkie sześć logicznych instalacji z prywatnego rejestru.
Android został zbadany przez deklaracje MediaCodec oraz odczyt ustawień
Umbrella. Dwa profile Flatpak używają tego samego Intel Iris Xe; brak aktywnego
EDID potraktowano zachowawczo jako brak potwierdzenia toru HDR/Dolby Vision.

## Wynik

| Urządzenie | Dowód możliwości | Zmienione filtry | Powtórny przebieg |
|---|---|---|---|
| `bluestacks1` | programowe HEVC i AV1, brak Dolby Vision | HEVC/AV1 odblokowane, HDR/DV zablokowane | `NO_CHANGE` |
| `sony-tv` | sprzętowe HEVC i Dolby Vision, brak AV1 | bez zmian | `NO_CHANGE` |
| `x88pro20` | sprzętowe HEVC, deklaracja AV1 ma `enabled=false` | AV1/DV zablokowane | `NO_CHANGE` |
| `bedroom-tv` | sprzętowe HEVC/AV1/DV, ale pusta lista HDR aktywnego wyjścia | HEVC/AV1 odblokowane, HDR/DV zablokowane | `NO_CHANGE` |
| `nuc-mwo` | Intel Iris Xe HEVC/AV1, brak aktywnego EDID | HDR/DV zablokowane | `NO_CHANGE` |
| `nuc-alek` | Intel Iris Xe HEVC/AV1, brak aktywnego EDID | HDR/DV zablokowane | `NO_CHANGE` |

Na wszystkich urządzeniach `remove.3D.sources=true`. Adapter Flatpak przy okazji
uzgodnił już istniejące wspólne wartości WatchNixtoons2, YouTube i Umbrella;
nie skopiował ani nie wypisał ustawień prywatnych.

## Odtworzenie testu

```bash
.venv/bin/python -m pytest -q \
  tests/test_kodi_managed_addon_settings.py \
  tests/test_kodi_flatpak_managed_addon_settings.py \
  tests/test_kodi_android_stable_rollout.py \
  tests/test_kodi_operations.py

.venv/bin/python tools/kodi_managed_addon_settings.py \
  --device bluestacks1 --serial 127.0.0.1:5555 \
  --adb /home/mwo/android-sdk/platform-tools/adb --adb-server-port 5038

.venv/bin/python tools/kodi_flatpak_managed_addon_settings.py audit \
  --device nuc-mwo
```

Oczekiwanym wynikiem drugiego przebiegu każdego adaptera jest `NO_CHANGE`.
