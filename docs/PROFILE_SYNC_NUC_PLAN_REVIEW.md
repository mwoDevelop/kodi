# Recenzja planu Profile Sync: NUC, Flatpak i wiele kont

Data: 2026-07-27

Zakres: niezależne sprawdzenie `PROFILE_SYNC_PLAN.md` po dodaniu Bedroom TV
oraz NUC Linux/Flatpak z dwoma kontami. Reviewer porównał plan z aktualnymi
kontraktami w repozytoriach `kodi`, `service.mwodevelop.profilesync` i
`kodi-profile-sync-server`. Reviewer nie edytował plików.

## Werdykt

Kierunek jest spójny, ale plan w poprzedniej postaci nie był jeszcze gotowy do
implementacji Linux/Flatpak. Mieszał transport SSH z lifecycle Flatpaka,
zakładał nieistniejącą ścieżkę migracji registry i profilu oraz zbyt szeroko
opisywał izolację Flatpaka. Kolejność publikacji i E2E była odwrócona.

## Zaakceptowane P0

1. Registry schema 1 -> 2 otrzymuje reader obu wersji, normalizację do modelu
   wewnętrznego v2, idempotentną i atomową migrację z backupem oraz zapis
   wyłącznie v2. Android-only reinstall odrzuca Linux do czasu dispatchera.
2. SSH zostaje oddzielony od platformy. Neutralne `AdbTransport` i
   `SshTransport` są komponowane z `AndroidKodiLifecycle` albo
   `FlatpakKodiLifecycle`; kod profilu nie dostaje dowolnego `run`.
3. Bootstrap NUC wymaga zweryfikowanego UID/home, discovery ścieżek wewnątrz
   Flatpaka, canonicalizacji, kontroli ownera i symlinków oraz zatrzymanego
   procesu właściwego konta. Zwykła sesja SSH nie jest uznawana za sesję GUI.
4. Produkcyjny TLS przechodzi test w Pythonie/OpenSSL rzeczywistego Kodi
   Android i Flatpak. MVP używa zaufanego certyfikatu/CA; pinning jest osobnym
   etapem, a test `curl` hosta nie jest dowodem.
5. Porównanie z aktualną implementacją ujawniło dodatkowy blocker: schema 2
   rewizji nie opisuje warstw platformowych. Przed ich apply powstaje schema 3,
   przy zachowaniu odczytu schema 2. Do tego czasu Linux może wykonać tylko
   read-only i portable common subset.

## Zaakceptowane P1

1. `principal_id` jest prywatnym, stabilnym i nieprzezroczystym ID. Login jest
   dostępny tylko przez `user_ref`; dane hosta/principala nie są autoryzacją.
2. Klasy kompatybilności są przypisywane administracyjnie enrollmentowi.
   Heartbeat może raportować obserwacje, ale self-report nie wybiera warstwy
   ani nie autoryzuje promocji.
3. Canary jest bramkowany klasami: Android emulator, Android TV według
   faktycznego ABI i Linux Flatpak x86_64. Test izolacji obu kont jest
   obowiązkowy, lecz oba konta nie blokują każdej promocji.
4. Kolejność wydania to `unit/local -> build -> testing -> device E2E ->
   obserwacja -> ręczne stable`.
5. Smoke 6A ma jawne zależności, osobne tunele/control sockety, loopback,
   `ExitOnForwardFailure` i gwarantowany cleanup. Bazowy smoke Android nie
   czeka na niegotową obsługę Linux; pełny smoke jest późniejszym rerunem.
6. Bootstrap repo używa wspieranej ścieżki Kodi. Gdy nie istnieje
   zakwalifikowany import bez UI, kończy się `BOOTSTRAP_REQUIRES_USER`; nie
   rozpakowuje kodu do `addons` i nie modyfikuje `Addons*.db`.
7. Istniejące dodatki `nuc-mwo` wymagają inventory origin i kontrolowanej
   migracji przez Kodi po backupie. Czystsze `nuc-alek` jest pierwszym canary.
8. Flatpak nie chroni tokenu przed tym samym użytkownikiem Unix ani
   administratorem. Granicą jest konto systemowe, a profil Profile Sync jest
   wykluczony ze snapshotów.

## Zaakceptowane P2

- operacje profilowe mają lock per `(physical_host_id, principal_id)`, a lock
  hosta tylko dla wspólnych operacji;
- synchronizator ma nie kopiować ani bezpośrednio modyfikować cache/DB/
  Thumbnails; samo Kodi może je legalnie zmienić;
- klucze SSH są osobnymi plikami wskazywanymi przez referencję, z przypiętym
  `known_hosts`, bez sudo i agent forwarding;
- ABI Bedroom TV jest wykrywaną listą `ro.product.cpu.abilist` i ABI APK, nie
  założoną pojedynczą wartością.

## Świadomie odroczone

- pinning certyfikatu w dodatku: odroczony, jeśli MVP potwierdzi poprawny
  publiczny lub prywatny trust chain wewnątrz obu runtime'ów Kodi;
- automatyczne uruchamianie GUI Kodi przez SSH: nie jest wymaganiem. Dopuszczony
  jest kontrolowany krok użytkownika;
- hostowy overlay: usunięty z MVP. `physical_host_id` pozostaje inventory i
  lockingiem, aby nie łączyć ustawień dwóch principalów.

## Wynik

Plan po poprawkach ma kolejność:

```text
registry v2
  -> neutralny transport + platform lifecycle
  -> per-account enrollment i administracyjne capability tags
  -> profile revision schema 3
  -> build i testing
  -> canary/E2E według klas
  -> obserwacja
  -> ręczne stable/active
```
