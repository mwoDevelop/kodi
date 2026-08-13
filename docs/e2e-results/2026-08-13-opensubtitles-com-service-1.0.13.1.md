# OpenSubtitles.com jako domyślna usługa Kodi

Data próby: 2026-08-13.

## Zakres

- fork `mwoDevelop/service.subtitles.opensubtitles-com` wersji `1.0.13.1` jest
  budowany deterministycznie jako zarządzany składnik repozytorium Kodi;
- dodatek ma nazwę `OpenSubtitles.com (mwoDevelop)` i nie zapisuje w logu loginu,
  hasła, tokenu, nagłówka autoryzacji ani pełnych odpowiedzi API;
- rollout ustawia konto z prywatnych referencji, sprawdza login i wyszukiwanie,
  a następnie wybiera `.com` jako domyślną usługę napisów filmów i seriali;
- OpenSubtitles.org pozostaje włączoną alternatywą w tym samym menu.

## Kanarki

| Urządzenie | Wersja `.com` | Wyszukiwanie PL | Kontrolne pobranie | Domyślna usługa | Menu Kodi |
|---|---:|---:|---:|---:|---:|
| BlueStacks1 | 1.0.13.1 | 25 wyników, HTTP 200 | 57 281 B, HTTP 200 | `.com` dla filmów i TV | oba dodatki, okno 10153 |
| X88 Pro 20 | 1.0.13.1 | 25 wyników, HTTP 200 | 57 281 B, HTTP 200 | `.com` dla filmów i TV | oba dodatki, okno 10153 |

Pobrany plik przeszedł kontrolę treści SRT i nie był HTML-em ani banerem VIP.
Test okna napisów uruchomił rzeczywiste odtwarzanie i potwierdził przez JSON-RPC
okno `Subtitle search` (`id=10153`). Na BlueStacks dodatkowo zachowano prywatny,
ignorowany przez Git zrzut ekranu pokazujący równocześnie `OpenSubtitles.org` oraz
`OpenSubtitles.com (mwoDevelop)`.

Powtarzalna sonda:

```bash
.venv/bin/python tests/e2e/kodi_subtitle_menu_probe.py \
  --adb-server-port 5038 --serial ADB_ENDPOINT
```

Jeżeli VPN urządzenia blokuje publiczny film kontrolny, można wskazać lokalny plik
Kodi przez `--media /sdcard/Download/probe.mp4`; walidacja usług, ustawień i okna
pozostaje taka sama.
