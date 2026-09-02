# Deklaratywna synchronizacja menu Aeon Nox Silvo

Data: 2026-09-02  
Zakres: Profile Sync, menu główne Aeon Nox Silvo, QNAP, BlueStacks, X88 i Sony TV  
Prywatność: raport nie zawiera sekretów, tokenów ani identyfikatorów enrollmentu.

## Wydany artefakt

- Profile Sync 1.5.0, commit
  `3f77fe5b52d2ed91babf5250763682a99bd8fe5f`, ZIP SHA-256
  `33ee831da191483e769bd73020c782fc11cca60ce1645de19d8073d6c016c2b0`;
- testing lock został scalony w PR #319, a certyfikowany stable lock w PR #320;
- snapshot `5d90f9f818596c1e9bcc39c11e0242dee0fd98ca7a3e329a1a70b356e079fbff`
  przeszedł skan bezpieczeństwa, certyfikację BlueStacks/X88 i publikację 57
  publicznych plików.

## Wyniki

1. Testy komponentu Profile Sync: 78 zaliczonych testów.
2. Pełna regresja repozytorium przed i podczas wydania: 742 zaliczone testy.
3. Certyfikacja urządzeń potwierdziła instalację Profile Sync 1.5.0 na
   BlueStacks i X88 oraz działanie Umbrella/Real-Debrid i WatchNixtoons2.
   Pierwsza próba na X88 utraciła transport ADB. Po ponownym połączeniu ten sam
   test WatchNixtoons2 przeszedł z katalogiem, rozwiązaniem źródła i 15 sekundami
   odtwarzania; ponowiona pełna certyfikacja także przeszła.
4. Dwa pełne rollouty potwierdziły na BlueStacks, X88 i Sony: stable, domyślne
   dodatki, MwoScrapers, Real-Debrid, Rapideo, OpenSubtitles.com, YouTube,
   Favourites i stan przenośny. QNAP raportował siedem usług bez alertów.
5. OpenSubtitles.org zachowuje znany status `VIP_REQUIRED`; działająca usługa
   OpenSubtitles.com przeszła test.

## Kontrolowane odroczenie

Podczas obu rolloutów `bedroom-tv`, `nuc-mwo` i `nuc-alek` były nieosiągalne.
Brama floty zwróciła `DEFERRED_CAPABILITY` wyłącznie dla tych trzech profili i
nie opublikowała częściowej rewizji menu. Sonda semantyczna stanu przed
aktywacją wykazała:

| Urządzenie | Źródło | Include wygenerowany | Liczba pozycji |
|---|---:|---:|---:|
| BlueStacks | różne od kontraktu | różne od kontraktu | 4 |
| X88 | różne od kontraktu | różne od kontraktu | 6 |
| Sony TV | zgodne | zgodne | 4 |

Po uruchomieniu brakujących klientów pierwszy rollout ma zaktualizować ich
Profile Sync i heartbeat, a drugi ma aktywować rewizję menu, wykonać ścisłą
weryfikację canary, restart Kodi oraz próbę `NO_CHANGE`.

## Powtarzalne polecenia

```bash
cd /home/mwo/projects/kodi
tests/e2e/run.sh

cd /home/mwo/projects/kodi/profile-sync-addon
PYTHONPATH=resources/lib ../.venv/bin/python -m pytest -q

cd /home/mwo/projects/kodi
.venv/bin/python tools/kodi_ops.py rollout
```

Końcową semantyczną sondę urządzeń wykonuje funkcja `probe_device` z
`tools/kodi_skin_menu.py`; ten sam rygorystyczny parser jest używany przez bramę
canary rolloutu.
