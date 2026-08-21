# Model zagrożeń QNAP Control Plane

## Aktywa

- tożsamości enrollmentów i stan floty;
- historia rolloutów i raportów;
- zaszyfrowane secret sety użytkownika oraz klucz główny Secret Brokera;
- integralność repo stable oraz konfiguracji urządzeń.

## Granice zaufania

- LAN nie jest uznawany za zaufany tylko dlatego, że jest lokalny;
- QTS root może odczytać pamięć i pliki kontenera, więc projekt nie obiecuje
  ochrony plaintextu przed przejętym rootem QNAP;
- przejęte urządzenie nie może czytać danych innego enrollmentu;
- GitHub pozostaje źródłem kodu, ale sam status workflow nie jest dowodem
  dokładnych bajtów;
- host deweloperski pozostaje break-glass do czasu pełnego cutoveru.

## Zabezpieczenia pierwszego przyrostu

- obowiązkowe mTLS dla API operatora i integracji Profile Sync, z osobnymi
  korzeniami zaufania dla operatorów i klientów integracyjnych;
- health/readiness tylko na loopback kontenera;
- brak mutującego GUI; operacje lifecycle Secret Brokera są ograniczone do
  audytowanego CLI przez SSH i stdin;
- oddzielny kontrakt integracyjny zamiast bezpośredniego SQLite;
- rekursywna redakcja przed zapisem cache/audytu;
- łańcuch SHA-256 audytu oraz checkpoint HMAC z kluczem poza bazą;
- backup online, integralność SQLite, digest i restore wyłącznie do pustego celu;
- obrazy read-only, non-root, `cap_drop: ALL`, `no-new-privileges` i digest GHCR.

## Jawne ryzyka pozostające do kolejnych faz

- checkpoint na tym samym QNAP nie dowodzi historii wobec przejętego root QTS;
  przed cutoverem wymagany jest cykliczny eksport poza QNAP;
- HMAC jest mechanizmem przejściowym dla read-only audytu, nie kluczem promotora;
- GitHub App, WebAuthn i delegated assignment key nie są częścią tego release;
  mutacje sekretów nie są dostępne w GUI;
- brak dostępności QNAP oznacza brak nowych operacji administracyjnych, lecz nie
  unieważnia ostatniej działającej konfiguracji Kodi.

## YouTube OAuth w release 1

- API key, client ID i client secret są dostarczane wyłącznie przez prywatne
  referencje; nie trafiają do Git, raportów ani Profile Sync;
- po zastosowaniu na urządzeniu wartości mogą zostać odczytane przez przejęty system,
  dlatego klient ma minimalne scope, a API key jest ograniczony do YouTube Data API;
- trzy refresh tokeny tworzą jeden wspólny fleet secret set przechowywany
  zaszyfrowanie na QNAP. Profile Sync transportuje wyłącznie kopertę HPKE dla
  konkretnego enrollmentu, a Agent zapisuje dane tylko w profilu oficjalnego
  dodatku YouTube;
- `YOUTUBE_USER` jest tylko lokalną wskazówką operatora, a `YOUTUBE_PASS` jest jawnie
  odrzucany. Device flow nie automatyzuje formularza Google, CAPTCHA ani 2FA;
- wszystkie trzy tokeny mają scope `https://www.googleapis.com/auth/youtube`,
  wymagany przez kwalifikowaną wersję oficjalnego dodatku. Ryzyko jest ograniczane
  dedykowanym kontem, nie deklaracją niezgodnego scope `youtube.readonly`;
- niedostępność QNAP nie unieważnia już zapisanej sesji. Czysta reinstalacja nie
  odzyska jej do czasu powrotu Broker/Profile Sync, ale nie wymaga ponownej zgody,
  jeżeli aktywny secret set i enrollment są dostępne.
