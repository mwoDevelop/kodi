# Review planu pozostałych zadań — 9 września 2026

Przedmiot: [`REMAINING_OPS_PLAN_2026-09-09.md`](REMAINING_OPS_PLAN_2026-09-09.md).
Tryb: niezależny challenge spójności i logiki, bez implementacji.
Werdykt: plan jest wykonalny jako lista prac, ale **nie był spójnym runbookiem
jednej sesji**. Główne ryzyko: mieszanie numeracji handoveru z kolejnością
realizacji oraz sukces NUC/Gateway/cron bez wystarczającego dowodu.

Poniższe znaleziska **zastosowano** w zaktualizowanym planie, o ile nie
oznaczono inaczej.

## Zastosowane

1. **Blocker — sprzeczna numeracja.** Handover, nagłówki `## 1–7` i lista
   wykonania mówiły trzy różne rzeczy; Bedroom odwoływał się do „punktu 5”
   (Copilot zamiast kandydata Profile Sync). Jedna kanoniczna numeracja
   wykonania + mapa handoveru.
2. **Important — Bedroom nie czeka na merge NUC / Gateway / native cron.**
   Bedroom jest Androidem; jedyny wymóg narzędziowy to walidator rozumiejący
   już obecne `flatpak_scope` w całym inventory.
3. **Important — cherry-pick ≠ prywatne `devices.json`.** Inventory zostaje
   lokalne. Sukces NUC: PR + CI; merge opcjonalny. Potem live inventory,
   nie sam dry-run.
4. **Blocker — Gateway `Version=0.3.4` ≠ tożsamość bajtów.** Przed commitem
   porównać SHA zainstalowanych plików z QNAP. Zgodność → commit bez deploy.
   Różnica → STOP, nie instalować „dla pewności”.
5. **Important — native `schedule` może nie zmieścić się w sesji.** Diagnoza
   teraz; native run to sukces późniejszy, nie brama Bedroom/NUC/Gateway.
6. **Important — tylko scoped `rollout --device bedroom-tv`.** Pełny rollout
   bez `--device` woła converge i fail-closed na obcym kandydacie.
7. **Blocker — nie `force-stop` gdy ktoś ogląda.** JSON-RPC player przed apply;
   przy odtwarzaniu `DEFERRED` / `playback_active`. Po teście zostawić Kodi
   w stanie sprzed (tu: uruchomione).
8. **Minor — jawne drzewa git.** NUC-PR z czystego `origin/main`; Bedroom z
   `1493a8f` bez uncommitted Gateway w indeksie.
9. **Minor — Copilot i OpenSubtitles.org poza implementacją sesji.**
10. **Minor — kandydat Profile Sync: STOP po odczycie**, bez CAS bez zgody.

## Odrzucone (rozszerzałyby zakres)

- Włączanie Copilot approvals / merge #29.
- Usuwanie ACL Edge.
- Promocja kandydata Profile Sync w tej sesji.
- Ponowna instalacja Gateway „dla pewności”.
- Podnoszenie `max_age` watchdoga.
- VIP OpenSubtitles / usuwanie `.org`.
- Pełny apply NUC (migracja już PASS).
- P3/P4, locki stable, ZeroTier, qnap-download-search.
