# Konwergencja menu Skin Shortcuts na całej flocie

Data: 2026-09-03

## Zakres

- aktywacja adaptera `kodi.skin_menu` po spełnieniu bramy capability;
- sprawdzenie BlueStacks, X88, Sony TV, Bedroom TV, `nuc-mwo` i `nuc-alek`;
- regresja Profile Sync, Favourites, stanu odtwarzania, dodatków domyślnych,
  providerów, Real-Debrid, YouTube i OpenSubtitles.com;
- weryfikacja powtarzalnego `NO_CHANGE` oraz odporności na restart Kodi.

## Wynik

Aktywna rewizja Profile Sync to generacja 7:

```text
sha256:63a8026e6454713ebbd18e9cdd9660e194ad99e0f90e224819922a963a72e6dc
```

BlueStacks i X88 zwróciły zgodność źródła oraz wygenerowanego menu `4/4`
przed i po restarcie, a kolejny przebieg zakończył się `NO_CHANGE`.
Sony TV, Bedroom TV i `nuc-mwo` osiągnęły aktywną rewizję bez regresji.

Na `nuc-alek` nie istniał poprzednio kanoniczny plik źródłowy Skin
Shortcuts. Wykonano jednorazowy bootstrap tego pliku przy zatrzymanym Kodi, a
następnie dwukrotnie uruchomiono rollout Flatpak. Pierwszy przebieg zastosował
rewizję, drugi potwierdził:

```text
sync_status=NO_CHANGE
skin_menu_status=HEALTHY
favourites_status=HEALTHY
playback_status=HEALTHY
```

Po uruchomieniu Kodi w sesji KDE menu źródłowe i wygenerowane zawierało
dokładnie `programs`, `settings`, `favourites`, `playdisc`. Nie występowały
odnośniki do Fen Light. Pozostałe katalogi diagnostyczne po dwóch przerwanych
próbach zostały usunięte po potwierdzeniu braku korzystających z nich procesów.

## Naprawione usterki narzędzi

1. Sonda menu Androida odczytuje stan wewnątrz Kodi. Eliminuje to fałszywy
   błąd `Permission denied`, gdy atomowo zapisany plik prywatny ma tryb `0600`.
2. Wywołanie EventServer na Flatpak zachowuje jedno gniazdo UDP dla pakietów
   `HELLO`, `ACTION` i `BYE`; wcześniejszy osobny proces `nc` dla każdego pakietu
   mógł spowodować ciche pominięcie akcji przez Kodi.
3. Wynik rolloutu Flatpak zawiera zredagowane pole `skin_menu_status`, dzięki
   czemu zgodność menu jest widoczna w dowodach operacyjnych.
4. Cleanup Flatpak ma fallback ograniczony do aplikacji `tv.kodi.Kodi`. Usuwa
   on osierocony proces sandboxa, gdy launcher zdążył zakończyć się przed
   sprzątaniem swojej grupy procesów.

## Odtworzenie

Testy jednostkowe i integracyjne:

```bash
.venv/bin/python -m pytest -q \
  tests/test_kodi_profile_sync_state.py \
  tests/test_profile_sync_portable_release.py \
  tests/test_kodi_flatpak_profile_sync_rollout.py
python3 -m pytest
```

Rollout i ponowienie przerwanego przebiegu:

```bash
.venv/bin/python tools/kodi_ops.py rollout --full-diagnostics
.venv/bin/python tools/kodi_ops.py rollout \
  --resume a7fb7020ec674a8984a988952c79b5d3
```

Stan usług QNAP sprawdzono poleceniem:

```bash
.venv/bin/python tools/qnap_images.py status
```

Dowody prywatne rolloutu pozostają w niesłedzonym katalogu
`.kodi-private/kodi-ops/runs/` i nie zawierają się w repozytorium.
