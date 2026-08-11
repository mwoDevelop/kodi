# Punkt kontrolny wdrożenia Bedroom TV

Data: 27.07.2026

Cel: urządzenie z prywatnym rejestrem `bedroom-tv` (Google TV Streamer, Android 14,
przestrzeń użytkownika ARMv7 Kodi).

## Ukończono

- inwentarz cyklu życia tylko do odczytu przekazany w Kodi 21.2;
- przed mutacją utworzono prywatną migawkę rollback;
- Kodi został zaktualizowany do wersji 21.3;
- zweryfikowana migawka Sony Android TV została przywrócona za pomocą ścieżki
  przywracania Kodi w procesie (4277 zarządzanych plików);
- Aktywowano Aeon Nox Silvo;
- `repository.mwodevelop` 1.0.0, Umbrella 6.7.81.14, MwoScrapers 0.1.3, opakowanie
  MwoScrapers 0.1.1 i WatchNixtoons2 0.25.2 były obecne z oczekiwanym pochodzeniem
  stable.

## Znaleziono defekty na żywo

1. Uszkodzona starsza wersja `plugin.video.pov/addon.xml` zawierająca tylko zero bajtów
   uniemożliwiała inwentaryzację migawek. Eksporter hosta zachowuje teraz uszkodzone
   bajty ładunku dla rollback, ale nie oznacza takiego dodatku jako bezpiecznego do
   ponownego włączenia.
2. Android 14 nie zezwalał na bezpośrednią ścieżkę profilu ADB, zanim Kodi go po raz
   pierwszy utworzył. Obiekt docelowy korzysta teraz z obsługiwanego trybu przywracania
   w procesie.
3. Google TV może zawiesić proces Kodi w tle, gdy ustawiony zostanie tryb HDMI/ambient.
   Urządzenie E2E musi obudzić cel i utrzymać Kodi na pierwszym planie.
4. Pierwsze sprawdzanie odtwarzania zostało zatrzymane przed rozwiązaniem dostawcy,
   ponieważ świeże przywracanie ma pusty znacznik wersji pamięci podręcznej Umbrella.
   Umbrella 6.7.81.15 traktuje ten starszy znacznik jako wersję zerową i jest
   publikowany w testing; stable pozostaje w wersji 6.7.81.14, dopóki nie minie ponowne
   uruchomienie urządzenia.
5. Automatyzacja urządzeń preferuje teraz Kodi JSON-RPC dla wbudowanych i zachowuje
   EventServer tylko jako rezerwę, unikając blokowania Android `nc`.

## Dowody dotyczące gospodarza i publikacji

- wszystkie 116 testów E2E repozytoriów głównych przeszło pomyślnie;
- Pomyślnie przeszło 40 testów downstream Umbrella i deterministyczną rekonstrukcję 27
  poprawek;
- publikacja testing workflow została ukończona pomyślnie:
  <https://github.com/mwoDevelop/kodi/actions/runs/30299301112>;
- publiczny indeks testing eksponuje Umbrella 6.7.81.15 i
  `service.mwodevelop.profilesync` 0.1.6.

## Powtarzalna kontynuacja

Po włączeniu zasilania Bedroom TV i autoryzacji ADB:

```bash
cd /home/mwo/projects/kodi

PYTHONPATH=. .venv/bin/python \
  tests/e2e/profile_sync_addon_device.py \
  --device bedroom-tv \
  --adb /home/mwo/android-sdk/platform-tools/adb \
  --adb-server-port 5037 \
  --server-repository /home/mwo/projects/kodi-profile-sync-server \
  --result .kodi-private/e2e/bedroom-tv-profile-sync-0.1.6.json
```

Następnie zainstaluj/zaktualizuj Umbrella 6.7.81.15 z kanału testing i ponownie uruchom
co najmniej jeden film i jeden odcinek za pomocą matrycy przelicznika. Przejdź do stable
dopiero wtedy, gdy dziennik usług nie zawiera świeżej pamięci podręcznej `ValueError` i
oba przypadki osiągną kontrolowane odtwarzanie.

## Odroczony cel

`mwonuc` nie zaakceptował protokołu TCP/22 podczas tego punktu kontrolnego. Nie można
bezpiecznie zakwalifikować ani wdrożyć jego wpisów do rejestru prywatnego ani kluczy SSH
przypisanych do konta, dopóki host nie będzie osiągalny; nie podjęto próby mutacji NUC.
