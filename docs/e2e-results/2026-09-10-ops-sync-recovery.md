# 10.09.2026 — naprawy operacji po handoverze agy/Grok

Plan i granice: [OPS_SYNC_RECOVERY_PLAN_2026-09-10.md](../OPS_SYNC_RECOVERY_PLAN_2026-09-10.md).
Odbiór floty PARTIAL; naprawa X88 i bramy WWW wykonana, ograniczenia poniżej.

## Implementacja

- Android: brama IDLE/ACTIVE/UNKNOWN również przed backupem, uninstall i
  restore; dry-run nie wywołuje portable adaptera, który może uruchomić Kodi.
- Flatpak: błąd `flatpak list` nie jest pustą instalacją; snapshot nie może
  zmieniać jawnego scope. NUC pozostaje `--user`, ACL Edge bez zmian.
- Rapideo: usunięty obowiązkowy eksport tokenu publishera; WAF odracza
  urządzenie bez retry całego adaptera. Tokeny i logi pozostają prywatne.
- Nowa wspólna polityka enrollmentu playback/favourites i uzgadnianie jej
  przy bootstrapie Android/Flatpak. Kontrola kanału, scope, capabilities,
  aktualnej generacji, nieudanego assignmentu i wyniku po zapisie.
- Stable sprawdza też zawartość plików ZIP przed NO_CHANGE, nie tylko bazę
  wersji Kodi. Probe Profile Sync pokazuje brak payloadu/ustawień i czasy cyklu.
- E2E używa osobnych katalogów `.e2e/run-*`, nie kasuje poprzednich dowodów.

## Testy lokalne i publiczne

- Bazowa regresja przed zmianami: 858 PASS.
- Pierwszy pełny E2E po implementacji: dwa identyczne buildy, 901 PASS
  (`.e2e/run-INoqbQ`). Późniejsze doprecyzowania mają osobne regresje;
  pełny aktualny zestaw uruchomiono ponownie w ramach scoped rolloutu.
- Scoped X88: ponownie dwa identyczne buildy i 903 PASS
  (`.e2e/run-i1XFM8`), operacja zakończona COMPLETE dla tego jednego celu.
- Końcowa regresja po naprawie blokady terminalnej: 912 PASS. Ponownie
  również deterministyczny build i 912 PASS (`.e2e/run-pfElr3`) w próbie
  Bedroom. Jedyny warning pochodzi z celowo zduplikowanego ZIP-a w teście.
- 7 testów klienta playback oraz 3 testy serwera: LWW, odrzucenie starego
  konfliktu, idempotencja, tombstone i fail-closed capabilities/opt-in PASS.
  To testy fixture, nie modyfikacje historii oglądania użytkownika.
- Publiczny smoke: 57/57 plików zgodnych z SHA-256.
- `git diff --check` i Ruff F821/F822/F823 PASS.

Odtwarzalne wywołania:

```bash
tests/e2e/run.sh
.venv/bin/python -m pytest -q profile-sync-addon/tests/test_playback.py
PYTHONPATH=../kodi-profile-sync-server/src .venv/bin/python -m pytest -q ../kodi-profile-sync-server/tests/test_store.py -k 'playback_lww or playback_idempotency or playback_is_fail_closed'
.venv/bin/python tools/smoke_public.py --base https://mwodevelop.github.io/kodi
.venv/bin/python tools/qnap_images.py status
.venv/bin/python tools/qnap_control_plane_gateway.py status
```

## Runtime

### X88

Probe wewnątrz Kodi wykazał brak plików Profile Sync i settings.xml,
UNPAIRED bez access tokenu/signing seed, mimo wpisu wersji 1.5.1 w bazie.
Log: 9.09 12:44 UTC NO_CHANGE, 18:44 UTC UNPAIRED. Nie ustalono sprawcy
usunięcia. Log zabezpieczony prywatnie przed zmianami.

Odbudowano dokładnie stabilny Profile Sync 1.5.1 transakcyjnym installerem.
Backend zabezpieczony backupem `ps-1789051055-x88-recovery-20260910-46b97a`.
Ponowne parowanie stworzyło generation 21 (utraconej tożsamości 20 nie
kopiowano). Pierwszy assignment ujawnił brak dalszych dodatków, m.in. Umbrella.
Scoped rollout `3d19872d284f4ab9836626ee3b106c1e` odbudował komplet stable:
adapter urządzenia PASS, Rapideo, YouTube, OpenSubtitles.com, providerzy i RD
PASS; 7 favourites, menu HEALTHY, Profile Sync APPLIED. `.org` VIP_REQUIRED
pozostaje ograniczeniem konta. Scoped rollout zakończony COMPLETE o 14:51 UTC.

Generation 21 ma playback/favourites enabled w scope:home, odczyt po zapisie
i kolejny dry-run NO_CHANGE. Kolejki obu mechanizmów: 0, stany HEALTHY.
Po pozytywnym assignment/heartbeat istniejącym mechanizmem CAS wycofano
wyłącznie starszą generation 20. Active/candidate kanału pozostawiono bez zmian.

Dodatkowo potwierdzono błąd cyklicznej pętli po naprawie: ręczny sync działał,
ale stary terminal fingerprint wstrzymywał scheduler. Hostowy adapter teraz
wycofuje taki błąd dopiero po zweryfikowanym sukcesie, z prywatnym backupem,
bez pending report/journalu/kwarantanny. Przeładowuje wyłącznie Profile Sync.
Live X88: cykl 14:56:30–14:56:32 UTC zakończony, heartbeat 14:56:59 UTC,
terminal block false; menu/playback/favourites HEALTHY. Ponowny converge:
NO_CHANGE, bez parowania i bez ponownego przeładowania usługi.
Polityka wszystkich sześciu najnowszych enrollmentów: NO_CHANGE.

### Pozostała flota

- Sony: NO_CHANGE, świeży heartbeat 10.09 14:38 UTC, menu/playback/favourites
  HEALTHY, brak terminalnej blokady. Podczas diagnozy wcześniejszy dry-run
  uruchomił Kodi przez portable audit; ten efekt uboczny został usunięty.
  Nie potwierdzono wcześniejszej awarii samego algorytmu synchronizacji Sony.
- NUC mwo/alek: oba osiągalne SSH, Kodi 21.3-Omega, scope user, ścieżki
  zakwalifikowane. Proces Kodi wyłączony; nie powtarzano reinstalacji.
- BlueStacks: port ADB niedostępny. Nie kwalifikowano nowego pakietu stable.
- Bedroom: początkowo offline, następnie dostęp ADB powrócił. Dry-run
  `f9e9486735ec4a678558486f30393757` potwierdził działający proces Kodi, ale
  playback UNKNOWN. Nie wolno wyłączać/restartować go ani przestawiać VPN
  przy takim wyniku. Próba Rapideo przez VPN pozostaje odroczona.
  Live apply `ae527d5038bc4abaa79f2a04c5605aee`: PARTIAL,
  `DEFERRED/playback_unknown`; bez mutacji celu, hostowe E2E PASS.

### QNAP, GitHub i GUI

- 7/7 kontenerów healthy; watchdog READY/HEALTHY, 12 workflow bez błędów.
- Niezależne GitHub API: ostatni zakończony przebieg każdego z 12 workflow
  success; rozróżniono schedule i workflow_dispatch. Bez dodatkowych dispatchy.
- Znaleziono HTTP 404 bramy WWW: brak dowiązania CGI przy poprawnie
  zainstalowanym QPKG 0.3.4. SHA skryptu startowego zgodne z repo; wykonano
  jego `start`, bez zmiany QTS, certyfikatów ani obrazów. `status`: cgi-ready.
  Przyczyna usunięcia dowiązania pozostaje nieustalona.
- CDP: działające logowanie i odświeżanie dashboardu. Panel zasadnie pokazał
  przejściowy ASSIGNMENT_FAILED/MULTIPLE_ACTIVE_GENERATIONS X88 podczas
  naprawy. Odbiór po naprawie: overall OK, 0 alertów, assignments 6/6,
  świeże Sony/X88 i cztery uczciwie oznaczone STALE. Przycisk wraca do
  aria-busy=false po odświeżeniu. Nie jest to dowód dostępności całej floty.

## Granice odbioru

Nie nazywać tego pełnym odbiorem floty, dopóki wskazane odroczenia pozostają.
Nie zmieniono wersji repo, dodatków ani obrazów; wdrażane były zatwierdzone
artefakty i konfiguracja, a nie nowy release pakietów. Copilot observe,
decyzja o zastanym kandydacie konfiguracji oraz zakup VIP pozostają poza zmianą.
