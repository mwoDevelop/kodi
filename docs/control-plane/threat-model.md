# Model zagrożeń QNAP Control Plane

## Aktywa

- tożsamości enrollmentów i stan floty;
- historia rolloutów i raportów;
- w dalszych fazach: sekrety użytkownika, release intent i klucze assignment;
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
- brak endpointów mutujących i brak magazynu sekretów;
- oddzielny kontrakt integracyjny zamiast bezpośredniego SQLite;
- rekursywna redakcja przed zapisem cache/audytu;
- łańcuch SHA-256 audytu oraz checkpoint HMAC z kluczem poza bazą;
- backup online, integralność SQLite, digest i restore wyłącznie do pustego celu;
- obrazy read-only, non-root, `cap_drop: ALL`, `no-new-privileges` i digest GHCR.

## Jawne ryzyka pozostające do kolejnych faz

- checkpoint na tym samym QNAP nie dowodzi historii wobec przejętego root QTS;
  przed cutoverem wymagany jest cykliczny eksport poza QNAP;
- HMAC jest mechanizmem przejściowym dla read-only audytu, nie kluczem promotora;
- GitHub App, WebAuthn, delegated assignment key i secret envelopes nie są częścią
  tego release i żadna mutacja nie może od nich pozornie zależeć;
- brak dostępności QNAP oznacza brak nowych operacji administracyjnych, lecz nie
  unieważnia ostatniej działającej konfiguracji Kodi.
