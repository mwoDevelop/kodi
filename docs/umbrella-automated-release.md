# Automatyczne wydawanie Umbrelli

Ten dokument opisuje bieżący, wykonywalny kontrakt automatycznej aktualizacji
`plugin.video.umbrella`. Źródłami prawdy są workflow w `.github/workflows`, locki
w `manifests/locks` oraz publiczny status
`https://mwodevelop.github.io/kodi/status/umbrella.json`.

## Przepływ

1. Fork Umbrelli odtwarza downstreamowy stos poprawek na dokładnym commitcie
   upstream i otwiera własny PR.
2. `reconcile-upstreams.yml` o 04:35 UTC uruchamia komponentowy wariant dla
   `plugin.video.umbrella`. Kandydat nie może zmienić żadnego innego pinu.
3. `approve-umbrella-update.yml` co 15 minut sprawdza autora, branch, dokładny
   head SHA, jedyny dozwolony plik, zmianę wersji do przodu i zielony check
   `e2e`. Zapisuje decyzję jako artefakt, autoryzuje oczekujący natywny przebieg
   PR dla dokładnie tego SHA i czeka na jego wynik. Dopiero potem, gdy
   repozytoryjny przełącznik jest włączony, ustawia natywne auto-merge.
4. Po scaleniu `publish-testing.yml` buduje, testuje i skanuje dokładne bajty,
   a następnie publikuje niezmienny snapshot testing. Odświeżenie samego statusu
   nie tworzy snapshotu.
5. `certify-umbrella-hermetic.yml` akceptuje wyłącznie snapshot, którego różnica
   względem stable zawiera samą Umbrellę. Testy działają w Bubblewrap bez sieci,
   sekretów i zapisu do hosta. Wynik wiąże snapshot, commit repozytorium, dowody
   testów i krótki okres ważności w atestacji `hermetic_ci`.
6. Atestacja oraz niezmieniony, ponownie zweryfikowany lock QNAP są dołączane do
   release snapshotu. `promote-stable.yml` otwiera PR stable, nie przebudowując
   ZIP-ów ani obrazów QNAP. `approve-umbrella-promotion.yml` ponownie sprawdza
   snapshot i atestację przed włączeniem auto-merge normalnej promocji.
7. `publish-pages.yml` jest jedynym writerem GitHub Pages. Składa stable,
   testing i status w jeden przeskanowany artefakt, po czym publikuje go atomowo.
8. Kodi ze stable origin i `general.addonupdates=0` pobiera nową wersję natywnym
   mechanizmem repozytoriów. Urządzenia nie są obowiązkową bramą pre-release;
   test urządzenia po wydaniu jest dodatkowym smoke testem.

## Konfiguracja automatyzacji

Automatyczna brama nie zastępuje niezależnego ludzkiego review. Jest kontrolą
polityki dla jednego, ściśle określonego typu PR: najpierw weryfikuje tożsamość,
dozwolone pliki, dokładny head SHA i wymagane checki, a dopiero potem ustawia
natywne auto-merge. Nie używa bypassu rulesetów.

Etap mutujący używa krótkotrwałego `GITHUB_TOKEN` bieżącego workflow z
uprawnieniami ograniczonymi do `actions`, `contents` i `pull-requests: write`.
Nie ma długowiecznego sekretu ani chronionego Environment. Ponieważ GitHub nie
uruchamia nowych workflow po scaleniu wykonanym własnym `GITHUB_TOKEN`, brama po
potwierdzeniu stanu `MERGED` jawnie wywołuje następny etap: `publish-testing`,
`deploy-stable` albo test głównej gałęzi forka.

Hermetyczna kwalifikacja materializuje dokładnie przypięte prywatne komponenty
przed wejściem do Bubblewrap, używając `KODI_COMPONENTS_TOKEN`. Token nie jest
przekazywany do środowiska `env -i`; testowany kod widzi wyłącznie lokalne,
tylko-do-odczytu drzewa komponentów i nie ma dostępu do sieci.

Oba repozytoria muszą zezwalać na native auto-merge. Rulesety nadal wymagają
checków, lecz nie wymagają approval, ponieważ zweryfikowana brama nie wykonuje
już sztucznego self-approval. Ustawienie Actions dla PR-ów pierwszych autorów
akceptuje tylko konta istniejące wcześniej; nowo utworzone konta zewnętrzne nadal
wymagają ręcznego zatwierdzenia uruchomienia workflow.

PR utworzony przez `github-actions[bot]` może otrzymać od GitHub stan
`action_required`, mimo że gałąź znajduje się w tym samym repozytorium. Brama
autoryzuje wyłącznie przebieg `test.yml` związany z uprzednio zweryfikowanym
head SHA i czeka na jego sukces. Powtórny reconcile nie przepisuje identycznego
kandydata na nowy commit, dzięki czemu nie unieważnia testu ani decyzji w toku.

Domyślnie część mutująca jest wyłączona. Po udanym teście obserwacyjnym, teście
negatywnym allowlisty i potwierdzonym no-op ustaw repozytoryjną variable:

```text
UMBRELLA_AUTO_MERGE_ENABLED=true
```

Usunięcie albo ustawienie innej wartości natychmiast przywraca tryb
obserwacyjny; weryfikacja nadal działa i publikuje dowód decyzji.

Od 3.09.2026 część mutująca jest włączona w obu repozytoriach. Wyłączenie
`UMBRELLA_AUTO_MERGE_ENABLED` nadal pozostawia pełną weryfikację i artefakt
decyzji, ale nie ustawia auto-merge. Brak albo pusty token kończy etap mutujący
błędem zamiast cichego raportowania sukcesu.

## Ręczne uruchomienia i diagnostyka

Wymuś izolowane odświeżenie locka Umbrelli:

```bash
gh workflow run reconcile-upstreams.yml --repo mwoDevelop/kodi \
  -f component=plugin.video.umbrella
```

Ponów kwalifikację istniejącego snapshotu:

```bash
gh workflow run certify-umbrella-hermetic.yml --repo mwoDevelop/kodi \
  -f snapshot_id=<64-znakowy-snapshot-id>
```

Odśwież jeden pełny payload Pages i status:

```bash
gh workflow run publish-pages.yml --repo mwoDevelop/kodi
```

Przygotuj, bez automatycznego scalenia, forward rollback o wyższej wersji:

```bash
gh workflow run prepare-umbrella-forward-rollback.yml \
  --repo mwoDevelop/kodi \
  -f known_good_commit=<40-znakowy-commit> \
  -f release_version=<wersja-wyzsza-od-stable>
```

Wygenerowany artefakt trzeba ręcznie przejrzeć i włączyć do forka. Workflow nie
zmienia gałęzi, locka stable ani publicznego repozytorium.

Sprawdź ostatnie przebiegi:

```bash
gh run list --repo mwoDevelop/kodi --workflow reconcile-upstreams.yml --limit 5
gh run list --repo mwoDevelop/kodi --workflow approve-umbrella-update.yml --limit 5
gh run list --repo mwoDevelop/kodi --workflow approve-umbrella-promotion.yml --limit 5
gh run list --repo mwoDevelop/kodi --workflow certify-umbrella-hermetic.yml --limit 5
gh run list --repo mwoDevelop/kodi --workflow publish-pages.yml --limit 5
```

## Status widoczny w Kodi

Manifest ma dwie niezależne osie:

- `pipeline.state`: `in_sync`, `detected`, `qualifying` albo `blocked`;
- `release.health`: `healthy`, `incident` albo `unknown`.

Zawiera też wersję upstream, wersję stable, rzeczywistą wersję i commit bazy
upstream stable, dokładny commit bieżącego upstream, czas wygenerowania i termin
ważności. Nie steruje instalacją. Błąd lub wygaśnięcie statusu uruchamia
ograniczony fallback do oficjalnego indeksu Omega i nie blokuje Umbrelli.

## Incydent i cofnięcie do przodu

`manifests/umbrella-release-health.json` jest wersjonowanym źródłem ręcznie
potwierdzonego stanu wydania. Stan `incident` blokuje zwykłą promocję, ale nie
przygotowanie poprawki. Profile Sync 1.0.6 wysyła w uwierzytelnionym heartbeacie
wyłącznie ID dodatku, wersję, stan enabled/broken, bezpieczny kod i czas. Backend
nie utrwala jeszcze tego pola w widoku floty, dlatego automatyczna korelacja i
zmiana `release.health` pozostają wyłączone do czasu skoordynowanego wydania
backendu i Control Plane; nie wolno ich symulować na podstawie logów.

Kodi nie zainstaluje automatycznie starszej wersji. Naprawa awaryjna musi więc
użyć znanych dobrych źródeł, ponownie przejść skanowanie i testy oraz otrzymać
wersję ściśle wyższą od wadliwej. Rzeczywisty commit i wersja bazy upstream są
przechowywane niezależnie od czteroczłonowej wersji downstream. Scalenie takiego
forward rollbacku pozostaje ręczne.

## Ostatnia kwalifikacja

Umbrella `6.7.85.1` została wydana z upstream
`653190cd64c37eadae537568518238b3f8e5a27d`. Publiczny ZIP ma SHA-256
`3eda5c1cbb8f04386ea9f8ddf869dad75a4842c7a6ee1d0b51e5dc3b56ebbcc9`,
a status raportuje `in_sync` i `healthy`. Hermetyczna atestacja, stable deploy,
atomowy Pages deploy, końcowy no-op oraz test X88 są zapisane w
[raporcie E2E](e2e-results/2026-08-19-umbrella-auto-release.md).
