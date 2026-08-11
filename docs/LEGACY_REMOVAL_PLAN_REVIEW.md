# Niezależny review planu usunięcia kodu legacy

Data: 2026-08-11

Przedmiot: [plan usunięcia kodu legacy](../LEGACY_REMOVAL_PLAN.md)

## Werdykt

Pierwotny kierunek `inventory -> migrate -> prove -> remove` był zasadny, ale
plan nie był jeszcze bezpieczny do realizacji. Niezależny reviewer wskazał trzy
luki P0 i kilka luk P1. Wszystkie potwierdzone uwagi zostały włączone do planu.

## Zaakceptowane uwagi P0

1. **Migratory znikały przed końcem retencji.** Rozdzielono usunięcie readera
   produkcyjnego od późniejszego wycofania przypiętego migratora offline,
   fixture i instrukcji recovery.
2. **Migracja registry/reinstall nie była transakcyjna ani idempotentna.** Plan
   wymaga teraz nowej transakcji dwóch dokumentów z journalem, recovery,
   scalaniem wyłącznie po zgodności kanonicznej i fault injection po każdym
   kroku zapisu.
3. **Migracja WatchNixtoons2 obejmowała tylko favourites i grafiki.** Dodano
   katalog dodatku, `addon_data`, origin repozytorium, nowy content-addressed
   snapshot, relację `migrated_from`, kwarantannę oryginału oraz restore drill.

## Zaakceptowane uwagi P1/P2

- Rozdzielono samodzielną policy schema 1 od bieżącego kontenera snapshot
  schema 1; historyczny `policy_sha256` nie jest przepisywany.
- Migracja policy tworzy poprawny default-deny scope routine i porównuje
  semantykę include/exclude na korpusie ścieżek.
- Usunięto założenie o nieistniejącym API QNAP do listowania danych. Bazą jest
  spójny `backup-production`, download oraz read-only inventory offline.
- QNAP clean candidate i canary poprzedzają wyrównanie pozostałych urządzeń, aby
  stara aktywna rewizja nie rozpropagowała ponownie legacy.
- Inventory obejmuje `.device-backups/`, snapshoty, portable-state i artefakty
  certyfikacji oraz bezpieczne skanowanie archiwów.
- Brama wymaga co najmniej dwóch pełnych cykli oraz wszystkich aktywnych i
  candidate assignments bez legacy.
- Rozdzielono hermetyczne `tests/e2e/run.sh` od live release gate na urządzeniach.
- Przed destrukcyjnym testem urządzenia wymagane są: potwierdzenie tożsamości,
  świeży backup i zweryfikowany rollback.
- Źródłem prawdy ma być `manifests/schema-lifecycle.json`, a dokument Markdown
  ma być generowany albo walidowany.
- Doprecyzowano ścieżkę downstream Umbrella i usunięto nieudowodnione założenie
  o należącej do downstream zgodności playcount.

## Uwagi odrzucone jako fałszywe alarmy

- testing lock schema 1 i stable lock schema 2 są odrębnymi, bieżącymi
  formatami;
- rewizja Profile Sync schema 2 nie jest legacy;
- oddzielenie kwalifikacji Umbrella od control plane jest poprawne i zgodne z
  OCP;
- globalne podnoszenie wszystkich `schema: 1` byłoby błędem;
- kod vendored i upstream pozostaje poza zakresem bez osobnej kwalifikacji.

## Wynik po korekcie

Plan jest logicznie spójny jako plan etapowy. Realizacja może się rozpocząć od
manifestu cyklu życia, read-only inventory i blokady writerów. Usunięcie readera
produkcyjnego oraz wycofanie migratora offline pozostają dwiema niezależnymi
decyzjami z osobnymi bramami.
