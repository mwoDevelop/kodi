# YouTube 7.4.4 — obejście zatrzymywania MPEG-DASH

Data testu: 2026-08-31

Urządzenie: BlueStacks1, Kodi 21.3

Dodatek: oficjalny `plugin.video.youtube` 7.4.4

InputStream Adaptive: 21.5.24

## Diagnoza

Problem odtworzono na BlueStacks przy włączonym MPEG-DASH. Po początkowym
buforowaniu dodatek używał klienta `ANDROID_VR`, a serwer GVS odpowiadał HTTP 403 na
kolejne zakresy strumienia. InputStream Adaptive ponawiał pobranie segmentu sześć
razy, po czym pojawiały się rosnące błędy synchronizacji audio i okresy bez postępu
odtwarzania.

Kodi używało domyślnych ustawień cache: `buffermode=4`, `memorysize=20 MiB`,
`readfactor=4.0` oraz `chunksize=128 KiB`. Objaw wynikał z odrzucania segmentów przez
serwer, dlatego zwiększenie globalnego cache nie było rozwiązaniem.

Diagnoza odpowiada zgłoszeniu upstream
[`plugin.video.youtube#1481`](https://github.com/anxdpanic/plugin.video.youtube/issues/1481).
Otwarty PR
[`plugin.video.youtube#1482`](https://github.com/anxdpanic/plugin.video.youtube/pull/1482)
nie został jeszcze włączony do wydania i nie jest wystarczającą podstawą do
modyfikowania oficjalnego dodatku w tym projekcie.

## Obejście

Polityka `manifests/kodi-managed-addon-settings.json` ustawia
`kodion.mpd.videos=false` wyłącznie dla wersji `7.4.4`. Dodatek przechodzi na
progresywny strumień bez wadliwej ścieżki `ANDROID_VR`. Kosztem jest maksymalna
jakość zwykłych filmów 720p. Zakres kończy się przed 7.4.5, aby przyszłej wersji nie
uznać automatycznie za wymagającą obejścia.

Uzgadnianie zarządzanych ustawień obejmuje teraz wszystkie zainstalowane, włączone
dodatki znajdujące się w polityce, także oficjalny YouTube instalowany po standardowym
adapterze stable. Dzięki temu czysta instalacja i kolejny rollout dochodzą do tego
samego stanu.

## Wynik

- pierwszy film po poprawce: obserwacja 100 s, postęp 92,7 s, zero HTTP 403, błędów
  segmentów, dużych błędów synchronizacji audio i okresów zatrzymania;
- drugi film wymieniony w zgłoszeniu upstream: obserwacja 90 s, postęp 91,0 s,
  start po 8,1 s i te same zerowe liczniki błędów;
- ponowny adapter stable: `NO_CHANGE`, 3 dodatki i 5 zarządzanych ustawień;
- standardowy `kodi_ops.py rollout --device bluestacks1`: `COMPLETE`, urządzenie
  `NO_CHANGE`, QNAP `NO_CHANGE`, pełna regresja `PASS` — 697 testów.

Odtwarzalna sonda:

```bash
.venv/bin/python tests/e2e/kodi_youtube_playback.py \
  --serial "$KODI_DEVICE_BLUESTACKS1_ADB" --observe-seconds 100
```

Raport sondy zapisuje tylko skrót identyfikatora filmu, postęp i zagregowane liczniki
diagnostyczne; nie utrwala URL-i odtwarzania ani sekretów.
