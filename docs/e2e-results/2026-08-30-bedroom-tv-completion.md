# Dokończenie rolloutu Bedroom TV

Data testu: 2026-08-30.

## Rollout

Scoped rollout `f68353469d064efbbd740a947e391fa7` zakończył się statusem
`COMPLETE`:

- stable, domyślne dodatki, providery, Rapideo, OpenSubtitles.com i YouTube:
  `pass`;
- mwoScrapers i Real-Debrid: zaliczone w pierwszej próbie;
- Profile Sync i prywatne ustawienia Umbrella: `NO_CHANGE`;
- portable state: `CONVERGED`, 9 favourites, bez brakujących grafik;
- QNAP: 7 usług, brak unhealthy i alertów;
- pełne `tests/e2e/run.sh`: `666 passed`.

OpenSubtitles.org nadal zwraca znany stan `VIP_REQUIRED`; nie blokuje działającego
OpenSubtitles.com ani rolloutu.

## NordVPN

Natywny NordVPN jest aktywny i zweryfikowany. Android 14 publikuje sieć jako
`ni{VPN CONNECTED}` z `OwnerUid`, podczas gdy starszy Android Sony używa
`type: VPN[]`, `state: CONNECTED/CONNECTED` i `EstablishingAppUid`.

Lista UID tunelu wyklucza wyłącznie UID Netflixa oraz odpowiadający mu UID SDK
Sandbox. Android zapewnia mapowanie 1:1 pomiędzy procesem aplikacji i jej SDK
Sandbox przez stałe zakresy UID. Kodi pozostaje objęte tunelem. Po rozszerzeniu
audytora o oba formaty i UID SDK Sandbox zarówno Bedroom TV, jak i Sony TV
zakończyły audyt wynikiem `compliant: true` (8/8).

Po poprawce audytora test regresyjny oraz pełne repozytoryjne
`tests/e2e/run.sh` zakończyły się wynikiem `667 passed`.

Źródło modelu UID:
[AOSP `android.os.Process`](https://android.googlesource.com/platform/frameworks/base/+/HEAD/core/java/android/os/Process.java).
