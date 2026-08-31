# Pełny rollout synchronizacji stanu odtwarzania

Data: 2026-08-31  
Zakres: wszystkie aktywne urządzenia Kodi, Profile Sync i usługi QNAP  
Prywatność: raport nie zawiera tytułów, URL-i, tokenów, adresów wyjściowych VPN ani
identyfikatorów enrollmentu.

## Zakres wdrożenia

Po zakwalifikowaniu canary wdrożono stable na sześciu celach:

- BlueStacks;
- X88 Pro 20;
- Sony TV;
- Bedroom TV;
- NUC, profil `mwo`;
- NUC, profil `alek`.

Rollout `c92631c91bb54a488eca2cee51be2281` zakończył się stanem `COMPLETE`.
BlueStacks pozostał `NO_CHANGE`, a pozostałe cele zakończyły się `PASS`. Usługi
QNAP i Profile Sync nie wymagały zmiany obrazu.

## Usterki wykryte podczas rolloutu

1. Bedroom TV był osiągalny, ale uśpiony. Audyt sprawdzał jedynie PID Kodi, dlatego
   oczekiwał na nieaktywny EventServer i zgłaszał mylący timeout. Narzędzie
   przenośnego stanu budzi teraz Androida, zdejmuje keyguard i zawsze czeka na
   faktyczną gotowość Kodi. Test regresji rozpoczęty jawnie ze stanu `Asleep`
   zakończył się pełnym audytem 9 favourites, 8 skrótów WatchNixtoons2 i kompletu
   grafik.
2. X88 zwracał z Rapideo stronę HTML zamiast JSON. Tunel OpenVPN był technicznie
   zdrowy, ale używał profilu PL314. Po przełączeniu na istniejący profil
   `NordVPN PL145 UDP Auto X88` endpoint konta ponownie zwrócił poprawny JSON,
   autoryzacja przeszła, a token nie wymagał rotacji.
3. Manifest X88 nadal deklarował PL314, a audyt nie porównywał nazwy aktywnego
   profilu. Audyt odczytuje ją teraz z interfejsu OpenVPN i fail-closed wykrywa
   rozbieżność. Żywy audyt X88 przeszedł 10/10 kontroli dla PL145.
4. Control Plane po wdrożeniu pokazał dwie aktywne generacje X88. Prywatny plan CAS
   wskazał wyłącznie starszą generację 15; apply unieważnił ją po potwierdzeniu
   świeżej generacji 16. Nie zmieniono enrollmentów pozostałych urządzeń.

## Weryfikacja synchronizacji playback

Playback LWW włączono dopiero po zakończeniu stabilnego rolloutu, osobno dla
dokładnie aktywnego enrollmentu każdego z sześciu urządzeń. Wszystkie korzystają ze
wspólnego `scope:home`.

Końcowe sondy klientów potwierdziły:

- `playback_status=HEALTHY` na 6/6 urządzeń;
- wspólny cursor 9;
- zero oczekujących eventów i zero błędów;
- brak oczekujących aplikacji; pozostające mapowania są spodziewane, dopóki dane
  urządzenie nie otworzy odpowiadającej im pozycji WatchNixtoons2.

Ponowne uruchomienie Kodi na czterech Androidach oraz ponowna stabilna konwergencja
obu profili Flatpak zachowały ten sam stan. Pełna hermetyczna macierz repozytorium
zakończyła się wynikiem 691 testów w dwóch kolejnych przebiegach rolloutu, a po
dodaniu regresji aktywnego profilu OpenVPN końcowy przebieg przeszedł 692 testy.

## Końcowy stan operacyjny

Wymuszone odświeżenie Control Plane potwierdziło:

- `overall_state=OK` i stan floty `OK`;
- 6/6 świeżych urządzeń i enrollment `OK` dla każdego celu;
- playback aktywny na każdym urządzeniu w `scope:home`;
- zdrowe usługi i procesy cykliczne;
- zero otwartych alertów.

Wszystkie siedem usług QNAP działa jako `running/healthy` na digestach zgodnych z
lockiem. Nie utworzono nowej wersji dodatków ani nowego wdrożenia obrazów, ponieważ
zmiana dotyczyła narzędzia hosta, dokumentacji i deklaratywnego profilu X88, a
publiczne artefakty stable nie uległy zmianie.

## Świadome ograniczenia

- OpenSubtitles.com działa i pozostaje domyślną usługą napisów.
- OpenSubtitles.org nadal odpowiada `VIP_REQUIRED`; jest to ograniczenie konta tej
  usługi, nie regresja rolloutu ani Profile Sync.
- Rapideo pozostaje fail-closed przy niepoprawnej odpowiedzi endpointu; X88 po
  przełączeniu na PL145 przechodzi kontrolę poprawnego JSON.
