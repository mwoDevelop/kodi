# Odnowienie sesji Kodi admin przez QTS — E2E 2026-08-28

## Zakres

Test kwalifikuje poprawkę przypadku, w którym przeterminowana sesja Control Plane
pozostawała w cookie przeglądarki. Gateway uznawał samą obecność cookie za dowód
ważnej sesji, pomijał QTS SSO, a backend kierował użytkownika na formularz
logowania. Dodatkowo otwarta karta mogła zachować stary dashboard i wyświetlać
`HTTP 401` podczas odświeżania.

## Wydane artefakty

- Control Plane `0.9.1`, commit `0dd174f916eff4a6464600f08af11dac38335610`;
- obraz `ghcr.io/mwodevelop/kodi-control-plane@sha256:d32da3dd56690f1db0e78c5ae149a886d0fd20b3d556a574561441bef7926780`;
- build, skan i approval: [GitHub Actions 33209431443](https://github.com/mwoDevelop/kodi-control-plane/actions/runs/33209431443);
- QPKG `KodiCPGateway` `0.3.2`;
- zmiany i stable lock: [PR mwoDevelop/kodi #285](https://github.com/mwoDevelop/kodi/pull/285).

W złożonym locku QNAP zmienił się wyłącznie `control-plane`. Digesty
`profile-sync`, `provider-relay`, `secret-broker` i `upstream-watchdog` pozostały
identyczne.

## Automatyczna regresja

- pełne testy repozytorium Kodi: `661 passed`;
- pełne testy Control Plane: `75 passed`;
- testy gatewaya: `10 passed`;
- testy locka, obrazów i wdrożenia QNAP: `53 passed`;
- dwa wymagane przebiegi E2E PR #285: `PASS`.

## Test produkcyjny QNAP

Po wdrożeniu wszystkie trzy kontenery Control Plane działały jako `healthy` na
zatwierdzonym digescie. Gateway raportował wersję `0.3.2`, aktywne CGI i brak
publikowanej usługi sieciowej.

W przeglądarce podłączonej przez CDP wykonano dwa kontrolowane scenariusze:

1. Istniejąca karta rzeczywiście prezentowała wcześniejszy błąd `HTTP 401`.
   Po wejściu ponownie na główną trasę gateway zweryfikował cookie po loopback,
   wykorzystał nadal ważną administracyjną sesję QTS i otworzył dashboard bez
   formularza logowania.
2. Aktualną sesję oznaczono jako przeterminowaną, kartę Control Plane zamknięto,
   a skrót **Kodi admin** uruchomiono natywnym podwójnym kliknięciem na pulpicie
   QTS. Nowa karta ponownie otworzyła dashboard bez formularza.

W obu przypadkach końcowy stan interfejsu wynosił `OK`, komunikat błędu był pusty,
a przycisk **Odśwież stan** zakończył ponowne zebranie danych. Po weryfikacji baza
authz zawierała jedną aktualną sesję; przeterminowane rekordy zostały usunięte.

Raport jest dowodem punktowym z 2026-08-28 i nie zastępuje bieżącego monitoringu.
