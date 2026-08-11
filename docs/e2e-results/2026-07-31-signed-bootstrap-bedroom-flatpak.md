# Kwalifikacja podpisanej inicjalizacji, Bedroom TV i Flatpak

Data: 2026-07-31

## Zwolniono ścieżkę serwera

- `kodi-profile-sync-server` 0.2.2 został połączony i oznaczony po 21 testach
  jednostkowych i pomyślnym przejściu pętli zwrotnej E2E z zweryfikowanym podpisem.
- Wydanie workflow zweryfikowało `linux/amd64` i `linux/arm/v7` pod kątem niezmiennego
  podsumowania obrazu
  `sha256:11e1abac86c4ca1ec9e53106617f8bc1ef78cb3448641d315ad03f94e9b14e63`.
- Inspekcja wstępna QNAP zgłosiła RAID `UU`, brak odzyskiwania, a następnie przed
  wdrożeniem pobrano kopię zapasową bazy danych o rozmiarze 69 632 bajtów ze sprawdzoną
  integralnością.
- Produkcja została gotowa na serwerze 0.2.2, kompilacja
  `git:955ecee87787356d5cd7ed9490f7a42aaf175959`, schemat bazy danych 2, z jednym
  kontenerem, jedną siecią i bez wolumenu Docker.

Interfejs API ładowania początkowego akceptuje jedynie przypisanie podpisane przez
promotora w trybie offline w przypadku istniejącej, nieodwołanej rejestracji. Kanał,
dokładna aktywna wersja i posortowane administracyjne znaczniki docelowe muszą
odpowiadać stanowi serwera. Zwolnieni klienci otrzymują już obsługiwany podpisany
kształt przypisania `candidate`; serwer nigdy nie przechowuje materiału siewnego
promotora.

## Bedroom TV

- Kodi 21.3 i Profile Sync 0.1.8 pochodzą z stable.
- Unikalna rejestracja produkcyjna na `home-stable` ze znacznikami administracyjnymi
  `home` i `android-tv:armeabi-v7a`.
- Podpisany aktywny bootstrap został zaakceptowany, zastosowano dokładną aktywną wersję,
  podpisany raport o powodzeniu został zapisany i nie pozostał żaden oczekujący raport.
- Audyt po wdrożeniu: 8 ulubionych, 7 przenośnych działań WatchNixtoons2, brak
  brakujących grafik, spójna tożsamość urządzenia, skonfigurowany prywatny urząd
  certyfikacji i punkt końcowy HTTPS.
- NordVPN 9.9.2-tv udostępnił sprawdzony, niemożliwy do obejścia transport VPN
  obejmujący wszystkie identyfikatory UID. Umbrella 6.7.81.18 zwrócił pasujące wyniki
  wyszukiwania filmów i programów telewizyjnych po przebudzeniu Kodi z trybu snu Android
  TV. Upłynął limit czasu pierwszej ponownej próby telewizora, gdy urządzenie śniło; ten
  sam test przeszedł po jawnym przebudzeniu, więc był to raczej stan cyklu życia niż
  regresja modułu rozpoznawania nazw.

## Linux Flatpak

Zarówno `nuc-mwo`, jak i `nuc-alek` przeszły kontrolę przypiętej tożsamości SSH,
właściciela, kanonicznego katalogu głównego danych, Kodi 21.3-Omega i x86_64. Zmapowany
własny dziennik wykonawczy Kodi:

- `special://home` do kanonicznego katalogu głównego danych dla każdego konta Flatpak;
- `special://masterprofile` i `special://profile` do katalogu `userdata` tego konta;
- `special://envhome` do dokładnego konta domowego konta SSH.

Cykl życia sprawdza teraz te mapowania oraz właściciela/typ dziennika przed oznaczeniem
kwalifikujących się ścieżek środowiska wykonawczego. NUC zawieszony podczas testowania
repozytorium, stał się nieosiągalny na SSH i nie wybudził się ze standardowego pakietu
magicznego. Dlatego żadna instalacja repozytorium, rejestracja ani mutacja stanu
przenośnego nie są zgłaszane jako zakończone w przypadku żadnego konta NUC.

## X88 Pro 20

NordVPN 9.9.2 sideload-tv nadal nie generuje klucza Android Keystore za pomocą
`ProviderException` / `KeyStoreException: Unknown error`. Urządzenie nie udostępnia
żadnej funkcji StrongBox i pozostaje objęte poprawką zabezpieczeń z 2021 r. Nie jest
tworzony żaden transport VPN. Jest to zachowywane jako ograniczenie
sprzętu/oprogramowania sprzętowego; nie zastosowano żadnego obniżenia wersji ani
obejścia zabezpieczeń.
